# Demo Guide — Jobs NightWatch

How to reproduce the demo, and why it has to be seeded.

---

## Why the demo needs seeding

Two properties of the system make a "just press play" demo impossible, and both
are deliberate:

1. **A company's first collection reports nothing.** Baselining is by design —
   "changed" is undefined with no previous version to compare against. Treating
   first sight as "new" would fire one alert per posting across 2,762 postings.
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
