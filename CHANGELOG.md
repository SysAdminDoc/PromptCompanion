# Changelog

All notable changes to PromptCompanion are documented in this file. Format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and this project adheres to
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.0.1] - 2026-04-18

Initial scaffold — data foundation phase.

### Added
- MIT license for tooling and curation.
- JSON Schema for prompt records (`data/schema.json`).
- Category + tag taxonomy (`data/taxonomy.json`) with 10 flat top-level buckets.
- Source registry (`data/sources/registry.json`) gating on CC0 / MIT only.
- `tools/fetch_sources.py` — clones upstream prompt repos into `data/sources/upstream/`.
- `tools/import_awesome.py` — parses `f/awesome-chatgpt-prompts` CSV.
- `tools/import_bigprompt.py` — parses `0xeb/TheBigPromptLibrary` markdown tree.
- `tools/import_system.py` — parses `dontriskit/awesome-ai-system-prompts` markdown tree.
- `tools/validate.py` — JSON Schema validation + ID dedupe report.
- `tools/build_index.py` — compiles SQLite FTS5 search index at `data/index/prompts.db`.
- `docs/SCHEMA.md` — human-readable schema documentation with field-by-field rationale.
- README with project overview, roadmap, schema preview, and quick-start pipeline.

### Notes
- GUI is deliberately out of scope for `0.0.x`. Data quality first.
- Upstream clones live under `data/sources/upstream/` and are gitignored; only the
  cleaned JSONL output under `data/prompts/` is committed.
