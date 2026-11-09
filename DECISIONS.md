# Decisions log

Each entry: date, decision, reason. Newest at the bottom.

## 2026-11-09 — Phase 0

- **D1. Name: "ShipBrief".** An original working name for "a brief of what shipped". It hasn't had a trademark search. Rename it before any App Store launch. The name appears in the README, the site title, feed metadata, and `shipbrief/config.py` (`PRODUCT_NAME`).
- **D2. Language: Python 3.12, stdlib-first.** Two pinned runtime dependencies:
  `PyYAML==6.0.2` (to parse `sources.yaml`) and `jsonschema==4.23.0` (to validate digests). The tests use `pytest==8.3.3`.
  HTTP uses `urllib.request`, XML uses `xml.etree.ElementTree`, and HTML is stripped with `html.parser`.
  The Claude API is called with raw HTTPS through `urllib`, so there's no SDK dependency.
- **D3. Storage = the git repo itself.** The workflow commits `data/` and `feed.xml` back to `main`. This gives the 90-day archive for free and keeps a full history, and the daily commit counts as repository activity (see D-later on the 60-day rule).
- **D4. Pages deploy via `actions/deploy-pages`.** The site is built into `_site/` from `site/` + `data/` + `feed.xml`. Nothing needs a build step: it's plain HTML/CSS/JS.
- **D5. Python package layout.** `shipbrief/` holds the pipeline modules, `schema/` the JSON Schemas, `site/` the static page, `scripts/` the one-off tools, and `tests/` with `tests/fixtures/` holds the saved feeds used by the offline dry run.

## 2026-11-09 — Phase 1

- **D6. The digest uses fixed section keys rather than a generic list of sections.** This is easier to decode in Swift with `Codable`. New sections can be added in a minor version as optional keys.
- **D7. Item `id` = first 16 hex characters of sha256(canonical URL).** Ids are stable across days, so a client can mark items "read".
- **D8. `date-time` formats are checked in our code (`datetime.fromisoformat`) rather than by jsonschema's format checker.** This avoids an extra dependency.
- **D9. The sample digest uses `example.com` content** so it can never be mistaken for real news.

## 2026-11-09 — Phase 2 (sources & pipeline core)

- **D10. Source verification (2026-11-09):** `scripts/verify_sources.py` fetched every candidate with our User-Agent and honoured robots.txt. Final result: 74/74 configured sources OK; llama.cpp is configured but disabled.
  - **Dropped:**
    - `microsoft-ai` (blogs.microsoft.com/ai/feed): HTTP 410 Gone.
    - `google-developers` (developers.googleblog.com/feeds/posts/default): items have **no dates**, so it can't satisfy the provenance rule.
    - `microsoft/autogen` releases: the project is in maintenance mode (last release 2025-09), replaced by `microsoft/agent-framework`.
    - `ggml-org/llama.cpp` releases: kept in the file but `enabled: false`. It only ships `bNNNN` build tags, many per day, with no semver.
  - **Fixed URLs:** PyTorch → `pytorch.org/blog/feed/`. LangChain → `www.langchain.com/blog/rss.xml` (the old URL now returns an HTML page). Ollama → `ollama.com/blog/rss.xml`.
  - **Added:** Mistral AI News (`mistral.ai/news/rss`, robots.txt `Allow: /`).
  - **Not available as a feed, so not included:** Anthropic news (no RSS; `/rss.xml` is 404) and Meta AI blog (404). We do **not** scrape pages without a feed. Anthropic and Meta announcements still arrive via HN when they are popular.
- **D11. Hacker News via the Algolia HN Search API** (`hn.algolia.com/api/v1/search_by_date`). It's the free public search API linked from HN's footer. One request returns stories from the last 36h with a points filter. The official Firebase API would need hundreds of requests per run.
- **D12. Item age window = 96h**, so Monday runs still see Friday's posts. Repeats are prevented by `history.py`, which excludes any item id published in the previous 7 days' digests. Re-running on the same day is idempotent because the history ignores today's own file.
- **D13. Releases:** only stable semver releases are kept. Nightlies, rc/alpha/beta/dev/preview, and `trunk/<sha>`-style tags are dropped. At most **one release per repo per run**, the most significant one (major > minor > patch), because monorepos like LangChain, Mastra and the Vercel AI SDK publish dozens of package tags daily.
- **D14. The AI-relevance filter runs after dedupe** (as the spec orders it). A non-AI-sounding HN title that links to an official lab post merges into that post instead of being dropped.
- **D15. Fixtures:** `tests/fixtures/live/` holds a real capture from 2026-11-09, **trimmed** to ≤20 entries per feed and ≤400 characters of text per entry so third-party article text isn't redistributed. `tests/fixtures/unit/` holds hand-written edge cases.
- **D16. Local TLS note:** the python.org macOS build ships without CA certificates. Run locally with `SSL_CERT_FILE=$(python -m certifi)` (`certifi` is a dev-only dependency). GitHub Actions runners don't need this.
- **D17. XML safety:** `xml.etree` on Python ≥3.7.1 with expat ≥2.4.1 doesn't resolve external entities and mitigates entity-expansion bombs. Responses are also capped at 5 MB.

