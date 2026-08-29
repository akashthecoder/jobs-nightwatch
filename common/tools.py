"""Agent tools. Plain Python functions with ZERO framework imports.

ADK registers plain callables as tools and builds the declaration sent to
Gemini from the type hints and docstring. `google-genai` function calling
accepts the same shape. Keeping this module framework-free means swapping
frameworks is a change to the orchestration file only, with all domain logic
untouched.

Design principle: a tool must do something the MODEL CANNOT do - fetch data it
does not have, run deterministic logic it should not guess at, or cause a side
effect. Judgement calls ("is this a good fit?") belong to the model. A tool
that returns a hardcoded verdict is theatre.

DOCSTRINGS ARE THE API. Gemini sees the description and the Args section, not
the implementation. Vague docstrings measurably degrade tool selection.
"""
from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import Any

log = logging.getLogger(__name__)

# Injected by the orchestration layer so this module imports nothing from the
# app. Kept module-level rather than passed per-call because ADK derives the
# tool signature from the type hints, and Gemini should not be asked to supply
# a database handle.
_store = None
_profile_cache: dict | None = None


def bind_store(store_module) -> None:
    """Wire up the Firestore accessor. Called once at startup."""
    global _store
    _store = store_module


# ---------------------------------------------------------------------------
# tools exposed to the model
# ---------------------------------------------------------------------------

def get_candidate_profile() -> dict:
    """Get the candidate's background: skills, experience, target roles, and
    the domains they know best.

    Call this before assessing fit, so the assessment is grounded in the
    candidate's actual background rather than assumptions.

    Returns:
        The candidate's profile including skills, target_titles, years of
        experience, domain_preference, highlights and what they want to avoid.
    """
    global _profile_cache
    if _profile_cache is None and _store is not None:
        _profile_cache = _store.get_profile("default") or {}
    return _profile_cache or {}


def get_previous_version(doc_id: str) -> dict:
    """Get what a job posting said the LAST time it was seen.

    Use this when a posting was modified, to find out what actually changed.
    Knowing a posting quietly added a requirement, changed seniority, or
    altered its location is the whole point of this system - and that history
    is not in the posting itself.

    Args:
        doc_id: The posting's document id, formatted as board_token_externalid
            (for example "sofi_4567890").

    Returns:
        The previously stored version with title, location, department and
        description_text, or a dict with "found": false if this posting has
        no recorded history.
    """
    if _store is None:
        return {"found": False, "reason": "store not bound"}
    # Read the history snapshot, NOT postings/{doc_id}. The collector has
    # already overwritten the live record with the new version by the time
    # this runs, so reading it would always report "nothing changed".
    prev = _store.get_history(doc_id)
    if not prev:
        return {"found": False, "reason": "no previous version recorded"}
    return {
        "found": True,
        "title": prev.get("title", ""),
        "location": prev.get("location", ""),
        "department": prev.get("department", ""),
        "description_text": (prev.get("description_text") or "")[:6000],
    }


def check_hard_blockers(posting_text: str) -> dict:
    """Check a posting for absolute eligibility blockers using exact text matching.

    This is a deterministic check, not a judgement. Use it rather than reading
    the posting yourself, because eligibility is a matter of fact and a missed
    blocker wastes the candidate's time on a role they cannot take.

    IMPORTANT: if this returns blocked=false, that means no restriction was
    STATED. Most postings say nothing about sponsorship at all. Never report
    that sponsorship is available - only that the posting is silent on it.

    Args:
        posting_text: The full text of the job posting.

    Returns:
        A dict with "blocked" (bool), "reason" (the matched phrase, if any),
        and "sponsorship_mentioned" (whether the posting addresses it at all).
    """
    profile = get_candidate_profile()
    wa = profile.get("work_authorization", {}) or {}
    patterns = wa.get("exclude_if_posting_matches", [])

    for pat in patterns:
        m = re.search(pat, posting_text, re.I)
        if m:
            return {
                "blocked": True,
                "reason": m.group(0)[:120],
                "sponsorship_mentioned": True,
            }

    mentioned = bool(re.search(r"sponsor|visa|work authorization", posting_text, re.I))
    return {
        "blocked": False,
        "reason": "",
        "sponsorship_mentioned": mentioned,
    }


def record_assessment(
    doc_id: str,
    worth_attention: bool,
    fit_score: int,
    headline: str,
    reasoning: str,
    what_changed: str,
    domain_match: str,
    application_bullets: list[str],
    concerns: list[str],
) -> dict:
    """Record the final assessment of this change. Call this exactly once, last.

    Args:
        doc_id: The posting's document id.
        worth_attention: Whether the candidate should actually look at this.
        fit_score: Fit from 0 to 100.
        headline: One sentence on why this change matters, or why it does not.
        reasoning: The reasoning behind the verdict, in two or three sentences.
        what_changed: What changed versus the previous version. For a new
            posting say "new posting"; for a removed one say "posting removed".
        domain_match: How the role's domain relates to the candidate's
            background - one of "strong", "adjacent", or "weak", plus a brief
            justification.
        application_bullets: Two to four specific bullets the candidate would
            lead with, each citing concrete experience from their profile.
            Empty if not worth attention.
        concerns: Anything giving pause - seniority mismatch, unstated
            sponsorship, missing skills. Empty if none.

    Returns:
        Confirmation that the assessment was recorded.
    """
    record = {
        "doc_id": doc_id,
        "worth_attention": bool(worth_attention),
        "fit_score": int(fit_score),
        "headline": headline,
        "reasoning": reasoning,
        "what_changed": what_changed,
        "domain_match": domain_match,
        "application_bullets": list(application_bullets or []),
        "concerns": list(concerns or []),
        "decided_at": datetime.now(timezone.utc).isoformat(),
    }
    if _store is not None:
        existing = _store.get_decision(doc_id) or {}
        # Preserve the original sighting time across re-assessments.
        record["first_seen_at"] = existing.get("first_seen_at", record["decided_at"])
        _store.put_decision(doc_id, {**existing, **record})
    log.info("recorded assessment %s worth=%s score=%s", doc_id, worth_attention, fit_score)
    return {"recorded": True, "doc_id": doc_id}


ALL_TOOLS = [
    get_candidate_profile,
    get_previous_version,
    check_hard_blockers,
    record_assessment,
]
