#!/usr/bin/env python3
"""Apply PromptCompanion's deterministic local tag suggestions to JSONL data."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import apply_suggested_tags, log, read_jsonl, write_jsonl  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Suggest taxonomy tags locally without a model or network request."
    )
    parser.add_argument(
        "--prompts-dir",
        type=Path,
        default=Path(__file__).resolve().parent.parent / "data" / "prompts",
    )
    parser.add_argument("--dry-run", action="store_true", help="Report changes without writing files")
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Replace existing tags with suggestions (default appends conservatively)",
    )
    parser.add_argument("--max-new", type=int, default=5, help="Maximum suggestions per record")
    args = parser.parse_args(argv)

    if not args.prompts_dir.exists():
        log(f"Prompt directory not found: {args.prompts_dir}")
        return 1

    changed = 0
    total = 0
    for path in sorted(args.prompts_dir.glob("*.jsonl")):
        records = read_jsonl(path)
        total += len(records)
        file_changed = apply_suggested_tags(
            records,
            overwrite=args.overwrite,
            max_new=max(0, args.max_new),
        )
        changed += file_changed
        if file_changed and not args.dry_run:
            write_jsonl(path, records)
        if file_changed:
            log(f"  {path.name}: {file_changed} records {'would change' if args.dry_run else 'changed'}")

    action = "would change" if args.dry_run else "changed"
    log(f"Scanned {total} records; {changed} {action}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
