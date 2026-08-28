# Decision Log — Jobs NightWatch

Append-only. Newest entries at the bottom. Every decision gets: what was decided, when, and **why**.
This file is the source material for the "findings and learnings" section of the Devpost submission.

---

## 2026-08-26 — Project name: Jobs NightWatch

**Decision:** The project is named "Jobs NightWatch."

**Why:** Evokes an always-on agent that works while you sleep and hands you a briefing in the morning — which is literally the product. Short and easy to say aloud in a 4-minute demo video.

---

## 2026-08-26 — Collector supports Greenhouse only (narrowed from Greenhouse + Lever + Ashby)

**Decision:** Only Greenhouse-hosted job boards are supported. `GET https://boards-api.greenhouse.io/v1/boards/{token}/jobs?content=true` — free, unauthenticated, full posting text in a single call.

**Why:** Originally scoped to three ATS platforms. Narrowed to one on 2026-08-27 after losing the Wednesday evening work session, to buy back ~1.5 hrs and remove two sources of format surprise. The company config stays generic, so adding Lever/Ashby later is an adapter file plus a config edit, not a redesign.

**Rejected alternative:** Arbitrary career-page scraping. Would require per-site logic or an HTML-parsing LLM step — not finishable by Sunday, and a reliability risk during a live demo.

---

## 2026-08-26 — Diff engine is deterministic code, never an LLM call

**Decision:** Change detection is a plain Python hash comparison. No Gemini involvement.

**Why:** Deciding whether two records differ is a comparison, not a judgment. Using a model there would be slower, non-deterministic, more expensive, and would signal poor engineering judgment to technical judges. The LLM's role starts *after* a change is detected — reasoning about whether the change matters.

---

## 2026-08-26 — Firestore keyed by `(company, external_id)` with a `content_hash`

**Decision:** One document per posting holding current state plus a content hash, updated in place — not a whole-snapshot-per-day document.

**Why:** Makes diffing a get-by-ID plus hash compare: no Firestore queries, no composite indexes, nothing to debug under time pressure. Hash beats Greenhouse's `updated_at` for change detection because the hash is what catches a posting being silently rewritten.

---

## 2026-08-26 — Resume hardcoded for MVP, but schema left open for multi-user

**Decision:** Resume lives in `config/profile.json` and is stored in Firestore as `profiles/{profileId}` with `profileId="default"` — not as a single global blob.

**Why:** Upload UI is out of scope for a 4-day build, but the stated future direction is per-user resume upload. Keying by `profileId` from day one means that future costs an upload route, not a schema migration. Near-zero cost now.

---

## 2026-08-26 — Dashboard reads Firestore server-side, not from the browser

**Decision:** The Dashboard Cloud Run service reads Firestore via the Admin SDK and renders HTML server-side. The browser never talks to Firestore.

**Why:** A public read-only dashboard backed by client-side Firestore would require hand-writing and debugging security rules (`allow read: if true`) — a real time sink and a security-review flag. Server-side rendering removes the entire problem class instead of solving it.

---

## 2026-08-26 — Vertex AI auth mode end-to-end

**Decision:** `GOOGLE_GENAI_USE_VERTEXAI=TRUE` in both local development and Cloud Run, with service accounts granted `roles/aiplatform.user`.

**Why:** GCP project and billing are already set up, so Vertex mode avoids creating, storing, and rotating an API key or a Secret Manager entry. Using the identical auth mode locally and deployed prevents a class of "works on my machine" failures during Saturday's deploy crunch.

---

## 2026-08-27 — Company selector controls tracking, not just display

**Decision:** Dashboard checkboxes toggle an `enabled` flag on `companies/{board_token}` in Firestore; the Collector only fetches enabled companies. Paired with a "Run now" button that triggers the Collector on demand.

**Why:** The product's pitch is "an agent, not a website you visit." A judge toggling a company on and watching the system pick it up is the most persuasive twenty seconds available in the demo — a cosmetic view-filter throws that away to save almost nothing. The "Run now" button exists because otherwise a judge toggles a company on and sees nothing until the next scheduled run; it also doubles as the on-camera manual trigger for the video, so one feature solves two problems.

---

## 2026-08-27 — No auth on the selector; disabling is non-destructive instead

**Decision:** Anyone with the dashboard URL can toggle companies. No shared secret, no login. Toggling a company off stops future collection but leaves its past decisions visible on the dashboard.

