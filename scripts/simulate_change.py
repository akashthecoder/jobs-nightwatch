"""Simulate posting changes by mutating stored Firestore state.

Job postings rarely change organically within a few days, and the first run of
any company is baselined and emits nothing. Without this, there is no way to
exercise the modified/removed paths - or to record a demo.

This mutates STORED state (what we think we saw last time), not the live board.
The next collection then sees the real board differ from the doctored history
and reports changes, which is exactly the real code path.
"""
import argparse
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")

from common import store  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(message)s")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--board", default="sofi")
    ap.add_argument("--modify", type=int, default=1, help="postings to alter")
    ap.add_argument("--remove", type=int, default=1, help="stored docs to delete "
                                                          "(makes them look NEW next run)")
    ap.add_argument("--vanish", type=int, default=1, help="postings to mark as if "
                                                          "still listed but gone from the board")
    args = ap.parse_args()

    stored = store.get_postings_for_company(args.board)
    if not stored:
        print(f"No stored postings for {args.board}. Run a collection first.")
        return

    doc_ids = sorted(stored.keys())
    print(f"{args.board}: {len(doc_ids)} stored postings\n")
    db = store.db()

    # 1. MODIFIED: rewrite the stored description so the live board now differs.
    for doc_id in doc_ids[: args.modify]:
        d = stored[doc_id]
        db.collection(store.POSTINGS).document(doc_id).update(
            {
                "description_text": "[SIMULATED OLD VERSION] " + (d.get("description_text") or "")[:400],
                "content_hash": "simulated_stale_hash_" + doc_id,
            }
        )
        print(f"  MODIFIED  {d.get('title','')[:56]}")

    # 2. NEW: delete stored state so the live posting looks newly appeared.
    for doc_id in doc_ids[args.modify: args.modify + args.remove]:
        d = stored[doc_id]
        db.collection(store.POSTINGS).document(doc_id).delete()
        print(f"  -> NEW    {d.get('title','')[:56]}  (stored copy deleted)")

    # 3. REMOVED: invent a stored posting with an id the live board will never
    #    return, so the next run sees it disappear.
    ghost_id = f"{args.board}_999999999"
    for _ in range(min(args.vanish, 1)):
        db.collection(store.POSTINGS).document(ghost_id).set(
            {
                "company": stored[doc_ids[0]].get("company", ""),
                "board_token": args.board,
                "external_id": "999999999",
                "title": "[SIMULATED] Staff Data Scientist, Retired Role",
                "location": "Remote",
                "department": "Data",
                "url": "https://example.com/retired",
                "description_text": "This posting no longer exists on the live board.",
                "updated_at": "2026-08-01T00:00:00Z",
                "source_ats": "greenhouse",
                "content_hash": "ghost",
            }
        )
        print(f"  -> REMOVED  ghost posting written as {ghost_id}")

    print("\nNow run a collection to see the changes detected.")


if __name__ == "__main__":
    main()
