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
