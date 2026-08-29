"""Cloud Run service: the dashboard.

Server-rendered HTML. The browser never talks to Firestore, so there are no
client-side security rules to write or debug -- the entire problem class is
removed rather than solved.
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from pathlib import Path

import requests
from dotenv import load_dotenv
from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

from common import store  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger("nightwatch.dashboard")

app = FastAPI(title="Jobs NightWatch")
templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))

COLLECTOR_URL = os.environ.get("COLLECTOR_URL", "")


@app.get("/health")
def health():
    return {"ok": True, "service": "dashboard"}


def ago(iso: str | None) -> str:
    """Render an ISO timestamp as 'just now' / '4 min ago' / '2 hours ago'.

    This page is about change over time, so a bare list with no timestamps
    gives a visitor no way to tell live results from a static mockup.
    """
    if not iso:
        return ""
    try:
        then = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    except ValueError:
        return ""
    secs = (datetime.now(timezone.utc) - then).total_seconds()
    if secs < 60:
        return "just now"
    if secs < 3600:
        m = int(secs // 60)
        return f"{m} min ago"
    if secs < 86400:
        h = int(secs // 3600)
        return f"{h} hour{'s' if h > 1 else ''} ago"
    d = int(secs // 86400)
    return f"{d} day{'s' if d > 1 else ''} ago"


@app.get("/", response_class=HTMLResponse)
def index(
    request: Request,
    company: str | None = None,
    ran: str | None = None,
    error: str | None = None,
):
    companies = store.list_companies()
    decisions = store.list_decisions(limit=200)

    for c in companies:
        c["last_checked"] = ago(c.get("last_collected_at"))
    for d in decisions:
        d["when"] = ago(d.get("decided_at"))

    # Company view: matching roles for one company, plus its own changes.
    selected = None
    matches = []
    if company:
        selected = next((c for c in companies if c["board_token"] == company), None)
        if selected:
            matches = selected.get("matches", []) or []
            # Attach the agent's verdict where one exists. Most matching roles
            # have never been assessed -- they passed the cheap gate but never
            # changed, so no model call was ever warranted.
            by_id = {d.get("doc_id"): d for d in decisions}
            for m in matches:
                d = by_id.get(m["doc_id"])
                if d:
                    m["fit_score"] = d.get("fit_score")
                    m["assessed"] = True
            decisions = [d for d in decisions if d.get("board_token") == company]

    # Surface what needs attention first; everything else is still visible
    # below, because "we looked and it is not a fit" is a useful answer too.
    worth = [d for d in decisions if d.get("worth_attention")]
    rest = [d for d in decisions if not d.get("worth_attention")]
    worth.sort(key=lambda d: d.get("fit_score", 0), reverse=True)

    last_run = max(
        (c.get("last_collected_at") for c in companies if c.get("last_collected_at")),
        default=None,
    )

    stats = {
        "companies": sum(1 for c in companies if c.get("enabled")),
        "postings": sum(c.get("posting_count", 0) for c in companies),
        "matches": sum(c.get("match_count", 0) for c in companies),
        "changes": len(decisions),
        "flagged": len(worth),
        "last_run": ago(last_run),
    }

    # Starlette >=1.x signature: request first, then template name, then context.
    # The older TemplateResponse(name, {"request": ...}) form raises an opaque
    # "unhashable type: dict" from deep inside Jinja.
    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "companies": companies,
            "worth": worth,
            "rest": rest,
            "stats": stats,
            "selected": selected,
            "matches": matches,
            "ran": ran,
            "error": error,
            "has_collector": bool(COLLECTOR_URL),
        },
    )


@app.post("/toggle")
def toggle(board_token: str = Form(...), enabled: str = Form(...)):
    """Turn tracking on or off for one company.

    Deliberately NON-DESTRUCTIVE: disabling stops future collection but leaves
    existing decisions on the dashboard. The worst a visitor can do is pause
    one company, so the page needs no auth to be safe to share with judges.
    """
    store.set_company_enabled(board_token, enabled == "true")
    log.info("toggled %s -> %s", board_token, enabled)
    return RedirectResponse("/", status_code=303)


@app.post("/run-now")
def run_now(board_token: str = Form(default="")):
    """Trigger a collection immediately.

    Without this a visitor toggles a company on and sees nothing until the next
    scheduled run. Also serves as the on-camera manual trigger for the demo.
    """
    if not COLLECTOR_URL:
        log.warning("COLLECTOR_URL not configured; cannot trigger a run")
        return RedirectResponse("/?error=collector_not_configured", status_code=303)

    url = f"{COLLECTOR_URL.rstrip('/')}/collect"
    params = {"board_token": board_token} if board_token else {}
    try:
        headers = _auth_header(COLLECTOR_URL)
        r = requests.post(url, params=params, headers=headers, timeout=600)
        log.info("collector responded %s", r.status_code)
    except Exception:
        log.exception("failed to trigger collector")
        return RedirectResponse("/?error=collector_failed", status_code=303)

    return RedirectResponse("/?ran=1", status_code=303)


def _auth_header(target_url: str) -> dict:
    """Mint an OIDC identity token for a private Cloud Run target.

    On Cloud Run the token comes from the instance metadata server, using the
    service's attached service account. Locally there is no metadata server, so
    this returns no header and the call only works against an unauthenticated
    or locally-running collector.
    """
    try:
        import google.auth.transport.requests
        import google.oauth2.id_token

        req = google.auth.transport.requests.Request()
        token = google.oauth2.id_token.fetch_id_token(req, target_url)
        return {"Authorization": f"Bearer {token}"}
    except Exception:
        log.info("no OIDC token available; calling collector unauthenticated")
        return {}
