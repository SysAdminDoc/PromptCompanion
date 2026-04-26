# PromptCompanion Roadmap

Offline curated AI prompt library with PyQt6 + SQLite FTS5 search, global hotkey, and paste-to-window. Roadmap pushes toward personal overlay, structured prompt composition, and deeper model/provider integration without becoming a chat app.

## Planned Features

### Personal Overlay (v0.4.x target)
- Edit bundled prompts without forking — overlay JSONL layered on top of immutable source
- Private prompts (never exported, optional encryption)
- Per-prompt notes field + tags separate from source tags
- Version history per prompt (local, diff-viewable)
- Import a folder of user `.md` prompts on launch

### Composition
- Prompt chains (A → B → C pipelines with variable passthrough)
- Variable presets per prompt ("safe defaults" + "aggressive" profile)
- Inline preview with live variable substitution and character/token count
- Snippet includes (`{{include:system/tone-dev}}`) from other prompts
- Export profile: Markdown with front-matter for static sites

### Library Growth
- Two more upstream sources vetted for CC0/MIT + dedupe
- Language tagging + translations (community PR lane)
- Quality scoring v2: signals from length, variables, author rank, review vote
- Deprecation flag for stale or LLM-specific obsolete prompts

### UX
- Results-as-you-type with BM25 + recency boost
- Category tree remembers expanded state
- Keyboard-only mode: up/down, enter=copy, space=preview, `/`=search
- "Open prompt in text editor" for power users
- Multi-select export bundle (JSON/Markdown)

### Provider Integration (optional, off by default)
- Send-to-ChatGPT / Claude.ai / local Ollama via URL handoff
- Token count estimate (tiktoken local) visible inline
- Model compatibility field honored in filter (OpenAI / Anthropic / local)

### Platform
- macOS / Linux global hotkey parity (currently Windows only)
- PyInstaller auto-update via GitHub Releases
- Portable mode (DB + config next to exe)

## Competitive Research
- **AnythingLLM / LibreChat / MSTY** — prompt library bolted onto chat. Lesson: stay library-first. Don't build a chat pane.
- **PromptHub / FlowGPT** — SaaS prompt marketplaces. Lesson: let users opt into external sync but default to offline/private.
- **Raycast Prompts** — spotlight-style keyboard UX. Lesson: polish the global hotkey flow so PromptCompanion beats it on Windows.
- **Obsidian + "Smart Templates" plugins** — freeform. Lesson: offer markdown export that drops straight into Obsidian vaults.

## Nice-to-Haves
- System tray quick-pick submenu of favorites
- "Prompt of the day" surfaced on launch
- CLI: `promptcompanion search "code review"` → clipboard
- Web share via signed URL (opt-in, self-hosted)
- Plugin API for custom importers
- Dark light theme switcher (currently Mocha only)

## Open-Source Research (Round 2)

### Related OSS Projects
- https://github.com/mikeybizzzle/prompt-library-app — SQLite+FTS5 prompt manager with Web/Desktop/CLI/MCP. Closest direct competitor.
- https://github.com/ComfyAssets/ComfyUI_PromptManager — SQLite-backed prompts with tags, ratings, image gallery linkage, AI autotag via WD14/JoyCaption.
- https://github.com/thibaultyou/prompt-library — CLI-first, Git-synced prompt library with fragment/variable system.
- https://github.com/MrXie23/PromptLibrary — Next.js multi-language categorized library (UX reference).
- https://github.com/abilzerian/LLM-Prompt-Library — Jinja2 templates + scripts for many providers.
- https://github.com/0xeb/TheBigPromptLibrary — Curated system-prompt corpus; great ingestion source.
- https://github.com/thunlp/OpenPrompt — Prompt-learning framework; reference for programmatic prompt composition.
- https://github.com/mrinasugosh/AI-Prompt-Database — Domain-categorized prompt repo; good category taxonomy source.

### Features to Borrow
- Fragment/snippet system with reusable variables (thibaultyou) — compose long prompts from named pieces.
- Version history with diff + revert per prompt (mikeybizzzle) — SQLite JSONB column per revision.
- MCP server mode so Claude/Cursor can query the library directly (mikeybizzzle) — kill "copy-paste from app" friction.
- AI autotag on import via a local VLM or tiny classifier (ComfyAssets).
- SHA256 dedupe on ingest (ComfyAssets) — current 5-source pipeline will benefit.
- Git-as-sync backend for power users (thibaultyou) — pair repo-backed library with FTS5 cache.
- Fragment-powered "fill-in-the-blanks" runner that invokes OpenAI/Anthropic directly (thibaultyou/mikeybizzzle).
- Import parsers for each major upstream (TheBigPromptLibrary / Awesome-ChatGPT-Prompts / abilzerian).

