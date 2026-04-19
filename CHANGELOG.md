# Changelog

All notable changes to PromptCompanion are documented in this file. Format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and this project adheres to
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.5.2] - 2026-04-18

Title normalization and data quality audit.

### Fixed
- **Title normalization**: 1,725 titles cleaned across all JSONL files. Removed markdown links (`[text](url)` -> `text`), raw URLs, bold markers (`**text**`), backtick code formatting, fenced code block markers, leading heading markers (`#`), attribution prefixes ("Contributed by..."), and trailing punctuation.
- **U+2028 line separator bug**: Bodies containing Unicode Line Separator (U+2028) broke `splitlines()`-based JSONL readers. `write_jsonl` now escapes U+2028/U+2029 in all output.
- **Empty body cleanup**: 1 record dropped (`awesome-mc`) where body was identical to title with no other content.
- **Body title echo**: Titles duplicated at start of body are now stripped.

### Added
- `tools/normalize_titles.py` — reusable title normalization script with `--dry-run` mode. Handles markdown stripping, URL removal, attribution cleanup, body repair, and safe truncation to 120 chars.

### Changed
- Dataset: 3,797 -> **3,796 records** (1 garbage record removed).
- `tools/_common.py`: `write_jsonl` now sanitizes U+2028/U+2029 Unicode line separators to prevent JSONL corruption.

---

## [0.5.1] - 2026-04-18

Premium UX polish pass and build reliability.

### Improved
- **Design system**: Standardized radius (6/8/10px), type scale (11/12/13/16px), spacing rhythm (4-32px) across all components.
- **Keyboard shortcuts**: Ctrl+K and Ctrl+F to focus search, Escape to clear search or unfocus.
- **Toolbar**: Visual separator between search and filter combos. Count badge styled as a pill. All filter combos normalized to equal widths.
- **Category tree**: Visual separator between special categories (All/Favorites/Recent) and regular ones. Removed indentation for cleaner flat list.
- **Preview pane**: Symmetrical margins, better spacing rhythm between header/meta/tags/body. Wider favorite button with pointer cursor. Renamed "Copy Filled" to "Copy with Variables" for clarity.
- **Body text**: Font fallback chain (Cascadia Code, Fira Code, JetBrains Mono, Consolas) via `setFamilies()`. Increased padding.
- **Empty states**: Each state now has a contextual icon. Better copy ("No recent prompts" instead of "No history yet"). Multi-line subtitles for readability.
- **Button states**: All three tiers (default/primary/accent) now have distinct pressed states. Inputs show subtle border on hover before focus ring.
- **Scrollbars**: Wider (8px) with rounded handles for easier grabbing.
- **Splitter**: 3px grab area with hover highlight but 1px visual line.
- **Status bar**: Top border separator, increased padding, better contrast.
- **All buttons**: Pointer cursor on clickable elements.
- **Build script**: Generates `.ico` from logo. Cleans stale artifacts. Hidden imports for PyQt6. Excludes unnecessary modules to reduce size.
- **Freeze support**: Added `multiprocessing.freeze_support()` to prevent infinite restart loop in PyInstaller `--onefile` builds.

---

## [0.5.0] - 2026-04-18

Favorites, history, smart search ranking, PyInstaller build.

### Added
- **Favorites**: star button (★/☆) in preview header. Click to toggle. "Favorites" pseudo-category in the tree with count. Stored in `data/user/user.db` (persistent across sessions).
- **History**: every copy/paste action is recorded. "Recent" pseudo-category in the tree shows the last 100 unique prompts used. Empty states ("No favorites yet", "No history yet") with contextual guidance.
- **Smart FTS5 ranking**: search results now use bm25 relevance scoring with weighted fields — title matches are 10x more important than body, tags 5x, author 2x. Title-matching prompts surface first instead of being buried.
- **PyInstaller build script**: `build.py` produces a single `PromptCompanion.exe` bundling the prompt database and logo. User data (favorites, history) stored in `~/.promptcompanion/` for persistence across updates.
- `PromptDB.get_by_ids()` method for efficient ordered ID-based lookups (used by favorites/recent).
- `UserDB` class managing favorites table + history table with auto-pruning (keeps last 500 entries).
- `build.py` and `dist/` added to `.gitignore`.