**Why:** Judge interactivity is worth more than protecting demo state, and auth code is time we don't have. Rather than gating the write, the blast radius is reduced in the schema: the worst a visitor can do is stop future collection for one company, and past results remain intact for the next viewer. Cheaper and safer than an auth layer.

---

## 2026-08-27 — Tools written framework-agnostic (zero ADK imports)

**Decision:** Every tool in `common/tools.py` is a plain Python function with typed parameters and a docstring, with no framework imports. `agent/agent.py` is the only file that imports ADK.

**Why:** ADK registers plain functions as tools; `google-genai` function calling accepts the same shape via declarations. This makes swapping frameworks a ~30-line change to one orchestration file with all domain logic untouched — converting the project's biggest technical unknown into a half-hour swap. Costs nothing to adopt up front, so there is no reason not to.

---

## 2026-08-27 — Own the container; no `adk deploy cloud_run`

**Decision:** Build a plain container and import ADK as a library inside it, rather than using the ADK CLI's deployment path.

**Why:** Custom containers are needed for the Collector and Dashboard regardless. The ADK CLI deploys a chat-session-shaped API server (`/run`, `/apps/{app}/users/{user}/sessions/{...}`), which is the wrong shape for a Pub/Sub push endpoint. Owning the container removes the entire ADK-CLI deployment surface from the risk register and leaves ADK as just a Python package we call.

---

## 2026-08-27 — ADK is Plan A, `google-genai` is a compliant fallback (not a rules violation)

**Decision:** Build on ADK. If Thursday's 60-minute canary spike doesn't go green, switch to `google-genai` function calling without further deliberation.

**Why:** Initially assumed ADK was mandatory, which oversized the risk of ADK's programmatic-invocation path. The hackathon rules require **at least one of ADK, Genkit, or the Google GenAI SDK** — so `google-genai` is independently eligible. ADK remains Plan A because it's the stronger story for an "agentic AI" hackathon and setup is already done, but the fallback cannot disqualify the submission. This is why the ADK risk is ranked third rather than first.

**To verify:** confirm against the actual rules text on the contest site before relying on this.

---

## 2026-08-27 — ADK spike gets a 60-minute hard kill switch

**Decision:** The Thursday canary is an `LlmAgent` with one stub tool returning a hardcoded dict, invoked from a plain `spike.py` via `InMemoryRunner`. No session service, no real logic, no FastAPI. At 60 minutes: green → proceed; close → 15 more minutes; still confused → switch to `google-genai` and don't revisit.

**Why:** This is the only component whose shape is unknown — the collector, diff, and Firestore work can already be estimated to the half-hour. Standard practice is to retire the unknown before anything depends on it. The one-shot case (no conversation, no session persistence, no cross-invocation memory) is the *easy* case for `Runner`, so a long timebox isn't justified; 60 minutes is the entire cost of finding out.

---

## 2026-08-27 — Do not hardcode a Gemini model ID from memory

**Decision:** Look up the current model ID in the ADK/Vertex docs at build time; prefer a `-latest` style alias (e.g. `gemini-flash-latest`) over a pinned version string.

**Why:** Model IDs churn and any ID recalled from memory may not exist. A wrong ID produces a confusing auth-or-404 failure at exactly the wrong moment. An alias also avoids needing to revisit this before the demo.

**Outcome (same day):** This decision immediately paid off — see the next entry.

---

## 2026-08-27 — Vertex AI rejects `-latest` aliases

**Decision:** Never use AI Studio's `-latest` alias convention with Vertex AI; always pin an explicit model version.

**Why:** The planned default `gemini-flash-latest` **404s on Vertex AI**. The `-latest` alias belongs to AI Studio; the Vertex publisher-model path requires an explicit version.

**Learning (for the Devpost write-up):** the two Google GenAI surfaces — AI Studio and Vertex AI — accept *different model identifier formats* through the *same* `google-genai` SDK. Code copied from AI Studio examples fails on Vertex with an error that reads like a permissions problem rather than a naming one.

---

## 2026-08-27 — Vertex location is `global`; Gemini 3.x is not served regionally ⚠️

**Decision:** `GOOGLE_CLOUD_LOCATION=global` for all Gemini calls. Firestore, Cloud Run, and Pub/Sub stay in `us-central1` under a **separate** env var, `GCP_REGION`.

**Why:** Empirically probed every Gemini 3.x model in both locations:

