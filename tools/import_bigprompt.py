#!/usr/bin/env python3
"""Import 0xeb/TheBigPromptLibrary markdown tree into data/prompts/*.jsonl.

Source: https://github.com/0xeb/TheBigPromptLibrary
License: MIT

Layout (as of 2026): top-level directories like CustomInstructions/, SystemPrompts/,
SecurityGPTs/, Articles/, Guides/, with one markdown file per prompt. We walk the
tree, treat each .md as a single prompt, and map the top-level directory to a
category.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import (
    build_record,
    ensure_upstream,
    infer_category,
    load_registry,
    log,
    merge_into_prompts_dir,
)


SOURCE_KEY = "bigprompt"

# Directory-name -> (category, extra_tags, role)
DIR_MAP: dict[str, tuple[str | None, tuple[str, ...], str]] = {
    "systemprompts":      ("system",  ("custom-gpt", "system"),     "system"),
    "custominstructions": ("system",  ("custom-instructions",),     "system"),
    "security":           ("system",  ("security", "jailbreak"),    "system"),
    "securitygpts":       ("system",  ("security", "jailbreak"),    "system"),
    "jailbreak":          ("system",  ("jailbreak", "caution"),     "system"),
    "tools":              ("system",  ("tool",),                    "system"),
    "articles":           (None,      (),                           "user"),
    "guides":             (None,      (),                           "user"),
    "opensourceprojects": (None,      (),                           "user"),
    ".github":            (None,      (),                           "user"),
}

SKIP_FILENAMES = {"readme.md", "license", "license.md", "contributing.md", "code_of_conduct.md"}


def _title_from_md(text: str, fallback: str) -> str:
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


def walk_markdown(upstream: Path, src_meta: dict) -> list[dict]:
    records: list[dict] = []
    seen_ids: dict[str, int] = {}

    for md_path in upstream.rglob("*.md"):
        parts = md_path.relative_to(upstream).parts
        if not parts:
            continue
        top_dir = parts[0].lower()
        if top_dir.startswith("."):
            continue
        if md_path.name.lower() in SKIP_FILENAMES:
            continue

        mapping = DIR_MAP.get(top_dir)
        if mapping and mapping[0] is None:
            continue

        try:
            raw = md_path.read_text(encoding="utf-8", errors="replace")
        except Exception as exc:
            log(f"  skip {md_path}: {exc}")
            continue

        body = _strip_front_matter(raw).strip()
        if len(body) < 40:
            continue

        title = _title_from_md(body, md_path.stem.replace("-", " ").replace("_", " ").strip())
        if not title:
            continue

        if mapping is not None:
            category, extra_tags, role = mapping
        else:
            category = infer_category(title, body, default="system")
            extra_tags = ()
            role = "user"

        tags = list(extra_tags)
        for p in parts[1:-1]:
            slug = p.lower().replace(" ", "-")
            if slug and slug.isascii() and len(slug) < 32:
                tags.append(slug)

        rec = build_record(
            source_key=SOURCE_KEY,
            title=title,
            body=body,
            category=category,
            role=role,
            tags=tags,
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
    records = walk_markdown(upstream, src_meta)
    log(f"Parsed {len(records)} records from {SOURCE_KEY}")

    counts = merge_into_prompts_dir(records)
    for cat, n in sorted(counts.items()):
        log(f"  {cat}.jsonl -> {n} total records")
    return 0


if __name__ == "__main__":
    sys.exit(main())
