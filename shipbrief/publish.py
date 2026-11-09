"""Write digest files, archive index, Atom feed, and health records. All writes are atomic."""
from __future__ import annotations

import json
import os
import re
import tempfile
from datetime import date, datetime, timedelta, timezone
from html import escape
from pathlib import Path
from typing import Any

from . import config

DAY_FILE = re.compile(r"^(\d{4}-\d{2}-\d{2})\.json$")


def write_json(path: Path, doc: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".tmp-", suffix=".json")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(doc, f, indent=2, ensure_ascii=False)
        f.write("\n")
    os.replace(tmp, path)


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".tmp-")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(text)
    os.replace(tmp, path)


def day_files(data_dir: Path) -> list[tuple[date, Path]]:
    out = []
    if data_dir.exists():
        for p in data_dir.iterdir():
            m = DAY_FILE.match(p.name)
            if m:
                out.append((date.fromisoformat(m.group(1)), p))
    return sorted(out, reverse=True)


def prune_archive(data_dir: Path, today: date, keep_days: int = config.ARCHIVE_DAYS) -> list[str]:
    cutoff = today - timedelta(days=keep_days)
    removed = []
    for d, p in day_files(data_dir):
        if d < cutoff:
            p.unlink()
            removed.append(p.name)
    hdir = data_dir / "health"
    if hdir.exists():
        for p in hdir.iterdir():
            m = DAY_FILE.match(p.name)
            if m and date.fromisoformat(m.group(1)) < cutoff:
                p.unlink()
    return removed


def build_index(data_dir: Path) -> dict[str, Any]:
    days = []
    for d, p in day_files(data_dir):
        try:
            doc = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        days.append({"date": d.isoformat(), "path": f"data/{p.name}",
                     "itemCount": int(doc.get("stats", {}).get("itemsPublished", 0)),
                     "headline": str(doc.get("headline", ""))[:200],
                     "summaryMode": str(doc.get("summaryMode", ""))})
    return {"schemaVersion": config.INDEX_SCHEMA_VERSION,
            "updatedAt": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "latest": days[0]["date"] if days else None,
            "days": days[: config.ARCHIVE_DAYS]}


SECTION_TITLES = [("topStories", "Top stories"), ("modelsAndAgents", "New models and agents"),
                  ("tools", "Tools worth trying"), ("openSource", "Open-source releases"),
                  ("research", "Research highlights")]


def _entry_html(doc: dict[str, Any], site_url: str) -> str:
    parts = []
    for key, title in SECTION_TITLES:
        items = doc["sections"].get(key) or []
        if not items:
            continue
        parts.append(f"<h2>{escape(title)}</h2><ul>")
        for it in items:
            parts.append(f'<li><a href="{escape(it["url"], quote=True)}">{escape(it["title"])}</a> '
                         f"<em>({escape(it['source'])})</em><br/>{escape(it['summary'])}</li>")
        parts.append("</ul>")
    p = doc["promptOfTheDay"]
    parts.append(f"<h2>Prompt of the day: {escape(p['title'])}</h2><pre>{escape(p['prompt'])}</pre>")
    w = doc["tryThisToday"]
    parts.append(f"<h2>Try this today: {escape(w['title'])}</h2><ol>"
                 + "".join(f"<li>{escape(s)}</li>" for s in w["steps"]) + "</ol>")
    parts.append(f'<p><a href="{escape(site_url, quote=True)}">Open ShipBrief</a></p>')
    return "".join(parts)


def build_feed(data_dir: Path, site_url: str = config.SITE_URL, max_entries: int = 30) -> str:
    site = site_url.rstrip("/") + "/"
    entries = []
    updated = "1970-01-01T00:00:00Z"
    for d, p in day_files(data_dir)[:max_entries]:
        try:
            doc = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        gen = doc.get("generatedAt", f"{d.isoformat()}T00:00:00Z")
        updated = max(updated, gen)
        title = f"{config.PRODUCT_NAME} {d.isoformat()}: {doc.get('headline', '')}"
        entries.append(
            "  <entry>\n"
            f"    <id>{escape(site)}#{d.isoformat()}</id>\n"
            f"    <title>{escape(title[:250])}</title>\n"
            f"    <updated>{escape(gen)}</updated>\n"
            f'    <link rel="alternate" type="text/html" href="{escape(site)}?date={d.isoformat()}"/>\n'
            f'    <content type="html">{escape(_entry_html(doc, site))}</content>\n'
            "  </entry>\n")
    return ('<?xml version="1.0" encoding="utf-8"?>\n'
            '<feed xmlns="http://www.w3.org/2005/Atom">\n'
            f"  <title>{escape(config.PRODUCT_NAME)}: daily AI brief</title>\n"
            f"  <subtitle>What shipped in AI today: models, agents, tools, research, and one prompt to try.</subtitle>\n"
            f"  <id>{escape(site)}</id>\n"
            f'  <link rel="alternate" type="text/html" href="{escape(site)}"/>\n'
            f'  <link rel="self" type="application/atom+xml" href="{escape(site)}feed.xml"/>\n'
            f"  <updated>{escape(updated)}</updated>\n"
            f"  <author><name>{escape(config.PRODUCT_NAME)} bot</name></author>\n"
            + "".join(entries) + "</feed>\n")


def publish_digest(digest: dict[str, Any], data_dir: Path, feed_path: Path, site_url: str = config.SITE_URL) -> dict:
    day = date.fromisoformat(digest["date"])
    write_json(data_dir / f"{digest['date']}.json", digest)
    write_json(data_dir / "latest.json", digest)
    removed = prune_archive(data_dir, day)
    index = build_index(data_dir)
    write_json(data_dir / "index.json", index)
    write_text(feed_path, build_feed(data_dir, site_url))
    return {"pruned": removed, "archiveDays": len(index["days"])}


def write_health(health: dict[str, Any], data_dir: Path) -> None:
    """data/health.json = last run; data/health/YYYY-MM-DD.json = all runs that day (for reports)."""
    write_json(data_dir / "health.json", health)
    day_path = data_dir / "health" / f"{health['date']}.json"
    runs: list = []
    if day_path.exists():
        try:
            runs = json.loads(day_path.read_text(encoding="utf-8"))
            if not isinstance(runs, list):
                runs = []
        except json.JSONDecodeError:
            runs = []
    runs = [r for r in runs if r.get("runId") != health["runId"]] + [health]
    write_json(day_path, runs[-10:])
