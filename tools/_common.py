#!/usr/bin/env python3
"""Shared helpers for PromptCompanion importers, validators, and indexers."""

from __future__ import annotations

import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


def _bootstrap(packages: list[str]) -> None:
    """Auto-install missing dependencies. Falls back to --user and --break-system-packages."""
    import importlib.util

    missing = [p for p in packages if importlib.util.find_spec(p.split("[")[0].split("==")[0]) is None]
    if not missing:
        return

    def _run(args: list[str]) -> int:
        return subprocess.call([sys.executable, "-m", "pip", "install", *args, *missing])

    if _run([]) != 0 and _run(["--user"]) != 0:
        _run(["--user", "--break-system-packages"])


ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
PROMPTS_DIR = DATA_DIR / "prompts"
SOURCES_DIR = DATA_DIR / "sources"
UPSTREAM_DIR = SOURCES_DIR / "upstream"
INDEX_DIR = DATA_DIR / "index"
SCHEMA_PATH = DATA_DIR / "schema.json"
TAXONOMY_PATH = DATA_DIR / "taxonomy.json"
REGISTRY_PATH = SOURCES_DIR / "registry.json"

VALID_CATEGORIES = {
    "development", "writing", "research", "creative", "business",
    "productivity", "system", "roleplay", "translation", "specialized",
    "uncategorized",
}


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


_SLUG_RE = re.compile(r"[^a-z0-9]+")


def slugify(text: str, max_len: int = 96) -> str:
    """Lowercase, collapse non-alnum runs to '-', trim, cap length."""
    s = _SLUG_RE.sub("-", text.lower()).strip("-")
    if len(s) > max_len:
        s = s[:max_len].rstrip("-")
    return s or "prompt"


_VAR_RE = re.compile(r"\{\{\s*([a-zA-Z_][a-zA-Z0-9_]{0,63})\s*\}\}")
_TAG_CLEAN_RE = re.compile(r"[^a-z0-9]+")


def sanitize_tag(tag: str) -> str | None:
    """Normalize a tag to match the schema pattern; return None if it can't be salvaged."""
    s = _TAG_CLEAN_RE.sub("-", tag.lower()).strip("-")
    if not s:
        return None
    if len(s) > 32:
        s = s[:32].rstrip("-")
    if not s or not s[0].isalnum():
        return None
    return s


def sanitize_tags(tags: list[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for t in tags or []:
        clean = sanitize_tag(t)
        if clean and clean not in seen:
            seen.add(clean)
            out.append(clean)
    return out


def extract_variables(body: str) -> list[dict]:
    """Return deduplicated variable descriptors for {{name}} placeholders."""
    seen: dict[str, dict] = {}
    for name in _VAR_RE.findall(body):
        if name not in seen:
            seen[name] = {"name": name}
    return list(seen.values())


def load_registry() -> dict:
    return json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))


def load_taxonomy() -> dict:
    return json.loads(TAXONOMY_PATH.read_text(encoding="utf-8"))


def load_schema() -> dict:
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


