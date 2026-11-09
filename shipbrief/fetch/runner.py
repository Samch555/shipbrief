"""Fetch all sources concurrently. One failing source never breaks the run."""
from __future__ import annotations

import logging
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Protocol
from urllib.parse import urlencode

from .. import http
from ..sources import Source
from . import parsers

log = logging.getLogger(__name__)


class Transport(Protocol):
    def __call__(self, source: Source, url: str) -> bytes: ...


def live_transport(source: Source, url: str) -> bytes:
    return http.get(url)


class FixtureTransport:
    """Serves saved responses from a directory: <dir>/<source.id>.(xml|json)."""

    def __init__(self, directory: Path):
        self.directory = Path(directory)

    def __call__(self, source: Source, url: str) -> bytes:
        for ext in (".xml", ".json"):
            p = self.directory / f"{source.id}{ext}"
            if p.exists():
                return p.read_bytes()
        raise http.FetchError(f"no fixture for {source.id}")


@dataclass
class SourceResult:
    source: Source
    entries: list[dict[str, Any]] = field(default_factory=list)
    ok: bool = True
    error: str | None = None
    seconds: float = 0.0


def request_url(source: Source, now: datetime) -> str:
    if source.type == "hn":
        since = int(now.timestamp()) - 36 * 3600
        params = {
            "tags": "story",
            "numericFilters": f"created_at_i>{since},points>={source.min_score}",
            "hitsPerPage": "300",
        }
        return f"{source.url}?{urlencode(params)}"
    return source.url


def parse_for(source: Source, data: bytes) -> list[dict[str, Any]]:
    if source.type == "hn":
        return parsers.parse_hn_algolia(data, source.min_score)
    if source.type == "arxiv":
        return parsers.parse_arxiv(data)
    if source.type == "github_releases":
        return parsers.parse_github_releases(data, source.repo or "")
    return parsers.parse_feed(data)


def fetch_one(source: Source, transport: Transport, now: datetime) -> SourceResult:
    t0 = time.monotonic()
    res = SourceResult(source=source)
    try:
        data = transport(source, request_url(source, now))
        res.entries = parse_for(source, data)
    except Exception as e:  # isolate every failure
        res.ok = False
        res.error = f"{type(e).__name__}: {str(e)[:200]}"
        log.warning("source %s failed: %s", source.id, res.error)
    res.seconds = round(time.monotonic() - t0, 3)
    return res


def fetch_all(sources: list[Source], transport: Transport, now: datetime,
              workers: int = 8, progress: Callable[[SourceResult], None] | None = None) -> list[SourceResult]:
    results: list[SourceResult] = []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        for r in pool.map(lambda s: fetch_one(s, transport, now), sources):
            results.append(r)
            if progress:
                progress(r)
    return results
