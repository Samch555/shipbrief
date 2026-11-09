"""Parsers turning raw bytes into RawEntry dicts. Pure functions, no network.

RawEntry = {
  "title": str, "url": str, "publishedAt": datetime | None, "summaryHtml": str,
  "extra": dict   # e.g. {"hnScore": 120, "discussionUrl": ..., "version": "v1.2"}
}
"""
from __future__ import annotations

import json
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any


class ParseError(ValueError):
    pass


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1] if "}" in tag else tag


def _child(el: ET.Element, *names: str) -> ET.Element | None:
    for c in el:
        if _local(c.tag) in names:
            return c
    return None


def _text(el: ET.Element | None) -> str:
    if el is None:
        return ""
    # Atom text constructs may be type="xhtml" with child elements.
    if len(el):
        return "".join(el.itertext()).strip()
    return (el.text or "").strip()


def parse_date(value: str) -> datetime | None:
    value = (value or "").strip()
    if not value:
        return None
    dt: datetime | None = None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        try:
            dt = parsedate_to_datetime(value)
        except (TypeError, ValueError, IndexError):
            return None
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _atom_link(entry: ET.Element) -> str:
    best = ""
    for c in entry:
        if _local(c.tag) != "link":
            continue
        rel = c.get("rel", "alternate")
        href = c.get("href", "")
        if rel == "alternate" and href:
            return href
        best = best or href
    return best


def parse_feed(data: bytes) -> list[dict[str, Any]]:
    """Parse RSS 2.0, RSS 1.0 (RDF) or Atom."""
    try:
        root = ET.fromstring(data)
    except ET.ParseError as e:
        raise ParseError(f"invalid XML: {e}") from e
    root_name = _local(root.tag)
    entries: list[dict[str, Any]] = []

    if root_name == "feed":  # Atom
        for e in root:
            if _local(e.tag) != "entry":
                continue
            published = _text(_child(e, "published")) or _text(_child(e, "updated"))
            summary = _text(_child(e, "summary")) or _text(_child(e, "content"))
            entries.append({
                "title": _text(_child(e, "title")),
                "url": _atom_link(e),
                "publishedAt": parse_date(published),
                "summaryHtml": summary,
                "extra": {},
            })
        return entries

    if root_name in ("rss", "RDF"):
        items = root.iter()
        for it in items:
            if _local(it.tag) != "item":
                continue
            link = _text(_child(it, "link"))
            if not link:
                guid = _child(it, "guid")
                if guid is not None and guid.get("isPermaLink", "true") != "false":
                    link = _text(guid)
            date = (_text(_child(it, "pubDate")) or _text(_child(it, "date"))
                    or _text(_child(it, "published")) or _text(_child(it, "updated")))
            entries.append({
                "title": _text(_child(it, "title")),
                "url": link,
                "publishedAt": parse_date(date),
                "summaryHtml": _text(_child(it, "description")) or _text(_child(it, "encoded")),
                "extra": {},
            })
        return entries

    raise ParseError(f"unknown feed root <{root_name}>")


_ARXIV_ANNOUNCE = re.compile(r"Announce Type:\s*([a-z-]+)", re.I)
_ARXIV_ABSTRACT = re.compile(r"Abstract:\s*", re.I)


def parse_arxiv(data: bytes) -> list[dict[str, Any]]:
    """arXiv RSS: keep only brand-new submissions; strip the 'arXiv:... Announce Type' preamble."""
    out = []
    for e in parse_feed(data):
        m = _ARXIV_ANNOUNCE.search(e["summaryHtml"])
        if m and m.group(1).lower() not in ("new",):
            continue
        parts = _ARXIV_ABSTRACT.split(e["summaryHtml"], maxsplit=1)
        e["summaryHtml"] = parts[-1]
        out.append(e)
    return out


_TAG_RE = re.compile(r"/releases/tag/([^/?#]+)")
_NOISE_VERSION = re.compile(r"^(b\d+|nightly|.*-(dev|nightly)\d*)$", re.I)


def parse_github_releases(data: bytes, repo: str) -> list[dict[str, Any]]:
    out = []
    for e in parse_feed(data):
        m = _TAG_RE.search(e["url"])
        version = m.group(1) if m else ""
        e["extra"]["version"] = version
        e["extra"]["repo"] = repo
        project = repo.split("/", 1)[1]
        title = e["title"].strip()
        # Normalize title to "<project> <version>" when the release name is just the tag.
        if not title or title == version or title.lstrip("v") == version.lstrip("v"):
            title = f"{project} {version}".strip()
        elif project.lower() not in title.lower():
            title = f"{project}: {title}"
        e["title"] = title
        out.append(e)
    return out


def parse_hn_algolia(data: bytes, min_score: int = 0) -> list[dict[str, Any]]:
    try:
        doc = json.loads(data)
    except json.JSONDecodeError as e:
        raise ParseError(f"invalid JSON: {e}") from e
    out = []
    for h in doc.get("hits", []):
        points = int(h.get("points") or 0)
        if points < min_score:
            continue
        oid = str(h.get("objectID", ""))
        if not oid.isdigit():
            continue
        hn_url = f"https://news.ycombinator.com/item?id={oid}"
        out.append({
            "title": (h.get("title") or h.get("story_title") or "").strip(),
            "url": h.get("url") or hn_url,
            "publishedAt": parse_date(h.get("created_at", "")),
            "summaryHtml": h.get("story_text") or "",
            "extra": {"hnScore": points, "discussionUrl": hn_url,
                      "comments": int(h.get("num_comments") or 0)},
        })
    return out