def write_jsonl(path: Path, records: list[dict]) -> None:
    """Write records as JSON lines. Sorted by id for stable diffs."""
    path.parent.mkdir(parents=True, exist_ok=True)
    records_sorted = sorted(records, key=lambda r: r["id"])
    with path.open("w", encoding="utf-8", newline="\n") as fh:
        for r in records_sorted:
            fh.write(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n")


def read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    out: list[dict] = []
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                out.append(json.loads(line))
    return out


def group_by_category(records: list[dict]) -> dict[str, list[dict]]:
    buckets: dict[str, list[dict]] = {}
    for r in records:
        buckets.setdefault(r["category"], []).append(r)
    return buckets


def merge_into_prompts_dir(new_records: list[dict]) -> dict[str, int]:
    """Merge records into data/prompts/<category>.jsonl files. Returns per-category counts written."""
    counts: dict[str, int] = {}
    grouped_new = group_by_category(new_records)
    existing_by_category: dict[str, dict[str, dict]] = {}
    for cat in VALID_CATEGORIES:
        existing = read_jsonl(PROMPTS_DIR / f"{cat}.jsonl")
        existing_by_category[cat] = {r["id"]: r for r in existing}

    for cat, new_list in grouped_new.items():
        bucket = existing_by_category.setdefault(cat, {})
        for rec in new_list:
            if rec["id"] in bucket:
                prev = bucket[rec["id"]]
                rec["created"] = prev.get("created", rec["created"])
                rec["version"] = max(prev.get("version", 1), rec.get("version", 1))
            bucket[rec["id"]] = rec

    for cat, bucket in existing_by_category.items():
        if not bucket:
            continue
        write_jsonl(PROMPTS_DIR / f"{cat}.jsonl", list(bucket.values()))
        counts[cat] = len(bucket)
    return counts


def build_record(
    *,
    source_key: str,
    title: str,
    body: str,
    category: str,
    source_url: str,
    license_: str,
    author: str | None = None,
    role: str = "user",
    tags: list[str] | None = None,
    target_models: list[str] | None = None,
    language: str = "en",
    notes: str | None = None,
    id_suffix: str | None = None,
) -> dict:
    """Construct a schema-valid prompt record."""
    slug = slugify(title)
    if id_suffix:
        slug = f"{slug}-{id_suffix}"
    rec_id = f"{source_key}-{slug}"[:128]
    ts = now_iso()
    rec: dict = {
        "id": rec_id,
        "title": title.strip()[:200],
        "body": body.strip(),
        "role": role,
        "category": category if category in VALID_CATEGORIES else "uncategorized",
        "tags": sanitize_tags(tags or [])[:12],
        "variables": extract_variables(body),
        "target_models": sorted(set(target_models or ["any"])),
        "language": language,
        "source": source_url,
        "license": license_,
        "version": 1,
        "created": ts,
        "updated": ts,
    }
    if author:
        rec["author"] = author
    if notes:
        rec["notes"] = notes
    return rec


# ------------------------------------------------------------------ #
# Lightweight category inference — used by importers that lack labels
# ------------------------------------------------------------------ #

_CATEGORY_KEYWORDS: list[tuple[str, tuple[str, ...]]] = [
    ("development", (
        "code", "coding", "developer", "programmer", "debug", "refactor",
        "sql", "regex", "shell", "devops", "api", "unit test", "algorithm",
        "software engineer", "git", "docker", "kubernetes",
    )),
    ("writing", (
        "write", "blog", "essay", "copywriter", "editor", "proofread",
        "rewrite", "headline", "email", "newsletter",
    )),
    ("research", (
        "research", "literature", "analyze", "analysis", "fact-check",
        "summarize", "compare", "citation", "paper",
    )),
    ("creative", (
        "story", "fiction", "novel", "poem", "poet", "lyric", "song",
        "midjourney", "dall-e", "stable diffusion", "image prompt",
        "worldbuilding",
    )),
    ("business", (
        "business", "strategy", "marketing", "sales", "pitch", "hr",
        "hiring", "interview", "meeting", "report", "executive",
    )),
    ("productivity", (
        "plan", "planner", "schedule", "flashcard", "teach", "tutor",
        "learn", "study", "productivity",
    )),
    ("translation", (
        "translate", "translator", "grammar", "localize", "interpret",
    )),
    ("specialized", (
        "doctor", "medical", "nurse", "lawyer", "legal", "financial advisor",
        "accountant", "scientist", "academic",
    )),
]


def infer_category(title: str, body: str, default: str = "roleplay") -> str:
    hay = f"{title}\n{body}".lower()
    for cat, keywords in _CATEGORY_KEYWORDS:
        if any(kw in hay for kw in keywords):
            return cat
    return default


def ensure_upstream(source_key: str) -> Path:
    """Return path to cloned upstream repo, erroring if missing."""
    registry = load_registry()
    src = next((s for s in registry["sources"] if s["key"] == source_key), None)
    if src is None:
        raise SystemExit(f"Unknown source key: {source_key}")
    path = UPSTREAM_DIR / source_key
    if not path.exists():
        raise SystemExit(
            f"Upstream for '{source_key}' not cloned. Run `python tools/fetch_sources.py` first."
        )
    return path


def log(msg: str) -> None:
    print(f"[promptcompanion] {msg}", flush=True)
