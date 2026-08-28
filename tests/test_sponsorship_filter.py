"""Validate the sponsorship-exclusion regexes.

False positives here are dangerous and SILENT: a wrongly-excluded posting
never reaches the agent and never appears on the dashboard, so the failure
is invisible. Test the positive AND negative cases.
"""
import json
import re

profile = json.load(open("/Users/aakash/Documents/Aakash/Python/adk-projects/Hackathon/config/profile.json"))
pats = [re.compile(p, re.I) for p in profile["work_authorization"]["exclude_if_posting_matches"]]

SHOULD_BLOCK = [
    "We are not able to sponsor visas at this time.",
    "Unable to sponsor or transfer visas for this position.",
    "The company will not sponsor applicants for work visas.",
    "We do not offer visa sponsorship for this role.",
    "No visa sponsorship is available for this position.",
    "Applicants must be authorized to work in the U.S. without sponsorship.",
    "Candidates must be legally authorized to work in the United States without sponsorship now or in the future.",
    "You will not be eligible for visa sponsorship.",
    "Must be a US citizen to be considered.",
    "U.S. citizenship is required for this role.",
    "Requires an active security clearance.",
    "Must have the ability to obtain a TS/SCI security clearance.",
]

SHOULD_NOT_BLOCK = [
    "We sponsor visas for qualified candidates.",
    "Visa sponsorship is available for this role.",
    "We are happy to sponsor H-1B and green card applications.",
    "We provide immigration sponsorship and relocation support.",
    "This role is open to candidates requiring sponsorship.",
    "We are an equal opportunity employer.",
    "You will sponsor internal initiatives across the data org.",
    "The team sponsors an annual hackathon.",
    "Partner with executive sponsors to align on roadmap.",
    "Build models to detect fraud and abuse.",
    "Work authorization: we support sponsorship where needed.",
    # REGRESSION (2026-08-28): real Cloudflare boilerplate. This is EXPORT
    # LICENCE sponsorship, not visa sponsorship. An unanchored
    # "without ... sponsorship" pattern matched it and silently dropped all
    # 313 Cloudflare postings. No synthetic test case would have contained
    # export-control language - only real data surfaced this.
    "Please note that any offer of employment may be conditioned on your "
    "authorization to receive software or technology controlled under these "
    "U.S. export laws without sponsorship for an export license.",
]


def blocked(text):
    for p in pats:
        if p.search(text):
            return p.pattern
    return None


fails = 0
print("=== SHOULD BLOCK ===")
for t in SHOULD_BLOCK:
    hit = blocked(t)
    ok = hit is not None
    fails += 0 if ok else 1
    print(f"  {'OK ' if ok else 'MISS'}  {t[:70]}")

print("\n=== SHOULD NOT BLOCK (false positives) ===")
for t in SHOULD_NOT_BLOCK:
    hit = blocked(t)
    ok = hit is None
    fails += 0 if ok else 1
    flag = "OK " if ok else "FALSE+"
    print(f"  {flag}  {t[:62]}")
    if hit:
        print(f"          ^ matched: {hit}")

print(f"\n{'ALL PASS' if fails == 0 else str(fails) + ' FAILURES'}")
