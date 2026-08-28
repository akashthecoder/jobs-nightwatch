"""Normalized job posting shape, shared by the collector, diff engine and agent.

One vendor-neutral shape so the rest of the system never knows or cares which
ATS a posting came from. Only Greenhouse is implemented today; adding Lever or
Ashby means writing another adapter that emits this same dataclass.
"""
from __future__ import annotations

import hashlib
import html
import re
from dataclasses import asdict, dataclass, field
from typing import Any

# Fields that define "did this posting meaningfully change".
# Deliberately EXCLUDES updated_at: an ATS can touch that timestamp without the
# posting changing at all, which would fire a false "modified" on every run.
# Deliberately EXCLUDES url: a canonical-URL change is not a content change.
HASHED_FIELDS = ("title", "location", "department", "description_text")

_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")


def clean_html(raw: str | None) -> str:
    """Turn an ATS's HTML-escaped description into plain text.

    Greenhouse returns the description HTML-entity-escaped, so the raw value
    looks like '&lt;div class=&quot;...&quot;&gt;'. It must be unescaped BEFORE
    tags are stripped, or the stripper sees no tags to remove and leaves markup
    in the text handed to the model.
    """
    if not raw:
        return ""
    return _WS_RE.sub(" ", _TAG_RE.sub(" ", html.unescape(raw))).strip()


@dataclass
class JobPosting:
    """One job posting, normalized across ATS vendors."""

    company: str
    board_token: str
    external_id: str
    title: str
    location: str
    department: str
    url: str
    description_text: str
    updated_at: str
    source_ats: str = "greenhouse"
    content_hash: str = field(default="")

    def __post_init__(self) -> None:
        if not self.content_hash:
            self.content_hash = self.compute_hash()

    def compute_hash(self) -> str:
        """Stable hash over the content-bearing fields only."""
        joined = "\x1f".join(str(getattr(self, f) or "") for f in HASHED_FIELDS)
        return hashlib.sha256(joined.encode("utf-8")).hexdigest()

    @property
    def doc_id(self) -> str:
        """Firestore document id.

        Keyed by (board_token, external_id) so the diff engine can fetch a
        posting's previous state with a direct get-by-id -- no query, and
        therefore no composite index to define or maintain.
        """
        return f"{self.board_token}_{self.external_id}"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> JobPosting:
        known = {k: v for k, v in d.items() if k in cls.__dataclass_fields__}
        return cls(**known)
