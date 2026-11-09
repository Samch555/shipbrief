# HANDOFF: read this first

Written 2026-11-09 for anyone, human or AI, continuing this project with **no memory of how it was built**.
Pair it with `README.md` (how to run), `DECISIONS.md` (why, D1–D32), `PROGRESS.md` (phase log), and `docs/SCHEMA.md` (data contract).

## 1. What this is

ShipBrief is a **zero-cost daily AI news digest**. A GitHub Actions cron job fetches 73 enabled, verified public feeds, then:

1. builds a ranked, deduplicated, summarized digest
2. validates it against a versioned JSON Schema
3. commits it to `data/`
4. deploys a static site to GitHub Pages

**The context:** the owner is running it as a **two-week experiment** (starting around 2026-11-10) to decide whether to build an **iOS app** on top of it. The JSON format is therefore the product's API, and it must stay stable (see §5).

## 2. What exists (all working, 71 tests passing)

| Area | State |
|---|---|
| Sources | 74 configured, 73 enabled, all verified on 2026-11-09: 18 company/lab/research blogs, HN (Algolia API), 3 arXiv lists, 52 GitHub release feeds (51 enabled; llama.cpp disabled). Dropped and missing sources are listed in DECISIONS D10. |
| Pipeline | fetch → normalize → dedupe/cluster → relevance filter → history filter → rank → select sections → summarize → compose → validate → publish. `shipbrief/pipeline.py` is the entry point. |
| MODE 1 ($0) | Default. Extractive summaries plus original templates for the prompt and workflow. |
| MODE 2 | Optional, when `ANTHROPIC_API_KEY` is set. Haiku 5.5 does per-item summaries in batches of 10; Sonnet 5.5 composes the headline, prompt, and workflow. Structured outputs, a budget guard, and deterministic fact checks apply. **Only tested with a fake client.** It has never called the real API, because no key was available while building. |
| Publishing | `data/YYYY-MM-DD.json`, `latest.json`, `index.json`, `feed.xml` (Atom), `health.json` plus `data/health/<date>.json`. 90-day pruning. Writes are atomic. |
| Workflow | `.github/workflows/daily.yml`: cron `7 11 * * *` plus manual trigger. It runs tests, the pipeline, commits data, keepalive, and Pages deploy. It **goes red and publishes nothing** on failure. `ci.yml` runs tests and an offline dry run on push/PR. |
| Web page | `site/`. Vanilla JS with a strict CSP; filters in localStorage, archive, copy button, dark mode, stale banner. |
| Measurement | `scripts/quality_report.py` → `REVIEW_REPORT.md`; `REVIEW_LOG.md` is the human daily log. |
| First real run | 2026-11-09: 3,815 entries fetched → 29 items published, 73/73 enabled sources OK, 11–14 s, $0. Committed in `data/`. |

**Not done yet** (needs the owner): the GitHub repo hasn't been created or pushed, and Pages isn't enabled. Steps are in README → Deploying. There's no LICENSE file.

## 3. How it works (the mental model)

- **Item** (`shipbrief/models.py`): one normalized story. Its `id` is the first 16 hex characters of sha256(canonical URL), which is stable across days.
- **Provenance is sacred.** `url` and `publishedAt` always come from a fetched feed record. `compose.py` checks every selected item against `factcheck.fetched_records()` before summarizing. Items without a feed date are dropped at normalization.
- **Ranking** (`shipbrief/ranking.py`): one formula, documented in that file's docstring: recency (24h half-life), source weight, HN points, release significance, cross-source coverage, AI relevance, and a kind adjustment. Diversity is applied at selection: at most 2 items per source per section, with HN keyed by linked domain and capped at 3. `python -m shipbrief explain` prints the score parts.
- **Sections** (`compose.py`): each item goes in one section only, filled in this order: topStories (5–8; papers excluded; releases only if x.0.0) → modelsAndAgents → tools (on quiet days, minor releases can fill it) → openSource (stable releases, 1 per repo) → research (≤3 papers).
- **History** (`history.py`): ids published in the previous 7 days are excluded. Same-day reruns ignore today's file, so they're idempotent.
- **MODE switch** (`summarize/__init__.py: choose_mode`): uses `llm` if the key env var is set, unless `SHIPBRIEF_MODE=extractive`. Any LLM failure (API error, refusal, bad JSON, budget hit, fact-check rejection) falls back to MODE 1 **per item**, so a digest is always produced.
- **Gates** (`pipeline.py`): fewer than 8 candidates means exit 3, and a validation error means exit 2. Either way only health is written.

