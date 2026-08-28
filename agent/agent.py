"""The ADK agent. The ONLY module that imports a framework.

Everything it reasons over lives in common/tools.py as plain Python, so
swapping ADK for google-genai function calling is a change to this file alone.
"""
from __future__ import annotations

import logging
import os

from google.adk import Agent
from google.adk.runners import InMemoryRunner
from google.genai import types

from common import store, tools

log = logging.getLogger(__name__)

APP_NAME = "jobs_nightwatch"

INSTRUCTION = """\
You watch job boards on behalf of one candidate and report what CHANGED.

You are not browsing job listings. You are assessing a single specific change
that was already detected: a posting appeared, was quietly rewritten, or was
pulled. Your value is explaining what that change means for this candidate.

Work in this order:

1. Call get_candidate_profile first. Never assess fit from assumptions about
   what the candidate might want.

2. If the change type is "modified", call get_previous_version to see what the
   posting said before. Compare them yourself and identify what actually
   changed - an added requirement, a seniority shift, a location change, a
   quietly narrowed scope. This is the most valuable thing you produce, because
   nobody else will tell the candidate a tracked role was rewritten.

3. Call check_hard_blockers on the posting text. This candidate requires visa
   sponsorship. If it returns blocked=true, the role is not viable regardless
   of how good the fit looks - say so plainly and set worth_attention to false.
   If it returns blocked=false with sponsorship_mentioned=false, the posting is
   SILENT on sponsorship. Report it as "not stated". Never tell the candidate
   sponsorship is available when the posting simply did not mention it.

4. Call record_assessment exactly once, at the end, with your verdict.

On judging fit, be honest and be specific:

- Most changes are NOT worth the candidate's attention. Saying so is useful.
  A long list of weak matches is worse than three real ones.
- Compare against the candidate's actual experience, seniority and target
  titles. A staff-level candidate should not be told a junior role is a fit.
- Assess domain overlap explicitly, using the domain_preference in the profile.
  Say "strong", "adjacent", or "weak" and justify it in one clause. Adjacent is
  a perfectly good answer - fintech risk modelling genuinely overlaps
  healthcare underwriting work.
- Application bullets must cite CONCRETE things from the candidate's profile -
  named systems, real numbers, specific technologies. Never write generic
  filler like "strong analytical skills". If you cannot ground a bullet in the
  profile, write fewer bullets.
- Put real concerns in the concerns field. A missing skill, a seniority gap or
  unstated sponsorship all belong there. Do not flatter.

For a REMOVED posting there is nothing to apply to. Explain what was lost and
whether it is worth noting - for example if the candidate may have applied to
it, or if it signals the team stopped hiring. Leave application_bullets empty.
"""


def build_agent() -> Agent:
    tools.bind_store(store)
    return Agent(
        name="nightwatch",
        model=os.environ.get("GEMINI_MODEL", "gemini-3.7-flash"),
        description="Assesses changes to tracked job postings for one candidate.",
        instruction=INSTRUCTION,
        tools=tools.ALL_TOOLS,
    )


def format_change_prompt(msg: dict) -> str:
    """Turn a Pub/Sub change message into the agent's task."""
    posting = msg.get("posting") or {}
    change_type = msg.get("change_type", "unknown")

    lines = [
        f"Change type: {change_type}",
        f"Document id: {msg.get('doc_id','')}",
        f"Company: {msg.get('company','')}",
        f"Title: {msg.get('title','')}",
        f"URL: {msg.get('url','')}",
    ]

    if msg.get("changed_fields"):
        lines.append(f"Fields that differ: {', '.join(msg['changed_fields'])}")

    if change_type == "removed":
        lines.append("\nThis posting is no longer on the board.")
        lines.append(f"Last known title: {msg.get('previous_title') or msg.get('title','')}")
    else:
        lines += [
            f"Location: {posting.get('location','')}",
            f"Department: {posting.get('department','')}",
            "",
            "Posting text:",
            (posting.get("description_text") or "")[:12000],
        ]

    return "\n".join(lines)


async def assess_change(msg: dict) -> dict:
    """Run the agent over one change. Returns a summary of what happened.

    A fresh runner and session per change: the workload is one-shot with no
    conversation, so there is no state worth carrying between invocations.
    This uses run_async rather than run_debug -- run_debug is a local testing
    convenience, and Runner does not auto-create sessions (auto_create_session
    defaults to False), so the session is created explicitly.
    """
    agent = build_agent()
    runner = InMemoryRunner(agent=agent, app_name=APP_NAME)

    user_id = msg.get("profile_id", "default")
    session = await runner.session_service.create_session(
        app_name=APP_NAME, user_id=user_id
    )

    prompt = format_change_prompt(msg)
    new_message = types.Content(role="user", parts=[types.Part(text=prompt)])

    events = []
    async for ev in runner.run_async(
        user_id=user_id,
        session_id=session.id,
        new_message=new_message,
    ):
        events.append(ev)

    tool_calls, final_text = [], None
    for ev in events:
        content = getattr(ev, "content", None)
        if not content or not getattr(content, "parts", None):
            continue
        for part in content.parts:
            if getattr(part, "function_call", None):
                tool_calls.append(part.function_call.name)
            if getattr(part, "text", None) and part.text.strip():
                final_text = part.text.strip()

    doc_id = msg.get("doc_id", "")
    decision = store.get_decision(doc_id)

    return {
        "doc_id": doc_id,
        "tool_calls": tool_calls,
        "recorded": decision is not None,
        "final_text": final_text,
        "decision": decision,
    }
