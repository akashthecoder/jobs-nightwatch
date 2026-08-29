# Demo Guide — Jobs NightWatch

## Submission checklist

Status as of **2026-08-29**. Deadline **Sunday 2026-08-30**.

### ✅ Done

| # | Requirement | Status |
|---|---|---|
| 1 | **Built with required developer tools** | ✅ Google **ADK 2.8.0** drives the agent loop; **Gemini 3.7 Flash** via **Vertex AI**. The rules require at least one of ADK / Genkit / Google GenAI SDK, and Gemini 3.5 or greater — both satisfied. |
| 2 | **Hosted project URL** | ✅ https://nightwatch-dashboard-745162634071.us-central1.run.app — public, no sign-in, judges can click and interact. |
| 3 | **Architecture diagram** | ✅ Live page at `/architecture` showing Gemini, backend, database and frontend, with 9 numbered edges tracing one request. **Note:** Devpost may want an image upload — screenshot the page if so. |
| 4 | **Backend demonstrably on Google Cloud** | ✅ Three Cloud Run services, Pub/Sub, Firestore, Cloud Scheduler, Vertex AI — all live in project `jobs-nightwatch`. The video must *show* this (see below). |

### ⬜ To do

| # | Requirement | Status | Notes |
|---|---|---|---|
| 5 | **Select one category** | ✅ **Taskmaster** | Confirmed 2026-08-29. |
| 6 | **Code repository URL** | ✅ **Done** | https://github.com/akashthecoder/jobs-nightwatch — private, 21 commits pushed with genuine Thu→Sat timestamps. Verified no secrets in history. |
| 6b | **Grant repo access to judges** | ✅ **Done** | `testing@devpost.com` and `cloudhackathons@google.com` added as collaborators. |
| 7 | **README.md with spin-up instructions** | ✅ **Done** | Local setup and full cloud deploy, both step by step. Every referenced file verified to exist; both test commands verified to pass. |
| 8 | **Text description** | ✅ **Drafted** | `SUBMISSION.md` — copy-paste source mapped to Devpost form fields. Covers features, technologies, data sources and findings/learnings. `scripts/make_submission_pdf.py` renders it to a print-ready page for PDF export. |
| 9 | **Demo video (≤4 min)** | ⬜ **Not started** | See the structure below. |

### Video sub-requirements (all part of #9)

| Requirement | Status |
|---|---|
| Overview of the problem being solved | ⬜ |
| Value proposition stated | ⬜ |
| Demo of the application in action | ⬜ |
| **Shows the backend running on Google Cloud** — Cloud Console, Cloud Run dashboard, Vertex AI logs, or a `.run.app` URL | ⬜ Mandatory, easy to forget |
| 4 minutes or less | ⬜ Only the first 4 minutes are evaluated |
| Publicly visible on YouTube or Vimeo | ⬜ Must be public, not unlisted-only-to-you |
| Link provided on the submission form | ⬜ |
| English, or English subtitles | ⬜ |
| No offensive / derogatory / discriminatory content | ⬜ |
| No unlawful content | ⬜ |
| **No third-party ads, logos, trademarks or implied endorsement** | ⬜ Note: the diagram uses **custom-drawn icons**, not Google's official marks, deliberately for this reason. Be careful filming company names on job boards — Reddit/Databricks logos may appear on their careers pages. |

### Suggested order for the remaining work

1. **README.md** — required, and needed before pushing the repo anyway
2. **Create GitHub repo and push** — 18 commits with real history
3. **Record the video** — do this before writing the description; recording surfaces details worth mentioning
4. **Write the text description** — pull findings straight from `decisions.md`
5. **Pick the category and submit** — leave buffer for upload and processing

### Useful facts for the write-up

- **2,756** postings watched across **10** companies
- **315** match the profile (11.4%) — the deterministic gate never spends a model call on the other 2,441
- **~35 seconds** per change end to end; three changes complete in ~48s because Pub/Sub processes them in parallel
- Gemini is invoked at exactly **one** point in the pipeline; everything before it is deterministic
- Best "learnings" material in `decisions.md`: the async race condition that passed every local test and failed silently only in production, and the sponsorship regex that silently dropped all 313 Cloudflare postings because of export-control boilerplate

---

## Reproducing the demo

How to reproduce the demo, and why it has to be seeded.

### Why the demo needs seeding

Two properties of the system make a "just press play" demo impossible, and both
are deliberate:

1. **A company's first collection reports nothing.** Baselining is by design —
   "changed" is undefined with no previous version to compare against. Treating
   first sight as "new" would fire one alert per posting across 2,756 postings.
2. **Real job postings rarely change within the span of a recording.** Waiting
   for an organic change is not a demo plan.

So `scripts/demo_seed.py` doctors **stored state** — what the system believes it
saw last time — rather than faking a board response. The next collection then
sees the *real live board* differ from that doctored history, and the entire
production path executes: real HTTP fetch, real diff, real relevance filter,
real Pub/Sub publish, real agent. Nothing is mocked.

---