## 4. Known weaknesses (honest list)

1. **MODE 2 is untested against the live API.**
   - Before relying on it, run `workflow_dispatch` once with the secret set and inspect `data/health.json → llm` and the summaries.
   - One assumption to check: Haiku 5.5 accepts `output_config.format` + `effort: low`. If it 400s, the run silently falls back to MODE 1 and `health.llm.errors` will show the error.
2. **MODE 1 summary quality varies by feed.**
   - The Hugging Face blog feed has no descriptions, and HN items have no text, so those cards say "Trending on Hacker News with N points…" or "New from …".
   - This is honest but thin. MODE 2 fixes most of it.
3. **Lab coverage gaps.** Anthropic and Meta have no official RSS, so they only appear via HN or GitHub releases. Don't add scraping; check occasionally whether official feeds have appeared.
4. **Heuristic classification.** Kind, tags, and the AI-relevance filter are keyword rules (`classify.py`). Expect some misfiled items, such as a business story in "models & agents", and occasional false negatives.
5. **Patch-release noise.** Frequent patch releases (claude-code, crewAI) can dominate the open-source section on slow days. You could require minor or major releases unless the repo weight is ≥ 1.0.
6. **Injection filter is blunt.** Sentences mentioning "system prompt" or "jailbreak" are dropped, which can strip legitimate AI-safety news text (DECISIONS D23).
7. **Scheduling limits.**
   - Scheduled runs can start late or, rarely, be dropped.
   - The 60-day auto-disable is countered by daily commits and an API re-enable call. The latter is community-reported, not officially documented. The stale banner on the site is the backstop.
8. **Fixtures age.** `tests/fixtures/live/` is a 2026-11-09 capture. Tests pin "now" to the capture time, so they stay green, but refresh the fixtures if feed formats change.
9. **No automated accessibility audit** (axe or Lighthouse) has been run. Do one on the deployed site.
10. **The name "ShipBrief" hasn't been trademark-checked.**

## 5. Rules for changing things

- **Schema:** additive changes only within v1, meaning new *optional* fields. Bump `config.SCHEMA_VERSION` minor, update `schema/digest.v1.schema.json`, `docs/SCHEMA.md`, and `docs/samples/sample-digest.json`, then run the tests. Breaking changes need a v2 file and a parallel `data/v2/` path (see SCHEMA.md).
- **Ranking:** edit only `ranking.py` weights or formula, then check with `python -m shipbrief explain`.
- **Sources:** edit `sources.yaml`, then `python scripts/verify_sources.py`, then record what changed in DECISIONS.md.
- **Never** publish an item without a fetched URL and date, never let model text bypass `factcheck.py`, and never log or write the API key.
- After each change, run `python -m pytest -q` and `python -m shipbrief dry-run`, add an entry to DECISIONS.md, and commit.

## 6. Likely next steps

**During the 2-week experiment (light touch):**
- Deploy (README → Deploying), then watch the first 2–3 scheduled runs.
- Optionally enable MODE 2 for half the period to compare usefulness. `summaryMode` is in every digest, so the report can split by mode.
- On day 14, run `python scripts/quality_report.py` and read it together with `REVIEW_LOG.md`.

**If the decision is to build the iOS app:**
- **Data:** fetch `https://<user>.github.io/shipbrief/data/index.json` and `data/latest.json` (static, CDN-cached, CORS-friendly). No backend is needed.
- **Swift models:** use `Codable` structs mirroring `docs/SCHEMA.md`. Decode leniently: use optionals for every non-required field, ignore unknown keys (the default with `Codable`), and treat unknown `kind` as `news`. Check `schemaVersion.hasPrefix("1.")`.
- **Features that map directly to the data:**
  - read and unread state via stable item `id`s
  - role and interest filters via `roles`/`tags`
  - share and copy for the prompt
  - offline cache of the last N days
  - a daily local notification after about 12:00 UTC using `headline`, with no push server
- **Possible later additions (all optional, additive):** an `imageUrl` from feed media tags (watch copyright), a per-item `readingMinutes`, and a JSON Feed (`feed.json`) for easier client parsing.

**Improving the digest itself:**
- Better MODE 1 HN summaries: allowed only if the linked page has a feed. Don't scrape.
- Smarter tool detection, for example Show HN items that link to GitHub repos with recent first releases.
- Per-source health alerts: open a GitHub issue automatically when a source fails 3 days in a row.
- A small human-labelled eval set (20 items) to tune the relevance filter and ranking weights.
