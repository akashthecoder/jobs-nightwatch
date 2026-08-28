"""Cloud Run service: receives Pub/Sub push messages, runs the agent.

HTTP status is the ack protocol, and getting it wrong is expensive:

    2xx  -> Pub/Sub acks the message and never redelivers
    5xx  -> Pub/Sub nacks and retries with backoff

So a MALFORMED message must return 200. It will never parse on retry, and
nacking it means Pub/Sub redelivers a poison message until it expires. A
TRANSIENT failure (Gemini timeout, Firestore blip) must return 5xx so the
work is not silently lost.
"""
from __future__ import annotations

import base64
import json
import logging
import os
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, Request, Response

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

from agent.agent import assess_change  # noqa: E402
from common import store  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger("nightwatch.agent")

app = FastAPI(title="Jobs NightWatch Agent")


@app.get("/health")
def health():
    return {"ok": True, "service": "agent", "model": os.environ.get("GEMINI_MODEL")}


def _decode_envelope(body: dict) -> dict | None:
    """Unwrap a Pub/Sub push envelope. Returns None if it is not one."""
    message = body.get("message")
    if not isinstance(message, dict):
        return None
    raw = message.get("data")
    if not raw:
        return None
    try:
        return json.loads(base64.b64decode(raw).decode("utf-8"))
    except Exception:
        log.exception("undecodable message data")
        return None


@app.post("/pubsub-push")
async def pubsub_push(request: Request):
    try:
        body = await request.json()
    except Exception:
        log.warning("non-JSON body; acking so it is not redelivered")
        return Response(status_code=204)

    # Accept either a real push envelope or a bare change dict, so the same
    # endpoint can be exercised with curl during development.
    change = _decode_envelope(body) or (body if "doc_id" in body else None)

    if not change or not change.get("doc_id"):
        log.warning("unparseable change payload; acking to avoid a poison loop")
        return Response(status_code=204)

    doc_id = change["doc_id"]
    posting = change.get("posting") or {}
    content_hash = posting.get("content_hash") or change.get("content_hash") or ""

    # Idempotency. Pub/Sub guarantees at-least-once, so the same message can
    # arrive twice. Re-running would cost another model call and overwrite an
    # identical verdict. Keyed on content_hash rather than doc_id, so a posting
    # that changes AGAIN is correctly reassessed.
    existing = store.get_decision(doc_id)
    if existing and content_hash and existing.get("content_hash") == content_hash:
        log.info("duplicate for %s (hash unchanged); acking without reprocessing", doc_id)
        return {"status": "duplicate", "doc_id": doc_id}

    try:
        result = await assess_change(change)
    except Exception as e:  # noqa: BLE001
        # Transient by assumption: nack so Pub/Sub retries with backoff.
        log.exception("agent failed for %s", doc_id)
        return Response(
            content=json.dumps({"error": str(e), "doc_id": doc_id}),
            media_type="application/json",
            status_code=500,
        )

    if not result.get("recorded"):
        # The agent ran but never called record_assessment. Retrying may work,
        # so nack -- but log loudly, because a persistent version of this is a
        # prompt problem, not an infrastructure one.
        log.error("agent did not record an assessment for %s", doc_id)
        return Response(
            content=json.dumps({"error": "no assessment recorded", "doc_id": doc_id}),
            media_type="application/json",
            status_code=500,
        )

    # Attach envelope metadata the model does not supply, so the dashboard can
    # render without re-reading the postings collection.
    store.merge_decision(
        doc_id,
        {
            "content_hash": content_hash,
            "change_type": change.get("change_type", ""),
            "company": change.get("company", ""),
            "board_token": change.get("board_token", ""),
            "title": change.get("title", ""),
            "url": change.get("url", ""),
            "changed_fields": change.get("changed_fields", []),
            "filter_reason": change.get("filter_reason", ""),
        },
    )

    log.info("assessed %s tools=%s", doc_id, result.get("tool_calls"))
    return {"status": "ok", "doc_id": doc_id, "tool_calls": result.get("tool_calls", [])}
