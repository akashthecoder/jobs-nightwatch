"""Deterministic relevance pre-filter. No LLM.

Sits between the diff engine and Pub/Sub. Its ONLY job is to stop obviously
irrelevant postings from costing a Gemini call. It is a cost guard, not the fit
decision -- the agent still makes the real judgement on everything that passes.

Design constraint: bias toward LETTING THINGS THROUGH. A false negative here is
invisible and unrecoverable -- the posting never reaches the agent, never
appears on the dashboard, and nobody ever learns it was dropped. A false
positive merely costs a fraction of a cent.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from common.schema import JobPosting


@dataclass
class FilterResult:
    passed: bool
    reason: str
    matched_titles: list[str]
    matched_skills: list[str]
    # "high"   -> the title itself matched a target title
    # "medium" -> no title match, but a dense cluster of core DS/ML skills
    # ""       -> did not pass
    strength: str = ""
    signals: int = 0

    @property
    def sort_key(self) -> tuple:
        """High before medium, then by how many signals fired."""
        return (0 if self.strength == "high" else 1, -self.signals)


def _compile(patterns: list[str]) -> list[re.Pattern]:
    return [re.compile(p, re.I) for p in patterns]


class RelevanceFilter:
    def __init__(self, profile: dict):
        self.profile = profile

        wa = profile.get("work_authorization", {})
        self.sponsorship_hard_block = bool(wa.get("hard_block"))
        self.sponsorship_patterns = _compile(wa.get("exclude_if_posting_matches", []))

        # Title matching is the primary volume reducer. Match on word-ish
        # boundaries so "Data Scientist" hits "Senior Data Scientist, Growth"
        # without "Scientist" alone matching "Research Scientist, Biology".
        self.title_terms = [t.lower() for t in profile.get("target_titles", [])]
        self.skills = [s.lower() for s in profile.get("skills", [])]

        # Titles that are categorically wrong no matter what the body says.
        self.exclude_titles = [t.lower() for t in profile.get("exclude_titles", [])]

        # Strong DS/ML signals only. The full skills list is useless as a
        # relevance signal because Python/SQL/GCP appear in sales, support and
        # recruiting postings too.
        self.core_skills = [s.lower() for s in profile.get("core_skills", [])]

    # Minimum core-skill hits for a posting with a non-matching title to still
    # be considered relevant. Catches unconventional titles ("Member of
    # Technical Staff", "Quantitative Researcher") without waving through every
    # presales role that happens to name Python.
    CORE_SKILL_THRESHOLD = 4

    def check(self, posting: JobPosting) -> FilterResult:
        title_l = posting.title.lower()
        body_l = posting.description_text.lower()

        # 1. HARD BLOCK: work authorization. A fact, not a judgement, so it is
        #    settled in code rather than by a model.
        if self.sponsorship_hard_block:
            for pat in self.sponsorship_patterns:
                m = pat.search(posting.description_text)
                if m:
                    return FilterResult(
                        False,
                        f"work authorization: {m.group(0)[:80]!r}",
                        [],
                        [],
                    )

        # 2. Title knockout. Categorically wrong roles are rejected regardless
        #    of body content -- a presales posting naming Python, SQL and GCP
        #    is still a presales posting.
        for bad in self.exclude_titles:
            if bad in title_l:
                return FilterResult(False, f"excluded title term {bad!r}", [], [])

        # 3. Title match -- the main volume reducer.
        matched_titles = [t for t in self.title_terms if t in title_l]

        matched_skills = [s for s in self.skills if s in body_l or s in title_l]
        matched_core = [s for s in self.core_skills if s in body_l or s in title_l]

        if matched_titles:
            return FilterResult(
                True,
                f"title matched {matched_titles[0]!r}",
                matched_titles,
                matched_skills,
                strength="high",
                signals=len(matched_core),
            )

        # 4. No title hit, but a dense concentration of CORE skills still
        #    suggests relevance (unconventional titles: "Member of Technical
        #    Staff", "Quantitative Researcher"). Counted over core skills only,
        #    because the full list includes generic terms that carry no signal.
        if len(matched_core) >= self.CORE_SKILL_THRESHOLD:
            return FilterResult(
                True,
                f"{len(matched_core)} core skills matched despite no title match",
                [],
                matched_skills,
                strength="medium",
                signals=len(matched_core),
            )

        return FilterResult(
            False,
            f"no title match; only {len(matched_core)} core skills matched",
            [],
            matched_skills,
        )