### Changed
- Removed non-English prompts (248 zh/zh-TW records) and zhprompts source — English-only dataset.
- Dataset: 4,045 → **3,797 records** across 5 sources.
- Preview pane: favorite star button in header row, `action_performed` and `favorite_toggled` signals for tracking.
- Category tree: "Favorites" (yellow) and "Recent" (blue) shown above category list.
- Path resolution: `ROOT` and `USER_DIR` adapt for PyInstaller frozen mode (`sys._MEIPASS`).

---

## [0.4.0] - 2026-04-18

Two new sources — Chinese prompts and ChatGPT system prompts.

### Added
- `tools/import_zhprompts.py` — imports `PlexPt/awesome-chatgpt-prompts-zh` (MIT). 124 zh + 124 zh-TW Chinese-language "act as" prompts in JSON format.
- `tools/import_chatsys.py` — imports `mustvlad/ChatGPT-System-Prompts` (MIT). 46 categorized system prompts across educational, entertainment, utility, and other domains.
- Source registry updated with `zhprompts` and `chatsys` entries.
- ATTRIBUTION.md updated with both new sources.

### Changed
- Dataset grew from 3,751 to **4,045 records** (294 added, 0 duplicate bodies).
- Multilingual support: dataset now includes `zh` and `zh-TW` language prompts alongside English.
- Total sources: **6** (up from 4).
- README updated with new sources, importers, and prompt count badge.

### Stats
- 6 sources, 11 category files, 4,045 unique records, 0 validation errors, 0 duplicate bodies.

---

## [0.3.2] - 2026-04-18

Engineering hardening audit — 15 issues found and fixed across 7 files.

### Fixed
- **P0 Crash**: FTS5 `MATCH` with empty query after stripping special chars (e.g. searching `+++`) no longer crashes SQLite — the FTS clause is skipped when all terms strip to empty.
- **P0 Crash**: Malformed JSON lines in JSONL files are now logged and skipped instead of crashing the entire import/validate/index pipeline.
- **P0 Data loss**: `write_jsonl` now uses atomic temp-file-then-rename — a crash mid-write no longer corrupts the JSONL file.
- **P0 Data loss**: `build_index.py` now builds into a temp DB and replaces on success — a crash mid-build preserves the previous working index.
- **P1 Logic**: `dedupe_by_body` sort order fixed — now correctly keeps the earliest-created record as the canonical copy (was keeping latest due to `reverse=True` on timestamp strings).
- **P1 Logic**: `infer_category` single-word keywords now use word-boundary `\b` regex to prevent false matches (e.g. "write" no longer matches "typewriter", "plan" no longer matches "airplane").
- **P1 Logic**: `import_llmprompt.py` fenced block regex now accepts any language identifier (`python`, `json`, etc.) — was restricted to `markdown`/`text`/empty.

### Improved
- **Robustness**: `import_awesome.py` CSV opened with `utf-8-sig` encoding to handle BOM transparently.
- **Robustness**: `build_index.py` and `validate.py` exit early with clear message if prompts directory or JSONL files are missing.
- **Platform**: GUI system tray fallback — if `QSystemTrayIcon` is unavailable (some Linux window managers), the close button quits the app normally instead of trapping the user with no exit path.
- **GUI**: `_flash_button` replaced fragile `setObjectName`+`setStyle` hack with direct `setStyleSheet` save/restore — no longer risks permanently restyled buttons under rapid clicking.
- **GUI**: Tags HTML removed `border-radius` from inline styles (unsupported by Qt's rich text engine).
- **Maintainability**: `_dedupe_ids` extracted to `_common.dedupe_ids()` — removed duplicate copies from `import_awesome.py` and `import_llmprompt.py`.
- **Documentation**: `ATTRIBUTION.md` updated with missing 4th source (`abilzerian/LLM-Prompt-Library`).
- Removed dead `successBtn` QSS rule.

---

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
