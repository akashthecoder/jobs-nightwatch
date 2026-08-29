# Jobs NightWatch — Devpost Submission

Copy-paste source for the Devpost form. Each section maps to a form field.

---

## Project name

**Jobs NightWatch**

## Tagline

Job boards show you what exists. This shows you what *changed*.

## Category

**Taskmaster**

## Hosted project URL

https://nightwatch-dashboard-745162634071.us-central1.run.app

## Repository URL

https://github.com/akashthecoder/jobs-nightwatch *(private — access granted to `testing@devpost.com` and `cloudhackathons@google.com`)*

## Demo video

*(YouTube link — to be added)*

---

## Description

### The problem

A job search means doing four tedious things by hand, over and over: **checking**
every company's board, **reading** each posting to see whether it is even
relevant, **judging** whether you are actually a fit, and **working out what to
say** if you apply.

Worse, job boards only ever show you the *current state*. Nobody tells you that a
role you have been tracking for three weeks quietly moved its experience bar from
five years to twelve. Nobody tells you the posting you applied to on Tuesday was
pulled on Thursday. You would only notice by re-reading every posting you care
about, every day, and remembering exactly what each one used to say.

Nobody does that. **That gap is the product.**

### What it does

Jobs NightWatch watches 10 companies' career pages on a timer, remembers what
every posting said last time, and reports what changed.

- **Filters to your profile.** Of ~2,750 postings tracked, ~315 (11%) match the
  candidate's target titles, core skills and seniority. The other ~2,440 never
  cost a model call.
- **Detects genuine change.** SHA-256 content fingerprints catch silent rewrites
  that a timestamp would miss — a requirement added, a title upleveled, a
  location changed.
- **Rates what is worth applying to.** Each meaningful change gets a fit score
  out of 100 with the reasoning behind it.
- **Drafts your opening bullets**, citing concrete projects and real numbers from
  the candidate's background, so the blank page is already filled in.
- **Tells you honestly.** Most changes are *not* worth attention, and it says so.
  Concerns — a seniority gap, an unstated visa position — are surfaced rather
  than buried.

A representative result from the live system:

> **MODIFIED · Principal Data Scientist, Ads**
> *What changed:* Title updated from "Data Scientist, Ads" to "Principal Data
> Scientist, Ads", raising the experience requirement to 12+ years for MS
> holders, and publishing the $268,000–$365,100 salary range.
> *Concerns:* requires 12+ years (candidate has 11); posting is silent on visa
> sponsorship.

No job board can tell you that, because no job board remembers what it said
yesterday.

### How it works

Five stages, and the boundary between them is the core design decision:

1. **Cloud Scheduler** wakes the system every three hours. This is what makes it
   an agent rather than a website you have to remember to visit.
2. **The Collector** (Cloud Run) fetches each company's board in one HTTP call,
   normalises wildly different posting shapes into a common schema, and
   fingerprints the content.
3. **The diff engine and relevance gate** — plain deterministic Python, no model.
4. **Pub/Sub** carries each detected change as an independent message.
5. **The Agent** (Cloud Run + ADK + Gemini 3.7 Flash) picks up one change at a
   time and decides which tools to call: fetch the candidate profile, retrieve
   what the posting said *last time*, run a deterministic eligibility check, and
   record its verdict.

