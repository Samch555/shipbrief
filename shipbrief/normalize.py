"""Raw entries -> Items (spec steps 2 and 4: normalize + AI-relevance filter)."""
from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from urllib.parse import unquote

from . import classify, config
from .fetch.runner import SourceResult
from .models import Item, item_id
from .ranking import release_significance
from .sources import Source
from .text import canonical_url, clean_text, truncate

# Sources whose items must contain AI keywords to be kept (general-purpose feeds).
MIN_RELEVANCE = 0.9
# Sources that are AI-specific by construction; relevance filter is skipped.
AI_NATIVE_TYPES = {"github_releases", "arxiv"}
AI_NATIVE_SOURCES = {"openai-news", "google-deepmind", "google-ai", "huggingface-blog", "github-blog-ai",
                     "cloudflare-ai", "mit-news-ai", "apple-ml", "aws-ml", "langchain-blog", "ollama-blog",
                     "mistral-news", "bair-blog"}

_PRERELEASE = re.compile(r"(?<![a-z])(rc|alpha|beta|dev|nightly|preview|pre|canary|bleeding|snapshot)(?![a-z])|\d(a|b)\d+$", re.I)
_SEMVER = re.compile(r"\d+\.\d+")


def is_stable_release(version: str) -> bool:
    """A publishable release: has an X.Y version and is not a pre-release/nightly/build tag."""
    return bool(version) and bool(_SEMVER.search(version)) and not _PRERELEASE.search(version) \
        and not version.lower().startswith(("trunk/", "viable/", "nightly", "latest"))


@dataclass
class NormalizeStats:
    kept: int = 0
    dropped: Counter = field(default_factory=Counter)


def normalize(results: list[SourceResult], now: datetime) -> tuple[list[Item], NormalizeStats]:
    stats = NormalizeStats()
    items: list[Item] = []
    oldest = now - timedelta(hours=config.MAX_ITEM_AGE_HOURS)
    newest = now + timedelta(hours=config.FUTURE_SKEW_HOURS)
    for res in results:
        src: Source = res.source
        per_source: list[Item] = []
        for e in res.entries:
            title = truncate(clean_text(e.get("title", "")), 280)
            url = (e.get("url") or "").strip()
            pub = e.get("publishedAt")
            if not title:
                stats.dropped["no-title"] += 1
                continue
            if not url.startswith(("http://", "https://")):
                stats.dropped["no-url"] += 1
                continue
            if pub is None:
                stats.dropped["no-date"] += 1
                continue
            if pub < oldest:
                stats.dropped["too-old"] += 1
                continue
            if pub > newest:
                stats.dropped["future-date"] += 1
                continue
            extra = dict(e.get("extra") or {})
            if src.type == "github_releases":
                v = unquote(extra.get("version", ""))
                extra["version"] = v
                if not is_stable_release(v):
                    stats.dropped["prerelease-or-build"] += 1
                    continue
            canon = canonical_url(url)
            it = Item(
                id=item_id(canon), title=title, url=url, source=src.name,
                published_at=pub, raw_summary=truncate(clean_text(e.get("summaryHtml", "")), 1500),
                tags=[], kind=src.kind, source_id=src.id, canonical_url=canon,
                source_weight=src.weight, extra=extra,
            )
            it.kind = classify.infer_kind(it, src.kind, src.type)
            it.relevance = classify.ai_relevance(f"{it.title} {it.raw_summary[:600]}")
            it.require_ai = not (src.type in AI_NATIVE_TYPES or src.id in AI_NATIVE_SOURCES)
            it.tags = classify.infer_tags(it, src.tags)
            it.roles = classify.infer_roles(it, src.roles)
            per_source.append(it)
        per_source.sort(key=lambda i: i.published_at, reverse=True)
        if src.type == "github_releases" and per_source:
            # Monorepos ship many packages a day: keep one release per repo per run,
            # the most significant (major > minor > patch), newest first on ties.
            per_source.sort(key=lambda i: (release_significance(i.extra["version"]), i.published_at), reverse=True)
            per_source = per_source[:1]
        dropped_cap = max(0, len(per_source) - src.max_items)
        stats.dropped["source-cap"] += dropped_cap
        items.extend(per_source[: src.max_items])
    stats.kept = len(items)
    return items, stats


def filter_relevance(items: list[Item], stats: NormalizeStats | None = None) -> list[Item]:
    """Spec step 4. Runs after dedupe, so an HN post about an official lab announcement
    survives by merging into the lab's item even if its own title lacks AI keywords."""
    out = []
    for it in items:
        if it.require_ai and it.relevance < MIN_RELEVANCE:
            if stats is not None:
                stats.dropped["not-ai"] += 1
            continue
        out.append(it)
    return out
