# Prompt Record Schema

Every prompt in `data/prompts/*.jsonl` is a JSON object conforming to
[`data/schema.json`](../data/schema.json). One record per line.

This document is the human-readable companion to that schema — it explains the
*why* behind each field so curators and importers apply them consistently.

## Example

```json
{
  "id": "awesome-linux-terminal",
  "title": "Linux Terminal",
  "body": "I want you to act as a linux terminal. I will type commands and you will reply with what the terminal should show. I want you to only reply with the terminal output inside one unique code block, and nothing else...",
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
  "updated": "2026-04-18T00:00:00Z"
}
```

## Fields

### Identity

| Field | Type | Required | Notes |
|---|---|---|---|
| `id` | string | yes | Stable slug `<source-key>-<normalized-title>`. Lowercase, dash-separated, 2-128 chars. Never changes once assigned. |
| `title` | string | yes | 1-200 chars. Shown in the list view. |
| `version` | int | yes | Starts at 1. Bump on any curation edit to `body`, `title`, `category`, or `tags`. |

### Content

| Field | Type | Required | Notes |
|---|---|---|---|
| `body` | string | yes | The prompt text. Markdown allowed. Use `{{variable_name}}` for template placeholders. |
| `role` | enum | yes | `system` / `user` / `assistant`. Default `user`. Use `system` only for prompts intended as system messages. |

### Organization

| Field | Type | Required | Notes |
|---|---|---|---|
| `category` | enum | yes | Exactly one of the top-level categories in [`data/taxonomy.json`](../data/taxonomy.json). Use `uncategorized` only as a last resort. |
| `tags` | string[] | yes (may be empty) | Up to 12 lowercase-dashed tags. Prefer vocabulary from the category's `example_tags`. |
| `variables` | object[] | no | Auto-populated by importers when `{{name}}` patterns are detected in the body. Each item: `{name, default?, description?}`. |

### Targeting

| Field | Type | Required | Notes |
|---|---|---|---|
| `target_models` | string[] | yes | Model IDs. Use `["any"]` when the prompt is model-agnostic. Otherwise prefer identifiers like `claude-3.5-sonnet`, `gpt-4o`, `gemini-1.5-pro`. |
| `language` | string | yes | BCP-47 code (`en`, `zh`, `pt-BR`). Default `en`. |

### Provenance

| Field | Type | Required | Notes |
|---|---|---|---|
| `source` | URI | yes | URL of the upstream source (repo, website, etc.). |
| `author` | string | no | Attribution string. Populated when the upstream record identifies an author. |
| `license` | enum | yes | SPDX identifier. Only `CC0-1.0` and `MIT` are accepted for bundled records. |
| `tested_with` | string | no | Free-text note on which models this has been verified against. |

### Lifecycle

| Field | Type | Required | Notes |
|---|---|---|---|
| `created` | date-time | yes | ISO 8601 UTC timestamp of first import. Never changes. |
| `updated` | date-time | yes | ISO 8601 UTC timestamp of most recent edit. Set equal to `created` on import. |
| `quality` | int 0-100 | no | Curator score. Reserved for v0.1.x. |
| `deprecated` | bool | no | Defaults to `false`. Set `true` for obsolete prompts we preserve for history. |
| `notes` | string | no | Curator rationale, caveats, known failure modes. |

## ID Generation Rules

`id = "<source-key>-<slug>"` where:

- `source-key` is the `key` field from [`data/sources/registry.json`](../data/sources/registry.json) (e.g. `awesome`, `bigprompt`, `sysprompt`).
- `slug` is the `title` lowercased, with non-alphanumeric runs collapsed to `-`, trimmed, and truncated to ~96 chars so the full id fits in 128.

If two records would produce the same id within a source, suffix `-2`, `-3`, ...

## File Layout

Prompts live under `data/prompts/<category>.jsonl`, one JSON object per line.
UTF-8. No trailing comma, no surrounding array. This layout keeps per-category
diffs clean and lets importers append without rewriting the whole file.

## Validation

Run `python tools/validate.py` after any import or manual edit. The validator:

1. Loads `data/schema.json`.
2. Walks every `*.jsonl` under `data/prompts/`.
3. Validates each record against the schema.
4. Reports duplicate `id`s, duplicate-body matches, and category-file mismatches.
5. Exits non-zero on any failure.

## Index Build

Run `python tools/build_index.py` to emit `data/index/prompts.db` — a SQLite 3
database with an FTS5 virtual table over `title`, `body`, `tags`, and
`author`. The GUI (v0.2.x) reads directly from this file.
