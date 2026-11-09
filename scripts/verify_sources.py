#!/usr/bin/env python3
"""Fetch every source in sources.yaml once and report status.

Usage:
  python scripts/verify_sources.py                 # report only
  python scripts/verify_sources.py --save-fixtures tests/fixtures/live --trim
        # also save (trimmed) responses for the offline dry run

Exit code 0 always; this is a diagnostic. A source is "OK" if it fetched, robots.txt
allowed it, and it parsed into >=1 entry.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from shipbrief import http  # noqa: E402
from shipbrief.fetch import runner  # noqa: E402
from shipbrief.sources import load_sources  # noqa: E402
from shipbrief.fixtures import trim_payload  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sources", default=None)
    ap.add_argument("--save-fixtures", default=None)
    ap.add_argument("--trim", action="store_true", help="truncate long text in saved fixtures")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    sources = load_sources(args.sources) if args.sources else load_sources()
    now = datetime.now(timezone.utc)
    save_dir = Path(args.save_fixtures) if args.save_fixtures else None
    if save_dir:
        save_dir.mkdir(parents=True, exist_ok=True)

    def transport(source, url):
        data = http.get(url)
        if save_dir:
            ext = ".json" if source.type == "hn" else ".xml"
            (save_dir / f"{source.id}{ext}").write_bytes(trim_payload(data, ext) if args.trim else data)
        return data

    results = runner.fetch_all(sources, transport, now, workers=6)
    report = []
    for r in results:
        dated = [e for e in r.entries if e["publishedAt"]]
        newest = max((e["publishedAt"] for e in dated), default=None)
        status = "OK" if r.ok and r.entries else ("EMPTY" if r.ok else "FAIL")
        report.append({"id": r.source.id, "status": status, "entries": len(r.entries),
                       "newest": newest.isoformat() if newest else None,
                       "error": r.error, "seconds": r.seconds, "url": r.source.url})
    if save_dir:
        (save_dir / "manifest.json").write_text(json.dumps(
            {"capturedAt": now.isoformat(), "sources": report}, indent=2))
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        for row in report:
            print(f"{row['status']:5} {row['id']:22} n={row['entries']:<4} newest={str(row['newest'])[:10]:10} "
                  f"{row['seconds']:5.1f}s {row['error'] or ''}")
        bad = [r for r in report if r["status"] != "OK"]
        print(f"\n{len(report) - len(bad)}/{len(report)} OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
