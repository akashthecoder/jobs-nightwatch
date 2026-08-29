"""Firestore access. The only module that talks to the database.

Collections:
    companies/{board_token}          tracked company, enabled + baselined flags
    postings/{board_token}_{ext_id}  current state of one posting + content_hash
    decisions/{board_token}_{ext_id} agent verdict, reasoning, draft bullets
    profiles/{profile_id}            candidate profile ("default" for now)

Postings are keyed by (board_token, external_id) so the diff engine reads a
posting's previous state with a direct get-by-id. No queries, so no composite
indexes to define, and nothing to tune under deadline.
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Any, Iterable

from google.cloud import firestore

from common.schema import JobPosting

log = logging.getLogger(__name__)

COMPANIES = "companies"
POSTINGS = "postings"
DECISIONS = "decisions"
HISTORY = "posting_history"
PROFILES = "profiles"

_client: firestore.Client | None = None


def db() -> firestore.Client:
    global _client
    if _client is None:
        _client = firestore.Client(project=os.environ.get("GOOGLE_CLOUD_PROJECT"))
    return _client


# --------------------------------------------------------------------------
# companies
# --------------------------------------------------------------------------

def seed_companies(companies: list[dict]) -> int:
    """Seed company docs from config, without clobbering runtime state.

    `enabled` and `baselined` live in Firestore because the dashboard toggles
    them at runtime. Re-seeding must not reset a company the user just turned
    off, so those fields are only written when the document is new.
    """
    written = 0
    for c in companies:
        ref = db().collection(COMPANIES).document(c["board_token"])
        snap = ref.get()
        base = {
            "board_token": c["board_token"],
            "name": c["name"],
            "ats": c.get("ats", "greenhouse"),
        }
        if snap.exists:
            ref.update(base)
        else:
            ref.set({**base, "enabled": c.get("enabled", True), "baselined": False})
            written += 1
    return written


def list_companies(enabled_only: bool = False) -> list[dict]:
    docs = db().collection(COMPANIES).stream()
    out = [d.to_dict() for d in docs]
    if enabled_only:
        out = [c for c in out if c.get("enabled")]
    return sorted(out, key=lambda c: c.get("name", ""))


def set_company_enabled(board_token: str, enabled: bool) -> None:
    db().collection(COMPANIES).document(board_token).update({"enabled": enabled})


def mark_baselined(board_token: str) -> None:
    db().collection(COMPANIES).document(board_token).update({"baselined": True})


def record_run_stats(
    board_token: str,
    posting_count: int,
    change_count: int,
    matches: list[dict] | None = None,
) -> None:
    """Stamp a company with the outcome of the run that just finished.

    `matches` is the list of postings that passed the relevance gate, already
    sorted. It is stored ON THE COMPANY DOCUMENT rather than queried, so the
    dashboard needs one read per company instead of scanning thousands of
    postings -- and no composite index has to exist.

    Capped at 100 entries to stay well inside Firestore's 1 MB document limit.
    """
    payload = {
        "last_collected_at": datetime.now(timezone.utc).isoformat(),
        "posting_count": posting_count,
        "last_change_count": change_count,
    }
    if matches is not None:
        payload["matches"] = matches[:100]
        payload["match_count"] = len(matches)
    db().collection(COMPANIES).document(board_token).update(payload)


# --------------------------------------------------------------------------
# postings
# --------------------------------------------------------------------------

def get_postings_for_company(board_token: str) -> dict[str, dict]:
    """All stored postings for a company, keyed by doc_id."""
    q = db().collection(POSTINGS).where(filter=firestore.FieldFilter("board_token", "==", board_token))
    return {d.id: d.to_dict() for d in q.stream()}


def get_posting(doc_id: str) -> dict[str, Any] | None:
    """One posting's current stored state."""
    snap = db().collection(POSTINGS).document(doc_id).get()
    return snap.to_dict() if snap.exists else None


def save_history(doc_id: str, previous: dict) -> None:
    """Preserve the version a posting had BEFORE this run overwrote it.

    Required because the agent runs asynchronously: the collector publishes to
    Pub/Sub and then immediately upserts the new state, so by the time the
    agent asks what the posting used to say, postings/{doc_id} already holds
    the NEW text. Without this the agent reports "nothing changed" for every
    modification -- a failure that only appears once deployed, since a local
    synchronous run reads the old value before it is overwritten.
    """
    db().collection(HISTORY).document(doc_id).set(previous)


def get_history(doc_id: str) -> dict[str, Any] | None:
    """The version a posting had before the most recent change."""
    snap = db().collection(HISTORY).document(doc_id).get()
    return snap.to_dict() if snap.exists else None


def upsert_postings(postings: Iterable[JobPosting]) -> int:
    """Write postings in batches. Firestore caps a batch at 500 operations."""
    batch = db().batch()
    n = 0
    pending = 0
    for p in postings:
        ref = db().collection(POSTINGS).document(p.doc_id)
        batch.set(ref, p.to_dict())
        n += 1
        pending += 1
        if pending == 400:
            batch.commit()
            batch = db().batch()
            pending = 0
    if pending:
        batch.commit()
    return n


def delete_postings(doc_ids: Iterable[str]) -> int:
    batch = db().batch()
    n = 0
    pending = 0
    for doc_id in doc_ids:
        batch.delete(db().collection(POSTINGS).document(doc_id))
        n += 1
        pending += 1
        if pending == 400:
            batch.commit()
            batch = db().batch()
            pending = 0
    if pending:
        batch.commit()
    return n


# --------------------------------------------------------------------------
# profiles
# --------------------------------------------------------------------------

def put_profile(profile: dict, profile_id: str = "default") -> None:
    db().collection(PROFILES).document(profile_id).set(profile)


def get_profile(profile_id: str = "default") -> dict[str, Any] | None:
    snap = db().collection(PROFILES).document(profile_id).get()
    return snap.to_dict() if snap.exists else None


# --------------------------------------------------------------------------
# decisions
# --------------------------------------------------------------------------

def put_decision(doc_id: str, decision: dict) -> None:
    db().collection(DECISIONS).document(doc_id).set(decision)


def merge_decision(doc_id: str, fields: dict) -> None:
    """Patch fields onto an existing decision without clobbering the verdict."""
    db().collection(DECISIONS).document(doc_id).set(fields, merge=True)


def get_decision(doc_id: str) -> dict[str, Any] | None:
    snap = db().collection(DECISIONS).document(doc_id).get()
    return snap.to_dict() if snap.exists else None


def list_decisions(limit: int = 100) -> list[dict]:
    q = (
        db()
        .collection(DECISIONS)
        .order_by("decided_at", direction=firestore.Query.DESCENDING)
        .limit(limit)
    )
    return [d.to_dict() for d in q.stream()]
