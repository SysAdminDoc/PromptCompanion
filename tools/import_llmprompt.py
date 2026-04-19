#!/usr/bin/env python3
"""Import abilzerian/LLM-Prompt-Library prompts + Jinja2 templates.

Source: https://github.com/abilzerian/LLM-Prompt-Library
License: MIT

Layout:
  prompts/<category>/*.md   — markdown files with prompt in fenced code block
  templates/<topic>/*.j2    — Jinja2 templates with YAML front matter
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


SOURCE_KEY = "llmprompt"

# prompts/ directory name -> category
PROMPT_DIR_MAP: dict[str, str] = {
    "creative": "creative",
    "finance": "specialized",
    "legal": "specialized",
    "marketing": "business",
    "medical": "specialized",
    "meta": "system",
    "miscellaneous": "",  # use infer_category
    "programming": "development",
    "sales": "business",
    "writing": "writing",
}

# templates/ directory name -> category
TEMPLATE_DIR_MAP: dict[str, str] = {
    "ai_research": "research",
    "bias": "research",
    "finance": "specialized",
    "finance_misc": "specialized",
    "foresight": "research",
    "framing": "research",
    "legal": "specialized",
    "med_point_care": "specialized",
    "med_scholar": "specialized",
    "medical": "specialized",
    "meta_prompt": "system",
    "private_equity": "specialized",
    "pro_code": "development",
    "prompt_eng": "system",
    "refusal": "system",
    "schema_ops": "development",
    "self_reflection": "productivity",
    "tone_modulation": "writing",
    "translation": "translation",
    "venture_capital": "specialized",
}

SKIP_FILENAMES = {"readme.md", "index.md", "license", "license.md", "__init__.py"}

_FRONT_MATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)
_JINJA_VAR_RE = re.compile(r"params\.([a-zA-Z_][a-zA-Z0-9_]{0,63})")
_FENCED_BLOCK_RE = re.compile(r"```[a-zA-Z]*\s*\n(.*?)```", re.DOTALL)


def _parse_front_matter(text: str) -> tuple[dict[str, str], str]:
    """Extract YAML-like front matter as simple key:value pairs. Returns (meta, remaining)."""
    m = _FRONT_MATTER_RE.match(text)
    if not m:
        return {}, text
    meta: dict[str, str] = {}
    for line in m.group(1).splitlines():
        if ":" in line:
            k, _, v = line.partition(":")
            meta[k.strip().lower()] = v.strip()
    return meta, text[m.end():]


def _extract_fenced_body(text: str) -> str | None:
    """Extract the first fenced code block body, or None."""
    m = _FENCED_BLOCK_RE.search(text)
    return m.group(1).strip() if m else None


def _extract_jinja_vars(text: str) -> list[str]:
    """Find params.X references in Jinja2 templates."""
    return list(dict.fromkeys(_JINJA_VAR_RE.findall(text)))


def _title_from_heading(text: str, fallback: str) -> str:
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("#"):
            t = line.lstrip("#").strip()
            if t:
                return t[:200]
    return fallback


def import_prompts(upstream: Path, src_meta: dict) -> list[dict]:
    """Walk prompts/*.md files."""
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

        # Extract body from fenced code block, or use full text
        body = _extract_fenced_body(raw)
        if not body:
            body = raw.strip()
        if len(body) < 40:
            continue

        dir_name = parts[0].lower() if len(parts) > 1 else ""
        title = _title_from_heading(raw, md_path.stem.replace("_", " ").replace("-", " "))

        category = PROMPT_DIR_MAP.get(dir_name, "")
        if not category:
            category = infer_category(title, body, default="uncategorized")

        tags = [dir_name] if dir_name else []

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


def import_templates(upstream: Path, src_meta: dict) -> list[dict]:
    """Walk templates/*.j2 files."""
    records: list[dict] = []
    templates_dir = upstream / "templates"
    if not templates_dir.exists():
        return records

    for j2_path in sorted(templates_dir.rglob("*.j2")):
        if j2_path.name.lower() in SKIP_FILENAMES:
            continue
        if j2_path.name.startswith("util_"):
            continue  # skip utility macro files

        parts = j2_path.relative_to(templates_dir).parts
        if not parts:
            continue

        try:
            raw = j2_path.read_text(encoding="utf-8", errors="replace")
        except Exception as exc:
            log(f"  skip {j2_path}: {exc}")
            continue

        meta, body_text = _parse_front_matter(raw)
        body = body_text.strip()
        if len(body) < 40:
            continue

        dir_name = parts[0].lower() if len(parts) > 1 else ""
        title = meta.get("name", j2_path.stem.replace("_", " ").replace("-", " "))
        title = title.title() if title == title.lower() else title

        category = TEMPLATE_DIR_MAP.get(dir_name, "")
        if not category:
            category = infer_category(title, body, default="uncategorized")

        tags = [dir_name.replace("_", "-")] if dir_name else []
        tags.append("template")

        # Extract Jinja2 param variables
        jinja_vars = _extract_jinja_vars(raw)
        extra_variables = [{"name": v} for v in jinja_vars]

        rec = build_record(
            source_key=SOURCE_KEY,
            title=title,
            body=body,
            category=category,
            role="system",
            tags=tags,
            source_url=src_meta["repo"].replace(".git", ""),
            author=meta.get("author", src_meta["author"]),
            license_=src_meta["license"],
        )
        # Merge Jinja2 params into variables (build_record extracts {{var}} from body)
        existing_names = {v["name"] for v in rec.get("variables", [])}
        for v in extra_variables:
            if v["name"] not in existing_names:
                rec.setdefault("variables", []).append(v)
                existing_names.add(v["name"])

        records.append(rec)
    return records


def main() -> int:
    registry = load_registry()
    src_meta = next(s for s in registry["sources"] if s["key"] == SOURCE_KEY)
    upstream = ensure_upstream(SOURCE_KEY)

    log(f"Walking {upstream}")
    prompt_records = import_prompts(upstream, src_meta)
    log(f"Parsed {len(prompt_records)} prompt records")
    template_records = import_templates(upstream, src_meta)
    log(f"Parsed {len(template_records)} template records")

    all_records = dedupe_ids(prompt_records + template_records)
    log(f"Total: {len(all_records)} records from {SOURCE_KEY}")

    counts = merge_into_prompts_dir(all_records)
    for cat, n in sorted(counts.items()):
        log(f"  {cat}.jsonl -> {n} total records")
    return 0


if __name__ == "__main__":
    sys.exit(main())
