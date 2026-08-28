"""ADK canary spike — the smallest thing that proves the agent loop works.

Run:  .venv/bin/python spikes/adk_spike.py

Success criteria (BOTH must hold):
  1. structured output comes back
  2. the tool call is VISIBLE in the event stream

The second is the one that matters. A plausible-looking answer with no
function_call in the events means the model answered from its own knowledge
and the agent loop never actually ran.

Deliberately minimal: one agent, one stub tool, no session service, no
FastAPI, no Firestore. Retires the framework unknown before anything is
built on top of it.

Result 2026-08-27: GREEN. See decisions.md.
"""
import asyncio
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from google.adk import Agent
from google.adk.runners import InMemoryRunner

MODEL = os.environ["GEMINI_MODEL"]

# Records real invocations so we can prove the Python function actually ran,
# independently of what the model claims in its prose.
TOOL_CALLS: list[dict] = []


def score_posting(title: str, body: str) -> dict:
    """Score how well a job posting matches the candidate.

    NOTE: ADK builds the function declaration sent to Gemini from this
    docstring, including the Args section. A thin docstring measurably
    degrades tool-calling accuracy.

    Args:
        title: The job posting title.
        body: The full text of the job posting.

    Returns:
        A dict with the fit score and a short reason.
    """
    TOOL_CALLS.append({"title": title, "body": body[:60]})
    return {"score": 87, "reason": "stubbed - strong Python and GCP overlap"}


async def main() -> bool:
    print(f"model={MODEL} location={os.environ['GOOGLE_CLOUD_LOCATION']} "
          f"project={os.environ['GOOGLE_CLOUD_PROJECT']}\n")

    agent = Agent(
        name="nightwatch_spike",
        model=MODEL,
        description="Scores job postings for candidate fit.",
        instruction=(
            "You evaluate job postings. You MUST call the score_posting tool "
            "to get the fit score. Never invent a score yourself. "
            "After calling it, report the score and reason."
        ),
        tools=[score_posting],
    )

    runner = InMemoryRunner(agent=agent, app_name="nightwatch_spike")

    prompt = (
        "Score this posting.\n"
        "Title: Senior Backend Engineer\n"
        "Body: We need someone strong in Python, FastAPI, and Google Cloud "
        "to build event-driven data pipelines."
    )

    # GOTCHA: run_debug is async despite a synchronous-looking signature.
    # Calling it without await raises "'coroutine' object is not iterable".
    events = await runner.run_debug(prompt, quiet=True)

    calls, responses, final_text = [], [], None
    for ev in events:
        content = getattr(ev, "content", None)
        if not content or not getattr(content, "parts", None):
            continue
        for part in content.parts:
            if getattr(part, "function_call", None):
                calls.append(part.function_call)
            if getattr(part, "function_response", None):
                responses.append(part.function_response)
            if getattr(part, "text", None) and part.text.strip():
                final_text = part.text.strip()

    print(f"events            : {len(events)}")
    print(f"tool calls seen   : {[c.name for c in calls]}")
    print(f"tool responses    : {[r.name for r in responses]}")
    print(f"python fn invoked : {len(TOOL_CALLS)} time(s)")
    print(f"\nfinal text: {final_text}")

    ok = bool(calls) and bool(TOOL_CALLS) and bool(final_text)
    print("\n" + "=" * 50)
    print("SPIKE RESULT:", "GREEN - agent loop confirmed" if ok else "RED - see above")
    print("=" * 50)
    return ok


if __name__ == "__main__":
    raise SystemExit(0 if asyncio.run(main()) else 1)
