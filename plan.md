# Jobs NightWatch — Hackathon Build Plan (Aug 27–30, 2026)

## Context

Entering the "All Things Agentic AI" hackathon (Google Cloud–sponsored, Devpost submission) with an agent that watches companies' career pages, detects what *changed* since last time (not just what exists), then uses Gemini to judge fit against a resume and draft application talking points — surfaced on a dashboard.

The insight: job boards show state, not deltas. Nobody tells you a role you're tracking quietly added a requirement, or that the posting you applied to last week was pulled. That gap is the product.

Deadline is **Sunday Aug 30, 2026**, solo, with GCP/billing/Gemini already in place but **zero prior ADK experience**. Starting Thursday Aug 27 — a **4-evening/weekend build, roughly 23–25 working hours**.

## Compliance note

The hackathon requires **at least one of ADK, Genkit, or the Google GenAI SDK**. That means `google-genai` is *independently compliant* — the fallback in Risk #3 is not a rules violation, it's a second eligible path. **Plan A remains ADK** (better story for an "agentic AI" hackathon, and setup is already done), but the escape hatch is real, which is why Risk #3 is sized small. Confirm against the actual rules text before relying on it.

## Key decisions

- **Greenhouse only** — `GET https://boards-api.greenhouse.io/v1/boards/{token}/jobs?content=true`, free and unauthenticated, full posting text in a single call. No scraping, no per-job second fetch.
- **10 companies, selectable from the dashboard.** Toggling controls what the Collector actually tracks, not just what's displayed. Rationale: the pitch is "an agent, not a website you visit"; a judge toggling a company on and watching it get picked up is the most persuasive moment in the demo, and it costs one Firestore doc + one POST route.
- **No auth on the selector.** Judges should be able to interact. De-risked in the schema instead: **toggling a company off is non-destructive** — past decisions stay on the dashboard, only future collection stops. Blast radius ≈ zero, no auth code needed.
- **"Run now" button** triggers the Collector on demand — otherwise a judge toggles a company on and sees nothing until the next scheduled run. Doubles as the on-camera manual trigger for the demo video.
- **Resume is hardcoded** as `config/profile.json` for the MVP, but stored in Firestore as `profiles/{profileId}` with `profileId="default"` — so a future per-user upload path doesn't need a schema rewrite.
- **Tools are written framework-agnostic.** Every tool is a plain Python function with typed parameters and a docstring, containing **zero ADK imports**. ADK registers plain functions as tools; `google-genai` function calling accepts the same shape via declarations. This makes a framework swap a change to one orchestration file (~30 lines) with all domain logic untouched — converting a project risk into a half-hour swap, at no up-front cost.
- **Own the container; import ADK as a library.** No `adk deploy cloud_run`. Custom containers are needed for the Collector and Dashboard anyway, so build one plain container and import ADK inside it. This removes the entire ADK-CLI deployment surface from the risk register.
- **Dashboard reads Firestore server-side** (Cloud Run + Admin SDK, server-rendered HTML). The browser never talks to Firestore, so there are no client-side security rules to write or debug.
- **Vertex AI auth mode** (`GOOGLE_GENAI_USE_VERTEXAI=TRUE`) end-to-end, local and deployed — avoids managing an API key or Secret Manager entry under time pressure.
- **Do not hardcode a model ID from memory.** Check what the current ADK/Vertex docs list at build time and prefer a `-latest` style alias (e.g. `gemini-flash-latest`) over a pinned guess.

## Architecture notes

- **Greenhouse gotcha:** `?content=true` is mandatory — without it you get title/location/URL only and no description, which is easy to miss and looks like you need a second fetch per job. The returned `content` field is **HTML-escaped**, so it needs `html.unescape()` plus tag-stripping before it reaches Gemini.
- **Finding board tokens:** Greenhouse publishes no directory. Find each company's token by viewing their careers page source or network tab for a `boards-api.greenhouse.io/v1/boards/{token}` or `job-boards.greenhouse.io/{token}` URL. Budget 30–45 min for 10 companies — this is not zero-effort.
- **Firestore schema:** one doc per `(company, external_id)` holding current posting state plus a `content_hash`, updated in place. Diffing becomes a get-by-ID + hash compare — **no queries, no composite indexes**, which matters under time pressure. Use `content_hash` rather than Greenhouse's `updated_at`, since the hash is what catches silent rewrites.
- **ADK invocation shape:** this agent is the *easy* case for `Runner` — one shot per posting, no conversation, no session persistence, no memory across invocations. Nearly everything difficult about `Runner` concerns multi-turn state this project doesn't have; `InMemoryRunner` covers it. The residual difficulty is not "can I call an agent from my own Python" (a documented ~30-min question) but "does it behave cleanly inside an async FastAPI handler under a Pub/Sub push envelope" — see Risk #3.

## Living documents

- **`flow.md`** — the current end-to-end system flow: what calls what, what shape the data is in at each hop, which services exist and their URLs. Updated *whenever anything changes*. Becomes the source material for Sunday's architecture diagram, which is why building it incrementally protects the deadline.
- **`decisions.md`** — append-only decision log: the decision, the date, and *why*. Every subsequent choice — including any descope from the cut list — gets logged. Feeds the "findings and learnings" section Devpost requires.

