#!/usr/bin/env python3
"""Import mustvlad/ChatGPT-System-Prompts markdown tree.

Source: https://github.com/mustvlad/ChatGPT-System-Prompts
License: MIT

Layout: prompts/<category>/<slug>.md — each file has:
  # Title
  ## System Message
  <prompt body>
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
)

SOURCE_KEY = "chatsys"

# Directory name -> PromptCompanion category
DIR_MAP: dict[str, str] = {
    "educational": "productivity",
    "entertainment": "creative",
    "utility": "development",
    "others": "",  # use infer_category
}

SKIP_FILENAMES = {"readme.md", "license", "license.md", "contributing.md"}


def _extract_system_message(text: str) -> str | None:
    """Extract the body after '## System Message' heading."""
    lines = text.splitlines()
    capture = False
    body_lines: list[str] = []
    for line in lines:
        stripped = line.strip()
        if stripped.lower().startswith("## system"):
            capture = True
            continue
        if capture:
            if stripped.startswith("## ") and body_lines:
                break  # next section
            body_lines.append(line)
    body = "\n".join(body_lines).strip()
    return body if len(body) >= 40 else None


def _title_from_heading(text: str, fallback: str) -> str:
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("# ") and not line.startswith("## "):
            t = line.lstrip("#").strip()
            if t:
                return t[:200]
    return fallback


def walk_prompts(upstream: Path, src_meta: dict) -> list[dict]:
    records: list[dict] = []
    prompts_dir = upstream / "prompts"
    if not prompts_dir.exists():
        return records

    for md_path in sorted(prompts_dir.rglob("*.md")):
        if md_path.name.lower() in SKIP_FILENAMES:
            continue
        parts = md_path.relative_to(prompts_dir).parts
        if not parts:
            continue

        try:
            raw = md_path.read_text(encoding="utf-8", errors="replace")
        except Exception as exc:
            log(f"  skip {md_path}: {exc}")
            continue

        body = _extract_system_message(raw)
        if not body:
            # Fallback: use everything after the first heading
            body = raw.strip()
            if len(body) < 40:
                continue

        dir_name = parts[0].lower() if len(parts) > 1 else ""
        title = _title_from_heading(raw, md_path.stem.replace("-", " ").replace("_", " ").title())

        category = DIR_MAP.get(dir_name, "")
        if not category:
            category = infer_category(title, body, default="system")

        tags = [dir_name] if dir_name else []
        tags.append("system-prompt")

        records.append(build_record(
            source_key=SOURCE_KEY,
            title=title,
            body=body,
            category=category,
            role="system",
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