## Quick version (2 commands)

```bash
# 1. Seed four changes
.venv/bin/python scripts/demo_seed.py --reset

# 2. Trigger a collection
curl -X POST "https://nightwatch-collector-745162634071.us-central1.run.app/collect?board_token=reddit" \
  -H "Authorization: Bearer $(gcloud auth print-identity-token)"
```

Wait ~50 seconds, then reload the dashboard:
**https://nightwatch-dashboard-745162634071.us-central1.run.app**

You can also trigger step 2 by clicking **Run now** on the dashboard, which is
better on camera — it shows a person driving the system rather than a terminal.

---

## What gets seeded

| # | Type | Posting | What it demonstrates |
|---|---|---|---|
| 1 | **MODIFIED** | Principal Data Scientist, Ads | **The headline feature.** Stored title is "Data Scientist, Ads"; the live board says "Principal". The agent must detect the uplevel and the raised experience bar. |
| 2 | **NEW** | Senior Data Scientist, Ads | A strong-fit role appearing. Typically scores in the high 80s. |
| 3 | **REMOVED** | Senior Data Scientist, Growth Analytics | A tracked role disappearing — you would never be told this otherwise. |
| 4 | **NEW (no fit)** | 3rd Party Partnerships Manager | Honesty. Dropped by the deterministic pre-filter before costing a model call. |

Expected result: **4 changes detected, 3 published, 1 filtered out, 3 decisions.**

---

## Suggested 4-minute video structure

**0:00–0:30 — The problem.**
Job boards show you what *exists*. Nobody tells you a role you are tracking
quietly added a requirement, changed seniority, or was pulled. That gap is the
product.

**0:30–1:00 — The dashboard at rest.**
Show the tracked companies and any existing results. Point out that a company's
first collection deliberately reports nothing — there is no "change" without a
previous version.

**1:00–1:30 — Trigger it.**
Click **Run now**. While it runs, explain the pipeline: Cloud Scheduler wakes
the Collector, which fetches the boards, hashes each posting, and compares
against stored state. *Change detection is plain deterministic code — no model.
Comparing two records is a comparison, not a judgement.*

**1:30–2:30 — Show the backend on Google Cloud** (required by the rules).
- Cloud Run: three services, live request counts
- Pub/Sub: the `job-changes` topic and push subscription
- Cloud Run logs for the agent, showing tool calls as they happen

Emphasise: one Pub/Sub message per change, so a slow or failing posting cannot
block the others — they were assessed **in parallel**, three in 48 seconds
rather than three sequential 35-second runs.

**2:30–3:30 — The results.**
Reload the dashboard. Walk through the MODIFIED card first — it is the whole
thesis:

> "Title updated from 'Data Scientist, Ads' to 'Principal Data Scientist, Ads',
> raising the experience requirement to 12+ years for MS holders."

Then the application bullets, which cite real specifics from the resume. Then
the concerns — the agent flags an 11-vs-12 years gap and notes the posting is
**silent** on visa sponsorship rather than claiming sponsorship is available.

**3:30–4:00 — Close.**
Gemini 3.7 Flash via Vertex AI, ADK for the agent loop, Firestore for state,
all on Cloud Run. Mention the honest limitation: single-tenant today, with a
costed path to multi-user.

---

## Before recording

```bash
# Warm the services so no cold start appears on camera (~$1-2/day)
gcloud run services update nightwatch-dashboard --min-instances=1 --region=us-central1 --project=jobs-nightwatch
gcloud run services update nightwatch-agent     --min-instances=1 --region=us-central1 --project=jobs-nightwatch
```

Then load the dashboard once to confirm it is warm.

## AFTER recording — important

```bash
# Turn min-instances back off, or you are billed 24/7 through judging
gcloud run services update nightwatch-dashboard --min-instances=0 --region=us-central1 --project=jobs-nightwatch
gcloud run services update nightwatch-agent     --min-instances=0 --region=us-central1 --project=jobs-nightwatch
```

Leaving `min-instances=1` on through a ~2 month judging window costs **$120–240**.
At `min-instances=0` the whole system idles at effectively zero, and judges just
see a ~5 second cold start on first load.

---

## Resetting between takes

```bash
.venv/bin/python scripts/demo_seed.py --reset
```

Clears all decisions and history, re-baselines, and re-seeds the same four
scenarios. Safe to run repeatedly — it never touches the live job boards.

---

## Troubleshooting

**"Nothing appears after Run now."**
Check the company is enabled and already baselined. A company's *first* run
stores postings and reports nothing by design.

**"Changes detected but no decisions."**
The agent is asynchronous. Give it ~35 seconds per change. If nothing lands,
check the agent's Cloud Run logs:

```bash
gcloud run services logs read nightwatch-agent --region=us-central1 --limit=50 --project=jobs-nightwatch
```

**"The MODIFIED card says nothing changed."**
The `posting_history` record is missing. Re-run `demo_seed.py --reset` — the
history snapshot is written by the collector *before* it overwrites stored
state, so seeding and collecting must happen in that order.
