"""Diff engine tests. Pure logic - no network, no Firestore."""
import sys

sys.path.insert(0, "/Users/aakash/Documents/Aakash/Python/adk-projects/Hackathon")

from common.schema import JobPosting
from diff.engine import ChangeType, diff_company


def mk(ext_id, title="Data Scientist", desc="Build models.", loc="Remote"):
    return JobPosting(
        company="TestCo",
        board_token="testco",
        external_id=ext_id,
        title=title,
        location=loc,
        department="Data",
        url=f"https://example.com/{ext_id}",
        description_text=desc,
        updated_at="2026-08-28T00:00:00Z",
    )


def run():
    failures = []

    def check(name, cond):
        print(f"  {'OK  ' if cond else 'FAIL'}  {name}")
        if not cond:
            failures.append(name)

    print("=== baselining ===")
    fetched = [mk("1"), mk("2"), mk("3")]
    changes, mark = diff_company("testco", fetched, {}, is_baselined=False)
    check("first run emits ZERO changes", len(changes) == 0)
    check("first run signals mark-baselined", mark is True)

    print("\n=== new posting ===")
    stored = {p.doc_id: p.to_dict() for p in [mk("1"), mk("2")]}
    changes, mark = diff_company("testco", [mk("1"), mk("2"), mk("3")], stored, True)
    check("one change detected", len(changes) == 1)
    check("classified NEW", changes and changes[0].change_type == ChangeType.NEW)
    check("does not re-mark baselined", mark is False)

    print("\n=== modified: description ===")
    stored = {p.doc_id: p.to_dict() for p in [mk("1", desc="Build models.")]}
    changes, _ = diff_company("testco", [mk("1", desc="Build models. Must know Rust.")], stored, True)
    check("one change", len(changes) == 1)
    check("classified MODIFIED", changes and changes[0].change_type == ChangeType.MODIFIED)
    check("names description_text as changed",
          changes and changes[0].changed_fields == ["description_text"])

    print("\n=== modified: title (the silent rewrite case) ===")
    stored = {p.doc_id: p.to_dict() for p in [mk("1", title="Data Scientist")]}
    changes, _ = diff_company("testco", [mk("1", title="Senior Data Scientist")], stored, True)
    check("title change detected", len(changes) == 1)
    check("names title as changed", changes and changes[0].changed_fields == ["title"])

    print("\n=== removed ===")
    stored = {p.doc_id: p.to_dict() for p in [mk("1"), mk("2")]}
    changes, _ = diff_company("testco", [mk("1")], stored, True)
    check("one change", len(changes) == 1)
    check("classified REMOVED", changes and changes[0].change_type == ChangeType.REMOVED)
    check("REMOVED carries no posting", changes and changes[0].posting is None)
    check("REMOVED carries previous state", changes and changes[0].previous is not None)

    print("\n=== no change ===")
    stored = {p.doc_id: p.to_dict() for p in [mk("1"), mk("2")]}
    changes, _ = diff_company("testco", [mk("1"), mk("2")], stored, True)
    check("identical input yields zero changes", len(changes) == 0)

    print("\n=== updated_at must NOT trigger a change ===")
    old = mk("1")
    new = mk("1")
    new.updated_at = "2099-01-01T00:00:00Z"   # ATS touched the timestamp only
    new.content_hash = new.compute_hash()
    stored = {old.doc_id: old.to_dict()}
    changes, _ = diff_company("testco", [new], stored, True)
    check("timestamp-only change is ignored", len(changes) == 0)

    print("\n=== mixed batch ===")
    stored = {p.doc_id: p.to_dict() for p in [mk("1"), mk("2"), mk("3")]}
    fetched = [mk("1"), mk("2", title="Staff Data Scientist"), mk("4")]
    changes, _ = diff_company("testco", fetched, stored, True)
    kinds = sorted(c.change_type.value for c in changes)
    check("detects modified + new + removed", kinds == ["modified", "new", "removed"])

    print("\n" + "=" * 46)
    print("ALL PASS" if not failures else f"{len(failures)} FAILURES: {failures}")
    return not failures


if __name__ == "__main__":
    raise SystemExit(0 if run() else 1)
