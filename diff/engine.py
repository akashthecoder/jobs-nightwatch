"""Change detection. Plain deterministic Python - NO LLM.

Deciding whether two records differ is a comparison, not a judgement. A model
here would be slower, non-deterministic, more expensive and less accurate than
a hash. The model's job starts AFTER a change is found: deciding whether that
change matters to this candidate.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import Enum

from common.schema import JobPosting

log = logging.getLogger(__name__)


class ChangeType(str, Enum):
    NEW = "new"
    MODIFIED = "modified"
    REMOVED = "removed"


@dataclass
class Change:
    change_type: ChangeType
    doc_id: str
    board_token: str
    company: str
    title: str
    url: str
    posting: JobPosting | None          # None for REMOVED
    previous: dict | None = None        # prior stored state, for MODIFIED
    changed_fields: list[str] | None = None

    def to_message(self) -> dict:
        """Compact payload for Pub/Sub.

        Carries the full posting text so the agent needs no extra fetch, and
        so the message is a self-contained record of what was true when the
        change was detected.
        """
        return {
            "change_type": self.change_type.value,
            "doc_id": self.doc_id,
            "board_token": self.board_token,
            "company": self.company,
            "title": self.title,
            "url": self.url,
            "changed_fields": self.changed_fields or [],
            "posting": self.posting.to_dict() if self.posting else None,
            "previous_title": (self.previous or {}).get("title"),
        }


# Fields compared to explain WHAT changed. Excludes updated_at (an ATS can
# touch it without the posting changing) and url.
COMPARED_FIELDS = ("title", "location", "department", "description_text")


def diff_company(
    board_token: str,
    fetched: list[JobPosting],
    stored: dict[str, dict],
    is_baselined: bool,
) -> tuple[list[Change], bool]:
    """Compare a freshly fetched board against stored state.

    Returns (changes, should_mark_baselined).

    If the company has never been baselined, returns NO changes. "Changed" is
    undefined with no prior snapshot, and treating first sight as "new" would
    emit one alert per posting on a board of hundreds - alerts nobody wants,
    each costing a model call.
    """
    if not is_baselined:
        log.info(
            "diff: %s not yet baselined - storing %d postings, emitting 0 changes",
            board_token,
            len(fetched),
        )
        return [], True

    changes: list[Change] = []
    fetched_by_id = {p.doc_id: p for p in fetched}

    for doc_id, posting in fetched_by_id.items():
        prev = stored.get(doc_id)

        if prev is None:
            changes.append(
                Change(
                    ChangeType.NEW,
                    doc_id,
                    board_token,
                    posting.company,
                    posting.title,
                    posting.url,
                    posting,
                )
            )
            continue

        if prev.get("content_hash") != posting.content_hash:
            changed = [
                f
                for f in COMPARED_FIELDS
                if (prev.get(f) or "") != (getattr(posting, f) or "")
            ]
            changes.append(
                Change(
                    ChangeType.MODIFIED,
                    doc_id,
                    board_token,
                    posting.company,
                    posting.title,
                    posting.url,
                    posting,
                    previous=prev,
                    changed_fields=changed,
                )
            )

    for doc_id, prev in stored.items():
        if doc_id not in fetched_by_id:
            changes.append(
                Change(
                    ChangeType.REMOVED,
                    doc_id,
                    board_token,
                    prev.get("company", ""),
                    prev.get("title", ""),
                    prev.get("url", ""),
                    None,
                    previous=prev,
                )
            )

    log.info(
        "diff: %s -> %d changes (%d new, %d modified, %d removed)",
        board_token,
        len(changes),
        sum(c.change_type == ChangeType.NEW for c in changes),
        sum(c.change_type == ChangeType.MODIFIED for c in changes),
        sum(c.change_type == ChangeType.REMOVED for c in changes),
    )
    return changes, False
