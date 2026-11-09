"""ShipBrief command line.

  python -m shipbrief run                 live run: fetch, compose, validate, publish into data/ + feed.xml
  python -m shipbrief dry-run             offline: saved fixtures, MODE 1, writes to out/ (no network, no keys)
  python -m shipbrief validate FILE...    validate digest JSON files
  python -m shipbrief explain [--top N]   offline ranking breakdown (why items ranked where they did)
  python -m shipbrief build-site [DIR]    assemble the static site (site/ + data/ + feed.xml) into DIR (_site)
"""
from __future__ import annotations

import argparse
import json
import logging
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

from . import config
from .summarize.safety import install_log_redaction


def _setup_logging(verbose: bool) -> None:
    logging.basicConfig(level=logging.DEBUG if verbose else logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    # third-party HTTP debug logs could include headers; keep them quiet
    for noisy in ("httpx", "httpx2", "httpcore", "anthropic", "urllib3"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
    install_log_redaction()


def _fixture_now(fixtures: Path) -> datetime:
    manifest = fixtures / "manifest.json"
    if manifest.exists():
        return datetime.fromisoformat(json.loads(manifest.read_text())["capturedAt"])
    return datetime.now(timezone.utc)


def _print_digest(d: dict) -> None:
    print(f"\n=== {d['product']['name']} — {d['date']} ({d['summaryMode']}) ===")
    print(f"Headline: {d.get('headline', '')}\n")
    for key, title in (("topStories", "Top stories"), ("modelsAndAgents", "New models & agents"),
                       ("tools", "Tools worth trying"), ("openSource", "Open-source releases"),
                       ("research", "Research highlights")):
        items = d["sections"][key]
        if not items:
            continue
        print(f"## {title}")
        for it in items:
            print(f"- {it['title']}  [{it['source']}]\n    {it['summary']}\n    {it['url']}")
        print()
    p = d["promptOfTheDay"]
    print(f"## Prompt of the day: {p['title']}\n{p['prompt']}\n  ({p['useCase']})\n")
    w = d["tryThisToday"]
    print(f"## Try this today: {w['title']}")
    for n, s in enumerate(w["steps"], 1):
        print(f"  {n}. {s}")


def cmd_run(args) -> int:
    from .fetch.runner import FixtureTransport, live_transport
    from .pipeline import run

    offline = args.cmd == "dry-run" or args.fixtures
    fixtures = Path(args.fixtures or config.FIXTURES_DIR / "live")
    transport = FixtureTransport(fixtures) if offline else live_transport
    now = datetime.fromisoformat(args.now) if args.now else (_fixture_now(fixtures) if offline else None)
    mode = args.mode or ("extractive" if args.cmd == "dry-run" else None)
    if args.cmd == "dry-run":
        out = Path(args.out or "out")
        data_dir, feed = out / "data", out / "feed.xml"
    else:
        data_dir = Path(args.data_dir or config.DEFAULT_DATA_DIR)
        feed = Path(args.feed or data_dir.parent / "feed.xml")
    res = run(transport=transport, now=now, data_dir=data_dir, feed_path=feed, mode=mode)
    h = res.health
    print(json.dumps({"status": res.status, "summaryMode": h["summaryMode"], "counts": h["counts"],
                      "sourcesFailed": [s["id"] for s in h["sources"] if not s["ok"]],
                      "llm": h["llm"], "failureReason": h["failureReason"],
                      "durationSeconds": h["durationSeconds"]}, indent=2))
    if res.errors:
        print("VALIDATION ERRORS:\n  " + "\n  ".join(res.errors), file=sys.stderr)
    if res.digest and (args.print or args.cmd == "dry-run"):
        _print_digest(res.digest)
    return res.exit_code


def cmd_validate(args) -> int:
    from .validate import validate_digest

    bad = 0
    for f in args.files:
        errs = validate_digest(json.loads(Path(f).read_text()))
        print(f"{'OK ' if not errs else 'BAD'} {f}")
        for e in errs:
            print(f"    {e}")
        bad += bool(errs)
    return 2 if bad else 0


def cmd_explain(args) -> int:
    from .dedupe import dedupe
    from .fetch.runner import FixtureTransport, fetch_all
    from .normalize import filter_relevance, normalize
    from .ranking import rank
    from .sources import load_sources

    fixtures = Path(args.fixtures or config.FIXTURES_DIR / "live")
    now = _fixture_now(fixtures)
    res = fetch_all(load_sources(), FixtureTransport(fixtures), now)
    items, st = normalize(res, now)
    ranked = rank(filter_relevance(dedupe(items)[0], st), now)
    for it in ranked[: args.top]:
        parts = " ".join(f"{k}={v:.2f}" for k, v in it.score_parts.items())
        print(f"{it.score:6.2f}  {it.kind:10} {it.source[:20]:20} {it.title[:60]}\n        {parts}")
    return 0


def cmd_build_site(args) -> int:
    out = Path(args.dir)
    if out.exists():
        shutil.rmtree(out)
    shutil.copytree(config.ROOT / "site", out)
    data = config.DEFAULT_DATA_DIR
    if data.exists():
        shutil.copytree(data, out / "data", ignore=shutil.ignore_patterns(".tmp-*"))
    feed = config.ROOT / "feed.xml"
    if feed.exists():
        shutil.copy(feed, out / "feed.xml")
    shutil.copytree(config.SCHEMA_DIR, out / "schema")
    (out / ".nojekyll").write_text("")
    print(f"site built in {out}")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="shipbrief", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("-v", "--verbose", action="store_true")
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("run", "dry-run"):
        p = sub.add_parser(name)
        p.add_argument("--fixtures", help="serve sources from saved fixtures in this directory (offline)")
        p.add_argument("--now", help="ISO timestamp to treat as 'now'")
        p.add_argument("--mode", choices=["extractive", "llm"], help="force summary mode")
        p.add_argument("--data-dir")
        p.add_argument("--feed")
        p.add_argument("--out", help="dry-run output directory (default out/)")
        p.add_argument("--print", action="store_true", help="print the digest as text")
        p.set_defaults(func=cmd_run)
    p = sub.add_parser("validate")
    p.add_argument("files", nargs="+")
    p.set_defaults(func=cmd_validate)
    p = sub.add_parser("explain")
    p.add_argument("--top", type=int, default=20)
    p.add_argument("--fixtures")
    p.set_defaults(func=cmd_explain)
    p = sub.add_parser("build-site")
    p.add_argument("dir", nargs="?", default="_site")
    p.set_defaults(func=cmd_build_site)
    args = ap.parse_args(argv)
    _setup_logging(args.verbose)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
