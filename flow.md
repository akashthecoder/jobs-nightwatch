# System Flow — Jobs NightWatch

**Living document.** Update this whenever anything changes: a new service, a changed data shape, a new deployed URL.
This is the source material for the architecture diagram due Sunday Aug 30 — keeping it current is what makes that diagram a 20-minute job instead of a 2-hour one.

**Last updated:** 2026-08-27 — environment verified, Vertex AI auth confirmed working.

---

## Deployment target

| | |
|---|---|
| GCP project | `jobs-nightwatch` (number `745162634071`) |
| Account | `akkis.akash@gmail.com` |
| **Vertex AI location** | **`global`** — required; Gemini 3.x 404s in every region |
| **Cloud Run / Firestore / Pub/Sub region** | **`us-central1`** — separate setting, separate env var |
| Gemini model | `gemini-3.7-flash` (meets the hackathon's 3.5+ requirement) |
| Python | 3.13.5, venv at `.venv/` |
| `google-adk` | 2.8.0 (note: most tutorials target 1.x) |

---

## Build status

| Component | Status | Deployed URL |
|---|---|---|
| Environment setup | ✅ Done — APIs enabled, venv built, Gemini verified | — |
| Firestore database | ✅ Created — `(default)`, us-central1, Native mode | — |
| ADK canary spike | ✅ **GREEN** — tool-calling loop confirmed | — |
| `common/schema.py` | ✅ Normalized shape + content hashing | — |
| Greenhouse adapter | ✅ Verified on all 10 boards | — |
| `common/relevance.py` | ✅ Cuts 2,762 → 316 (11.4%) | — |
| `common/store.py` | ✅ Firestore access, seeded | — |
| Diff engine | ✅ 17 unit tests pass, baselining verified | — |
| Pub/Sub topic | ✅ `job-changes`, publish/pull verified | — |
| Collection pipeline | ✅ End-to-end on live data | — |
| `common/tools.py` | ✅ 4 tools, zero framework imports | — |
| Agent (`agent/agent.py`) | ✅ **Verified on live new + modified postings** | — |
| Agent server (`server.py`) | ✅ Ack-protocol + idempotency | 🚀 [agent](https://nightwatch-agent-745162634071.us-central1.run.app) |
| Dashboard | ✅ Stats, timestamps, change hero | 🚀 **[LIVE](https://nightwatch-dashboard-745162634071.us-central1.run.app)** |
| Collector service | ✅ `/collect` | 🚀 [collector](https://nightwatch-collector-745162634071.us-central1.run.app) |
| Pub/Sub push subscription | ✅ OIDC, ack-deadline 600s | — |
| Cloud Scheduler | ✅ every 3h | — |

### Verified working ADK pattern (2.8.0)

```python
from google.adk import Agent
from google.adk.runners import InMemoryRunner

def my_tool(title: str, body: str) -> dict:
    """Docstring with an Args: section — ADK builds the
    function declaration sent to Gemini from this."""
    return {...}

agent = Agent(name=..., model="gemini-3.7-flash",
              instruction=..., tools=[my_tool])
runner = InMemoryRunner(agent=agent, app_name=...)
events = await runner.run_debug(prompt, quiet=True)   # NOTE: async!
```

Tool activity is confirmed by scanning events for `part.function_call` /
`part.function_response`. `run_debug` is for local testing; the Pub/Sub handler
will use `runner.run_async(user_id=..., session_id=..., new_message=...)`.

Legend: ⬜ not started · 🟨 in progress · ✅ working locally · 🚀 deployed

---

## Target end-to-end flow

```
Cloud Scheduler (every N hours)
        │  OIDC-authenticated HTTP POST
        ▼
   Collector  (Cloud Run)
        │  1. read companies/{board_token} where enabled == true
        │  2. GET boards-api.greenhouse.io/v1/boards/{token}/jobs?content=true
        │  3. html.unescape() + strip tags → plain description text
        │  4. normalize to the common schema, compute content_hash
        │  5. upsert postings/{company}_{external_id}
        ▼
   Diff Engine  (deterministic Python — NO LLM)
        │  IF company not yet baselined:
        │      write postings, set baselined=true, PUBLISH NOTHING
        │      ("changed" is undefined with no prior snapshot)
        │  ELSE:
        │      compare each posting's new content_hash to the stored one
        │      classify: new | modified | removed
        ▼
   Relevance pre-filter  (deterministic — NO LLM)
        │  cheap title/keyword match against profiles/default
        │  drops obviously-irrelevant roles before they cost a Gemini call
        │  deliberately LOOSE — a cost guard, not the fit decision
        ▼
   Pub/Sub topic  (one message per surviving change)
        │  push subscription, OIDC-authenticated
        ▼
   Agent  (Cloud Run + ADK + Gemini)
        │  POST /pubsub-push — decode base64 envelope, one change per message
        │  tools the model chooses to call:
        │    · compare_to_resume(posting_text, profile)
        │    · decide_worth_attention(...)
        │    · draft_application_bullets(...)
        │  writes decisions/{company}_{external_id} with reasoning
        │  dedup check against last-alerted hash
        ▼
   Firestore
        ▲
        │  Admin SDK, server-side read
   Dashboard  (Cloud Run)
        │  server-rendered HTML — browser never touches Firestore
        │  company checkboxes → POST toggles companies/{token}.enabled
        │  "Run now" button → triggers Collector on demand
        ▼
   Judge's browser  (public, no auth)
```

**Why Pub/Sub sits between the diff and the agent:** each change is an independent message, so if Gemini is slow or errors on posting #14, postings #15–40 still process and #14 retries on its own.

---

## Firestore collections

| Collection | Doc ID | Holds |
|---|---|---|
| `companies` | `{board_token}` | Company name, Greenhouse board token, `enabled` bool, `baselined` bool |
| `postings` | `{company}_{external_id}` | Current normalized posting state + `content_hash` |
| `decisions` | `{company}_{external_id}` | Agent verdict, reasoning, draft bullets, change type, timestamp |
| `profiles` | `default` | Resume/profile used for fit comparison |

Keyed by `(company, external_id)` so diffing is a get-by-ID — **no queries, no composite indexes.**
`profiles` is keyed by ID rather than being a single global blob so per-user upload is possible later without a migration.

---

## Normalized posting schema

Defined in `common/schema.py`, produced by the Greenhouse adapter, consumed by the diff engine and agent:

```
company           str
external_id       str
title             str
location          str
department        str
url               str
description_text  str    # unescaped, tag-stripped plain text
updated_at        str
content_hash      str    # what change detection compares
```

---

## Tracked companies

10 Greenhouse boards, **2,749 postings total** (verified live 2026-08-27):

| Board token | Company | Postings |
|---|---|---|
| `databricks` | Databricks | 845 |
| `datadog` | Datadog | 450 |
| `cloudflare` | Cloudflare | 311 |
| `pinterest` | Pinterest | 215 |
| `affirm` | Affirm | 205 |
| `coinbase` | Coinbase | 183 |
| `airbnb` | Airbnb | 180 |
| `reddit` | Reddit | 154 |
| `twilio` | Twilio | 145 |
| `sofi` | SoFi | 61 |

That total is *why* baselining and the pre-filter exist — see the flow above.

---

## Notes and gotchas

- **`?content=true` is mandatory** on the Greenhouse call. Without it the response has no description at all, which looks like it needs a second per-job fetch. It doesn't.
- **Greenhouse `content` is HTML-escaped** — needs `html.unescape()` plus tag-stripping before reaching Gemini.
- **Change detection uses `content_hash`, not Greenhouse's `updated_at`** — the hash is what catches a posting being silently rewritten.
- **Disabling a company is non-destructive** — it stops future collection but leaves existing `decisions` docs intact and visible.
- Both Cloud Scheduler → Collector and Pub/Sub → Agent use OIDC auth; the fallback if the IAM chain fights back is `--allow-unauthenticated`, documented as a deliberate prototype tradeoff.
