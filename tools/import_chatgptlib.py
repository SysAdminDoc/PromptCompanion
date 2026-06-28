#!/usr/bin/env python3
"""Import pacholoamit/chatgpt-prompts TypeScript prompt definitions.

Source: https://github.com/pacholoamit/chatgpt-prompts
License: MIT

Layout: src/lib/prompts.ts with repeated:
  export const promptName = (...) => {
    const prompt = `...`;
  }
"""

from __future__ import annotations

import re
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


SOURCE_KEY = "chatgptlib"
PROMPT_RE = re.compile(
    r"export const\s+([A-Za-z0-9_]+)\s*=.*?const prompt\s*=\s*`((?:\\`|[^`])*)`;",
    re.DOTALL,
)


def _title_from_identifier(identifier: str) -> str:
    spaced = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", identifier).replace("_", " ")
    return spaced.strip().title()


def _decode_template_literal(text: str) -> str:
    return (
        text.replace("\\`", "`")
        .replace("\\${", "${")
        .replace("\\n", "\n")
        .replace("\\t", "\t")
    )


def parse_prompts(upstream: Path, src_meta: dict) -> list[dict]:
    prompt_file = upstream / "src" / "lib" / "prompts.ts"
    if not prompt_file.exists():
        return []
    raw = prompt_file.read_text(encoding="utf-8", errors="replace")
    records: list[dict] = []
    for identifier, template in PROMPT_RE.findall(raw):
        title = _title_from_identifier(identifier)
        body = _decode_template_literal(template).strip()
        if len(body) < 40:
            continue
        category = infer_category(title, body, default="roleplay")
        records.append(build_record(
            source_key=SOURCE_KEY,
            title=title,
            body=body,
            category=category,
            role="user",
            tags=["chatgpt-prompts"],
            source_url=src_meta["repo"].replace(".git", ""),
            author=src_meta["author"],
            license_=src_meta["license"],
        ))
    return records


def main() -> int:
    registry = load_registry()
    src_meta = next(s for s in registry["sources"] if s["key"] == SOURCE_KEY)
    upstream = ensure_upstream(SOURCE_KEY)

    log(f"Parsing {upstream}")
    records = dedupe_ids(parse_prompts(upstream, src_meta))
    log(f"Parsed {len(records)} records from {SOURCE_KEY}")

    counts = merge_into_prompts_dir(records)
    for cat, n in sorted(counts.items()):
        log(f"  {cat}.jsonl -> {n} total records")
    return 0


if __name__ == "__main__":
    sys.exit(main())
