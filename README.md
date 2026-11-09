# ShipBrief

A free, automated 5-minute daily brief of what shipped in AI: new models, agents and tools, open-source releases, a research highlight, plus one practical prompt and one workflow to try today.

- Runs daily on **GitHub Actions** (free for public repos), publishes to **GitHub Pages** (free).
- **MODE 1 (default, $0):** extractive summaries + heuristic ranking. No LLM.
- **MODE 2 (optional):** if the `ANTHROPIC_API_KEY` repository secret is set, uses Claude with a hard per-run budget guard.
- Output: versioned JSON (`data/latest.json`, `data/YYYY-MM-DD.json`, `data/index.json`), an Atom feed (`feed.xml`), and a static web page.

> Status: under construction. See PROGRESS.md. Full docs are written in Phase 7.
