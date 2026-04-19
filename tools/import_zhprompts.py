#!/usr/bin/env python3
"""Import PlexPt/awesome-chatgpt-prompts-zh JSON files.

Source: https://github.com/PlexPt/awesome-chatgpt-prompts-zh
License: MIT

Layout: prompts-zh.json and prompts-zh-TW.json — JSON arrays of {act, prompt}.
Same structure as f/awesome-chatgpt-prompts but in Chinese (zh and zh-TW).
"""

from __future__ import annotations

import json
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

SOURCE_KEY = "zhprompts"


def parse_json(json_path: Path, language: str, src_meta: dict) -> list[dict]:
    records: list[dict] = []
    try:
        data = json.loads(json_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        log(f"  skip {json_path}: {exc}")
        return records

    if not isinstance(data, list):
        log(f"  skip {json_path}: expected JSON array, got {type(data).__name__}")
        return records

    for item in data:
        title = (item.get("act") or "").strip()
        body = (item.get("prompt") or "").strip()
        if not title or not body or len(body) < 20:
            continue

        category = infer_category(title, body, default="roleplay")
        tags = ["act-as", language]

        records.append(build_record(
            source_key=SOURCE_KEY,
            title=title,
            body=body,
            category=category,
            tags=tags,
            language=language,
            source_url=src_meta["repo"].replace(".git", ""),
            author=src_meta["author"],
            license_=src_meta["license"],
        ))
    return records


def main() -> int:
    registry = load_registry()
    src_meta = next(s for s in registry["sources"] if s["key"] == SOURCE_KEY)
    upstream = ensure_upstream(SOURCE_KEY)

    records: list[dict] = []

    zh_path = upstream / "prompts-zh.json"
    if zh_path.exists():
        zh_recs = parse_json(zh_path, "zh", src_meta)
        log(f"Parsed {len(zh_recs)} records from prompts-zh.json")
        records.extend(zh_recs)

    tw_path = upstream / "prompts-zh-TW.json"
    if tw_path.exists():
        tw_recs = parse_json(tw_path, "zh-TW", src_meta)
        log(f"Parsed {len(tw_recs)} records from prompts-zh-TW.json")
        records.extend(tw_recs)

    records = dedupe_ids(records)
    log(f"Total: {len(records)} records from {SOURCE_KEY}")

    counts = merge_into_prompts_dir(records)
    for cat, n in sorted(counts.items()):
        log(f"  {cat}.jsonl -> {n} total records")
    return 0


if __name__ == "__main__":
    sys.exit(main())
