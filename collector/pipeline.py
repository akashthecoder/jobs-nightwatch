"""The collection run: fetch -> diff -> filter -> publish.

Order matters and is deliberate:

  1. fetch      one HTTP call per enabled company
  2. diff       deterministic hash comparison (no LLM)
  3. filter     deterministic relevance check (no LLM)
  4. publish    one Pub/Sub message per surviving change
  5. persist    write postings AFTER publishing decisions are made

Step 5 comes last on purpose. If publishing fails, the stored state is left
untouched, so the next run re-detects the same changes rather than silently
losing them. Persisting first would mark the changes as seen even though
nothing was ever dispatched.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

from common import store
from common.publisher import publish_changes
from common.relevance import RelevanceFilter
from common.schema import JobPosting
from collector.greenhouse import fetch_board
from diff.engine import ChangeType, diff_company

log = logging.getLogger(__name__)


@dataclass
class CompanyResult:
    board_token: str
    company: str
    fetched: int = 0
    changes: int = 0
    published: int = 0
    filtered_out: int = 0
    baselined_now: bool = False
    error: str | None = None


@dataclass
class RunResult:
    companies: list[CompanyResult] = field(default_factory=list)

    @property
    def totals(self) -> dict:
        return {
            "companies": len(self.companies),
            "fetched": sum(c.fetched for c in self.companies),
            "changes": sum(c.changes for c in self.companies),
            "published": sum(c.published for c in self.companies),
            "filtered_out": sum(c.filtered_out for c in self.companies),
            "errors": sum(1 for c in self.companies if c.error),
        }

    def to_dict(self) -> dict:
        return {
            "totals": self.totals,
            "companies": [c.__dict__ for c in self.companies],
        }


def run_collection(only_board_token: str | None = None) -> RunResult:
    """Run one collection pass over enabled companies."""
    profile = store.get_profile("default") or {}
    rel = RelevanceFilter(profile)

    companies = store.list_companies(enabled_only=True)
    if only_board_token:
        companies = [c for c in companies if c["board_token"] == only_board_token]

    result = RunResult()

    for c in companies:
        token = c["board_token"]
        cr = CompanyResult(board_token=token, company=c.get("name", token))
        try:
            postings: list[JobPosting] = fetch_board(token, c.get("name", token))
            cr.fetched = len(postings)

            stored = store.get_postings_for_company(token)
            changes, should_baseline = diff_company(
                token, postings, stored, is_baselined=bool(c.get("baselined"))
            )
            cr.changes = len(changes)

            # Relevance filter. REMOVED changes skip it - if a role was
            # relevant enough to alert on, its disappearance is relevant too,
            # and there is no posting body left to match against anyway.
            to_publish = []
            for ch in changes:
                if ch.change_type == ChangeType.REMOVED:
                    to_publish.append(ch.to_message())
                    continue
                verdict = rel.check(ch.posting)
                if verdict.passed:
                    msg = ch.to_message()
                    msg["filter_reason"] = verdict.reason
                    to_publish.append(msg)
                else:
                    cr.filtered_out += 1

            # Preserve prior versions BEFORE the upsert overwrites them.
            # The agent runs asynchronously, so without this it would read the
            # already-updated record and conclude nothing changed.
            for ch in changes:
                if ch.change_type == ChangeType.MODIFIED and ch.previous:
                    store.save_history(ch.doc_id, ch.previous)

            cr.published = publish_changes(to_publish)

            # Persist only after publishing succeeded.
            store.upsert_postings(postings)
            removed_ids = [
                ch.doc_id for ch in changes if ch.change_type == ChangeType.REMOVED
            ]
            if removed_ids:
                store.delete_postings(removed_ids)

            if should_baseline:
                store.mark_baselined(token)
                cr.baselined_now = True

        except Exception as e:  # noqa: BLE001 - one company must not kill the run
            log.exception("collection failed for %s", token)
            cr.error = f"{type(e).__name__}: {e}"

        result.companies.append(cr)

    log.info("collection complete: %s", result.totals)
    return result
