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

---

## 2026-08-27 — Sponsorship is a hard pre-filter block; domain match is NOT

**Decision:** Two profile constraints, handled deliberately differently.

**Sponsorship — hard block, deterministic, pre-model.** The candidate requires visa sponsorship, so postings that explicitly decline to sponsor are excluded before any Gemini call. Eligibility is a *fact*, not a judgement, so it belongs in code. Twelve regexes cover the common phrasings plus citizenship/clearance requirements.

**Domain — a scored dimension, NOT a knockout.** The candidate asked for "a domain match," but the deepest domains (healthcare, marketing analytics) appear in **none** of the ten tracked companies, which are fintech, infra and consumer. Hard-gating on domain would filter out essentially every posting from the boards actually being watched. Instead `domain_preference` carries `strong` / `adjacent` / `weak` term lists, and the agent must explicitly state and justify domain overlap in its output. This preserves the signal without making the system return nothing.

---

## 2026-08-27 — Sponsorship filter validated against 1,090 real postings

**What was tested:** 23 synthetic cases (12 must-block, 11 must-not-block), then every posting across SoFi, Coinbase and Databricks.

**Results:**

| Board | Blocked | Notes |
|---|---|---|
| SoFi | 0 / 61 | no restrictions stated |
| Coinbase | 0 / 184 | no restrictions stated |
| Databricks | 3 / 845 | all Public Sector roles requiring U.S. citizenship for classified access |

**Zero false positives across 1,090 postings**, despite abundant decoy language: "Sponsor bank", "citizen developers", "co-sponsored demand gen", "sponsor development", "sponsoring pre-consensus bets". Naive matching on `sponsor` or `citizen` would have wrongly excluded all of these — a silent failure, since an over-filtered posting never reaches the agent and never appears on the dashboard.

**The important finding: ~0.3% of postings state any sponsorship restriction at all.** Two consequences:

1. **The sponsorship filter is a safety net, not a volume reducer.** Cutting the 2,749 down to a sane number must come from title/skills relevance matching, not this.
2. **Silence must not be read as either answer.** The agent must report sponsorship as *"not stated"* when the posting is silent. Inferring "sponsorship available" from absence would be fabricating a fact the candidate would act on.

**Method note:** the regexes were tested against real postings before being trusted, not just against invented examples. The decoy phrases above were not anticipated when the patterns were written — they were discovered by scanning live data.

---

## 2026-08-28 — Pre-filter cuts 2,762 → 316 (11.4%); two real bugs found by testing on live data

**Decision:** Relevance pre-filter is title-match first, with a core-skills fallback, plus a categorical title knockout.

**Measured result across all ten boards:**

| Company | Total | Passed | % |
|---|---|---|---|
| Databricks | 856 | 61 | 7.1% |
| Datadog | 453 | 21 | 4.6% |
| Cloudflare | 313 | 14 | 4.5% |
| Pinterest | 214 | 55 | 25.7% |
| Affirm | 210 | 24 | 11.4% |
| Coinbase | 184 | 22 | 12.0% |
| Airbnb | 174 | 43 | 24.7% |
| Reddit | 153 | 53 | 34.6% |
| Twilio | 145 | 13 | 9.0% |
| SoFi | 60 | 10 | 16.7% |
| **TOTAL** | **2,762** | **316** | **11.4%** |

**316 is the worst case, not the daily rate.** The first run is baselined and publishes nothing; steady state processes only actual changes.

### Bug 1: the sponsorship regex silently killed all 313 Cloudflare postings

Cloudflare's boilerplate contains:

> "...your authorization to receive software or technology controlled under these U.S. export laws **without sponsorship for an export license**."

That is **export-licence** sponsorship, not visa sponsorship. The unanchored pattern `without (?:visa |immigration )?sponsorship` matched it and dropped every Cloudflare posting — a **silent** failure, since filtered postings never reach the agent or the dashboard. Cloudflare simply showed 0.0% and looked like a company with no data roles.

Fixed by requiring the "authorization **to work**" anchor, which export-control language never satisfies. Added to `tests/test_sponsorship_filter.py` as a regression case.

**Why no synthetic test would have caught it:** all 23 hand-written cases passed. Nobody invents export-control boilerplate when imagining sponsorship phrasings. Only real postings contained it.

### Bug 2: `[^.]` cannot cross the periods in "U.S."

`authoriz(?:ed|ation) to work[^.]{0,80}without sponsorship` failed on *"authorized to work in the U.S. without sponsorship"* because the negated character class stops at the periods inside the abbreviation. Replaced with a bounded non-greedy `.{0,90}?`, keeping the "to work" anchor so Cloudflare stays out.

