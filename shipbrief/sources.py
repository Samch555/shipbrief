"""Load and validate sources.yaml."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from . import config

VALID_TYPES = {"rss", "github_releases", "hn", "arxiv"}
VALID_KINDS = {"news", "release", "paper", "tool", "discussion"}
DEFAULT_KIND = {"rss": "news", "github_releases": "release", "hn": "discussion", "arxiv": "paper"}


@dataclass(frozen=True)
class Source:
    id: str
    name: str
    type: str
    url: str
    weight: float = 1.0
    tags: tuple[str, ...] = ()
    kind: str = "news"
    roles: tuple[str, ...] = ("everyone",)
    max_items: int = config.MAX_ITEMS_PER_SOURCE
    min_score: int = 0
    repo: str | None = None
    enabled: bool = True
    extra: dict[str, Any] = field(default_factory=dict, compare=False, hash=False)


class SourceConfigError(ValueError):
    pass


def _build(raw: dict[str, Any], defaults: dict[str, Any]) -> Source:
    merged = {**defaults, **raw}
    sid = merged.get("id")
    if not sid or not isinstance(sid, str):
        raise SourceConfigError(f"source without id: {raw}")
    stype = merged.get("type")
    if stype not in VALID_TYPES:
        raise SourceConfigError(f"{sid}: unknown type {stype!r}")
    repo = merged.get("repo")
    url = merged.get("url")
    if stype == "github_releases":
        if not repo or "/" not in repo:
            raise SourceConfigError(f"{sid}: github_releases needs repo: owner/name")
        url = url or f"https://github.com/{repo}/releases.atom"
    if not url or not str(url).startswith(("http://", "https://")):
        raise SourceConfigError(f"{sid}: missing or non-http url")
    kind = merged.get("kind") or DEFAULT_KIND[stype]
    if kind not in VALID_KINDS:
        raise SourceConfigError(f"{sid}: bad kind {kind!r}")
    roles = tuple(merged.get("roles") or ("everyone",))
    for r in roles:
        if r not in config.ROLES:
            raise SourceConfigError(f"{sid}: bad role {r!r}")
    weight = float(merged.get("weight", 1.0))
    if not 0.1 <= weight <= 2.0:
        raise SourceConfigError(f"{sid}: weight must be in [0.1, 2.0]")
    return Source(
        id=sid,
        name=str(merged.get("name") or sid),
        type=stype,
        url=str(url),
        weight=weight,
        tags=tuple(merged.get("tags") or ()),
        kind=kind,
        roles=roles,
        max_items=int(merged.get("maxItems", config.MAX_ITEMS_PER_SOURCE)),
        min_score=int(merged.get("minScore", 0)),
        repo=repo,
        enabled=bool(merged.get("enabled", True)),
    )


def load_sources(path: Path | str = config.DEFAULT_SOURCES, include_disabled: bool = False) -> list[Source]:
    doc = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    defaults = doc.get("defaults") or {}
    out: list[Source] = []
    seen: set[str] = set()
    for raw in doc.get("sources") or []:
        s = _build(raw, defaults)
        if s.id in seen:
            raise SourceConfigError(f"duplicate source id {s.id}")
        seen.add(s.id)
        if s.enabled or include_disabled:
            out.append(s)
    return out
