#!/usr/bin/env python3
"""Summarize the last N days of runs into REVIEW_REPORT.md.

Reads data/health/YYYY-MM-DD.json (every run) and data/YYYY-MM-DD.json (published digests).
Also counts how many days of REVIEW_LOG.md you filled in.

Usage:
  python scripts/quality_report.py                # last 14 days ending today (UTC)
  python scripts/quality_report.py --days 14 --end 2026-11-23 --data-dir data --out REVIEW_REPORT.md
"""
from __future__ import annotations

import argparse
import json
import re
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def load_runs(data_dir: Path, start: date, end: date) -> dict[date, list[dict]]:
    out: dict[date, list[dict]] = {}
    hdir = data_dir / "health"
    if not hdir.exists():
        return out
    for p in sorted(hdir.glob("*.json")):
        try:
            d = date.fromisoformat(p.stem)
        except ValueError:
            continue
        if start <= d <= end:
            try:
                runs = json.loads(p.read_text())
                out[d] = runs if isinstance(runs, list) else [runs]
            except json.JSONDecodeError:
                out[d] = []
    return out


def load_digests(data_dir: Path, start: date, end: date) -> dict[date, dict]:
    out = {}
    for p in data_dir.glob("????-??-??.json"):
        d = date.fromisoformat(p.stem)
        if start <= d <= end:
            try:
                out[d] = json.loads(p.read_text())
            except json.JSONDecodeError:
                pass
    return out


def first_run_day(data_dir: Path) -> date | None:
    days = []
    for p in (data_dir / "health").glob("????-??-??.json"):
        try:
            days.append(date.fromisoformat(p.stem))
        except ValueError:
            pass
    return min(days) if days else None


def review_log_days(path: Path) -> int:
    if not path.exists():
        return 0
    text = path.read_text()
    # A day counts as filled if its "Read it?" line has an answer.
    return len(re.findall(r"^- \*\*Read it\?\*\* *(?!yes / skimmed / no)\S+", text, re.M))


