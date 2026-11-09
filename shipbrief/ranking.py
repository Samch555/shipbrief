"""Transparent ranking (spec step 5). THE ranking formula lives here and only here.

    score =  W_RECENCY  * recency          recency   = exp(-age_hours / RECENCY_HALF_LIFE_H * ln2)  in (0, 1]
           + W_SOURCE   * source_weight    0.1 .. 2.0 from sources.yaml
           + W_HN       * hn               hn        = log10(1 + points) / 3   (100 pts -> 0.67, 1000 -> 1.0)
           + W_RELEASE  * release_sig      release_sig: major 1.0, minor 0.6, patch 0.2, pre-release 0.0
           + W_COVERAGE * coverage         coverage  = min(#other sources covering the story, 3)
           + W_RELEVANCE* relevance        relevance = min(AI keyword score, 3) / 3
           + KIND_ADJ[kind]                small nudge; papers/releases have their own sections

Source diversity is applied at *selection* time (`select_diverse`): each extra item from a
source already picked for a section pays DIVERSITY_PENALTY, and a source may not exceed
MAX_PER_SOURCE items in one section. Hacker News items are keyed by the linked site
(`diversity_key`), since HN aggregates many publishers, but at most MAX_HN_PER_SECTION
HN items may appear in one section.

Each item keeps its `score_parts` so you can see why it ranked where it did
(`python -m shipbrief explain` prints them).
"""
from __future__ import annotations

import math
import re
from datetime import datetime
from urllib.parse import urlsplit

from .models import Item

W_RECENCY = 4.0
W_SOURCE = 3.0
W_HN = 2.5
W_RELEASE = 1.5
W_COVERAGE = 1.2
W_RELEVANCE = 1.0
RECENCY_HALF_LIFE_H = 24.0
KIND_ADJ = {"news": 0.0, "tool": 0.0, "discussion": -0.3, "release": -0.8, "paper": -1.2}
DIVERSITY_PENALTY = 1.5
MAX_PER_SOURCE = 2
MAX_HN_PER_SECTION = 3     # HN is one aggregator even though it links many sites

_SEMVER = re.compile(r"(\d+)\.(\d+)(?:\.(\d+))?")
_PRE = re.compile(r"(?<![a-z])(rc|alpha|beta|dev|nightly|preview|pre|canary|bleeding|snapshot)(?![a-z])|\d(a|b)\d+$", re.I)


def release_significance(version: str) -> float:
    if not version:
        return 0.0
    if _PRE.search(version):
        return 0.0
    m = _SEMVER.search(version)
    if not m:
        return 0.3
    major, minor, patch = int(m.group(1)), int(m.group(2)), int(m.group(3) or 0)
    if minor == 0 and patch == 0:
        return 1.0
    if patch == 0:
        return 0.6
    return 0.2


def score_item(it: Item, now: datetime) -> float:
    age_h = max(0.0, (now - it.published_at).total_seconds() / 3600)
    recency = math.exp(-age_h / RECENCY_HALF_LIFE_H * math.log(2))
    hn_pts = int(it.extra.get("hnScore") or 0)
    hn = min(math.log10(1 + hn_pts) / 3, 1.2)
    rel_sig = release_significance(it.extra.get("version", "")) if it.kind == "release" else 0.0
    coverage = min(len(it.related) + len(it.extra.get("alsoIn", [])), 3)
    relevance = min(it.relevance, 3.0) / 3.0
    parts = {
        "recency": W_RECENCY * recency,
        "source": W_SOURCE * it.source_weight,
        "hn": W_HN * hn,
        "release": W_RELEASE * rel_sig,
        "coverage": W_COVERAGE * coverage,
        "relevance": W_RELEVANCE * relevance,
        "kind": KIND_ADJ.get(it.kind, 0.0),
    }
    it.score_parts = {k: round(v, 3) for k, v in parts.items()}
    it.score = round(sum(parts.values()), 3)
    return it.score


def rank(items: list[Item], now: datetime) -> list[Item]:
    for it in items:
        score_item(it, now)
    # Deterministic tie-break: score desc, then newer first, then id.
    return sorted(items, key=lambda i: (-i.score, -i.published_at.timestamp(), i.id))


def diversity_key(it: Item) -> str:
    """Aggregators (Hacker News) are diversified by the linked site, not by 'hn'."""
    if it.source_id == "hn":
        host = urlsplit(it.url).netloc.lower().removeprefix("www.")
        return f"hn:{host}"
    return it.source_id


def select_diverse(ranked: list[Item], n: int, exclude: set[str] | None = None,
                   max_per_source: int = MAX_PER_SOURCE) -> list[Item]:
    """Greedy pick of n items with a per-source penalty and cap."""
    exclude = exclude or set()
    pool = [i for i in ranked if i.id not in exclude]
    order = {i.id: n for n, i in enumerate(ranked)}
    picked: list[Item] = []
    counts: dict[str, int] = {}
    while pool and len(picked) < n:
        best = max(pool, key=lambda i: (i.score - DIVERSITY_PENALTY * counts.get(diversity_key(i), 0), -order[i.id]))
        pool.remove(best)
        k = diversity_key(best)
        if counts.get(k, 0) >= max_per_source:
            continue
        if best.source_id == "hn" and counts.get("hn:*", 0) >= MAX_HN_PER_SECTION:
            continue
        counts[k] = counts.get(k, 0) + 1
        if best.source_id == "hn":
            counts["hn:*"] = counts.get("hn:*", 0) + 1
        picked.append(best)
    return picked