| Location | Result |
|---|---|
| `global` | `gemini-3.5-flash`, `3.6-flash`, `3.7-flash`, `3.5-flash-lite`, `3.1-flash-lite`, `3-flash-preview`, `3.1-pro-preview` — **all resolve** |
| `us-central1` | **all 404** |

The hackathon requires Gemini 3.5 or greater, so this is not a preference — the submission is **only compliant via the global endpoint**.

**How this was nearly missed:** the first verification script picked candidate model IDs from memory and included no 3.x names at all, so `gemini-2.5-flash` "passed" and looked like a settled answer. It only passed because the location was pinned to `us-central1`, where nothing newer exists. Caught when the 3.5+ rule was raised — the enumeration of `client.models.list()` showed `gemini-3.5-flash` sitting in the catalog while a direct call to it 404'd, which is what pointed at regional availability rather than a naming problem.

**Learning (for the Devpost write-up):** a model appearing in `models.list()` does **not** mean it is callable from your configured location — the catalog is broader than any single regional endpoint. And "region" is not one decision: the Vertex AI location and the Cloud Run/Firestore region are independent, and using a single variable for both silently caps you at older models. The two are kept as separate variables specifically to prevent that.

---

## 2026-08-27 — Model is `gemini-3.7-flash`

**Decision:** `GEMINI_MODEL=gemini-3.7-flash`.

**Why:** Newest flash-tier model available to the project and comfortably above the hackathon's 3.5 floor. Flash tier keeps demo latency low; the full (non-lite) variant was chosen over `3.5-flash-lite` because lite models are typically weaker at multi-step tool use, which is precisely the load-bearing behaviour of this agent. Verified end-to-end with a real prompt through the final `.env` config.

**Fallback if it misbehaves:** `gemini-3.5-flash` — still compliant, longer-established.

---

## 2026-08-27 — Environment: Python 3.13 (not the 3.14 default), `uv`, `google-adk` 2.8.0

**Decision:** venv on Python 3.13.5 via `uv`, rather than the machine's default Python 3.14.4.

**Why:** 3.14 is bleeding-edge and the dependency tree pulls in compiled packages (`grpcio`, `pydantic-core`) via Firestore and Pub/Sub. A missing wheel means a source build — slow, and prone to failing in ways that consume an evening we don't have. 3.13 was already installed, so the safer choice cost nothing. Install completed clean with no build steps, confirming the call.

**Noted for later:** the installed `google-adk` is **2.8.0**. Most ADK tutorials online target 1.x, where import paths and `Runner` signatures differ. When the canary spike errors, suspect a version mismatch in the tutorial before assuming a conceptual misunderstanding.

---

## 2026-08-27 — GCP project is `jobs-nightwatch` under `akkis.akash@gmail.com`

**Decision:** Build in project `jobs-nightwatch` (number `745162634071`), region `us-central1`, authenticated as `akkis.akash@gmail.com`.

**Why:** Initially pointed at `adk-prep` under a different account (`akashhongal@gmail.com`); switched to a dedicated project for the hackathon. Billing confirmed enabled (`01F7EB-E9DD49-986F13`) — a project without billing cannot use Vertex AI or Cloud Run at all, so this was verified before anything else.

**Gotcha worth remembering:** switching the active gcloud *account* does **not** switch the active *project*, and Application Default Credentials carry their own separate *quota project*. Three distinct settings. Missing the third produces a confusing runtime quota error from the client libraries rather than a clear auth failure. All three now point at `jobs-nightwatch`.

---

## 2026-08-27 — ADK canary spike GREEN; ADK stays as Plan A ✅

**Decision:** Build on ADK. The `google-genai` fallback is retired as an active concern (though the framework-agnostic tool design that made it cheap is retained).

**Why:** The 60-minute canary went green in roughly 10 minutes, including package introspection. Confirmed end-to-end:

- ADK 2.8.0 drives `gemini-3.7-flash` successfully
- **ADK honours `GOOGLE_CLOUD_LOCATION=global`** — the main open worry, since a hardcoded regional endpoint would have 404'd on a model already proven to work
- The model *called the tool* rather than fabricating an answer: both `function_call` and `function_response` appear in the event stream, and the Python function recorded exactly one invocation
- **Plain Python functions register directly as ADK tools with zero framework imports**, validating the framework-agnostic decision

