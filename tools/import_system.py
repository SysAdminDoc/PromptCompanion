#!/usr/bin/env python3
"""Import dontriskit/awesome-ai-system-prompts markdown tree.

Source: https://github.com/dontriskit/awesome-ai-system-prompts
License: MIT

Layout: top-level folders per product (claude/, chatgpt/, cursor/, v0/, windsurf/,
perplexity/, ...), each containing .md / .txt files with system prompts. We emit one
record per file, tag with the product name, and force role=system.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import (
    build_record,
    ensure_upstream,
    load_registry,
    log,
    merge_into_prompts_dir,
)


SOURCE_KEY = "sysprompt"

# Product folder -> target_models
PRODUCT_MODELS: dict[str, list[str]] = {
    "claude": ["claude-3.5-sonnet", "claude-3-opus"],
    "anthropic": ["claude-3.5-sonnet"],
    "chatgpt": ["gpt-4o", "gpt-4"],
    "openai": ["gpt-4o", "gpt-4"],
    "gpt": ["gpt-4o", "gpt-4"],
    "cursor": ["cursor"],
    "v0": ["v0"],
    "vercel": ["v0"],
    "windsurf": ["windsurf"],
    "perplexity": ["perplexity"],
    "gemini": ["gemini-1.5-pro", "gemini-1.5-flash"],
    "google": ["gemini-1.5-pro"],
    "deepseek": ["deepseek-v3"],
    "grok": ["grok"],
    "xai": ["grok"],
    "llama": ["llama-3.1"],
    "meta": ["llama-3.1"],
    "mistral": ["mistral-large"],
    "devin": ["devin"],
    "replit": ["replit-agent"],
    "bolt": ["bolt"],
    "lovable": ["lovable"],
    "same": ["same"],
}

SKIP_FILENAMES = {"readme.md", "license", "license.md", "contributing.md", "code_of_conduct.md", ".gitignore"}


def _title_from_text(text: str, fallback: str) -> str:
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("#"):
            return line.lstrip("#").strip()[:200] or fallback
        if line:
            return line[:200]
    return fallback


def _strip_front_matter(text: str) -> str:
    lines = text.splitlines()
    if lines and lines[0].strip() == "---":
        for i in range(1, len(lines)):
            if lines[i].strip() == "---":
                return "\n".join(lines[i + 1:]).lstrip("\n")
    return text


def walk_prompts(upstream: Path, src_meta: dict) -> list[dict]:
    records: list[dict] = []
    seen_ids: dict[str, int] = {}

    for path in sorted(list(upstream.rglob("*.md")) + list(upstream.rglob("*.txt"))):
        parts = path.relative_to(upstream).parts
        if not parts:
            continue
        if path.name.lower() in SKIP_FILENAMES:
            continue
        if parts[0].startswith("."):
            continue

        try:
            raw = path.read_text(encoding="utf-8", errors="replace")
        except Exception as exc:
            log(f"  skip {path}: {exc}")
            continue

        body = _strip_front_matter(raw).strip()
        if len(body) < 40:
            continue

        product = parts[0].lower()
        tool_hint = path.stem.replace("-", " ").replace("_", " ").strip()
        if len(parts) > 1:
            # Use the leaf filename as the tool name
            raw_title = path.stem.replace("-", " ").replace("_", " ")
            title = f"{product.title()} — {raw_title}"[:200]
        else:
            title = tool_hint.title()[:200]

        heading_title = _title_from_text(body, "")
        if heading_title and len(heading_title) > 4:
            title = f"{product.title()} — {heading_title}"[:200]

        target_models = PRODUCT_MODELS.get(product, ["any"])
        tags = [product] + [p.lower().replace(" ", "-") for p in parts[1:-1] if p]
        tags = [t for t in tags if t.isascii() and len(t) < 32]

        rec = build_record(
            source_key=SOURCE_KEY,
            title=title,
            body=body,
            category="system",
            role="system",
            tags=tags,
            target_models=target_models,
            source_url=src_meta["repo"].replace(".git", ""),
            author=src_meta["author"],
            license_=src_meta["license"],
        )
        base = rec["id"]
        n = seen_ids.get(base, 0) + 1
        seen_ids[base] = n
        if n > 1:
            rec["id"] = f"{base}-{n}"
        records.append(rec)
    return records


def main() -> int:
    registry = load_registry()
    src_meta = next(s for s in registry["sources"] if s["key"] == SOURCE_KEY)
    upstream = ensure_upstream(SOURCE_KEY)

    log(f"Walking {upstream}")
    records = walk_prompts(upstream, src_meta)
    log(f"Parsed {len(records)} records from {SOURCE_KEY}")

    counts = merge_into_prompts_dir(records)
    for cat, n in sorted(counts.items()):
        log(f"  {cat}.jsonl -> {n} total records")
    return 0


if __name__ == "__main__":
    sys.exit(main())
