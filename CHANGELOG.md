# Changelog

All notable changes to PromptCompanion are documented in this file. Format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and this project adheres to
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.3.1] - 2026-04-18

Premium UX/UI polish pass.

### Improved
- **Welcome state**: centered empty-state guidance when no prompt is selected, with contextual "No prompts found" when search returns zero results.
- **Prompt list**: reduced from 5 columns to 3 (Score, Title, Category) so titles are fully readable. Category column shows subdued text. Titles have tooltips for overflow.
- **Preview pane**: quality displayed as a colored pill badge with tooltip (e.g., "High quality (82/100)"). Meta separator changed from dots to slashes. Tags rendered as inline styled HTML spans. Variable labels humanized ("max_tokens_out" becomes "Max Tokens Out"). Body displayed in a card-like container with border and rounded corners.
- **Action bar**: clearer hierarchy — Copy (secondary), Copy Filled (primary/lavender), Paste to App (accent/teal). All buttons disabled when no prompt is selected. Export format combo has tooltip. Copy feedback changes button color to green briefly.
- **Search bar**: placeholder shows actual prompt count ("Search 3,751 prompts..."). Built-in clear button enabled. Rounded corners increased. Focus ring on lavender.
- **Toolbar**: consistent naming — "Any Role", "Any Score", "Any Source". All combos have tooltips. Better spacing with visual gaps between groups.
- **Category tree**: formatted counts with commas. No alternating row colors for cleaner look.
- **Stylesheet**: comprehensive overhaul — transparent input borders (appear on hover/focus), refined scrollbars (6px, transparent track), 1px splitter, tooltip styling, better button disabled states, better combo hover states, body editor card styling, refined table header (no uppercase, letter-spacing), semi-transparent hover states.
- **Status bar**: shows total with source count on startup. Contextual messages with timeout. Tray balloon message adapts to platform.
- **Tray menu**: separator between Show and Quit. "Show PromptCompanion" label.
- **Window**: slightly larger default (1300x800). Search debounce reduced to 200ms.

---

## [0.3.0] - 2026-04-18

Paste flow — system tray, global hotkey, paste-to-active-window, export profiles.

### Added
- **System tray**: app minimizes to tray on close, stays running. Double-click tray icon or right-click > Show to restore.
- **Global hotkey** (Windows): Win+Shift+P summons the window from anywhere, remembers the previously active window.
- **Paste to Window** button: copies the prompt (with variables filled + export format applied), switches to the previous window, and simulates Ctrl+V.
- **Export profiles**: Plain Text (default), Markdown (title + metadata + body), JSON (structured object). Selector in preview bottom bar applies to all copy/paste actions.
- Styled `QMenu` for tray context menu matching Catppuccin Mocha theme.
- `QSystemTrayIcon` with balloon notification on minimize.

### Changed
- Close button now minimizes to tray instead of quitting. Use tray > Quit to exit.
- `QApplication.setQuitOnLastWindowClosed(False)` to support tray lifecycle.
- Copy buttons renamed: "Copy" (respects export format), "Copy Filled" (variables + format).
- Status bar shows hotkey hint on Windows.

### Notes
- Global hotkey and paste-to-window are Windows-only (Win32 API via ctypes). On other platforms the GUI works normally without these features.
- Hotkey listener runs in a `QThread` polling `PeekMessageW` to avoid blocking the UI.

---

## [0.2.0] - 2026-04-18

PyQt6 desktop GUI — the "Zotero for prompts."

### Added
- `promptcompanion.py` — single-file PyQt6 desktop application.
- Three-pane layout: category tree (with counts) | prompt list (sortable by quality) | preview pane.
- FTS5 full-text search bar with debounced input and prefix matching.
- Filter controls: role (system/user/assistant), quality threshold (20+/40+/60+), source key.
- Variable substitution panel: detects `{{placeholders}}` in prompt body, lets you fill inline.
- One-click copy: "Copy Raw" and "Copy with Variables" buttons with toast feedback.
- Catppuccin Mocha dark theme applied globally via QSS stylesheet.
- Quality badges: color-coded (green 60+, yellow 35+, grey <35) in list and preview.
- Tag pills displayed in preview pane metadata section.

### Changed
- `tools/build_index.py` now includes `quality` column + index in SQLite schema.
- `requirements.txt` updated with `PyQt6>=6.6.0`.
- README updated with GUI section, launch instructions, and feature checklist.

---

## [0.1.0] - 2026-04-18

Fourth source, body-hash deduplication, and quality scoring.

### Added
- `tools/import_llmprompt.py` — parses `abilzerian/LLM-Prompt-Library` (62 markdown prompts + 149 Jinja2 templates).
- Body-hash deduplication in `_common.py` — removes exact-body duplicates across all JSONL files, keeping the record with the most metadata.
- Quality scoring heuristic (0-100) in `_common.py` — scores every record on body length, structure, examples, variables, title quality, tags, and role clarity. Penalizes jailbreak patterns.
- `uncategorized.jsonl` bucket for prompts that resist auto-categorization (2 records).

### Changed
- Dataset grew from 3,562 to **3,751 records** (210 added from LLM-Prompt-Library, 21 duplicates removed).
- Every record now carries a `quality` score (min 6, max 88, avg 48.4, median 50).
- Registry updated with 4th source entry for `llmprompt`.
- README badges updated to v0.1.0 with prompt count.

### Stats
- 4 sources, 11 category files, 3,751 unique records, 0 validation errors, 0 duplicate bodies.

---

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