### Patterns & Architectures Worth Studying
- **SQLite FTS5 + BM25 + vector column via sqlite-vec** — hybrid search with RRF, matches the current GUI plan.
- **Drizzle ORM + migrations-on-startup** (mikeybizzzle) — if a Node/Electron port is ever explored.
- **Fragment-graph execution** (thibaultyou) — prompt = DAG of fragments; cycle-detect on save.
- **Multi-interface single-store** (mikeybizzzle) — one DB, four UIs (Web, Desktop, CLI, MCP). Current repo is PyQt-only; MCP + CLI additions are low-cost.
- **Local VLM autotag pipeline** (ComfyAssets) — CPU-only phi-3-vision or sentence-transformers for tag suggestion at import time.

## Implementation Deep Dive (Round 3)

### Reference Implementations to Study
- **OlivierLDff/QOlm** — https://github.com/OlivierLDff/QOlm — QAbstractListModel subclass with proper `beginInsertRows`/`endInsertRows` semantics; reference for 10K+ prompt list without UI stalls.
- **Ultimaker/Uranium `UM/Qt/ListModel.py`** — https://github.com/Ultimaker/Uranium/blob/main/UM/Qt/ListModel.py — production-grade Python QAbstractListModel with macOS `endResetModel()` workaround; directly portable.
- **Qt docs `QAbstractListModel`** — https://doc.qt.io/qt-6/qabstractlistmodel.html — authoritative `rowCount` + `data` + `canFetchMore` / `fetchMore` contract for incremental BM25 result streaming.
- **sqlite/sqlite FTS5 docs** — https://www.sqlite.org/fts5.html — canonical `bm25()` ranking-function syntax; `MATCH` + `ORDER BY bm25(fts_table)` + `highlight()` for snippet rendering.
- **qtrangeslider for tag-filter UI** — https://github.com/pyapp-kit/superqt — PyQt6-compatible widgets (range slider, searchable combo) fill gaps PyQt6 stdlib misses.
- **f0uriest/KeyHac** — https://github.com/crftwr/keyhac — Windows global hotkey reference using `ctypes` + `RegisterHotKey`; direct replacement for `keyboard` package which breaks as non-admin.
- **paste-to-window via `pywinauto`** — https://github.com/pywinauto/pywinauto — `Application().top_window().set_focus()` + clipboard fallback is more reliable than `SendKeys` for Unicode prompts.

### Known Pitfalls from Similar Projects
- QListView with 3500+ rows stalls on first show — call `setUniformItemSizes(True)` for ~10× speedup (https://forum.qt.io/topic/159449/).
- QListView fundamentally scales worse than QTableView past ~100K rows — switch to `QTableView` with hidden headers for future-proofing.
- FTS5 `MATCH` with user input containing `:` or `-` raises `SQLITE_ERROR: fts5: syntax error` — sanitize by wrapping each term in double quotes.
- `canFetchMore` / `fetchMore` only fires when scrolled near bottom — for "load all on Ctrl+A" flows, call `fetchMore()` in a loop or preload.
- PyInstaller one-file builds on Windows hit `multiprocessing` fork bomb unless `multiprocessing.freeze_support()` is literally line 1 and a runtime hook is registered (see CLAUDE.md global rule).
- Global hotkeys via `keyboard` package require admin on Win11 23H2+; migrate to `RegisterHotKey` Win32 API via ctypes.
- System tray icon on Win11 fails silently if `QSystemTrayIcon.isSystemTrayAvailable()` returns false before QApplication paint loop starts — check inside `QTimer.singleShot(0, ...)`.

### Library Integration Checklist
- `PyQt6==6.8.0` — key API `QAbstractListModel` subclass + `setUniformItemSizes(True)`. Gotcha: Qt6 dropped `QRegExp`; use `QRegularExpression`.
- `sqlite-utils==3.38` — convenience wrapper around stdlib `sqlite3` for FTS5 schema migrations. Gotcha: stdlib `sqlite3` on Windows ships without FTS5 before Python 3.11; verify via `sqlite3.connect(':memory:').execute("SELECT fts5(?)", ('tokenize',))`.
- `pyperclip==1.9.0` — clipboard fallback for paste-to-window. Gotcha: on X11/Wayland requires `xclip` / `wl-clipboard`; Windows-only this is fine.
- `pywin32==308` — `win32gui.GetForegroundWindow()` + `SendInput` for paste-to-window. PyInstaller: add `--hidden-import win32timezone`.
- `pystray==0.19.5` — alt to Qt's `QSystemTrayIcon` if you want a lighter tray; gotcha: pystray + QApplication in same process deadlock on Win11 — pick one.
- `superqt==0.6.7` — PyQt6-compatible `QSearchableComboBox`, `QRangeSlider` for filter UI; Qt stdlib lacks these.
- `PyInstaller==6.11.1` — key flags: `--collect-submodules PyQt6` + `--collect-data superqt` + runtime hook for `multiprocessing.freeze_support()`.
