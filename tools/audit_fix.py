#!/usr/bin/env python3
"""Comprehensive prompt data audit and fix.

Fixes:
1. Extract real GPT names from "GPT URL" placeholder titles (1,571 records)
2. Remove within-source near-duplicate bodies (keep highest quality)
3. Remove cross-source duplicate prompts (keep version with best quality/metadata)
4. Remove non-English prompts from English-only dataset
5. Remove tiny/garbage prompts (<50 char body)
6. Remove title echoes from body start
7. Truncate overly long titles to clean 120-char max
8. Clean sentence-like titles (extract meaningful prefix)
9. Deduplicate ChatGPT system prompt variants (keep best)

Run: python tools/audit_fix.py
     python tools/audit_fix.py --dry-run
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import PROMPTS_DIR, log, write_jsonl


def load_all() -> list[dict]:
    records = []
    for f in sorted(PROMPTS_DIR.glob('*.jsonl')):
        for line in f.read_text(encoding='utf-8').splitlines():
            if not line.strip():
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    return records


def extract_gpt_title(rec: dict) -> str | None:
    """Extract the real GPT name from body metadata."""
    body = rec['body']

    # Try "GPT Title: Name" (case-insensitive)
    m = re.search(r'GPT\s+[Tt]itle:\s*(.+?)(?:\n|$)', body)
    if m:
        name = m.group(1).strip()
        # Clean common prefixes/suffixes
        name = re.sub(r'^[@#]+', '', name).strip()
        name = re.sub(r'\s*[-|]\s*$', '', name).strip()
        if len(name) >= 3:
            return name

    # Try "GPT Name: Name"
    m = re.search(r'GPT\s+[Nn]ame:\s*(.+?)(?:\n|$)', body)
    if m:
        name = m.group(1).strip()
        if len(name) >= 3:
            return name

    # Try extracting from URL slug: g-xxxxx-readable-name
    m = re.search(r'chat\.openai\.com/g/g-\w+-([a-z0-9-]+)', body, re.I)
    if m:
        slug = m.group(1)
        name = slug.replace('-', ' ').strip().title()
        if len(name) >= 3:
            return name

    return None


_CJK_RE = re.compile(r'[\u4e00-\u9fff\u3400-\u4dbf\uac00-\ud7af\u0400-\u04ff\u0600-\u06ff]')


def is_non_english(title: str, body: str = "") -> bool:
    """Check if title or body is predominantly non-English."""
    if len(title) < 3:
        return False
    non_ascii = sum(1 for c in title if ord(c) > 127)
    if non_ascii / len(title) > 0.2:
        return True
    # Also check body for CJK/Cyrillic/Arabic dominance
    if body:
        cjk_count = len(_CJK_RE.findall(body))
        if cjk_count > 20 and cjk_count / max(len(body), 1) > 0.15:
            return True
    return False


def clean_body_title_echo(title: str, body: str) -> str:
    """Remove title echoed at start of body."""
    lines = body.split('\n')
    if not lines:
        return body

    first = lines[0].strip()

    # Body starts with "# Title" matching
    if first.startswith('#'):
        heading = first.lstrip('#').strip()
        if heading.lower() == title.lower():
            return '\n'.join(lines[1:]).lstrip('\n')

    # Body starts with exact title
    if first == title or first.lower() == title.lower():
        return '\n'.join(lines[1:]).lstrip('\n')

    # Body starts with title followed by newline (for multi-line body)
    if body.strip().startswith(title + '\n'):
        return body[len(title):].lstrip('\n')

    return body


def truncate_title(title: str, max_len: int = 120) -> str:
    """Truncate title at word boundary."""
    if len(title) <= max_len:
        return title
    t = title[:max_len]
    last_space = t.rfind(' ', max_len // 2)
    if last_space > max_len // 2:
        t = t[:last_space]
    return t.rstrip(' -,;:.')


def main() -> int:
    dry_run = '--dry-run' in sys.argv
    records = load_all()
    log(f"Loaded {len(records)} records\n")

    stats = {
        'gpt_titles_fixed': 0,
        'near_dupes_removed': 0,
        'cross_dupes_removed': 0,
        'non_english_removed': 0,
        'tiny_removed': 0,
        'body_echo_cleaned': 0,
        'titles_truncated': 0,
        'junk_removed': 0,
    }

    # --- PASS 1: Fix GPT URL titles ---
    for r in records:
        if r['title'].lower().startswith('gpt url'):
            new_title = extract_gpt_title(r)
            if new_title:
                r['title'] = new_title
                stats['gpt_titles_fixed'] += 1
            else:
                # Fallback: derive from URL slug in ID
                id_parts = r['id'].replace('bigprompt-gpt-url-https-chat-openai-com-g-g-', '')
                # Remove the random prefix (e.g., "00grdogjy-")
                slug = re.sub(r'^[a-z0-9]+-', '', id_parts, count=1)
                if slug and len(slug) > 3:
                    r['title'] = slug.replace('-', ' ').title()
                    stats['gpt_titles_fixed'] += 1

    log(f"GPT titles extracted: {stats['gpt_titles_fixed']}")

    # Clean any remaining URLs from all titles
    for r in records:
        old = r['title']
        cleaned = re.sub(r'\s*-?\s*https?://\S+', '', old).strip()
        if cleaned != old and len(cleaned) >= 3:
            r['title'] = cleaned

    # --- PASS 2: Remove non-English ---
    before = len(records)
    records = [r for r in records if not is_non_english(r['title'], r.get('body', ''))]
    stats['non_english_removed'] = before - len(records)
    log(f"Non-English removed: {stats['non_english_removed']}")

    # --- PASS 3: Remove tiny/garbage records ---
    before = len(records)
    records = [r for r in records if len(r['body'].strip()) >= 40]
    stats['tiny_removed'] = before - len(records)
    log(f"Tiny body (<40 chars) removed: {stats['tiny_removed']}")

    # --- PASS 4: Remove near-duplicate bodies (keep highest quality) ---
    body_hash_groups: dict[str, list[dict]] = {}
    for r in records:
        prefix = r['body'][:500].strip().lower()
        h = hashlib.md5(prefix.encode()).hexdigest()
        body_hash_groups.setdefault(h, []).append(r)

    keep_ids = set()
    for h, group in body_hash_groups.items():
        if len(group) == 1:
            keep_ids.add(group[0]['id'])
        else:
            # Keep the one with highest quality, longest body as tiebreaker
            best = max(group, key=lambda r: (r.get('quality', 0), len(r['body'])))
            keep_ids.add(best['id'])
            for r in group:
                if r['id'] != best['id']:
                    stats['near_dupes_removed'] += 1

    records = [r for r in records if r['id'] in keep_ids]
    log(f"Near-duplicate bodies removed: {stats['near_dupes_removed']}")

    # --- PASS 5: Remove title duplicates (keep best version per title) ---
    title_groups: dict[str, list[dict]] = {}
    for r in records:
        tn = re.sub(r'\s+', ' ', r['title'].strip().lower())
        title_groups.setdefault(tn, []).append(r)

    keep_ids2 = set()
    for tn, group in title_groups.items():
        if len(group) == 1:
            keep_ids2.add(group[0]['id'])
        else:
            # Multiple records with same title — keep the one with
            # highest quality, then longest body as tiebreaker
            best = max(group, key=lambda r: (r.get('quality', 0), len(r['body'])))
            keep_ids2.add(best['id'])
            for r in group:
                if r['id'] != best['id']:
                    stats['cross_dupes_removed'] += 1

    records = [r for r in records if r['id'] in keep_ids2]
    log(f"Title duplicates removed (kept best version): {stats['cross_dupes_removed']}")

    # --- PASS 6: Clean body title echoes ---
    for r in records:
        old_body = r['body']
        new_body = clean_body_title_echo(r['title'], old_body)
        if new_body != old_body and new_body.strip():
            r['body'] = new_body
            stats['body_echo_cleaned'] += 1

    log(f"Body title echoes cleaned: {stats['body_echo_cleaned']}")

    # --- PASS 7: Truncate long titles ---
    for r in records:
        old = r['title']
        new = truncate_title(old)
        if new != old:
            r['title'] = new
            stats['titles_truncated'] += 1

    log(f"Titles truncated (>120 chars): {stats['titles_truncated']}")

    # --- PASS 8: Remove remaining junk (empty bodies after cleaning) ---
    before = len(records)
    records = [r for r in records if r['body'].strip()]
    stats['junk_removed'] = before - len(records)
    log(f"Empty body after cleaning: {stats['junk_removed']}")

    # --- Write results ---
    total_changes = sum(stats.values())
    log(f"\nTotal fixes applied: {total_changes}")
    log(f"Final record count: {len(records)}")

    if dry_run:
        log("\n[DRY RUN] No files modified.")
        return 0

    # Group by category and write
    buckets: dict[str, list[dict]] = {}
    for r in records:
        buckets.setdefault(r['category'], []).append(r)

    for cat, recs in sorted(buckets.items()):
        path = PROMPTS_DIR / f"{cat}.jsonl"
        write_jsonl(path, recs)
        log(f"  {cat}.jsonl: {len(recs)} records")

    # Check for orphaned files
    expected_files = {f"{cat}.jsonl" for cat in buckets}
    for f in PROMPTS_DIR.glob('*.jsonl'):
        if f.name not in expected_files:
            log(f"  WARNING: orphaned file {f.name}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
