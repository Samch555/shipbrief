# ShipBrief data format (schema v1)

This is the contract between the pipeline and every client: the web page, the Atom feed, and a future iOS app.
The machine-readable sources of truth are:

| File | Schema |
|---|---|
| `data/YYYY-MM-DD.json`, `data/latest.json` | `schema/digest.v1.schema.json` |
| `data/index.json` | `schema/index.v1.schema.json` |
| `data/health.json` | `schema/health.v1.schema.json` |

A full valid example is at `docs/samples/sample-digest.json`.

## Versioning policy

- `schemaVersion` is semver, `MAJOR.MINOR.PATCH`. The current version is **1.0.0**.
- **PATCH:** documentation or constraint fixes that never reject a previously valid file.
- **MINOR:** additive only. A minor version adds new *optional* fields, sections, or enum values for `kind` or `tags`. Clients **must ignore unknown fields** and should treat unknown `kind` values as `news`.
- **MAJOR:** anything that removes or renames a field or changes its type. A major change ships with a new schema file (`digest.v2.schema.json`). The pipeline would then publish to a new path (`data/v2/...`) while still publishing v1 for a transition period, so old app builds keep working.
- Clients should check that `schemaVersion` starts with `1.` and refuse or degrade gracefully otherwise.

> Note: the published schema is strict (`additionalProperties: false`) because it validates *our own output*. Client decoders should be lenient, which is the opposite rule, so additive changes don't break them.

## URLs (on GitHub Pages)

```
<site>/data/latest.json        today's digest (same content as the dated file)
<site>/data/YYYY-MM-DD.json    one day's digest (kept for 90 days)
<site>/data/index.json         archive list, newest first
<site>/data/health.json        last run's health
<site>/feed.xml                Atom feed (one entry per day)
```

## Digest object

| Field | Type | Notes |
|---|---|---|
| `schemaVersion` | string | `"1.x.y"` |
| `date` | string | `YYYY-MM-DD` (UTC day of the run) |
| `generatedAt` | string | ISO-8601 with timezone |
| `product` | object? | `{name, siteUrl?, feedUrl?}` |
| `summaryMode` | enum | `extractive` (MODE 1), `llm` (MODE 2), or `llm-partial` (MODE 2 hit the budget and the rest fell back to MODE 1) |
| `headline` | string? | One line, the title of the #1 story |
| `stats` | object | `itemsFetched`, `itemsAfterDedupe?`, `itemsPublished`, `sourcesOk`, `sourcesFailed` |
| `sections` | object | See below. All five keys are always present; arrays may be empty except `topStories`, which needs 3 to 8 items. |
| `promptOfTheDay` | Prompt | |
| `tryThisToday` | Workflow | |

### `sections`

| Key | Max | Item type | Meaning |
|---|---|---|---|
| `topStories` | 8 | Item | The highest-ranked stories of any kind |
| `modelsAndAgents` | 6 | Item | New models and agent products or frameworks |
| `tools` | 5 | ToolItem | Tools worth trying |
| `openSource` | 10 | Item | GitHub releases (`kind: release`, with `version`) |
| `research` | 3 | Item | Papers (`kind: paper`) |

Each item appears in **at most one** section. Sections are filled in order: topStories → modelsAndAgents → tools → openSource → research. On quiet days, `tools` may include notable minor or major releases (`kind: release`), so clients must not assume `tools` items have `kind: tool`.

### Item

| Field | Type | Notes |
|---|---|---|
| `id` | string | 16 hex characters: the first 16 of sha256(canonical URL). It's stable across runs and days. |
| `title` | string | ≤300 chars, the original title from the source, stripped of HTML |
| `url` | string | http(s) link to the source. **Always comes from a fetched feed** (enforced by the fact-check guard). |
| `source` | string | Human name of the source, e.g. "Hugging Face Blog" |
| `sourceId` | string? | Key into `sources.yaml` |
| `publishedAt` | string | ISO-8601 with timezone, **taken from the feed** and never invented |
| `kind` | enum | `news` `release` `paper` `tool` `discussion` |
| `tags` | string[] | lowercase slugs, e.g. `models`, `agents`, `open-source`, `research`, `coding`, `safety`, `multimodal`, `tools`, `evals`, `robotics`, `policy`, `hardware` |
| `roles` | enum[] | `developer` `researcher` `product` `founder` `designer` `everyone` |
| `summary` | string | 1–2 short sentences, ≤400 chars. Original or extractive, never long quotes. |
| `generatedBy` | string | `extractive`, `template`, or a Claude model id such as `claude-haiku-5-5` |
| `score` | number | Ranking score (see `shipbrief/ranking.py`). Higher means more important. |
| `version` | string? | For releases, e.g. `v0.5.0` |
| `hnScore` | int? | Hacker News points, if the item was found on HN |
| `discussionUrl` | string? | HN thread URL |
| `related` | Related[]? | Other sources covering the same story: `{source, url, title?}` |
| `whatItDoes` | string? | Required on ToolItem |
| `whoItsFor` | string? | Required on ToolItem |

### Prompt (`promptOfTheDay`)

`{title, prompt (≤150 words), useCase, roles[], basedOn: {itemId, title, url}, generatedBy}`.
`basedOn.itemId` must reference an item in the same digest. The prompt contains a placeholder such as `<PASTE TEXT>` where the user inserts their own content.

### Workflow (`tryThisToday`)

`{title, steps[2..6], roles[], basedOn, generatedBy}`.

## Semantic rules enforced in code (`shipbrief/validate.py`, `shipbrief/summarize/factcheck.py`)

1. Valid against the JSON Schema.
2. `publishedAt` must parse and must not be more than 12 hours in the future.
3. `basedOn.itemId` must exist in the digest.
4. The prompt is ≤150 words.
5. `topStories` has ≥3 items, and the run must have ≥8 ranked candidates. Otherwise nothing is published.
6. **Provenance:** every published item's `url` and `publishedAt` must exactly match a record fetched in the same run (`factcheck.py`).
7. Summaries must not contain numbers, versions, or URLs that aren't present in that item's source text (`factcheck.py`, which applies to LLM output).

## index.json

```json
{"schemaVersion": "1.0.0", "updatedAt": "...", "latest": "2026-11-09",
 "days": [{"date": "2026-11-09", "path": "data/2026-11-09.json", "itemCount": 31, "headline": "...", "summaryMode": "extractive"}]}
```
`days` is newest first and holds at most 90 entries.

## health.json

Written after **every** run, including failed ones. It records per-source counts and errors, dedupe counts, the summary mode, LLM token usage and estimated cost, fact-check rejections, and the duration. See the schema file for fields. It is diagnostics, not product data, so its shape may change more freely, but it is still versioned.
