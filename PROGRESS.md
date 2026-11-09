# Progress

## Phase 0 — Repo setup ✅
Done: git repo, directory structure, README, DECISIONS, PROGRESS, .gitignore, pinned requirements.
Left: everything else (Phases 1–7).
Risks: none yet.

## Phase 1 — Digest schema ✅
Done: `schema/digest.v1.schema.json` (strict, versioned), index and health schemas, `shipbrief/validate.py` (schema + semantic checks), `docs/samples/sample-digest.json`, `docs/SCHEMA.md` (fields + versioning policy), 12 tests.
Left: pipeline (Phase 2+).
Risks: The schema is strict for our own output. Clients must be lenient (this is documented).

## Phase 2 — Pipeline core ✅
Done: `sources.yaml` (74 verified sources: 21 blogs, 1 HN, 3 arXiv, 49 GitHub repos), polite HTTP client (timeouts, retries, backoff, size cap, robots.txt), parsers (RSS 2.0, Atom, RDF, arXiv, GitHub releases, HN Algolia), normalization, classification (AI relevance, tags, kind, roles), dedupe and title clustering, a transparent ranking formula (`shipbrief/ranking.py`), history-based repeat suppression, `scripts/verify_sources.py`, trimmed live fixtures, 38 tests passing.
Left: summarization, composer, publishing, workflow, site, measurement, docs.
Risks: feeds change URLs over time, so re-run `verify_sources.py` and watch `health.json`. Blog volume is low on weekends.

## Phase 3 — Summarization ✅
Done: MODE 1 extractive summarizer (sentence cleanup, boilerplate and injection removal, release-note highlights, templates), MODE 2 Claude client (Haiku batches + Sonnet compose, structured outputs, effort low), budget guard with cost accounting, deterministic fact checks (provenance, ungrounded numbers, URLs, injection), log redaction, original prompt and workflow templates, 57 tests passing (MODE 2 is tested with a fake client).
Left: composer, publishing, workflow, site, measurement, docs.
Risks: MODE 2 hasn't been exercised against the live API in this session (no key available). The fallbacks are tested.

## Phase 4 — Composer & publishing ✅
Done: section composer (diversity, one section per item), prompt and workflow (MODE 2 Sonnet with validation, otherwise templates), atomic publishing (dated file, latest, index, Atom feed, 90-day pruning), health.json plus per-day health history, CLI (`run`, `dry-run`, `validate`, `explain`, `build-site`), `.github/workflows/daily.yml` (cron 11:07 UTC + manual, tests → run → commit → keepalive → Pages deploy, red on failure), `ci.yml`, Dependabot, 70 tests passing.
Left: web page, measurement tooling, docs.
Risks: the cron may run late. The 60-day keepalive via the enable API isn't officially documented (it's a backup to the daily commits).

## Phase 5 — Web page ✅
Done: `site/` (index.html, style.css, app.js, no frameworks or trackers, strict CSP). It has today's cards by section, role and interest filters saved in localStorage, an archive list with `?date=` links, a copy button on the prompt, dark mode (follows the OS, with a manual override), a stale-data banner after 48h, and links to the RSS feed and JSON. Accessibility notes are in `docs/ACCESSIBILITY.md`, screenshots in `docs/screenshots/`.
Risks: no automated axe or Lighthouse run yet (do one after the first deploy).

## Phase 6 — Measurement ✅
Done: `scripts/quality_report.py` produces `REVIEW_REPORT.md` (success rate, items per day, flaky and silent sources, schedule delay, LLM cost, fact-check rejections, per-day table; the window starts at the first recorded run). `REVIEW_LOG.md` is the daily hand-filled template. Health records the trigger (schedule or manual). **First real run on 2026-11-09: 74/74 sources OK, 3,815 entries fetched → 29 items published, MODE 1, 11–14 s, $0.** Release highlights are now extracted from GitHub release HTML. 71 tests passing.
Left: docs (Phase 7). The user needs to create the GitHub repo and enable Pages.
Risks: the Hugging Face blog feed has no descriptions, so its cards use the template text in MODE 1.
