#!/usr/bin/env python3
"""Compile data/prompts/*.jsonl into a SQLite FTS5 search index at data/index/prompts.db.

Tables:
  prompts(id PK, title, body, role, category, tags_json, target_models_json,
          language, source, author, license, version, created, updated)
  prompts_fts(title, body, tags, author, content='prompts', content_rowid=rowid)

The GUI (v0.2.x) reads directly from this database with no write access needed.
"""

from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import INDEX_DIR, PROMPTS_DIR, log, read_jsonl


SCHEMA = """
DROP TABLE IF EXISTS prompts_fts;
DROP TABLE IF EXISTS prompts;

CREATE TABLE prompts (
    rowid         INTEGER PRIMARY KEY AUTOINCREMENT,
    id            TEXT UNIQUE NOT NULL,
    title         TEXT NOT NULL,
    body          TEXT NOT NULL,
    role          TEXT NOT NULL,
    category      TEXT NOT NULL,
    tags          TEXT NOT NULL,           -- JSON array
    variables     TEXT NOT NULL,           -- JSON array
    target_models TEXT NOT NULL,           -- JSON array
    language      TEXT NOT NULL,
    source        TEXT NOT NULL,
    author        TEXT NOT NULL DEFAULT '',
    license       TEXT NOT NULL,
    version       INTEGER NOT NULL,
    created       TEXT NOT NULL,
    updated       TEXT NOT NULL
);

CREATE INDEX idx_prompts_category ON prompts(category);
CREATE INDEX idx_prompts_language ON prompts(language);
CREATE INDEX idx_prompts_license  ON prompts(license);

CREATE VIRTUAL TABLE prompts_fts USING fts5(
    title,
    body,
    tags,
    author,
    content='prompts',
    content_rowid='rowid',
    tokenize='porter unicode61 remove_diacritics 2'
);

CREATE TRIGGER prompts_ai AFTER INSERT ON prompts BEGIN
    INSERT INTO prompts_fts(rowid, title, body, tags, author)
    VALUES (new.rowid, new.title, new.body, new.tags, new.author);
END;
CREATE TRIGGER prompts_ad AFTER DELETE ON prompts BEGIN
    INSERT INTO prompts_fts(prompts_fts, rowid, title, body, tags, author)
    VALUES ('delete', old.rowid, old.title, old.body, old.tags, old.author);
END;
CREATE TRIGGER prompts_au AFTER UPDATE ON prompts BEGIN
    INSERT INTO prompts_fts(prompts_fts, rowid, title, body, tags, author)
    VALUES ('delete', old.rowid, old.title, old.body, old.tags, old.author);
    INSERT INTO prompts_fts(rowid, title, body, tags, author)
    VALUES (new.rowid, new.title, new.body, new.tags, new.author);
END;
"""


def main() -> int:
    INDEX_DIR.mkdir(parents=True, exist_ok=True)
    db_path = INDEX_DIR / "prompts.db"
    if db_path.exists():
        db_path.unlink()

    conn = sqlite3.connect(db_path)
    try:
        conn.executescript(SCHEMA)
        cur = conn.cursor()

        total = 0
        per_category: dict[str, int] = {}
        for jsonl_path in sorted(PROMPTS_DIR.glob("*.jsonl")):
            records = read_jsonl(jsonl_path)
            per_category[jsonl_path.stem] = len(records)
            for r in records:
                cur.execute(
                    """
                    INSERT INTO prompts
                    (id, title, body, role, category, tags, variables,
                     target_models, language, source, author, license,
                     version, created, updated)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        r["id"],
                        r["title"],
                        r["body"],
                        r["role"],
                        r["category"],
                        json.dumps(r.get("tags", []), ensure_ascii=False),
                        json.dumps(r.get("variables", []), ensure_ascii=False),
                        json.dumps(r.get("target_models", []), ensure_ascii=False),
                        r["language"],
                        r["source"],
                        r.get("author") or "",
                        r["license"],
                        r["version"],
                        r["created"],
                        r["updated"],
                    ),
                )
                total += 1

        conn.commit()
        cur.execute("INSERT INTO prompts_fts(prompts_fts) VALUES('optimize')")
        conn.commit()
        log(f"Wrote {total} records to {db_path}")
        for cat, n in sorted(per_category.items()):
            log(f"  {cat:15s}  {n:5d}")

        cur.execute("SELECT COUNT(*) FROM prompts_fts")
        (fts_count,) = cur.fetchone()
        log(f"FTS rows: {fts_count}")
    finally:
        conn.close()

    return 0


if __name__ == "__main__":
    sys.exit(main())