## 2026-11-09 — Phase 3 (summarization)

- **D18. MODE 2 uses the official `anthropic` Python SDK (pinned 2.6.0)** instead of raw HTTP, as Anthropic's API guidance recommends for Python projects. It is imported lazily, so MODE 1 never needs it. The SDK reads `ANTHROPIC_API_KEY` from the environment, and our code never touches the value.
- **D19. Models:** `claude-haiku-5-5` for per-item summaries ($0.10/$0.50 per MTok), batched 10 items per request. `claude-sonnet-5-5` for one compose call per run ($2/$10 per MTok). Both use `output_config.effort: "low"` and **structured outputs** (`output_config.format: json_schema`), so the response is valid JSON matching our schema.
- **D20. Budget guard defaults** (all env-overridable): 40 items, 80k input tokens, 20k output tokens, **$0.10 per run**. Expected real cost is about $0.01–0.02/run (≈$0.50/month). Every call is pre-estimated (chars/3 + max_tokens) and refused if it could cross any limit. After that the run continues in MODE 1 and `summaryMode` becomes `llm-partial`.
- **D21. No server-side refusal fallback to another model.** Anthropic's guidance suggests enabling `fallbacks` on Sonnet 5.5. We don't, because a fallback could route to a pricier model outside the budget guard's price table. On `stop_reason: refusal` (or `max_tokens`, invalid JSON, or any API error) that batch falls back to the $0 MODE 1 output instead.
- **D22. Deterministic guards on model output** (`factcheck.py`):
  - A summary is rejected (and MODE 1 text used) if it contains a number, version, or percentage not present in that item's fetched text, any URL, instruction-like text, a long quote, or is too long.
  - Prompt and workflow text may not contain URLs, version numbers, or percentages.
  - **Provenance:** every published item's `(url, publishedAt)` must exactly match a fetched record.
- **D23. Injection hygiene.** Fetched text goes into the prompt inside `<item>` tags with `<`/`>` replaced by `‹›`. The system prompt states the data is untrusted and must never be obeyed. Extractive summaries drop instruction-like sentences.
  - Trade-off: news that *quotes* phrases like "system prompt" or "jailbreak" loses those sentences, or falls back to MODE 1 text.
- **D24. MODE 1 prompt and workflow are original templates** (`summarize/templates.py`), chosen by the tags of a real top item and rotated by date. The untrusted item title only appears in the `useCase` line, never inside the prompt body readers paste.

## 2026-11-09 — Phase 4 (composer, publishing, workflow)

- **D25. Schedule `7 11 * * *` (11:07 UTC).** The spec's default is 11:00. GitHub's docs say scheduled runs can be delayed during high load, with the start of every hour the busiest time, and that queued jobs may be dropped. Offsetting by 7 minutes lowers that risk. Expect start delays anyway.
- **D26. The 60-day rule** (verified on docs.github.com, "Events that trigger workflows", 2026-11-09): *"In a public repository, scheduled workflows are automatically disabled when no repository activity has occurred in 60 days."* The docs don't define "activity". Our defences:
  1. Each run commits `data/` (health is committed even on failure), so there is a commit every day.
  2. Each run calls `PUT /repos/{repo}/actions/workflows/daily.yml/enable`. Community keepalive tools report this resets the timer; this is not officially documented, so it's best effort and never fails the run.
  3. The web page shows a "stale" banner when `latest.json` is older than 48h, so you'll notice quickly. If it ever happens, re-enable the workflow under Actions → daily-digest → "Enable workflow", or push any commit.
- **D27. Failure semantics.** Pipeline exit codes: 0 ok, 1 error, 2 validation failed, 3 too few items (< 8 candidates). On any non-zero exit nothing in `data/*.json` (except health) or `feed.xml` changes, Pages is not redeployed, and the job ends red with an `::error::` annotation. GitHub emails the repo owner about failed scheduled runs by default.
- **D28. Each item appears in one section only.** Top stories admit releases only for major versions (x.0.0) and never papers. On quiet days, minor or major releases may fill "Tools worth trying".
- **D29. Diversity.** At most 2 items per source per section. Hacker News items are diversified by linked domain, but at most 3 HN items per section.
- **D30. Health history.** Each run is appended to `data/health/YYYY-MM-DD.json` (up to 10 runs per day), and `data/health.json` holds the last run. `quality_report.py` reads the history.
- **D31. Atom feed.** One entry per day (last 30), with HTML content linking every item to its source. Entry links point to `?date=YYYY-MM-DD` on the site.
- **D32. Action versions are pinned to major tags** (checkout@v4, setup-python@v5, configure-pages@v5, upload-pages-artifact@v3, deploy-pages@v4). Dependabot (monthly) proposes updates.
