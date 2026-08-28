"""Seed Firestore from config files. Idempotent - safe to re-run.

Company `enabled` / `baselined` flags are runtime state owned by Firestore,
so re-seeding never resets a company the dashboard just toggled off.
"""
import json
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
    companies = json.loads((ROOT / "config/companies.json").read_text())["companies"]
    profile = json.loads((ROOT / "config/profile.json").read_text())

    new = store.seed_companies(companies)
    print(f"companies: {len(companies)} seeded ({new} newly created)")

    store.put_profile(profile, profile.get("profile_id", "default"))
    print(f"profile:   {profile.get('name')} -> profiles/{profile.get('profile_id')}")

    print("\ncurrent company state:")
    for c in store.list_companies():
        print(f"  {c['board_token']:12} enabled={str(c.get('enabled')):5} "
              f"baselined={str(c.get('baselined')):5}  {c.get('name')}")


if __name__ == "__main__":
    main()
