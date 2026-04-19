#!/usr/bin/env python3
"""Validate every prompt record against data/schema.json. Report duplicates.

Exit code is non-zero if any record fails validation, any id is duplicated, or any
record's 'category' field does not match the file it lives in.
"""

from __future__ import annotations

import hashlib
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import _bootstrap, PROMPTS_DIR, load_schema, log, read_jsonl

_bootstrap(["jsonschema"])

from jsonschema import Draft202012Validator  # noqa: E402


def _body_hash(body: str) -> str:
    return hashlib.sha256(body.strip().lower().encode("utf-8")).hexdigest()[:16]


def main() -> int:
    schema = load_schema()
    validator = Draft202012Validator(schema)

    errors = 0
    total = 0
    ids_seen: dict[str, str] = {}
    bodies_seen: dict[str, list[str]] = defaultdict(list)
    per_file: dict[str, int] = {}

    for jsonl_path in sorted(PROMPTS_DIR.glob("*.jsonl")):
        file_category = jsonl_path.stem
        records = read_jsonl(jsonl_path)
        per_file[file_category] = len(records)
        for rec in records:
            total += 1

            for err in validator.iter_errors(rec):
                loc = "/".join(str(p) for p in err.absolute_path) or "<root>"
                log(f"SCHEMA {jsonl_path.name} [{rec.get('id', '?')}] {loc}: {err.message}")
                errors += 1

            rec_cat = rec.get("category", "")
            if rec_cat and rec_cat != file_category:
                log(f"CATEGORY {jsonl_path.name} [{rec.get('id', '?')}] category={rec_cat} does not match filename")
                errors += 1

            rec_id = rec.get("id")
            if rec_id:
                if rec_id in ids_seen:
                    log(f"DUP-ID {rec_id} in {jsonl_path.name} (also in {ids_seen[rec_id]})")
                    errors += 1
                else:
                    ids_seen[rec_id] = jsonl_path.name

            body = rec.get("body")
            if body:
                bodies_seen[_body_hash(body)].append(rec_id or "<no-id>")

    dup_bodies = 0
    for h, ids in bodies_seen.items():
        if len(ids) > 1:
            dup_bodies += 1
            if dup_bodies <= 20:
                log(f"DUP-BODY hash={h} ids={ids}")

    log("---")
    for cat in sorted(per_file):
        log(f"  {cat:15s}  {per_file[cat]:5d}")
    log(f"Total records:       {total}")
    log(f"Unique ids:          {len(ids_seen)}")
    log(f"Duplicate bodies:    {dup_bodies} (first 20 logged above)")
    log(f"Validation errors:   {errors}")

    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
