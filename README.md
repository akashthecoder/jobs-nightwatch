# Jobs NightWatch

**Job boards show you what exists. This shows you what *changed*.**

An autonomous agent that watches company career pages on a timer, remembers what
every posting said last time, and tells you when something meaningful changes —
a role quietly upleveled, a requirement added, a posting pulled. It then judges
whether the change matters to *you* and drafts what you would lead with if you
applied.

🔗 **Live:** https://nightwatch-dashboard-745162634071.us-central1.run.app
&nbsp;&nbsp;·&nbsp;&nbsp; [About](https://nightwatch-dashboard-745162634071.us-central1.run.app/about)
&nbsp;&nbsp;·&nbsp;&nbsp; [Architecture](https://nightwatch-dashboard-745162634071.us-central1.run.app/architecture)

Built for the **All Things Agentic AI** hackathon · category: **Taskmaster**

---

## The problem

A job search means doing four tedious things by hand, repeatedly: **checking**
every company's board, **reading** each posting to see if it is relevant,
**judging** whether you are a fit, and **working out what to say** if you apply.

And job boards only ever show you the current state. Nobody tells you that a role
you have been tracking for three weeks quietly moved its experience bar from five
years to twelve, or that the posting you applied to on Tuesday was pulled on
Thursday. You would only notice by re-reading everything daily and remembering
exactly what each posting used to say.

**That gap is the product.**

---

## What it does

Across **10 companies** and **~2,750 postings**:

- **Filters to your profile** — ~315 postings (11 %) match target titles, core
  skills and seniority. The other ~2,440 never cost a model call.
- **Detects real change** — SHA-256 content fingerprints catch silent rewrites
  that a timestamp would miss.
- **Rates what is worth applying to** — a fit score out of 100 with reasoning,
  from Gemini 3.7 Flash.
- **Drafts your opening bullets** — citing concrete projects and numbers from
  your background.
- **Tells you honestly** — most changes are *not* worth your attention, and it
  says so. Concerns (seniority gaps, unstated visa position) are surfaced, not
  buried.

---

## Architecture

```
EXTERNAL          your browser                    Greenhouse Job Board API
                       ▲                                    ▲
──────────────────────┼────────────────────────────────────┼───────────────
GOOGLE CLOUD          │                                    │ 1 call/company
                      │                                    │
  TRIGGER      Cloud Scheduler ──┐          ┌── Dashboard ──┘
               (every 3 h, OIDC) │          │  (Cloud Run, public)
                                 ▼          ▼
  INGEST                    ┌─────────────────────┐
  & DETECT                  │      Collector      │
                            │  ┌───────────────┐  │        ┌──────────┐
                            │  │ deterministic │  │ ─────▶ │ Pub/Sub  │
                            │  │ core — NO LLM │  │        │ 1 msg per│
                            │  │ diff + gate   │  │        │  change  │
                            │  └───────────────┘  │        └────┬─────┘
                            └─────────────────────┘             │ push+OIDC
                                                                ▼
  REASON                                              ┌──────────────┐   ┌────────────┐
                                                      │    Agent     │◀─▶│ Vertex AI  │
                                                      │ Cloud Run+ADK│   │ Gemini 3.7 │
                                                      └──────────────┘   └────────────┘
  STATE        ┌──────────────────────────────────────────────────────────────────┐
               │ Firestore · companies · postings · posting_history · decisions   │
               └──────────────────────────────────────────────────────────────────┘
```

A rendered version with numbered request flow is at
[`/architecture`](https://nightwatch-dashboard-745162634071.us-central1.run.app/architecture).

### The one design decision that matters

**Gemini is called at exactly one point.** Everything before it is ordinary
Python:

| Stage | Implementation | Why |
|---|---|---|
| Change detection | SHA-256 comparison | Deciding whether two records differ is a *comparison*, not a judgement. A model would be slower, non-deterministic and less accurate than a hash. |
| Relevance gate | String matching | No model call should be spent concluding that a warehouse role is not a fit for a data scientist. |
| **Fit assessment** | **Gemini 3.7 Flash** | Judgement: does this change matter to this person, and what would they say about it? |

---

## Tech stack

| Component | Technology |
|---|---|
| Agent framework | **Google ADK 2.8.0** |
| Model | **Gemini 3.7 Flash** via **Vertex AI** (location `global`) |
| Compute | **Cloud Run** × 3 (collector, agent, dashboard) |
| Messaging | **Pub/Sub** — push subscription, OIDC, 600 s ack deadline |
| Database | **Firestore** (Native mode) |
| Scheduling | **Cloud Scheduler** — every 3 hours |
| Web | FastAPI + Jinja2, server-rendered |
| Data source | [Greenhouse Job Board API](https://developers.greenhouse.io/job-board.html) — public, unauthenticated |

---

## Spin-up: run it locally

### Prerequisites

- Python **3.13** (3.14 is not recommended — some compiled dependencies lag)
- [`gcloud` CLI](https://cloud.google.com/sdk/docs/install)
- A Google Cloud project with **billing enabled**

### 1. Clone and install

```bash
git clone <this-repo-url>
cd Hackathon

# uv is fastest, but python -m venv works identically
uv venv --python 3.13 .venv
VIRTUAL_ENV=.venv uv pip install -r requirements.txt
```

### 2. Set up Google Cloud

```bash
export PROJECT_ID=your-project-id
gcloud config set project $PROJECT_ID

gcloud services enable \
  run.googleapis.com pubsub.googleapis.com firestore.googleapis.com \
  cloudscheduler.googleapis.com aiplatform.googleapis.com

# Firestore in Native mode. NOTE: location and mode are PERMANENT.
gcloud firestore databases create --location=us-central1 --type=firestore-native

gcloud pubsub topics create job-changes
```

### 3. Authenticate

Two separate steps — the first authenticates the CLI, the second writes
Application Default Credentials, which is what the Python libraries actually
read. Skipping the second produces confusing auth errors.

```bash
gcloud auth application-default login
gcloud auth application-default set-quota-project $PROJECT_ID
```

No API key is needed anywhere: Vertex AI mode exchanges your ADC refresh token
for a short-lived OAuth token.

### 4. Configure

```bash
cp .env.example .env
```

Edit `.env` and set `GOOGLE_CLOUD_PROJECT`. Leave the rest as-is:

```ini
GOOGLE_GENAI_USE_VERTEXAI=TRUE
GOOGLE_CLOUD_PROJECT=your-project-id
GOOGLE_CLOUD_LOCATION=global      # MUST be global — Gemini 3.x 404s in regions
GCP_REGION=us-central1            # Firestore / Cloud Run / Pub-Sub
GEMINI_MODEL=gemini-3.7-flash
PUBSUB_TOPIC=job-changes
```

> ⚠️ `GOOGLE_CLOUD_LOCATION` and `GCP_REGION` are **deliberately separate**.
> Gemini 3.x publisher models are not served from regional endpoints — every 3.x
> model returns 404 in `us-central1` but resolves on `global`. Using one variable
> for both silently caps you at older models.

### 5. Add your profile and companies

Edit `config/profile.json` — target titles, skills, core skills, excluded
titles, work-authorisation rules. Edit `config/companies.json` to choose which
Greenhouse boards to watch. Find a board token by viewing a company's careers
page source for a `boards-api.greenhouse.io/v1/boards/{token}` URL.

Then seed Firestore:

```bash
.venv/bin/python scripts/seed.py
```

### 6. Run it

```bash
# collection pass (first run per company is a baseline and reports nothing)
.venv/bin/python -c "
from dotenv import load_dotenv; load_dotenv('.env')
from collector.pipeline import run_collection
print(run_collection().totals)"

# the dashboard
.venv/bin/python -m uvicorn dashboard.main:app --port 8080 --reload
```

Open http://localhost:8080

### Verify the agent independently

```bash
.venv/bin/python spikes/adk_spike.py     # proves the ADK tool-calling loop works
.venv/bin/python tests/test_diff_engine.py
.venv/bin/python tests/test_sponsorship_filter.py
```

---

## Spin-up: deploy to Google Cloud

### 1. Service account

```bash
gcloud iam service-accounts create nightwatch-sa --display-name="Jobs NightWatch"
SA=nightwatch-sa@$PROJECT_ID.iam.gserviceaccount.com

for role in roles/datastore.user roles/aiplatform.user roles/pubsub.publisher; do
  gcloud projects add-iam-policy-binding $PROJECT_ID --member="serviceAccount:$SA" --role="$role"
done
```

If the first build fails with `storage.objects.get denied`, newer projects need
Cloud Build roles granted explicitly:

```bash
NUM=$(gcloud projects describe $PROJECT_ID --format='value(projectNumber)')
for role in roles/cloudbuild.builds.builder roles/storage.objectViewer \
            roles/artifactregistry.writer roles/logging.logWriter; do
  gcloud projects add-iam-policy-binding $PROJECT_ID \
    --member="serviceAccount:$NUM-compute@developer.gserviceaccount.com" --role="$role"
done
```

### 2. Deploy the three services

One image, three deployments — the start command is `SERVICE_MODULE`.

```bash
ENVS="GOOGLE_GENAI_USE_VERTEXAI=TRUE,GOOGLE_CLOUD_PROJECT=$PROJECT_ID,\
GOOGLE_CLOUD_LOCATION=global,GCP_REGION=us-central1,\
GEMINI_MODEL=gemini-3.7-flash,PUBSUB_TOPIC=job-changes"

gcloud run deploy nightwatch-agent --source . --region=us-central1 \
  --service-account=$SA --set-env-vars="$ENVS,SERVICE_MODULE=agent.server:app" \
  --no-allow-unauthenticated --max-instances=10 --timeout=600 --memory=1Gi

gcloud run deploy nightwatch-collector --source . --region=us-central1 \
  --service-account=$SA --set-env-vars="$ENVS,SERVICE_MODULE=collector.server:app" \
  --no-allow-unauthenticated --max-instances=2 --timeout=900 --memory=1Gi

COLLECTOR_URL=$(gcloud run services describe nightwatch-collector \
  --region=us-central1 --format='value(status.url)')

gcloud run deploy nightwatch-dashboard --source . --region=us-central1 \
  --service-account=$SA \
  --set-env-vars="GOOGLE_CLOUD_PROJECT=$PROJECT_ID,GCP_REGION=us-central1,\
SERVICE_MODULE=dashboard.main:app,COLLECTOR_URL=$COLLECTOR_URL" \
  --allow-unauthenticated --max-instances=5 --timeout=900 --memory=512Mi
```

### 3. Wire Pub/Sub push

```bash
AGENT_URL=$(gcloud run services describe nightwatch-agent \
  --region=us-central1 --format='value(status.url)')
NUM=$(gcloud projects describe $PROJECT_ID --format='value(projectNumber)')

gcloud run services add-iam-policy-binding nightwatch-agent --region=us-central1 \
  --member="serviceAccount:$SA" --role=roles/run.invoker
gcloud run services add-iam-policy-binding nightwatch-collector --region=us-central1 \
  --member="serviceAccount:$SA" --role=roles/run.invoker
gcloud iam service-accounts add-iam-policy-binding $SA \
  --member="serviceAccount:service-$NUM@gcp-sa-pubsub.iam.gserviceaccount.com" \
  --role=roles/iam.serviceAccountTokenCreator

gcloud pubsub subscriptions create job-changes-push \
  --topic=job-changes \
  --push-endpoint="$AGENT_URL/pubsub-push" \
  --push-auth-service-account="$SA" \
  --push-auth-token-audience="$AGENT_URL" \
  --ack-deadline=600 \
  --min-retry-delay=30s --max-retry-delay=600s
```

> ⚠️ **`--ack-deadline=600` is not optional.** One change takes ~35 s end to end.
> Under the 10 s default, Pub/Sub redelivers three times mid-flight, quadrupling
> model spend while everything looks healthy.

### 4. Schedule it

```bash
gcloud scheduler jobs create http nightwatch-collect \
  --location=us-central1 --schedule="0 */3 * * *" \
  --uri="$COLLECTOR_URL/collect" --http-method=POST \
  --oidc-service-account-email="$SA" \
  --oidc-token-audience="$COLLECTOR_URL" \
  --attempt-deadline=900s
```

### 5. Trigger a run

```bash
curl -X POST "$COLLECTOR_URL/collect" \
  -H "Authorization: Bearer $(gcloud auth print-identity-token)"
```

Or click **Run now** on the dashboard.

---

## Cost

Everything runs at `min-instances=0`, so Cloud Run scales to zero and bills
nothing when idle. Cold start is ~5 s, warm ~0.3 s.

For a demo recording you can warm the services — **but turn it back off**:

```bash
gcloud run services update nightwatch-dashboard --min-instances=1 --region=us-central1
# ... record ...
gcloud run services update nightwatch-dashboard --min-instances=0 --region=us-central1
```

Leaving `min-instances=1` on for two months costs $120–240. At `0` the ongoing
cost is a few dollars.

---

## Repository layout

```
collector/    Greenhouse adapter, collection pipeline, Cloud Run service
diff/         deterministic change detection — no LLM
agent/        ADK agent + FastAPI Pub/Sub push handler
dashboard/    server-rendered UI (dashboard, about, architecture)
common/       schema, Firestore access, relevance filter, agent tools
config/       companies.json, profile.json
scripts/      seed.py, demo_seed.py, simulate_change.py
tests/        diff engine, sponsorship filter
spikes/       adk_spike.py — the smallest proof the ADK loop works
```

`common/tools.py` contains **zero framework imports** — the agent's tools are
plain Python functions, so `agent/agent.py` is the only file that imports ADK.
Swapping to `google-genai` function calling would be a ~30-line change.

---

## Documentation

| File | Contents |
|---|---|
| [`demo.md`](demo.md) | Submission checklist and how to reproduce the demo |
| [`decisions.md`](decisions.md) | Every decision with its reasoning, and the bugs found along the way |
| [`flow.md`](flow.md) | Living system flow, Firestore collections, build status |

---

## Known limitations

- **Single-tenant.** One profile, one company list. `decisions/{doc_id}` is not
  scoped by profile, so two users would overwrite each other's verdicts. The
  `profiles/{profile_id}` schema was chosen to keep multi-user additive rather
  than a migration.
- **Greenhouse only.** Lever and Ashby expose similar public APIs; each is a new
  adapter emitting the same `JobPosting` dataclass.
- **No dead-letter topic.** A permanently failing message retries until it
  expires.
- **Resume is a curated JSON file**, not an upload. `pypdf` extraction already
  works locally; the upload route does not exist yet.

---

## Note on company names

Company names appear as factual references to publicly available job board APIs.
No affiliation, sponsorship or endorsement is implied. No company logos or
branding are used anywhere in this project.
