#!/usr/bin/env python3
"""Import codingthefuturewithai/software-dev-prompt-library markdown prompts.

Source: https://github.com/codingthefuturewithai/software-dev-prompt-library
License: MIT

Layout: prompts/<domain>/<audience>/<slug>.md plus optional *.meta.md files.
Each non-meta markdown file is treated as one software-development prompt.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import (
    build_record,
    dedupe_ids,
    ensure_upstream,
    infer_category,
    load_registry,
    log,
    merge_into_prompts_dir,
    slugify,
)


SOURCE_KEY = "devprompts"

DIR_MAP: dict[str, str] = {
    "architecture": "development",
    "code-analysis": "development",
    "coding": "development",
    "documentation": "writing",
    "learning": "productivity",
    "planning": "productivity",
    "requirements": "business",
    "testing": "development",
}

SKIP_FILENAMES = {"readme.md", "license.md", "contributing.md"}


def _strip_front_matter(text: str) -> str:
    lines = text.splitlines()
    if lines and lines[0].strip() == "---":
        for idx in range(1, len(lines)):
            if lines[idx].strip() == "---":
                return "\n".join(lines[idx + 1:]).lstrip("\n")
    return text


def _title_from_markdown(text: str, fallback: str) -> str:
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("# "):
            return stripped[2:].strip()[:200] or fallback
    return fallback


def walk_prompts(upstream: Path, src_meta: dict) -> list[dict]:
    records: list[dict] = []
    prompts_dir = upstream / "prompts"
    if not prompts_dir.exists():
        return records

    for md_path in sorted(prompts_dir.rglob("*.md")):
        if md_path.name.lower().endswith(".meta.md"):
            continue
        if md_path.name.lower() in SKIP_FILENAMES:
            continue

        try:
            raw = md_path.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            log(f"  skip {md_path}: {exc}")
            continue

        body = _strip_front_matter(raw).strip()
        if len(body) < 80:
            continue

        rel = md_path.relative_to(prompts_dir)
        parts = rel.parts
        top = parts[0].lower() if parts else ""
        title = _title_from_markdown(body, md_path.stem.replace("-", " ").replace("_", " ").title())
        category = DIR_MAP.get(top) or infer_category(title, body, default="development")

        tags = ["software-dev", slugify(top, 32)]
        if len(parts) > 2:
            tags.append(slugify(parts[1], 32))

        records.append(build_record(
            source_key=SOURCE_KEY,
            title=title,
            body=body,
            category=category,
            role="user",
            tags=tags,
            source_url=src_meta["repo"].replace(".git", ""),
            author=src_meta["author"],
            license_=src_meta["license"],
        ))
    return records


def main() -> int:
    registry = load_registry()
    src_meta = next(s for s in registry["sources"] if s["key"] == SOURCE_KEY)
    upstream = ensure_upstream(SOURCE_KEY)

    log(f"Walking {upstream}")
    records = dedupe_ids(walk_prompts(upstream, src_meta))
    log(f"Parsed {len(records)} records from {SOURCE_KEY}")

    counts = merge_into_prompts_dir(records)
    for cat, n in sorted(counts.items()):
        log(f"  {cat}.jsonl -> {n} total records")
    return 0


if __name__ == "__main__":
    sys.exit(main())