Results are served from a read-only dashboard on Cloud Run, with live
[About](https://nightwatch-dashboard-745162634071.us-central1.run.app/about) and
[Architecture](https://nightwatch-dashboard-745162634071.us-central1.run.app/architecture)
pages.

### Technologies used

| Layer | Technology |
|---|---|
| Agent framework | **Google Agent Development Kit (ADK) 2.8.0** |
| Model | **Gemini 3.7 Flash** via **Vertex AI** |
| Compute | **Cloud Run** × 3 — collector, agent, dashboard |
| Messaging | **Pub/Sub** — push subscription, OIDC auth, 600s ack deadline |
| Database | **Firestore** (Native mode) |
| Scheduling | **Cloud Scheduler** |
| Auth | OIDC service-account tokens throughout — no API keys anywhere |
| Web | FastAPI + Jinja2, server-rendered |
| Language | Python 3.13 |

### Data sources

**Greenhouse Job Board API** — public and unauthenticated. One call per company
returns every posting with full description text. Ten boards are tracked:
Databricks, Datadog, Cloudflare, Pinterest, Affirm, Coinbase, Airbnb, Reddit,
Twilio and SoFi.

The candidate profile is a curated JSON document extracted from a resume,
containing target titles, skills, domain preferences and work-authorisation
constraints. No third-party job aggregators, scrapers or paid data sources are
used.

*Company names appear as factual references to publicly available APIs. No
affiliation, sponsorship or endorsement is implied, and no company logos or
branding are used anywhere in the project.*

---

## Findings and learnings

### 1. The bug that only existed in production

The agent's most valuable capability — telling you what a posting used to say —
worked perfectly in every local test and failed **silently** once deployed.

The Collector publishes to Pub/Sub and then immediately overwrites stored
postings. Locally the agent runs synchronously and reads the old value before the
overwrite. In production it runs asynchronously via Pub/Sub, arriving seconds
later, so it read the *already-updated* record, compared the new version against
itself, and confidently reported "title, qualifications and responsibilities are
unchanged" — for a posting whose title had demonstrably changed.

No exception, no retry, no error log. Just a well-written wrong answer.

The fix was a dedicated `posting_history` collection written *before* the
overwrite. The lesson is sharper than the fix: **asynchronous systems have
ordering hazards that synchronous tests cannot expose**, and decoupling for fault
isolation buys resilience at the cost of ordering guarantees. Nothing short of
deploying it and reading the actual output would have caught this.

### 2. Test filters against real data, not imagined data

The work-authorisation filter passed all 23 hand-written test cases. Run against
live postings, it silently dropped **all 313 Cloudflare postings**.

Cloudflare's boilerplate contains: *"...your authorization to receive software or
technology controlled under these U.S. **export laws without sponsorship for an
export license**."* That is export-licence sponsorship, not visa sponsorship. An
unanchored `without ... sponsorship` pattern matched it.

Cloudflare simply showed 0.0% matches and looked like a company with no data
roles. The failure was invisible — a filtered posting never reaches the agent or
the dashboard, so nobody learns it was dropped.

No synthetic test would have caught this, because nobody invents export-control
boilerplate when imagining sponsorship phrasings. Real data contained decoys —
"Sponsor bank", "citizen developers", "co-sponsored demand gen" — that no amount
of imagination would have produced.

### 3. Know where the model belongs — and where it does not

Gemini is called at exactly **one** point in the pipeline. Change detection is a
SHA-256 comparison; relevance filtering is string matching. Neither involves a
model, and both complete in about two seconds across 2,750 postings.

Deciding whether two records differ is a *comparison*, not a judgement. A model
there would be slower, non-deterministic, more expensive and **less accurate**
than a hash. The model earns its place on the question only it can answer: does
this change matter to this person, and what would they say about it?

### 4. The cold-start flood

Under the original design, the first run over ten boards would classify all 2,750
postings as "new" — 2,750 model calls producing alerts nobody wants.

This is a category error, not just a cost problem: "changed" is *undefined* when
there is no previous version. The fix was to make a company's first collection a
silent baseline, with alerting starting from the second run. It cost twenty lines
and was caught by summing the board sizes before writing the code.

### 5. Google Cloud specifics worth writing down

- **Gemini 3.x is not served from regional Vertex endpoints.** Every 3.x model
  returns 404 in `us-central1` and resolves on `global`. This was nearly missed
  because an older model worked fine in-region — a working system is not
  evidence of a correct one.
- **A model appearing in `models.list()` does not mean it is callable** from your
  configured location. The catalog is broader than any single endpoint.
- **Pub/Sub's default 10-second ack deadline is a trap** for LLM workloads. One
  change takes ~35 seconds; under the default, Pub/Sub redelivers three times
  mid-flight, quadrupling model spend while everything looks healthy.
- **ADK 2.x reorganised the API** relative to the 1.x material online. Reading
  the installed package (`Agent.model_fields`, `inspect.signature`) was faster
  than following any tutorial. `run_debug()` is async despite a
  synchronous-looking signature.

### 6. What I would do next

- **Multi-user.** Currently single-tenant. `decisions/{doc_id}` is not scoped by
  profile, so two users would overwrite each other's verdicts — a real bug, not
  just a missing feature. The `profiles/{profile_id}` schema was chosen from day
  one to keep this additive rather than a migration.
- **A dead-letter topic** for permanently failing messages.
- **More ATS adapters.** Lever and Ashby expose similar public APIs; each is one
  adapter emitting the same dataclass.
- **Evaluation.** The agent's fit judgements are unmeasured. Labelling a few
  dozen postings by hand would turn "seems good" into a number.

---

## Notes for judges

- The dashboard is **public with no sign-in**. Pausing a company is deliberately
  **non-destructive** — it stops future collection but leaves existing results
  visible, so exploring cannot break the demo.
- A company's first collection **reports nothing by design**. If you add a new
  company and see no results, that is baselining working correctly.
- `decisions.md` in the repository logs every design decision with its reasoning
  and date, including the bugs above as they were found.
