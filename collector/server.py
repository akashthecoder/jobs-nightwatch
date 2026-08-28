"""Cloud Run service: triggers a collection run.

Called by Cloud Scheduler on a timer, and by the dashboard's "Run now" button.
Kept thin on purpose -- all the logic lives in collector/pipeline.py so it can
be tested without HTTP.
"""
from __future__ import annotations

import logging
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, Query

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

from collector.pipeline import run_collection  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger("nightwatch.collector")

app = FastAPI(title="Jobs NightWatch Collector")


@app.get("/health")
def health():
    return {"ok": True, "service": "collector"}


@app.post("/collect")
def collect(board_token: str | None = Query(default=None)):
    """Run one collection pass.

    Cloud Scheduler POSTs here with no arguments to sweep every enabled
    company. Passing board_token limits the run to one company, which is what
    the dashboard uses so a single click stays fast.
    """
    result = run_collection(only_board_token=board_token)
    log.info("collection finished: %s", result.totals)
    return result.to_dict()
