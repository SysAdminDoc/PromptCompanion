#!/usr/bin/env python3
"""Normalize prompt titles across all JSONL files.

Fixes:
- Markdown links [text](url) -> extract text portion
- Raw URLs stripped from titles
- Markdown bold **text** -> text
- Backtick code `text` -> text
- Leading # heading markers removed
- Trailing colons and ellipses cleaned
- Excessive whitespace collapsed
- Titles capped at 120 chars with clean truncation
- Attribution prefixes ("Contributed by...", "Credits to...") cleaned
- Malformed JSON lines repaired (body with literal newlines)
- Body de-duplicated from title (removes title line from body start)

Run: python tools/normalize_titles.py
     python tools/normalize_titles.py --dry-run   (preview without writing)
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import PROMPTS_DIR, log, read_jsonl, write_jsonl


def normalize_title(title: str) -> str:
    """Clean a single title string."""
    t = title

    # Strip leading markdown heading markers: "## Title" -> "Title"
    t = re.sub(r'^#{1,6}\s+', '', t)

    # Convert markdown links to just the text: [text](url) -> text
    t = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', t)

    # Remove raw URLs
    t = re.sub(r'https?://\S+', '', t)

    # Remove markdown bold: **text** -> text
    t = re.sub(r'\*\*(.+?)\*\*', r'\1', t)

    # Remove markdown italic (underscores): __text__ -> text
    t = re.sub(r'__(.+?)__', r'\1', t)

    # Remove fenced code block markers: ```markdown -> empty
    t = re.sub(r'```\w*', '', t)

    # Remove backtick code formatting: `text` -> text
    t = re.sub(r'`([^`]+)`', r'\1', t)

    # Clean attribution prefixes that aren't actual titles
    # "Contributed by Name" -> "Name" (only if that's ALL the title is)
    t = re.sub(r'^(?:Contributed?\s+by|Credits?\s+to(?:\s+X\s+user)?)\s*:?\s*', '', t, flags=re.IGNORECASE)

    # Strip "source" or "check" link remnants
    t = re.sub(r'\s*\(?(?:source|check)\s*:?\s*\)?\s*$', '', t, flags=re.IGNORECASE)

    # Clean common leftover patterns
    t = re.sub(r'^From\s+:\s*', '', t)  # "From :" leftover
    t = re.sub(r'\s*:\s*$', '', t)       # trailing colon
    t = re.sub(r'\s*\.{3,}$', '', t)     # trailing ellipsis
    t = re.sub(r'\s*\.\s*$', '', t)      # trailing period (for "Contribute by X.")

    # Collapse whitespace
    t = re.sub(r'\s+', ' ', t).strip()

    # Cap at 120 chars, break at word boundary
    if len(t) > 120:
        t = t[:120]
        # Try to break at last space
        last_space = t.rfind(' ', 60)
        if last_space > 60:
            t = t[:last_space]
        t = t.rstrip(' -,;:')

    return t


def clean_body_title_echo(title: str, body: str) -> str:
    """Remove the title from the start of the body if it's echoed there."""
    lines = body.split('\n')
    if not lines:
        return body

    first = lines[0].strip()

    # Body starts with "# Title" that matches
    if first.startswith('#'):
        heading_text = first.lstrip('#').strip()
        if heading_text == title or heading_text.lower() == title.lower():
            body = '\n'.join(lines[1:]).lstrip('\n')

    # Body starts with the exact title text
    elif first == title:
        body = '\n'.join(lines[1:]).lstrip('\n')

    return body


