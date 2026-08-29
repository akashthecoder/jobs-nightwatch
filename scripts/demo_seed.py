"""Set up a reproducible demo scenario.

Job postings rarely change organically within the span of a recording, and a
company's first collection is baselined to silence by design. This seeds four
changes that together tell the whole story:

  1. MODIFIED - a tracked role quietly upleveled (the headline feature)
  2. NEW      - a strong-fit role appears
  3. REMOVED  - a role disappears from the board
  4. NEW      - a role that is NOT a fit, to show the agent says so honestly

It mutates STORED state, not the live board, so the next collection runs the
real production code path: real HTTP fetch, real diff, real filter, real
publish, real agent.

Usage:
    python scripts/demo_seed.py          # set up
    python scripts/demo_seed.py --reset  # clear decisions and start over
"""
import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")

from collector.greenhouse import fetch_board  # noqa: E402
from common import store  # noqa: E402
from common.relevance import RelevanceFilter  # noqa: E402

BOARD = "reddit"
COMPANY = "Reddit"


def clear_demo_state():
    """Remove decisions and history so the demo can be re-run cleanly."""
    db = store.db()
    n = 0
    for coll in (store.DECISIONS, store.HISTORY):
        for doc in db.collection(coll).stream():
            doc.reference.delete()
            n += 1
    print(f"  cleared {n} decision/history documents")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--reset", action="store_true", help="clear decisions first")
    args = ap.parse_args()

    print("Jobs NightWatch - demo seed\n")

    if args.reset:
        print("Resetting demo state...")
        clear_demo_state()
        print()

    profile = store.get_profile("default") or {}
    rel = RelevanceFilter(profile)

    print(f"Fetching live {COMPANY} board...")
    postings = fetch_board(BOARD, COMPANY)
    print(f"  {len(postings)} postings\n")

    # Establish a baseline so the diff has something to compare against.
    store.upsert_postings(postings)
    store.mark_baselined(BOARD)

    relevant = [p for p in postings if rel.check(p).passed]
    ds_roles = [p for p in relevant if "data scientist" in p.title.lower()]
    ml_roles = [p for p in relevant if "machine learning" in p.title.lower()]
    irrelevant = [p for p in postings if not rel.check(p).passed]

    if len(ds_roles) < 2:
        print("Not enough Data Scientist roles on the board to seed the demo.")
        return

    db = store.db()

    # ---------------------------------------------------------------- 1. MODIFIED
    # The headline scenario: a role you are tracking is quietly upleveled.
    target = ds_roles[0]
    prev = target.to_dict()
    prev["title"] = (
        target.title.replace("Principal ", "").replace("Staff ", "").replace("Senior ", "")
    )
    prev["description_text"] = (
        target.description_text.replace("Principal", "")
        .replace("12+ years", "5+ years")
        .replace("8+ years", "4+ years")[:3500]
    )
    prev["content_hash"] = "demo_stale_modified"
    db.collection(store.POSTINGS).document(target.doc_id).set(prev)
    print("1. MODIFIED (the headline scenario)")
    print(f"     live  : {target.title}")
    print(f"     stored: {prev['title']}")
    print("     -> agent should report the uplevel and raised experience bar\n")

    # ---------------------------------------------------------------- 2. NEW (fit)
    appearing = ds_roles[1] if len(ds_roles) > 1 else ml_roles[0]
    db.collection(store.POSTINGS).document(appearing.doc_id).delete()
    print("2. NEW - strong fit")
    print(f"     {appearing.title}")
    print("     -> stored copy deleted, so it looks newly posted\n")

    # ---------------------------------------------------------------- 3. REMOVED
    ghost_id = f"{BOARD}_900000001"
    db.collection(store.POSTINGS).document(ghost_id).set(
        {
            "company": COMPANY,
            "board_token": BOARD,
            "external_id": "900000001",
            "title": "Senior Data Scientist, Growth Analytics",
            "location": "Remote - United States",
            "department": "Data Science",
            "url": "https://job-boards.greenhouse.io/reddit",
            "description_text": (
                "Reddit is looking for a Senior Data Scientist on the Growth Analytics "
                "team to drive experimentation, causal inference and marketing "
                "attribution across acquisition channels. You will build propensity "
                "models, design A/B tests, and partner with marketing to measure "
                "incrementality."
            ),
            "updated_at": "2026-08-20T00:00:00Z",
            "source_ats": "greenhouse",
            "content_hash": "demo_ghost",
        }
    )
    print("3. REMOVED")
    print("     Senior Data Scientist, Growth Analytics")
    print("     -> exists in stored state only; the live board will not return it\n")

    # ---------------------------------------------------------------- 4. NEW (no fit)
    # Shows the agent declining honestly rather than flattering everything.
    if irrelevant:
        dud = irrelevant[0]
        db.collection(store.POSTINGS).document(dud.doc_id).delete()
        print("4. NEW - deliberately NOT a fit")
        print(f"     {dud.title}")
        print("     -> may be dropped by the pre-filter before reaching the agent\n")

    print("=" * 62)
    print("Seeded. Now trigger a collection:")
    print()
    print('  - click "Run now" on the dashboard, or')
    print("  - curl the collector (see demo.md)")
    print()
    print("Expect ~35s per change for the agent to finish.")
    print("=" * 62)


if __name__ == "__main__":
    main()
