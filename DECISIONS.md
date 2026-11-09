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
