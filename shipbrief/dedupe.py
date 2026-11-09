"""Deduplicate and cluster items (spec step 3).

1. Exact duplicates: same canonical URL -> merge.
2. Same story from several sources: title-token Jaccard similarity >= TITLE_SIM within
   CLUSTER_WINDOW_HOURS -> cluster. GitHub releases are never title-clustered (versions differ).

The primary item of a cluster is the one from the highest-weight source (official sources
outrank aggregators); ties go to the earliest publication. Others become `related` links.
HN points/discussion links are carried onto the primary.
"""
from __future__ import annotations

from dataclasses import dataclass

from .models import Item
from .text import title_tokens

TITLE_SIM = 0.6
MIN_TOKENS = 3
CLUSTER_WINDOW_HOURS = 72


@dataclass
class DedupeStats:
    exact_duplicates: int = 0
    clustered: int = 0


def jaccard(a: frozenset[str], b: frozenset[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def _rank_key(it: Item):
    # Official/high-weight first; HN-only items lose to the article's own source.
    return (-it.source_weight if it.source_id != "hn" else 0.0, it.published_at)


def _merge(primary: Item, other: Item) -> None:
    if other.extra.get("hnScore") and not primary.extra.get("hnScore"):
        primary.extra["hnScore"] = other.extra["hnScore"]
        primary.extra["discussionUrl"] = other.extra.get("discussionUrl")
    elif other.extra.get("hnScore"):
        primary.extra["hnScore"] = max(primary.extra["hnScore"], other.extra["hnScore"])
    for t in other.tags:
        if t not in primary.tags and len(primary.tags) < 8:
            primary.tags.append(t)
    for r in other.roles:
        if r not in primary.roles and len(primary.roles) < 6:
            primary.roles.append(r)
    if other.url != primary.url and all(r["url"] != other.url for r in primary.related):
        primary.related.append({"source": other.source, "url": other.url, "title": other.title})
    for r in other.related:
        if r["url"] != primary.url and all(x["url"] != r["url"] for x in primary.related):
            primary.related.append(r)
    primary.relevance = max(primary.relevance, other.relevance)


def dedupe(items: list[Item]) -> tuple[list[Item], DedupeStats]:
    stats = DedupeStats()
    # Pass 1: canonical URL
    by_url: dict[str, list[Item]] = {}
    for it in items:
        by_url.setdefault(it.canonical_url, []).append(it)
    merged: list[Item] = []
    for group in by_url.values():
        group.sort(key=_rank_key)
        primary = group[0]
        for other in group[1:]:
            _merge(primary, other)
            # same URL from a different source still counts as coverage, but not as a related *link*
            primary.related = [r for r in primary.related if r["url"] != primary.url]
            if other.source != primary.source:
                primary.extra.setdefault("alsoIn", []).append(other.source)
        stats.exact_duplicates += len(group) - 1
        merged.append(primary)

    # Pass 2: title similarity clustering (greedy, deterministic order)
    merged.sort(key=_rank_key)
    tokens = {id(it): title_tokens(it.title) for it in merged}
    out: list[Item] = []
    for it in merged:
        tk = tokens[id(it)]
        target = None
        if it.kind != "release" and len(tk) >= MIN_TOKENS:
            for p in out:
                if p.kind == "release":
                    continue
                if abs((p.published_at - it.published_at).total_seconds()) > CLUSTER_WINDOW_HOURS * 3600:
                    continue
                if jaccard(tk, tokens[id(p)]) >= TITLE_SIM:
                    target = p
                    break
        if target is None:
            out.append(it)
        else:
            _merge(target, it)
            stats.clustered += 1
    for it in out:
        it.related = it.related[:6]
    return out, stats