### Bug 3: `avoid_terms` was dead code

The constructor loaded `profile["avoid"]` into `self.avoid_terms` and never referenced it. Replaced with an explicit `exclude_titles` list applied as a categorical knockout.

**Why it mattered:** the skills fallback was passing `Customer Engineer, India`, `Presales Customer Engineer, Sydney`, and `Full Stack Engineer - Internal Audit`. Sales and presales postings routinely name Python, SQL and GCP without being technical roles. Counting *any* six skills was measuring vocabulary, not relevance.

**Fix:** two changes. Title knockout for categorically wrong roles (sales, presales, recruiting, support, design, intern...), and a `core_skills` list for the fallback that deliberately **excludes** generic terms like Python/SQL/Git/GCP, which appear across every job function and carry almost no signal alone. Threshold: 4 core skills.

**Deliberately NOT fixed:** a few marginal survivors remain (`Staff Product Manager, AI Platform`, `Sr. Developer Advocate, AI and ML`). Tuning these away would move fit judgement out of the agent and into brittle keyword lists — the exact failure the pre-filter design warns against. The agent correctly rejects them, and a false positive costs a fraction of a cent while a false negative is invisible and unrecoverable.

---

## 2026-08-28 — Collection pipeline works end to end (verified against live data + Firestore)

**Order of operations in `collector/pipeline.py`, and why:**

    fetch -> diff -> filter -> publish -> persist

**Persist comes LAST, deliberately.** If publishing fails, stored state is left
untouched so the next run re-detects the same changes. Persisting first would
mark changes as seen even though nothing was ever dispatched — silently losing
them with no error anywhere.

**Verified sequence (SoFi, 60 postings):**

| Step | Result |
|---|---|
| First run (not baselined) | 60 stored, **0 changes**, `baselined=true` |
| Second run (unchanged board) | **0 changes** — hash comparison stable |
| After simulated mutations | **4 changes: 1 new, 2 modified, 1 removed** |
| Relevance filter | 2 published, 2 dropped (Product Designer, Credit Manager) |
| Pub/Sub | message pulled back with correct `change_type` / `doc_id` attributes |

**REMOVED changes bypass the relevance filter.** If a role mattered enough to
alert on, its disappearance matters too — and there is no posting body left to
match against anyway.

---

## 2026-08-28 — `scripts/simulate_change.py` mutates STORED state, not the live board

**Decision:** The demo/test harness doctors what Firestore believes it saw last
time, rather than faking a board response.

**Why:** The next collection then sees the *real* Greenhouse board differ from
the doctored history, so the entire production code path executes — real HTTP
fetch, real diff, real filter, real publish. Mocking the board response would
exercise a different path than the one being demonstrated, which is the classic
way a demo passes while the real system is broken.

This is the mitigation for the "there is nothing to diff" risk in `plan.md`:
postings rarely change organically within a few days, and every company's first
run is baselined to silence.

---

## 2026-08-28 — Tools redesigned: the model judges, tools fetch facts

**Decision:** Replaced the originally planned tools (`extract_requirements`,
`compare_to_resume`, `decide_worth_attention`, `draft_application_bullets`)
with four that do something the model cannot:

| Tool | Why it earns its place |
|---|---|
| `get_candidate_profile()` | Retrieves profile from Firestore — data the model does not have |
| `get_previous_version(doc_id)` | Returns what the posting said last time. **The product's whole premise**, and genuinely unknowable to the model |
| `check_hard_blockers(text)` | Deterministic eligibility matching — a fact, not a judgement |
| `record_assessment(...)` | Writes the structured verdict — a real side effect |

**Why the original set was wrong:** three of the four were *judgements*, which
is the model's job. Implemented as Python functions they would either be stubs
(theatre) or hardcoded logic quietly replacing model reasoning with keyword
matching. "What does `decide_worth_attention` actually do?" would have been the
weakest question a judge could ask.

---

## 2026-08-28 — Agent verified end to end on live postings ✅

**New posting** (Reddit, Principal Data Scientist, Ads) — called
`get_candidate_profile` and `check_hard_blockers` but correctly **did not**
call `get_previous_version`, since a new posting has no history. Tool selection
was reasoned, not scripted.

- Bullets cited concrete profile facts: Markov chain attribution, GBM at
  40%/50%, 500K records at 80% accuracy, $178M/$57M
- Caught an unanticipated gap: *"requires 12+ years for MS holders (candidate
  has 11)"*
