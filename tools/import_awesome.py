#!/usr/bin/env python3
"""Import f/awesome-chatgpt-prompts CSV into data/prompts/*.jsonl.

Source: https://github.com/f/awesome-chatgpt-prompts
License: CC0-1.0
Format: CSV with columns (act, prompt, for_devs)
"""

from __future__ import annotations

import csv
import sys
from pathlib import Path

csv.field_size_limit(min(sys.maxsize, 2**31 - 1))

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import (
    build_record,
    ensure_upstream,
    infer_category,
    load_registry,
    log,
    merge_into_prompts_dir,
)


SOURCE_KEY = "awesome"


def _coerce_for_devs(raw: str) -> bool:
    return str(raw).strip().lower() in {"true", "1", "yes"}


def parse_csv(csv_path: Path, src_meta: dict) -> list[dict]:
    records: list[dict] = []
    with csv_path.open("r", encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            title = (row.get("act") or "").strip()
            body = (row.get("prompt") or "").strip()
            if not title or not body:
                continue
            for_devs = _coerce_for_devs(row.get("for_devs", "") or "")

            tags: list[str] = []
            if for_devs:
                tags.append("developer")
            tags.append("act-as")

            category = infer_category(title, body, default="roleplay")
            if for_devs and category == "roleplay":
                category = "development"

            records.append(build_record(
                source_key=SOURCE_KEY,
                title=title,
                body=body,
                category=category,
                tags=tags,
                source_url=src_meta["repo"].replace(".git", ""),
                author=src_meta["author"],
                license_=src_meta["license"],
            ))
    return records


def _dedupe_ids(records: list[dict]) -> list[dict]:
    seen: dict[str, int] = {}
    out: list[dict] = []
    for r in records:
        base = r["id"]
        n = seen.get(base, 0) + 1
        seen[base] = n
        if n > 1:
            r = {**r, "id": f"{base}-{n}"}
        out.append(r)
    return out


def main() -> int:
    registry = load_registry()
    src_meta = next(s for s in registry["sources"] if s["key"] == SOURCE_KEY)
    upstream = ensure_upstream(SOURCE_KEY)
    csv_path = upstream / src_meta["entry_path"]
    if not csv_path.exists():
        raise SystemExit(f"Missing CSV: {csv_path}")

    log(f"Parsing {csv_path}")
    records = _dedupe_ids(parse_csv(csv_path, src_meta))
    log(f"Parsed {len(records)} records from {SOURCE_KEY}")

    counts = merge_into_prompts_dir(records)
    for cat, n in sorted(counts.items()):
        log(f"  {cat}.jsonl -> {n} total records")
    return 0


if __name__ == "__main__":
    sys.exit(main())
