# Progress

## Phase 0 — Repo setup ✅
Done: git repo, directory structure, README, DECISIONS, PROGRESS, .gitignore, pinned requirements.
Left: everything else (Phases 1–7).
Risks: none yet.

## Phase 1 — Digest schema ✅
Done: `schema/digest.v1.schema.json` (strict, versioned), index and health schemas, `shipbrief/validate.py` (schema + semantic checks), `docs/samples/sample-digest.json`, `docs/SCHEMA.md` (fields + versioning policy), 12 tests.
Left: pipeline (Phase 2+).
Risks: The schema is strict for our own output. Clients must be lenient (this is documented).