**Approach that worked:** introspecting the installed package (`Agent.model_fields`, `inspect.signature(Runner.__init__)`) instead of following tutorials. ADK 2.x differs materially from the 1.x material online — `Agent` and `Runner` are top-level exports and there is no `LlmAgent` at top level — so tutorial-driven code would have failed on imports before reaching anything real.

---

## 2026-08-27 — ADK 2.8.0 API gotchas (found during the spike)

**Gotchas worth remembering:**

1. **`Runner.run_debug()` is async despite a synchronous-looking signature.** `inspect.signature` reports `-> list[Event]`, but it returns a coroutine; calling it without `await` raises `TypeError: 'coroutine' object is not iterable`. Not discoverable from the signature — only from running it.
2. **`Runner.__init__` requires `session_service` as a keyword-only argument.** `InMemoryRunner` supplies it automatically. Because this workload is one-shot per posting with no conversation, `InMemoryRunner` is sufficient and the multi-turn session machinery is never exercised.
3. **Tool functions need a real docstring with an `Args:` section** — ADK derives the function declaration sent to Gemini from it. A missing or thin docstring degrades tool-calling accuracy.
4. ADK emits `UserWarning: [EXPERIMENTAL] feature FeatureName.JSON_SCHEMA_FOR_FUNC_DECL is enabled` on every run. Noise, not an error.

**For the Devpost write-up:** the widely-repeated claim that ADK's programmatic (non-`adk web`) path is poorly documented did not hold up. For a one-shot, no-conversation agent, `InMemoryRunner` plus a plain function tool was about 20 lines. The real friction was **version drift** — online material targets ADK 1.x while 2.8.0 reorganised the top-level API — which introspection solved in minutes.

---

## 2026-08-27 — Tracked companies: 10 Greenhouse boards, 2,749 postings

**Decision:** Track `databricks`, `datadog`, `cloudflare`, `pinterest`, `affirm`, `coinbase`, `airbnb`, `reddit`, `twilio`, `sofi`.

**Why:** Chosen by the candidate as genuine targets rather than a generic sample — a real target list demos better. All ten verified live against the Greenhouse API before being written to config, along with `?content=true` returning full descriptions (~6KB raw HTML per posting, ~5KB after cleaning).

**Verified during selection:** 15 of 20 initially probed tokens resolved; a wider 83-token probe found 47 more. `openai`, `doordash`, `snowflake`, `plaid`, and `ramp` are not on those Greenhouse tokens. Board sizes range from 845 (Databricks) to 61 (SoFi).

---

## 2026-08-27 — First collection per company is a BASELINE, not 2,749 alerts ⚠️

**Decision:** The first successful collection for a company writes postings to Firestore and sets a `baselined` flag on the company doc, but publishes **no** change messages. Alerting begins from the second run onward.

**Why:** The ten boards hold **2,749 postings**. Under the original design every one is classified `new` on first sight, producing 2,749 Pub/Sub messages and 2,749 Gemini calls — material cost, a long runtime, and output nobody wants. More fundamentally it is a **category error**: "changed" is undefined when there is nothing to compare against. The product's premise is *what changed since last time*, which requires a "last time" to exist.

**Consequence for the demo:** the system correctly shows **nothing** after a first run on a fresh company. The demo therefore requires a seeded before/after state rather than a cold first run — already anticipated as Risk #2 in `plan.md`.

**Gap this closes:** the original plan specified dedup (don't re-alert on the same role forever) but never addressed the cold-start flood. Caught when the ten selected boards were summed.

---

## 2026-08-27 — Deterministic pre-filter sits between the diff engine and the agent

**Decision:** Detected changes pass through a cheap, deterministic relevance filter (title/keyword matching against `config/profile.json`) before being published to Pub/Sub. Only survivors reach Gemini.

**Why:** Even in steady state, a large board can turn over dozens of postings a day, most irrelevant to one candidate. Spending an LLM call to conclude "this warehouse associate role is not a fit for a backend engineer" is waste that a string match settles for free.

**Reinforces the existing architecture principle:** deterministic code does cheap, mechanical work (comparison, filtering); the model does expensive judgment (does this change *matter*, and what would you say about it). This is the same reasoning that keeps the diff engine LLM-free — see the 2026-08-26 entry on that.

**Note:** the filter must stay deliberately loose. It is a cost guard, not the fit decision — over-tuning it moves judgment out of the agent and into brittle keyword lists, which would undercut the product.