- Reported *"silent on visa sponsorship"* rather than claiming it was
  available — the specific failure the instruction was written to prevent

**Modified posting** (Airbnb, Senior Data Scientist, MarTech Measurement) —
called all four tools including `get_previous_version`, and identified both
changes: the title upgrade to Senior **and** newly added AI-agent requirements.
Also caught the 24-month contract term from the body and named a real skills
gap (Bayesian MMM / geo-experimentation vs. the candidate's attribution work).

**Significance:** this retires the largest remaining risk in `plan.md`
(Saturday's agent build) a day early. The instruction's explicit anti-sycophancy
and anti-fabrication rules — "most changes are NOT worth attention", "never say
sponsorship is available when the posting is silent" — both held under real data.

---

## 2026-08-28 — Single-tenant by design; multi-user deferred (with the gap documented)

**Decision:** Ship single-tenant. Do not add multi-user before the Sunday
deadline.

**Why:** it is real scope on the day `plan.md` already flags as the schedule's
single point of failure, and judges will not test multi-tenancy. The stronger
move is to state the boundary explicitly rather than to sit on one accidentally.

### What IS configurable today

Everything describing *who the candidate is* lives in `config/profile.json` and
is read at runtime — no code changes required to swap people:

`target_titles`, `skills`, `core_skills`, `exclude_titles`,
`work_authorization.exclude_if_posting_matches`, `domain_preference`,
`highlights`, `avoid`.

**Verified empirically**, not assumed. Running the same unmodified filter over
Reddit's 153 postings with two different profiles:

| Profile | Passed | Sample of what surfaced |
|---|---|---|
| Aakash (DS/ML) | 53/153 | ML Engineering Manager, Ads Conversion Modeling |
| Test persona (junior frontend) | 30/153 | Senior Frontend Engineer, Media / Home Experience |

The agent's instruction is persona-neutral and reads the profile through the
`get_candidate_profile` tool, so it adapts without edits.

### What is NOT configurable — three single-tenant assumptions

1. **`profile_id="default"` is hardcoded** at two call sites
   (`collector/pipeline.py:67`, `common/tools.py:57`).

2. **`decisions/{doc_id}` is not scoped by profile.** This is the one actual
   *bug*, not merely a missing feature: two users assessing the same Reddit
   posting share a document id, so the second verdict **silently overwrites**
   the first. Postings are correctly shared — a job posting is the same fact
   for everyone — but a verdict is per-person and is not keyed that way.

3. **The `companies` collection is global.** All users would share one tracked
   list; nobody can watch Stripe while someone else watches Airbnb.

### What multi-user would take (~2–3 hrs, post-submission)

- Key decisions as `decisions/{profile_id}_{doc_id}` — fixes the collision
- Scope companies per profile (`companies/{profile_id}_{board_token}`, or a
  `profile_ids` array on each company doc)
- Thread `profile_id` through the pipeline and into the Pub/Sub message payload
- Add an upload + parse route (`pypdf` already works — it was used to extract
  the candidate's own resume from PDF)

The `profiles/{profile_id}` schema was chosen on 2026-08-26 specifically to
keep this cheap, so none of the above is a migration — it is additive.

**For the Devpost write-up:** state this as a known boundary with a costed
path, not as an oversight.

---

## 2026-08-28 — Agent server: HTTP status IS the ack protocol

**Decision:** `POST /pubsub-push` maps failure modes to status codes deliberately.

| Situation | Status | Why |
|---|---|---|
| Malformed / undecodable message | **204** | It will never parse on retry. Nacking would make Pub/Sub redeliver a poison message until it expires. |
| Agent raised (Gemini timeout, Firestore blip) | **500** | Assumed transient — nack so Pub/Sub retries with backoff rather than silently losing the work. |
| Agent ran but never called `record_assessment` | **500** | Retry may succeed, but logged loudly: a persistent version of this is a *prompt* problem, not an infrastructure one. |
| Success, or duplicate | **200** | Ack. |

**Verified locally:** malformed body → 204, non-JSON body → 204, real base64
Pub/Sub envelope → 200 with the expected tool calls.

---

## 2026-08-28 — ⚠️ Ack deadline MUST be raised to 600s (default 10s would 4x the cost)

**Measured:** one change takes **35.7 seconds** end to end (Gemini reasoning +
3–4 tool calls + Firestore writes).

**The default Pub/Sub push ack deadline is 10 seconds.** Left alone, Pub/Sub
would redeliver at 10s, 20s and 30s while the first delivery is still working.
Idempotency does **not** save us here: the check reads the decision document,
and the first invocation has not written it yet, so every redelivery sees no
prior decision and runs the agent. That is roughly **4× the model spend per
message**, and nothing would look broken — the right answer still lands.

**Required when creating the subscription:**

    gcloud pubsub subscriptions create job-changes-push \
      --topic=job-changes \
      --push-endpoint=<AGENT_URL>/pubsub-push \
      --ack-deadline=600

**Also implied:** Cloud Run request timeout must exceed 35s (default 300s is
fine), and the agent service should not have low concurrency limits that
serialise messages the design intends to process in parallel.

---

## 2026-08-28 — Idempotency keyed on content_hash, not doc_id

**Decision:** A duplicate is defined as *same doc_id AND same content_hash*.

**Why:** keying on `doc_id` alone would permanently suppress reassessment — a
posting that changes a second time would be skipped as "already seen", which
defeats the entire product. Keying on the content hash means a genuinely
changed posting is correctly reassessed while an at-least-once redelivery of
the *same* change is not.

**Verified:** first delivery 35.7s (full agent run), duplicate delivery 0.18s
returning `{"status": "duplicate"}` with no model call.

---

## 2026-08-29 — 🐛 Race condition: the agent's core tool was broken ONLY in production

**Symptom:** the first fully-deployed end-to-end run produced a decision saying
*"title, qualifications, and responsibilities are unchanged"* — for a posting
whose stored title had been deliberately changed from "Data Scientist" to
"Principal Data Scientist". The agent's most valuable capability silently
returned nothing useful.

**Cause:** `collector/pipeline.py` publishes to Pub/Sub and then immediately
calls `upsert_postings`, overwriting `postings/{doc_id}` with the NEW version.
The agent runs **asynchronously**, a few seconds later, and
`get_previous_version` read that same document — which by then held the new
text. It compared the new version against itself and correctly concluded
nothing had changed.

**Why every local test passed:** running the agent directly is *synchronous* —
it reads the stored record before the pipeline overwrites it. The bug requires
the async Pub/Sub hop to appear. Local tests, unit tests, and the FastAPI
handler tests all passed while production was broken.

**Fix:** a dedicated `posting_history/{doc_id}` collection. The pipeline writes
the prior version there **before** the upsert, and `get_previous_version` reads
history rather than live state. The previous version is now explicitly
preserved rather than incidentally still-present.

**Verified after redeploy:** *"Title updated from 'Data Scientist, Ads' to
'Principal Data Scientist, Ads', ... adding explicit experience minimums (12+
years for M.S.), and publishing the $268,000–$365,100 salary range."*

**Learning (for the Devpost write-up):** this is the single most instructive bug
of the build. An asynchronous system has ordering hazards that a synchronous
test cannot expose, and *the failure was silent* — no error, no exception, no
retry, just a confidently-worded wrong answer. Nothing short of deploying it
and reading the actual output would have caught it. It is also a direct
consequence of a deliberate architectural choice (Pub/Sub for fault isolation):
decoupling buys resilience and costs ordering guarantees.

---

## 2026-08-29 — Deployed to Cloud Run; OIDC wired end to end

| Service | URL | Auth | Max instances |
|---|---|---|---|
| Dashboard | `nightwatch-dashboard-745162634071.us-central1.run.app` | **public** | 5 |
| Collector | `nightwatch-collector-745162634071.us-central1.run.app` | OIDC only | 2 |
| Agent | `nightwatch-agent-745162634071.us-central1.run.app` | OIDC only | 10 |

**Auth chosen: OIDC, not username/password.** Pub/Sub and Cloud Scheduler speak
OIDC natively; a shared password would mean writing auth code *and* fighting
the platform to make those callers use it — strictly more work and less secure,
with a secret that would live in a repo handed to judges. The dashboard needs
no auth at all because toggling was deliberately made non-destructive.

**Cloud Build IAM friction (expected — Risk #4):** newer GCP projects no longer
grant the default compute service account the roles Cloud Build needs. First
deploy failed with `storage.objects.get denied`. Fixed by granting the compute
SA `cloudbuild.builds.builder`, `storage.objectViewer`, `artifactregistry.writer`
and `logging.logWriter`.

**Cost posture:** `min-instances=0` everywhere, so Cloud Run scales to zero and
bills nothing when idle — measured cold start 5.2s, warm 2.4s. `min-instances=1`
is to be enabled **only while recording the demo**, then turned off; leaving it
on through a ~2 month judging window would cost $120–240. `max-instances` caps
(5 / 2 / 10) bound the worst case against a retry storm or crawler.