def repair_malformed_lines(filepath: Path) -> list[dict]:
    """Read JSONL, repairing records where body newlines split across lines."""
    records = []
    text = filepath.read_text(encoding='utf-8')
    lines = text.split('\n')

    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if not line:
            i += 1
            continue

        # Try parsing as-is first
        try:
            records.append(json.loads(line))
            i += 1
            continue
        except json.JSONDecodeError:
            pass

        # This line starts with { -- it's a broken JSON record whose body
        # contained literal newlines. Rejoin subsequent lines until we get
        # valid JSON by escaping the embedded newlines.
        if line.startswith('{'):
            accumulated = line
            j = i + 1
            repaired = False
            while j < len(lines) and j < i + 100:  # generous limit
                next_line = lines[j]
                # If next line starts with {, it's a new record -- stop
                if next_line.strip().startswith('{') and j > i + 1:
                    break
                # Escape the newline join point as literal \n in the JSON string
                accumulated += '\\n' + next_line.strip()
                try:
                    records.append(json.loads(accumulated))
                    repaired = True
                    i = j + 1
                    break
                except json.JSONDecodeError:
                    j += 1

            if repaired:
                continue

        # Can't repair - skip this line
        log(f"  SKIP unfixable line {i+1} in {filepath.name}")
        i += 1

    return records


def main() -> int:
    dry_run = '--dry-run' in sys.argv

    total_fixed = 0
    total_repaired = 0
    total_removed = 0
    total_records = 0
    changes: list[tuple[str, str, str]] = []  # (id, old, new)

    for jsonl_path in sorted(PROMPTS_DIR.glob('*.jsonl')):
        records = repair_malformed_lines(jsonl_path)
        initial_count = len(records)
        repaired_diff = initial_count - len(read_jsonl(jsonl_path))
        if repaired_diff > 0:
            total_repaired += repaired_diff

        fixed_records = []
        for rec in records:
            total_records += 1
            old_title = rec.get('title', '')
            new_title = normalize_title(old_title)

            # If normalization produced an empty/tiny title, try to derive a better one
            if not new_title or len(new_title) < 3:
                # Try first meaningful line from body
                for bline in rec.get('body', '').split('\n'):
                    bline = bline.lstrip('#').strip()
                    bline = re.sub(r'```\w*', '', bline).strip()
                    if len(bline) >= 10 and not bline.startswith('{') and not bline.startswith('<'):
                        new_title = normalize_title(bline)
                        if len(new_title) >= 5:
                            break

            # Still too short? Derive from record ID
            if not new_title or len(new_title) < 3:
                id_parts = rec['id'].split('-', 1)
                fallback = id_parts[1] if len(id_parts) > 1 else id_parts[0]
                new_title = fallback.replace('-', ' ').replace('_', ' ').strip().title()
                if not new_title or len(new_title) < 3:
                    log(f"  DROP {rec['id']}: empty title after normalization")
                    total_removed += 1
                    continue

            if new_title != old_title:
                changes.append((rec['id'], old_title, new_title))
                rec['title'] = new_title
                total_fixed += 1

            # Clean body echo
            old_body = rec.get('body', '')
            new_body = clean_body_title_echo(new_title, old_body)
            if new_body != old_body:
                rec['body'] = new_body

            # Drop records with empty body after cleaning
            if not rec.get('body', '').strip():
                log(f"  DROP {rec['id']}: empty body after title dedup")
                total_removed += 1
                continue

            fixed_records.append(rec)

        removed = initial_count - len(fixed_records)
        if removed > 0:
            total_removed += removed

        if not dry_run and (total_fixed > 0 or repaired_diff > 0 or removed > 0):
            write_jsonl(jsonl_path, fixed_records)
            log(f"  {jsonl_path.name}: {len(fixed_records)} records ({initial_count - len(fixed_records)} removed)")

    # Report
    log(f"\nTotal records scanned: {total_records}")
    log(f"Titles normalized: {total_fixed}")
    log(f"Malformed lines repaired: {total_repaired}")
    log(f"Records removed (empty title): {total_removed}")

    if dry_run:
        log("\n[DRY RUN] No files were modified.")
        log(f"\nSample changes (first 30):")
        for pid, old, new in changes[:30]:
            log(f"  {pid}")
            log(f"    OLD: {old[:100]}")
            log(f"    NEW: {new[:100]}")
            log("")

    return 0


if __name__ == "__main__":
    sys.exit(main())
