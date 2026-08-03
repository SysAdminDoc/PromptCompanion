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


def validate_translation_links(records_by_id: dict[str, dict]) -> list[str]:
    messages: list[str] = []
    for rec_id, rec in sorted(records_by_id.items()):
        translation_of = str(rec.get("translation_of") or "").strip()
        translated_from = str(rec.get("translated_from") or "").strip()
        translator = str(rec.get("translator") or "").strip()
        language = str(rec.get("language") or "").strip()

        if not translation_of:
            if translated_from or translator:
                messages.append(
                    f"TRANSLATION [{rec_id}] translated_from/translator requires translation_of"
                )
            continue

        if translation_of == rec_id:
            messages.append(f"TRANSLATION [{rec_id}] translation_of cannot point to itself")
            continue

        source = records_by_id.get(translation_of)
        if not source:
            messages.append(f"TRANSLATION [{rec_id}] translation_of={translation_of} was not found")
            continue

        source_language = str(source.get("language") or "").strip()
        if not translated_from:
            messages.append(f"TRANSLATION [{rec_id}] translated_from is required")
        elif translated_from != source_language:
            messages.append(
                f"TRANSLATION [{rec_id}] translated_from={translated_from} does not match "
                f"{translation_of} language={source_language}"
            )

        if language and source_language and language == source_language:
            messages.append(
                f"TRANSLATION [{rec_id}] language={language} matches original language"
            )

    return messages


def main() -> int:
    if not PROMPTS_DIR.exists():
        log("No data/prompts/ directory found. Run importers first.")
        return 1

    jsonl_files = sorted(PROMPTS_DIR.glob("*.jsonl"))
    if not jsonl_files:
        log("No JSONL files in data/prompts/. Run importers first.")
        return 1

    schema = load_schema()
    validator = Draft202012Validator(schema)

    errors = 0
    total = 0
    ids_seen: dict[str, str] = {}
    records_by_id: dict[str, dict] = {}
    bodies_seen: dict[str, list[str]] = defaultdict(list)
    per_file: dict[str, int] = {}

    for jsonl_path in jsonl_files:
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
                    records_by_id[rec_id] = rec

            body = rec.get("body")
            if body:
                bodies_seen[_body_hash(body)].append(rec_id or "<no-id>")

    for message in validate_translation_links(records_by_id):
        log(message)
        errors += 1

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
