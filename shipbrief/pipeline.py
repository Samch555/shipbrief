"""End-to-end daily run. Publishes only a valid digest; always writes health.

Exit codes (used by the GitHub workflow to fail visibly):
  0  published (or dry run succeeded)
  2  digest failed validation        -> previous digest kept
  3  too few items to publish         -> previous digest kept
  1  unexpected error                 -> previous digest kept
"""
from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import config, history, publish
from .compose import compose
from .dedupe import dedupe
from .fetch.runner import Transport, fetch_all
from .normalize import filter_relevance, normalize
from .ranking import rank
from .sources import Source, load_sources
from .summarize import choose_mode, factcheck
from .validate import validate_digest, validate_health

log = logging.getLogger(__name__)

EXIT_OK, EXIT_ERROR, EXIT_INVALID, EXIT_TOO_FEW = 0, 1, 2, 3


@dataclass
class RunResult:
    exit_code: int
    status: str
    digest: dict[str, Any] | None
    health: dict[str, Any]
    errors: list[str] = field(default_factory=list)


def run(*, transport: Transport, now: datetime | None = None, data_dir: Path = config.DEFAULT_DATA_DIR,
        feed_path: Path | None = None, sources: list[Source] | None = None, mode: str | None = None,
        client: Any = None, budget: Any = None, write: bool = True, dry_run: bool = False) -> RunResult:
    t0 = time.monotonic()
    now = now or datetime.now(timezone.utc)
    day = now.date()
    data_dir = Path(data_dir)
    feed_path = feed_path or data_dir.parent / "feed.xml"
    mode = mode or choose_mode()
    run_id = f"{now.strftime('%Y%m%dT%H%M%SZ')}-{uuid.uuid4().hex[:6]}"
    health: dict[str, Any] = {
        "schemaVersion": config.HEALTH_SCHEMA_VERSION, "runId": run_id, "date": day.isoformat(),
        "startedAt": now.isoformat().replace("+00:00", "Z"), "durationSeconds": 0.0, "status": "error",
        "failureReason": None, "summaryMode": mode, "sources": [], "counts": {}, "llm": None, "factCheck": None,
    }
    digest = None
    status, code, errors = "error", EXIT_ERROR, []
    try:
        sources = sources if sources is not None else load_sources()
        results = fetch_all(sources, transport, now)
        health["sources"] = [{"id": r.source.id, "ok": r.ok, "items": len(r.entries), "error": r.error,
                              "seconds": r.seconds} for r in results]
        fetched = sum(len(r.entries) for r in results)
        items, nstats = normalize(results, now)
        deduped, dstats = dedupe(items)
        relevant = filter_relevance(deduped, nstats)
        seen = history.recent_item_ids(data_dir, day)
        fresh = [i for i in relevant if i.id not in seen]
        ranked = rank(fresh, now)
        counts = {
            "itemsFetched": fetched, "itemsNormalized": nstats.kept, "dropped": dict(nstats.dropped),
            "duplicatesRemoved": dstats.exact_duplicates, "clustered": dstats.clustered,
            "itemsAfterDedupe": len(deduped), "itemsRelevant": len(relevant),
            "alreadyPublishedRecently": len(relevant) - len(fresh), "candidates": len(ranked),
        }
        health["counts"] = counts
        ok_sources = sum(1 for r in results if r.ok)
        log.info("fetched=%d normalized=%d deduped=%d relevant=%d fresh=%d sources_ok=%d/%d",
                 fetched, nstats.kept, len(deduped), len(relevant), len(fresh), ok_sources, len(results))

        if len(ranked) < config.MIN_ITEMS_TO_PUBLISH:
            status, code = "too-few-items", EXIT_TOO_FEW
            health["failureReason"] = f"only {len(ranked)} candidate items (< {config.MIN_ITEMS_TO_PUBLISH})"
        else:
            records = factcheck.fetched_records(results)
            res = compose(ranked, day=day, now=now, mode=mode, records=records,
                          stats={"itemsFetched": fetched, "itemsAfterDedupe": len(deduped),
                                 "sourcesOk": ok_sources, "sourcesFailed": len(results) - ok_sources},
                          client=client, budget=budget)
            digest = res.digest
            health["summaryMode"] = res.outcome.mode_used
            health["factCheck"] = res.outcome.report.as_dict()
            if res.outcome.budget is not None:
                health["llm"] = {**res.outcome.budget.as_dict(), "errors": res.outcome.errors[:10],
                                 "itemsSummarizedByLLM": res.outcome.llm_items}
            counts["itemsPublished"] = digest["stats"]["itemsPublished"]
            errors = validate_digest(digest, now=now)
            if errors:
                status, code = "failed-validation", EXIT_INVALID
                health["failureReason"] = "; ".join(errors[:5])
            elif dry_run:
                status, code = "dry-run", EXIT_OK
            else:
                status, code = "published", EXIT_OK
            if code == EXIT_OK and write:
                counts["publish"] = publish.publish_digest(digest, data_dir, feed_path)
    except Exception as e:  # never let a crash publish anything
        log.exception("run failed")
        health["failureReason"] = f"{type(e).__name__}: {str(e)[:300]}"
        status, code = "error", EXIT_ERROR
    health["status"] = status
    health["durationSeconds"] = round(time.monotonic() - t0, 2)
    herr = validate_health(health)
    if herr:
        log.error("health record invalid: %s", herr)
    if write:
        publish.write_health(health, data_dir)
    return RunResult(exit_code=code, status=status, digest=digest, health=health, errors=errors)
