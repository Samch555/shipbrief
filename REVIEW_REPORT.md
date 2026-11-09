# ShipBrief review report: 2026-11-09 → 2026-11-09 (1 days)

_Generated 2026-11-09 17:48 UTC by `scripts/quality_report.py`._

## Headline numbers

| Metric | Value |
|---|---|
| Days with a published digest | 1 / 1 (**100%**) |
| Runs recorded | 3 (published: 3) |
| Average items per digest | 29.0 (min 29, max 29) |
| Summary modes | extractive: 1 |
| Average run duration | 12.7s |
| Scheduled start delay vs 11:07 UTC | no scheduled runs yet |
| LLM cost (estimated) | $0.0000 total · 0 in / 0 out tokens · budget hit on 0 run(s) |
| Fact-check rejections | 0 model texts replaced by MODE 1 · 0 provenance rejections |
| REVIEW_LOG.md days filled in | 0 |

## Missing days

None. 🎉

## Flaky sources (failed at least once)

None.

## Sources that returned nothing in the window

None.

These fetched fine but published nothing new. Consider removing them if they stay silent.

## Per-day detail

| Date | Status | Items | Mode | Sources failed | Cost |
|---|---|---|---|---|---|
| 2026-11-09 | published | 29 | extractive | 0 | $0.0000 |

## How to read this

- **Success rate < 90%:** check the Actions tab for red runs. `data/health/<date>.json` has the reason.
- **A source failing more than 30% of the time:** run `python scripts/verify_sources.py` and fix or drop it in `sources.yaml`.
- **Cost:** MODE 1 is always $0. MODE 2 is capped per run by `SHIPBRIEF_LLM_MAX_COST_USD`.
- Combine this with your answers in `REVIEW_LOG.md` to decide whether to build the iOS app.
