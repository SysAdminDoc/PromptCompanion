# Changelog

All notable changes to PromptCompanion are documented in this file. Format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and this project adheres to
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Quality scoring v2 with length, structure, variables, source rank, and review signals.
- Deterministic stale/obsolete-model deprecation flags and reasons in the prompt schema and index.
- Recency-aware BM25 ranking while preserving fast results-as-you-type search.
- Persistent collection/category tree expansion state and keyboard-only prompt navigation.
- Markdown editor drafts and multi-select JSON/Markdown bundle export.
- Optional ChatGPT/Claude/Ollama URL handoff, local tiktoken token estimates, and model-provider filtering.

## [0.8.1] - 2026-06-28

Language tagging and translation metadata.

### Added
- Language filter in the desktop toolbar, including local overlay/private prompt languages.
- Optional `translation_of`, `translated_from`, and `translator` fields for translated prompt records.
- Validator checks that translated records reference an existing original and declare the original language.
- Translation metadata in Markdown, Front Matter, and JSON exports.

---

## [0.8.0] - 2026-06-28

Library growth.

### Added
- `codingthefuturewithai/software-dev-prompt-library` as a vetted MIT upstream source.
- `pacholoamit/chatgpt-prompts` as a vetted MIT upstream source with TypeScript template literal parsing.
- Importers for software-dev markdown prompts and TypeScript ChatGPT prompt definitions.

### Changed
- Dataset rebuilt to 3,585 records across 7 sources after exact-body dedupe and quality rescoring.

---

## [0.7.4] - 2026-06-28

Front matter export.

### Added
- Front Matter export profile for static-site-friendly Markdown.
- YAML metadata for title, prompt ID, role, category, quality, language, source, author, license, updated timestamp, tags, and local tags.
- Unit coverage for quoted YAML fields and tag list output.

---

## [0.7.3] - 2026-06-28

Snippet includes.

### Added
- `{{include:...}}` expansion in preview, copy, paste, and prompt chain output.
- Include resolver for exact prompt IDs and `category/title-slug` references.
- Variable extraction from resolved snippets so included placeholders appear in the Variables panel.
- Unit coverage for include resolution, expansion, and include-aware variable filling.

---

## [0.7.2] - 2026-06-28

Live preview stats.

### Added
- Prompt preview character count and approximate token count label.
- Counts update as variable values are filled, edited, or history diffs are shown.
- Unit coverage for prompt stat formatting and token estimation.

---

## [0.7.1] - 2026-06-28

Variable presets.

### Added
- Per-prompt Safe defaults and Aggressive variable profiles stored in the local overlay.
- Variables panel controls to apply, save, and clear prompt-specific variable presets.
- Unit coverage for preset normalization, persistence, and filled prompt output.

---

## [0.7.0] - 2026-06-28

Prompt chains.

### Added
- In-memory prompt chain queue with Add Step, Copy Chain, and Clear Chain controls.
- Chain copy output as a structured multi-step prompt pipeline.
- Shared variable passthrough across chain steps when the same placeholder appears in multiple prompts.
- Unit coverage for chain composition and variable passthrough.

---

## [0.6.4] - 2026-06-28

Markdown import folder.

### Added
- `imports/` folder under the user data directory for local `.md` prompt files.
- Launch-time markdown sync into private overlay records with stable path-based IDs.
- Simple front matter support for title, category, tags, role, author, and language.
- Import update detection via SHA-256 content hash, with local history snapshots when imported files change.

---

## [0.6.3] - 2026-06-27

Local version history.

### Added
- Overlay saves now retain the prior local revision snapshot for each prompt.
- Preview History button toggles an embedded unified diff against the latest saved local revision.
- Tests covering local history persistence and diff output.

---

## [0.6.2] - 2026-06-27

Local notes and tags.

### Added
- Per-prompt local notes field stored in the overlay without altering bundled source records.
- Local tags stored separately from upstream/source tags and shown in the Local Details panel.
- Overlay search now matches local notes and local tags without rebuilding the bundled FTS index.

---

## [0.6.1] - 2026-06-27

Private prompts.

### Added
- `New Private` toolbar action for creating local-only prompts stored in the user overlay.
- Private pseudo-category in the tree, with private prompts included in total/search/source filtering without touching the bundled index.
- Private prompt copy/export is constrained to plain text so local-only records are not emitted as Markdown/JSON export profiles.
- Optional encrypted private prompt overlay lines via `PROMPTCOMPANION_PRIVATE_PASSPHRASE`.

---

## [0.6.0] - 2026-06-27

Personal overlay editing.

### Added
- Local prompt overlay stored as `data/user/overlay.jsonl` in source runs and `~/.promptcompanion/overlay.jsonl` in frozen builds.
- Inline preview editing for bundled prompt titles and bodies with Save, Cancel, and Revert controls.
- Overlay-aware search, favorites, recent prompts, category counts, and source filters without rebuilding the bundled FTS index.
- Focused unit tests covering overlay persistence, variable extraction, and overlay-only search matches.

### Fixed
- Frozen builds now skip runtime dependency bootstrapping and include a PyInstaller multiprocessing runtime hook.

---

## [0.5.3] - 2026-04-18

Comprehensive prompt library audit and quality pass.

### Fixed
- **GPT title extraction**: 1,570 records titled "GPT URL" now have real GPT names extracted from body metadata (`GPT Title:` field).
- **Title deduplication**: 94 within-source title duplicates removed (multiple versions of same GPT/system prompt — kept highest quality version).
- **Near-duplicate bodies**: 23 records with identical first-500-chars removed (kept best quality/longest body).
- **Non-English cleanup**: 140 non-English records removed (CJK, Cyrillic, Arabic content in an English-only dataset).
- **Cross-source duplicates**: 26 cross-source title duplicates removed (e.g., same prompt in awesome + chatsys).
- **Garbage records**: 2 records removed (tiny body <40 chars, unfixable title).

### Added
- `tools/audit_fix.py` — comprehensive audit + fix script with `--dry-run` mode. Handles GPT title extraction, non-English removal, body/title dedup, URL cleanup, title truncation.

### Changed
- Dataset: 3,796 -> **3,511 records** (285 removed: 140 non-English, 94 title dupes, 23 body dupes, 26 cross-source dupes, 2 garbage).
- All 1,570 "GPT URL" placeholder titles replaced with actual GPT names.

---

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
