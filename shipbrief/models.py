"""Internal item model (normalized schema)."""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


def item_id(canonical: str) -> str:
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]


@dataclass
class Item:
    # --- normalized schema (spec step 2) ---
    id: str
    title: str
    url: str                      # display URL, exactly as fetched
    source: str                   # display name
    published_at: datetime        # from the feed, UTC
    raw_summary: str              # cleaned (HTML-stripped) feed text; never published verbatim beyond 1-2 sentences
    tags: list[str]
    kind: str                     # news | release | paper | tool | discussion
    # --- bookkeeping ---
    source_id: str = ""
    canonical_url: str = ""
    source_weight: float = 1.0
    roles: list[str] = field(default_factory=list)
    extra: dict[str, Any] = field(default_factory=dict)   # hnScore, discussionUrl, version, comments, repo
    related: list[dict[str, str]] = field(default_factory=list)
    relevance: float = 0.0
    require_ai: bool = False      # general-purpose source: must pass the AI-relevance filter
    score: float = 0.0
    score_parts: dict[str, float] = field(default_factory=dict)
    # --- summarization output ---
    summary: str = ""
    generated_by: str = ""
    what_it_does: str = ""
    who_its_for: str = ""

    @property
    def source_text(self) -> str:
        """All text the summarizer may rely on (used by fact checks)."""
        return f"{self.title}\n{self.raw_summary}"

    def provenance_key(self) -> tuple[str, str]:
        return (self.url, self.published_at.isoformat())