## Day-by-Day Sequence

### Thu Aug 27, evening (~4 hrs) — Environment, canary, scaffold

1. **Environment setup (~1 hr)**
   - Python venv; `pip install google-adk google-genai google-cloud-firestore google-cloud-pubsub fastapi uvicorn requests jinja2`
   - `gcloud auth application-default login`; set the active project
   - Enable APIs: `run`, `pubsub`, `firestore`, `cloudscheduler`, `aiplatform`
   - Create the Firestore database in **Native mode**
   - `.env` with `GOOGLE_GENAI_USE_VERTEXAI=TRUE`, `GOOGLE_CLOUD_PROJECT`, `GOOGLE_CLOUD_LOCATION`
   - **Verify with a single throwaway Gemini call before moving on** — do not discover auth problems on Saturday

2. **ADK canary spike (~60 min, HARD KILL SWITCH)** — retire the only unknown before anything depends on it. Keep it *tiny*:
   - An `LlmAgent` with exactly **one stub tool** — `score_posting(title, body)` returning a hardcoded dict
   - Invoked from a plain `spike.py` via `InMemoryRunner`. **No session service, no real logic, no FastAPI.**
   - Success = structured output returned, with the tool call visible in the events
   - **At 60 min:** if green, move on. If close, take 15 more. If still confused about the basic shape, switch to `google-genai` function calling, log it in `decisions.md`, and don't revisit. The 60 minutes is the entire cost of finding out — and because tools are framework-agnostic, the swap costs ~30 lines regardless.

3. **Repo scaffold + seed `flow.md` and `decisions.md` (~30 min)** — `collector/`, `agent/`, `dashboard/`, `common/`, `config/`
4. **Hunt 10 Greenhouse board tokens (~45 min)** → `config/companies.json`; write `config/profile.json`

### Fri Aug 28, evening (~4 hrs) — Collector, Diff, Pub/Sub