def build_report(data_dir: Path, start: date, end: date, review_log: Path) -> str:
    runs_by_day = load_runs(data_dir, start, end)
    digests = load_digests(data_dir, start, end)
    n_days = (end - start).days + 1
    all_runs = [r for runs in runs_by_day.values() for r in runs]

    published_days = sorted(digests)
    success_rate = len(published_days) / n_days if n_days else 0
    items = [digests[d]["stats"]["itemsPublished"] for d in published_days]
    avg_items = sum(items) / len(items) if items else 0
    statuses = Counter(r.get("status", "?") for r in all_runs)
    modes = Counter(digests[d].get("summaryMode", "?") for d in published_days)
    durations = [r.get("durationSeconds", 0) for r in all_runs]

    src_runs: dict[str, int] = defaultdict(int)
    src_fail: dict[str, int] = defaultdict(int)
    src_items: dict[str, int] = defaultdict(int)
    last_err: dict[str, str] = {}
    for r in all_runs:
        for s in r.get("sources", []):
            src_runs[s["id"]] += 1
            src_items[s["id"]] += s.get("items", 0)
            if not s.get("ok"):
                src_fail[s["id"]] += 1
                last_err[s["id"]] = s.get("error") or ""
    flaky = sorted(((sid, src_fail[sid] / src_runs[sid]) for sid in src_fail if src_runs[sid]),
                   key=lambda x: -x[1])
    silent = sorted(sid for sid in src_runs if src_items[sid] == 0 and src_fail.get(sid, 0) == 0)

    cost = sum((r.get("llm") or {}).get("estimatedCostUsd", 0) for r in all_runs)
    tokens_in = sum((r.get("llm") or {}).get("inputTokens", 0) for r in all_runs)
    tokens_out = sum((r.get("llm") or {}).get("outputTokens", 0) for r in all_runs)
    budget_hits = sum(1 for r in all_runs if (r.get("llm") or {}).get("budgetExhausted"))
    fc_rej = sum((r.get("factCheck") or {}).get("summariesRejected", 0) for r in all_runs)
    prov_rej = sum((r.get("factCheck") or {}).get("provenanceRejected", 0) for r in all_runs)
    missing_days = [start + timedelta(days=i) for i in range(n_days) if (start + timedelta(days=i)) not in digests]
    run_delays = []
    for r in all_runs:
        if r.get("trigger") != "schedule":
            continue
        try:
            st = datetime.fromisoformat(r["startedAt"].replace("Z", "+00:00"))
            run_delays.append((st.hour * 60 + st.minute) - (11 * 60 + 7))
        except (KeyError, ValueError):
            pass
    sched = [d for d in run_delays if -60 < d < 600]
    filled = review_log_days(review_log)

    L = []
    L.append(f"# ShipBrief review report: {start} → {end} ({n_days} days)\n")
    L.append(f"_Generated {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')} by `scripts/quality_report.py`._\n")
    L.append("## Headline numbers\n")
    L.append("| Metric | Value |\n|---|---|")
    L.append(f"| Days with a published digest | {len(published_days)} / {n_days} (**{success_rate:.0%}**) |")
    L.append(f"| Runs recorded | {len(all_runs)} ({', '.join(f'{k}: {v}' for k, v in statuses.most_common()) or 'none'}) |")
    L.append(f"| Average items per digest | {avg_items:.1f} (min {min(items) if items else 0}, max {max(items) if items else 0}) |")
    L.append(f"| Summary modes | {', '.join(f'{k}: {v}' for k, v in modes.most_common()) or 'n/a'} |")
    L.append(f"| Average run duration | {sum(durations) / len(durations):.1f}s |" if durations else "| Average run duration | n/a |")
    if sched:
        L.append(f"| Scheduled start delay vs 11:07 UTC | median {sorted(sched)[len(sched) // 2]} min, max {max(sched)} min ({len(sched)} scheduled runs) |")
    else:
        L.append("| Scheduled start delay vs 11:07 UTC | no scheduled runs yet |")
    L.append(f"| LLM cost (estimated) | ${cost:.4f} total · {tokens_in:,} in / {tokens_out:,} out tokens · budget hit on {budget_hits} run(s) |")
    L.append(f"| Fact-check rejections | {fc_rej} model texts replaced by MODE 1 · {prov_rej} provenance rejections |")
    L.append(f"| REVIEW_LOG.md days filled in | {filled} |\n")

    L.append("## Missing days\n")
    L.append(", ".join(str(d) for d in missing_days) + "\n" if missing_days else "None. 🎉\n")

    L.append("## Flaky sources (failed at least once)\n")
    if flaky:
        L.append("| Source | Failure rate | Last error |\n|---|---|---|")
        for sid, rate in flaky:
            L.append(f"| `{sid}` | {rate:.0%} ({src_fail[sid]}/{src_runs[sid]}) | {last_err.get(sid, '')[:90]} |")
    else:
        L.append("None.")
    L.append("")
    L.append("## Sources that returned nothing in the window\n")
    L.append((", ".join(f"`{s}`" for s in silent) or "None.") + "\n")
    L.append("These fetched fine but published nothing new. Consider removing them if they stay silent.\n")

    L.append("## Per-day detail\n")
    L.append("| Date | Status | Items | Mode | Sources failed | Cost |\n|---|---|---|---|---|---|")
    for i in range(n_days):
        d = start + timedelta(days=i)
        runs = runs_by_day.get(d, [])
        last = runs[-1] if runs else {}
        dg = digests.get(d)
        failed = sum(1 for s in last.get("sources", []) if not s.get("ok"))
        c = sum((r.get("llm") or {}).get("estimatedCostUsd", 0) for r in runs)
        L.append(f"| {d} | {last.get('status', 'no run')} | {dg['stats']['itemsPublished'] if dg else '-'} | "
                 f"{dg.get('summaryMode') if dg else '-'} | {failed if runs else '-'} | ${c:.4f} |")
    L.append("\n## How to read this\n")
    L.append("- **Success rate < 90%:** check the Actions tab for red runs. `data/health/<date>.json` has the reason.")
    L.append("- **A source failing more than 30% of the time:** run `python scripts/verify_sources.py` and fix or drop it in `sources.yaml`.")
    L.append("- **Cost:** MODE 1 is always $0. MODE 2 is capped per run by `SHIPBRIEF_LLM_MAX_COST_USD`.")
    L.append("- Combine this with your answers in `REVIEW_LOG.md` to decide whether to build the iOS app.")
    return "\n".join(L) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=14)
    ap.add_argument("--end", help="last day (YYYY-MM-DD), default today UTC")
    ap.add_argument("--data-dir", default=str(ROOT / "data"))
    ap.add_argument("--review-log", default=str(ROOT / "REVIEW_LOG.md"))
    ap.add_argument("--out", default=str(ROOT / "REVIEW_REPORT.md"))
    ap.add_argument("--include-before-first-run", action="store_true",
                    help="count days before the first recorded run as missing")
    args = ap.parse_args()
    end = date.fromisoformat(args.end) if args.end else datetime.now(timezone.utc).date()
    start = end - timedelta(days=args.days - 1)
    first = first_run_day(Path(args.data_dir))
    if first and first > start and not args.include_before_first_run:
        start = first  # the experiment hadn't started yet; don't count those days as failures
    report = build_report(Path(args.data_dir), start, end, Path(args.review_log))
    Path(args.out).write_text(report, encoding="utf-8")
    print(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
