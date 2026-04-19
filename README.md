<p align="center">
  <img src="logo.png" alt="PromptCompanion" width="180" />
</p>

<h1 align="center">PromptCompanion</h1>

<p align="center">
  <em>The AI Prompt Companion — a curated, searchable, offline library of the best AI prompts.</em>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/version-0.1.0-blue?style=flat-square" alt="version" />
  <img src="https://img.shields.io/badge/license-MIT-green?style=flat-square" alt="license" />
  <img src="https://img.shields.io/badge/platform-Windows%20%7C%20macOS%20%7C%20Linux-lightgrey?style=flat-square" alt="platform" />
  <img src="https://img.shields.io/badge/python-3.10%2B-yellow?style=flat-square" alt="python" />
  <img src="https://img.shields.io/badge/prompts-3%2C751-brightgreen?style=flat-square" alt="prompts" />
</p>

---

## What is this?

**PromptCompanion** is a library-first tool for AI prompts. It aggregates, cleans, and
categorizes the best publicly-available prompts from multiple upstream sources into a
single structured dataset, and will eventually expose them through a dark-themed desktop
GUI with fast search, variable substitution, and one-click copy-to-clipboard.

Unlike existing tools (AnythingLLM, LibreChat, MSTY) that bolt a prompt library onto a
full chat application, PromptCompanion is built around the *library* itself. The primary
action is "find the right prompt and copy it." No chat window, no accounts, no cloud.

### Current status — `v0.1.0`

- [x] Prompt record JSON Schema
- [x] Category + tag taxonomy
- [x] 4 importers for upstream sources (CC0 + MIT only)
- [x] Body-hash deduplication (exact-match removal)
- [x] Quality scoring (0-100 heuristic on every record)
- [x] Validation pipeline + SQLite FTS5 index builder
- [x] 3,751 curated prompts across 11 categories
- [ ] Desktop GUI (PyQt6, Catppuccin Mocha) — *planned for v0.2.0*
- [ ] Variable substitution UI — *planned for v0.2.0*
- [ ] Global hotkey + paste-to-active-window — *planned for v0.3.0*

## Bundled Sources

| Source | License | Status |
|---|---|---|
| [f/awesome-chatgpt-prompts](https://github.com/f/awesome-chatgpt-prompts) | CC0-1.0 | Bundled |
| [0xeb/TheBigPromptLibrary](https://github.com/0xeb/TheBigPromptLibrary) | MIT | Bundled |
| [dontriskit/awesome-ai-system-prompts](https://github.com/dontriskit/awesome-ai-system-prompts) | MIT | Bundled |
| [abilzerian/LLM-Prompt-Library](https://github.com/abilzerian/LLM-Prompt-Library) | MIT | Bundled |

Each record retains its upstream `source`, `author`, and `license` fields for attribution.
Only CC0 and MIT sources are bundled to keep the aggregate dataset permissively licensed.

## Repository Layout

```
PromptCompanion/
├── data/
│   ├── prompts/           # Curated prompts, JSONL, one file per category
│   ├── sources/           # Source registry + attribution (upstream clones gitignored)
│   ├── index/             # Built SQLite FTS5 index (gitignored)
│   ├── schema.json        # JSON Schema for a prompt record
│   └── taxonomy.json      # Category + tag vocabulary
├── tools/
│   ├── fetch_sources.py   # Clone upstream repos into data/sources/upstream/
│   ├── import_awesome.py  # Parse f/awesome-chatgpt-prompts CSV
│   ├── import_bigprompt.py# Parse TheBigPromptLibrary markdown tree
│   ├── import_system.py   # Parse awesome-ai-system-prompts markdown tree
│   ├── import_llmprompt.py# Parse LLM-Prompt-Library markdown + Jinja2
│   ├── validate.py        # Schema validation + deduplication
│   └── build_index.py     # Compile SQLite FTS5 search index
├── docs/
│   └── SCHEMA.md          # Human-readable schema documentation
├── CHANGELOG.md
├── LICENSE
└── README.md
```

## Quick Start (data pipeline)

```bash
# From the repo root
python tools/fetch_sources.py      # Clone upstream prompt repos
python tools/import_awesome.py     # Parse CSV → data/prompts/*.jsonl
python tools/import_bigprompt.py   # Parse markdown tree
python tools/import_system.py      # Parse system-prompt collection
python tools/import_llmprompt.py   # Parse LLM-Prompt-Library (md + j2)
python tools/validate.py           # Schema check + dedupe report
python tools/build_index.py        # Emit data/index/prompts.db (FTS5)
```

Python 3.10+. All scripts auto-install dependencies on first run via `_bootstrap()`.

## Prompt Record Schema

```json
{
  "id": "awesome-linux-terminal",
  "title": "Linux Terminal",
  "body": "I want you to act as a linux terminal...",
  "role": "user",
  "category": "roleplay",
  "tags": ["shell", "simulation", "developer"],
  "variables": [],
  "target_models": ["any"],
  "language": "en",
  "source": "https://github.com/f/awesome-chatgpt-prompts",
  "author": "f (Fatih Kadir Akın)",
  "license": "CC0-1.0",
  "version": 1,
  "created": "2026-04-18T00:00:00Z",
  "quality": 55,
  "updated": "2026-04-18T00:00:00Z"
}
```

Full schema documentation lives in [docs/SCHEMA.md](docs/SCHEMA.md).

## Category Taxonomy

Ten flat top-level buckets + free-form tags:

- **development** — code gen, review, debugging, refactor, SQL, devops, regex
- **writing** — blog, copy, email, editing, summarize
- **research** — literature review, data analysis, fact-check, compare
- **creative** — fiction, worldbuilding, poetry, lyrics, image prompts
- **business** — strategy, meeting notes, reports, pitch, hiring
- **productivity** — planning, learning, teaching, flashcards
- **system** — agent personas, custom-GPT system prompts
- **roleplay** — "act as" prompts
- **translation** — translate, grammar, localize
- **specialized** — medical, legal, finance, academic (each gated with disclaimer)

See [data/taxonomy.json](data/taxonomy.json) for the machine-readable vocabulary.

## Roadmap

| Version | Focus |
|---|---|
| **0.0.x** | Data foundation, schema, importers, validation |
| **0.1.x** | More sources, dedupe heuristics, quality scoring |
| **0.2.x** | PyQt6 desktop GUI, SQLite FTS5 search, variable panel |
| **0.3.x** | Global hotkey, paste-to-active-window, export profiles |
| **0.4.x** | Personal overlay (edit bundled prompts without forking) |
| **1.0.0** | First stable release with full feature set |

See [CHANGELOG.md](CHANGELOG.md) for detailed release history.

## Contributing

This is currently a personal curation project. Issues and PRs welcome for:
- New upstream sources (CC0 or MIT only)
- Schema extensions
- Category taxonomy refinements
- Quality flags / deprecation of low-value prompts

## License

Tooling and curation: **MIT** (see [LICENSE](LICENSE)).
Bundled prompt data: retains upstream licenses (CC0 and MIT only).