- Common normalized schema in `common/schema.py`: `company, external_id, title, location, department, url, description_text, updated_at, content_hash`
- Greenhouse adapter: fetch with `content=true`, unescape/strip HTML, normalize, upsert to Firestore. Collector filters to `enabled == true` companies.
- Diff engine — **plain deterministic Python, no LLM call**: hash-compare each posting against its stored doc, classify new / modified / removed
- Pub/Sub topic; publish one message per change; verify consumption with the `gcloud pubsub` CLI *before* any agent logic depends on it
- **Write the tool functions tonight if time allows** — plain Python with no framework dependency, so they can be built and unit-tested before the orchestration layer exists
- **Manually mutate a Firestore posting doc between two Collector runs** to prove the modified/removed paths fire (Risk #2)
- Update `flow.md` and `decisions.md` before stopping

### Sat Aug 29, full day (~10 hrs) — Agent, dashboard, deploy

**This day is overloaded and is the plan's single point of schedule failure — see Risk #1. Work it in the order below and take cut-list items rather than pushing work to Sunday.**

- **Agent orchestration (~2 hrs):** register the already-written, already-tested tools — `compare_to_resume`, `decide_worth_attention`, `draft_application_bullets`. Skip a "fetch full posting" tool; Greenhouse already returned the text. Verify structured decision+reasoning JSON locally.
- **FastAPI wrapper (~2 hrs):** takes a change event, calls the runner, iterates events to extract the final structured response, writes `decisions/{company}_{external_id}` with a dedup check against the last-alerted hash. Exposed as `POST /pubsub-push`, decoding the base64 Pub/Sub envelope.
- **Dashboard (~2 hrs):** server-rendered results table + company checkboxes (POST toggles `enabled`) + "Run now" button.
- **Deploy + wire (~2.5 hrs):** Cloud Run services for Collector, Agent, Dashboard; Pub/Sub push subscription; Cloud Scheduler → Collector. Test each auth hop in isolation before layering logic on it.
- **E2E smoke test (~1 hr):** Run now → snapshot write → diff → Pub/Sub → agent decision → dashboard row
- **Storyboard the video script tonight**, while the system is fresh — do not improvise this Sunday

### Sun Aug 30 — Deadline day (~6–7 hrs)

- Morning: **bug fixes only, no new features**
- **Hard code freeze by early-to-mid afternoon** — everything after is submission assets
- Architecture diagram (generated from `flow.md`, not from scratch)
- README spin-up instructions — test from a clean checkout if time allows
- Record the ≤4 min demo video. Pre-warm services first; must visibly show the GCP backend (Cloud Run dashboard / logs / `.run.app` URL)
- Text description: features, tech, data sources, learnings — pull learnings straight from `decisions.md`
- Select the Devpost category; submit **with buffer** before the deadline

## Top Risks and Mitigations

1. **Saturday carries ~10 hrs of work with no slack** — the largest risk in the plan. Every prior day's overrun lands here, and Sunday has no capacity to absorb it. Mitigation: work Saturday in the listed order (agent → wrapper → dashboard → deploy), and if not deployed end-to-end by early evening, **take Tier 2 cuts immediately** rather than trading into Sunday. A deployed system with fewer features beats a feature-complete system that never got a hosted URL.
2. **There is nothing to diff.** Postings rarely change organically within days, and every company's first run marks everything "new" by definition — this threatens the demo directly. Mitigation: manually mutate Firestore docs between runs to exercise modified/removed; seed a known before/after state for the recording rather than hoping for a live change.
3. **ADK inside an async FastAPI handler.** Basic programmatic invocation is a documented ~30-min question, `InMemoryRunner` covers the one-shot case, and Thursday's spike retires it before anything depends on it. What remains is narrower — event iteration to extract a final structured response, and async behavior under a Pub/Sub push envelope on Cloud Run. Mitigation: the Thursday kill switch, plus framework-agnostic tools making a `google-genai` swap ~30 lines. **Per the compliance note, that swap is fully eligible** — this risk cannot sink the submission.
4. **Pub/Sub push → Cloud Run OIDC auth is a multi-step IAM chain** (service account → `roles/run.invoker` on the Agent → Pub/Sub service agent needs `roles/iam.serviceAccountTokenCreator` → subscription created with matching `--push-auth-service-account` and `--push-auth-token-audience`). A mismatched audience is the classic silent-403 loop. Mitigation: wire and test in isolation Saturday. Fallback: `--allow-unauthenticated`, documented as a conscious prototype tradeoff — a 2-minute escape.
5. **Cold starts + Gemini latency during the demo.** One message through the full pipeline can take 10–30+ seconds, with a scale-to-zero cold start on top. Mitigation: `--min-instances=1` on Agent and Dashboard for the demo window, pre-warm before recording, narrate over processing instead of filming a spinner.
6. **Submission assets eating the final hours.** Mitigation: `flow.md` and `decisions.md` make the diagram and writeup near-mechanical on Sunday; storyboard the video Saturday night; enforce the freeze so Sunday is execution, not improvisation.

## Cut-Line List (cut Tier 1 first)

**Tier 1 — if behind after Fri Aug 28:**
- Drop from 10 companies to 3–5 (a config edit, not a code change)
- Drop the "Run now" button and trigger the Collector via `curl` on camera
- Don't depend on Cloud Scheduler's timer for the demo; the resource can still exist and be described as production cadence

**Tier 2 — if behind after Sat Aug 29:**
- Skip Pub/Sub OIDC push auth; `--allow-unauthenticated` with a plain HTTPS push subscription, documented as a known simplification
- Drop `draft_application_bullets`; ship "what changed + why it matters" only
- Drop the company selector to a read-only list; skip dashboard styling entirely (an unstyled table is fine — judges care that the URL works)

**Tier 3 — last resort, protect the demo above all:**
- Seed one guaranteed-clean example directly in Firestore for the recording, while still showing the real pipeline deployed and running (Cloud Console/logs) for at least one real company
- Swap ADK for `google-genai` function calling (still fully compliant — see the compliance note)

## Critical Files

- `flow.md` — living system flow; source material for Sunday's architecture diagram
- `decisions.md` — living append-only decision log; source material for the "learnings" writeup
- `common/schema.py` — shared normalized posting schema
- `common/tools.py` — **framework-agnostic** plain Python tool functions, zero ADK imports
- `collector/main.py` — Cloud Run service: Greenhouse adapter, normalize, upsert, filter to enabled companies
- `diff/engine.py` — deterministic hash-compare + classification; publishes to Pub/Sub
- `agent/agent.py` — the only file with framework imports; registers `common/tools.py` functions
- `agent/server.py` — FastAPI app wrapping the runner; exposes `POST /pubsub-push`
- `dashboard/main.py` — server-rendered Firestore read, company toggle POST, "Run now" trigger
- `config/companies.json` — 10 Greenhouse companies + board tokens
- `config/profile.json` — hardcoded resume/profile for MVP fit comparison

## Verification

- **Spike:** `spike.py` returns structured output with the stub tool call visible in the events — the Thursday go/no-go gate
- **Tools:** unit-test each function in `common/tools.py` directly with plain Python calls, before any framework touches them
- **Adapter:** run the Greenhouse adapter against 3 real board tokens; confirm normalized output matches the schema and descriptions are unescaped, tag-stripped plain text
- **Diff:** mutate a stored posting doc, re-run the Collector, confirm exactly one `modified` classification; remove a source posting and confirm `removed`
- **Pub/Sub:** `gcloud pubsub topics publish` a hand-crafted message; confirm the Agent handler processes it and writes a decision doc
- **Selector:** toggle a company off in the UI, run the Collector, confirm it's skipped **and that its past decisions remain visible** (proves the non-destructive design)
- **E2E deployed:** hit "Run now", then trace one change through the Firestore console — posting doc → Pub/Sub message → decision doc → dashboard row — with each Cloud Run service's logs showing expected activity
- **Public access:** load the dashboard URL in a logged-out browser and confirm it renders (proves the server-side-Firestore design keeps the client ungated)
