#!/usr/bin/env python3
from __future__ import annotations

import json
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from promptcompanion import OverlayStore, PromptDB, extract_variables


SCHEMA = """
CREATE TABLE prompts (
    rowid INTEGER PRIMARY KEY AUTOINCREMENT,
    id TEXT UNIQUE NOT NULL,
    title TEXT NOT NULL,
    body TEXT NOT NULL,
    role TEXT NOT NULL,
    category TEXT NOT NULL,
    tags TEXT NOT NULL,
    variables TEXT NOT NULL,
    target_models TEXT NOT NULL,
    language TEXT NOT NULL,
    source TEXT NOT NULL,
    author TEXT NOT NULL DEFAULT '',
    license TEXT NOT NULL,
    version INTEGER NOT NULL,
    quality INTEGER NOT NULL DEFAULT 0,
    created TEXT NOT NULL,
    updated TEXT NOT NULL
);
CREATE VIRTUAL TABLE prompts_fts USING fts5(
    title, body, tags, author,
    content='prompts',
    content_rowid='rowid',
    tokenize='porter unicode61 remove_diacritics 2'
);
CREATE TRIGGER prompts_ai AFTER INSERT ON prompts BEGIN
    INSERT INTO prompts_fts(rowid, title, body, tags, author)
    VALUES (new.rowid, new.title, new.body, new.tags, new.author);
END;
"""


def insert_prompt(conn: sqlite3.Connection, prompt_id: str, title: str, body: str) -> None:
    conn.execute(
        """
        INSERT INTO prompts
        (id, title, body, role, category, tags, variables, target_models,
         language, source, author, license, version, quality, created, updated)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            prompt_id,
            title,
            body,
            "user",
            "writing",
            json.dumps(["drafting"]),
            json.dumps([]),
            json.dumps(["any"]),
            "en",
            "https://example.test/source",
            "Example",
            "MIT",
            1,
            55,
            "2026-04-18T00:00:00Z",
            "2026-04-18T00:00:00Z",
        ),
    )
    conn.commit()


class OverlayTests(unittest.TestCase):
    def test_extract_variables_preserves_first_seen_order(self):
        self.assertEqual(
            extract_variables("Hello {{ name }} and {{topic}} then {{name}}"),
            [{"name": "name"}, {"name": "topic"}],
        )

    def test_overlay_jsonl_layers_over_base_record(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "overlay.jsonl"
            store = OverlayStore(path)
            store.save(
                {
                    "id": "demo-one",
                    "title": "Edited",
                    "body": "Edited body",
                    "role": "user",
                    "category": "writing",
                    "tags": ["edited"],
                    "variables": [],
                    "target_models": ["any"],
                    "language": "en",
                    "source": "https://example.test/source",
                    "author": "Example",
                    "license": "MIT",
                    "version": 2,
                    "quality": 55,
                    "created": "2026-04-18T00:00:00Z",
                    "updated": "2026-06-27T00:00:00Z",
                }
            )

            reloaded = OverlayStore(path)
            layered = reloaded.apply({"id": "demo-one", "title": "Base", "body": "Base body"})

            self.assertEqual(layered["title"], "Edited")
            self.assertEqual(layered["tags"], ["edited"])
            self.assertTrue(layered["_overlay"])

    def test_search_finds_overlay_only_text_without_rebuilding_fts(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            db_path = tmp_path / "prompts.db"
            conn = sqlite3.connect(db_path)
            conn.executescript(SCHEMA)
            insert_prompt(conn, "demo-one", "Base title", "Base body")
            conn.close()

            overlay = OverlayStore(tmp_path / "overlay.jsonl")
            overlay.save(
                {
                    "id": "demo-one",
                    "title": "Edited overlay title",
                    "body": "The overlayonly phrase lives outside the bundled index.",
                    "role": "user",
                    "category": "writing",
                    "tags": ["edited"],
                    "variables": [],
                    "target_models": ["any"],
                    "language": "en",
                    "source": "https://example.test/source",
                    "author": "Example",
                    "license": "MIT",
                    "version": 2,
                    "quality": 55,
                    "created": "2026-04-18T00:00:00Z",
                    "updated": "2026-06-27T00:00:00Z",
                }
            )

            db = PromptDB(db_path, overlay)
            try:
                results = db.search(query="overlayonly")
            finally:
                db.close()

            self.assertEqual([r["id"] for r in results], ["demo-one"])
            self.assertEqual(results[0]["title"], "Edited overlay title")


if __name__ == "__main__":
    unittest.main()
