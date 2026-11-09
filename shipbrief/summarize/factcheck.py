"""Deterministic fact-check guards. These never call a model.

1. Provenance (all modes): every published item's url and publishedAt must exactly match a
   record fetched in this run. Anything else is rejected.
2. Grounding (model-written text): a summary may not contain numbers, versions, percentages,
   or URLs that do not appear in that item's own source text, nor instruction-like text.
3. Shape: length / sentence / word limits.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Iterable

from .. import config
from ..fetch.runner import SourceResult
from .safety import looks_like_injection

_NUM = re.compile(r"(?<![\w.])v?\d+(?:[.,]\d+)*(?:%|x|k|m|b)?(?![\w])", re.I)
_URL = re.compile(r"https?://|www\.", re.I)
_SMALL_WORDS_OK = {"1", "2", "3", "one", "two"}


@dataclass
class FactCheckReport:
    provenance_rejected: list[str] = field(default_factory=list)
    summaries_rejected: list[dict[str, str]] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {"provenanceRejected": len(self.provenance_rejected),
                "summariesRejected": len(self.summaries_rejected),
                "summaryRejections": self.summaries_rejected[:20]}


def fetched_records(results: Iterable[SourceResult]) -> set[tuple[str, str]]:
    recs = set()
    for r in results:
        for e in r.entries:
            pub = e.get("publishedAt")
            if isinstance(pub, datetime) and e.get("url"):
                recs.add((e["url"].strip(), pub.isoformat()))
    return recs


def check_provenance(url: str, published_iso: str, records: set[tuple[str, str]]) -> bool:
    return (url, published_iso) in records


def _norm_num(tok: str) -> str:
    return tok.lower().lstrip("v").replace(",", "")


def ungrounded_numbers(text: str, source_text: str) -> list[str]:
    src = {_norm_num(t) for t in _NUM.findall(source_text)}
    out = []
    for t in _NUM.findall(text):
        n = _norm_num(t)
        if n in src or n in _SMALL_WORDS_OK:
            continue
        # allow "40%" when source has "40 percent" / "40"
        if n.rstrip("%xkmb") in src:
            continue
        out.append(t)
    return out


def check_summary(summary: str, source_text: str) -> str | None:
    """Return a rejection reason, or None if the model-written summary passes."""
    s = summary.strip()
    if not s:
        return "empty"
    if len(s) > config.SUMMARY_MAX_CHARS + 40:
        return "too-long"
    if len(re.findall(r"[.!?](\s|$)", s)) > 3:
        return "too-many-sentences"
    if _URL.search(s):
        return "contains-url"
    if looks_like_injection(s):
        return "instruction-like"
    bad = ungrounded_numbers(s, source_text)
    if bad:
        return f"ungrounded-numbers:{','.join(bad[:3])}"
    if s.count('"') >= 2 and re.search(r'"[^"]{60,}"', s):
        return "long-quote"
    return None


def check_generated_text(text: str, max_words: int | None = None) -> str | None:
    """For prompt-of-the-day / workflow text: no URLs, no injection, no version/benchmark claims."""
    if _URL.search(text):
        return "contains-url"
    if looks_like_injection(text):
        return "instruction-like"
    if re.search(r"\d+\.\d+|\d+\s?%", text):
        return "numeric-claim"
    if max_words and len(text.split()) > max_words:
        return "too-many-words"
    return None
