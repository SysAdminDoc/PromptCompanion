#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import promptcompanion
from tools.validate import validate_translation_links
from tools._common import (  # noqa: E402
    apply_deprecation_flags,
    apply_suggested_tags,
    deprecation_reasons,
    score_quality,
    suggest_tags,
)
from promptcompanion import (
    compose_prompt_chain,
    OverlayStore,
    PromptDB,
    estimate_token_count,
    expand_prompt_includes,
    export_markdown_front_matter,
    export_prompt_bundle,
    extract_variables,
    fill_prompt_body,
    format_prompt_stats,
    format_history_diff,
    make_private_prompt,
    markdown_file_record,
    model_compatible,
    model_provider,
    prompt_of_day,
    provider_handoff_url,
    set_variable_preset,
    variable_preset_map,
    parse_tag_input,
    recency_boost,
    theme_stylesheet,
    write_editor_draft,
    resolve_runtime_paths,
)
from tools.updater import (  # noqa: E402
    ReleaseAsset,
    ReleaseInfo,
    choose_asset,
    download_asset,
    fetch_latest_release,
    is_newer_version,
)
from tools.plugins import discover_importers, run_importer  # noqa: E402
from promptcompanion_cli import search_prompts  # noqa: E402


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
    translation_of TEXT NOT NULL DEFAULT '',
    translated_from TEXT NOT NULL DEFAULT '',
    translator TEXT NOT NULL DEFAULT '',
    version INTEGER NOT NULL,
    quality INTEGER NOT NULL DEFAULT 0,
    deprecated INTEGER NOT NULL DEFAULT 0,
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


def insert_prompt(
    conn: sqlite3.Connection,
    prompt_id: str,
    title: str,
    body: str,
    category: str = "writing",
    variables: list[dict] | None = None,
    language: str = "en",
) -> None:
    if variables is None:
        variables = []
    conn.execute(
        """
        INSERT INTO prompts
        (id, title, body, role, category, tags, variables, target_models,
         language, source, author, license, translation_of, translated_from,
         translator, version, quality, created, updated)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            prompt_id,
            title,
            body,
            "user",
            category,
            json.dumps(["drafting"]),
            json.dumps(variables),
            json.dumps(["any"]),
            language,
            "https://example.test/source",
            "Example",
            "MIT",
            "",
            "",
            "",
            1,
            55,
            "2026-04-18T00:00:00Z",
            "2026-04-18T00:00:00Z",
        ),
    )
    conn.commit()


class OverlayTests(unittest.TestCase):
    def test_local_autotagging_is_deterministic_and_preserves_curated_tags(self):
        record = {
            "title": "Review Python code",
            "body": "Debug the traceback, refactor the function, and add a unit test.",
            "tags": ["curated"],
        }

        first = suggest_tags(record)
        second = suggest_tags(record)

        self.assertEqual(first, second)
        self.assertIn("debugging", first)
        self.assertIn("refactor", first)
        self.assertNotIn("curated", first)
        self.assertEqual(apply_suggested_tags([record]), 1)
        self.assertIn("curated", record["tags"])
        self.assertIn("debugging", record["tags"])

    def test_local_autotagging_can_replace_tags_with_bounded_output(self):
        record = {
            "title": "Translate this text",
            "body": "Translate the text and preserve the tone.",
            "tags": ["old", "old", "manual"],
        }

        self.assertEqual(apply_suggested_tags([record], overwrite=True, max_new=2), 1)
        self.assertLessEqual(len(record["tags"]), 12)
        self.assertNotIn("old", record["tags"])
        self.assertIn("translate", record["tags"])

    def test_quality_v2_uses_author_and_review_signals(self):
        base = {
            "id": "awesome-demo",
            "title": "Useful Prompt",
            "body": "# Task\n\n1. Do the work.\n2. Show an example output.",
            "variables": [{"name": "topic"}],
            "tags": ["drafting", "review"],
            "role": "user",
        }
        reviewed = {
            **base,
            "author_rank": 100,
            "review_score": 5,
            "review_votes": 5,
        }

        self.assertGreater(score_quality(reviewed), score_quality(base))
        self.assertLessEqual(score_quality(reviewed), 100)

    def test_recency_boost_is_bounded_and_prefers_newer_records(self):
        now = promptcompanion.datetime(2026, 8, 9, tzinfo=promptcompanion.timezone.utc)
        newer = recency_boost("2026-08-01T00:00:00Z", now=now)
        older = recency_boost("2025-08-01T00:00:00Z", now=now)

        self.assertGreater(newer, older)
        self.assertGreaterEqual(newer, 0.0)
        self.assertLessEqual(newer, 1.0)
        self.assertEqual(recency_boost("not-a-date", now=now), 0.0)

    def test_deprecation_flags_obsolete_models_and_stale_records(self):
        now = promptcompanion.datetime(2026, 8, 9, tzinfo=promptcompanion.timezone.utc)
        record = {
            "id": "demo",
            "target_models": ["gpt-3.5-turbo"],
            "updated": "2025-01-01T00:00:00Z",
        }

        reasons = deprecation_reasons(record, now=now)

        self.assertTrue(any("obsolete model" in reason for reason in reasons))
        self.assertTrue(any("not updated" in reason for reason in reasons))

    def test_apply_deprecation_flags_persists_only_changed_records(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "writing.jsonl"
            path.write_text(
                json.dumps({
                    "id": "demo",
                    "title": "Demo",
                    "body": "Body",
                    "target_models": ["gpt-3.5-turbo"],
                    "updated": "2025-01-01T00:00:00Z",
                }) + "\n",
                encoding="utf-8",
            )

            now = promptcompanion.datetime(2026, 8, 9, tzinfo=promptcompanion.timezone.utc)
            self.assertEqual(apply_deprecation_flags(Path(tmp), now=now), 1)
            flagged = json.loads(path.read_text(encoding="utf-8"))
            self.assertTrue(flagged["deprecated"])
            self.assertIn("obsolete model", flagged["deprecation_reason"])
            self.assertEqual(apply_deprecation_flags(Path(tmp), now=now), 0)

    def test_extract_variables_preserves_first_seen_order(self):
        self.assertEqual(
            extract_variables("Hello {{ name }} and {{topic}} then {{name}}"),
            [{"name": "name"}, {"name": "topic"}],
        )

    def test_parse_tag_input_normalizes_unique_local_tags(self):
        self.assertEqual(
            parse_tag_input("Review, Drafting; review  Needs polish!"),
            ["review", "drafting", "needs", "polish"],
        )

    def test_export_prompt_bundle_supports_json_and_markdown(self):
        records = [{
            "id": "demo-one",
            "title": "Demo One",
            "body": "Write about {{topic}}.",
            "role": "user",
            "category": "writing",
            "language": "en",
            "tags": '["drafting"]',
            "variables": "[]",
            "target_models": '["any"]',
            "_overlay": True,
        }]

        json_bundle = export_prompt_bundle(records, "JSON")
        markdown_bundle = export_prompt_bundle(records, "Markdown")

        self.assertIn('"prompts"', json_bundle)
        self.assertIn('"tags": [\n        "drafting"', json_bundle)
        self.assertNotIn("_overlay", json_bundle)
        self.assertIn("# Prompt Bundle", markdown_bundle)
        self.assertIn("## 1. Demo One", markdown_bundle)
        self.assertIn("Write about {{topic}}.", markdown_bundle)

    def test_write_editor_draft_uses_stable_atomic_markdown_path(self):
        record = {
            "id": "demo-one",
            "title": "Demo One",
            "body": "Body",
            "role": "user",
            "category": "writing",
            "language": "en",
        }
        with tempfile.TemporaryDirectory() as tmp:
            path = write_editor_draft(record, "Body", Path(tmp))

            self.assertEqual(path.name, "demo-one.md")
            self.assertIn("# Demo One", path.read_text(encoding="utf-8"))

    def test_prompt_stats_format_counts_characters_and_estimated_tokens(self):
        text = "Hello, world!\nShip v0.7.3."

        self.assertGreater(estimate_token_count(text), 0)
        self.assertEqual(
            format_prompt_stats(text),
            f"26 chars / ~{estimate_token_count(text):,} tokens",
        )

    def test_model_compatibility_maps_any_and_provider_families(self):
        self.assertEqual(model_provider("gpt-4o"), "openai")
        self.assertEqual(model_provider("claude-3.5-sonnet"), "anthropic")
        self.assertEqual(model_provider("llama3:8b"), "local")
        self.assertTrue(model_compatible({"target_models": ["any"]}, "openai"))
        self.assertTrue(model_compatible({"target_models": ["claude-3.5-sonnet"]}, "Anthropic"))
        self.assertFalse(model_compatible({"target_models": ["gpt-4o"]}, "local"))

    def test_provider_handoff_urls_encode_prompt_text(self):
        prompt = "Write a release note\nfor v1.0"

        self.assertIn("q=Write%20a%20release%20note%0Afor%20v1.0", provider_handoff_url("ChatGPT", prompt))
        self.assertIn("q=Write%20a%20release%20note%0Afor%20v1.0", provider_handoff_url("Claude", prompt))
        self.assertIn("prompt=Write%20a%20release%20note%0Afor%20v1.0", provider_handoff_url("Ollama", prompt))

    def test_prompt_of_day_is_stable_and_skips_deprecated_records(self):
        records = [
            {"id": "old", "title": "Old", "body": "Old", "quality": 100, "deprecated": True},
            {"id": "one", "title": "One", "body": "One", "quality": 80},
            {"id": "two", "title": "Two", "body": "Two", "quality": 70},
        ]

        first = prompt_of_day(records, day="2026-08-09")
        second = prompt_of_day(records, day="2026-08-09")

        self.assertEqual(first, second)
        self.assertIn(first["id"], {"one", "two"})

    def test_light_theme_stylesheet_replaces_dark_surface_colors(self):
        light = theme_stylesheet("light")
        dark = theme_stylesheet("dark")

        self.assertIn("#F8F8FC", light)
        self.assertIn("#1E1E2E", dark)
        self.assertNotEqual(light, dark)

    def test_cli_search_uses_the_same_fts_index_contract(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "prompts.db"
            conn = sqlite3.connect(db_path)
            conn.executescript(SCHEMA)
            insert_prompt(conn, "demo-one", "CLI title", "CLI searchable body")
            conn.close()

            results = search_prompts(db_path, "searchable", limit=1)

            self.assertEqual([record["id"] for record in results], ["demo-one"])

    def test_plugin_entry_points_load_callable_and_object_plugins(self):
        class Entry:
            def __init__(self, name, loaded):
                self.name = name
                self.loaded = loaded

            def load(self):
                return self.loaded

        class Entries:
            def select(self, **_kwargs):
                return [
                    Entry("callable", lambda **options: options["value"] + 1),
                    Entry("object", type("Plugin", (), {"import_prompts": lambda self, **kwargs: kwargs["value"] * 2})()),
                ]

        discovered = discover_importers(Entries())

        self.assertEqual(set(discovered), {"callable", "object"})
        self.assertEqual(run_importer("callable", {"value": 2}, Entries()), 3)
        self.assertEqual(run_importer("object", {"value": 2}, Entries()), 4)

    def test_portable_runtime_paths_use_external_database_when_present(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            executable_dir = root / "dist"
            bundle_root = root / "bundle"
            portable_db = executable_dir / "data" / "index" / "prompts.db"
            portable_db.parent.mkdir(parents=True)
            portable_db.write_bytes(b"portable")

            resolved_root, user_dir, resolved_db = resolve_runtime_paths(
                True, executable_dir, bundle_root, True
            )

            self.assertEqual(resolved_root, executable_dir)
            self.assertEqual(user_dir, executable_dir / "data" / "user")
            self.assertEqual(resolved_db, portable_db)

    def test_release_helpers_select_assets_and_download_atomically(self):
        release = ReleaseInfo(
            "v1.2.0",
            "1.2.0",
            "https://github.com/SysAdminDoc/PromptCompanion/releases/tag/v1.2.0",
            (
                ReleaseAsset("PromptCompanion.zip", "https://github.com/example/app.zip"),
                ReleaseAsset("PromptCompanion.exe", "https://github.com/example/app.exe"),
            ),
        )

        self.assertTrue(is_newer_version("1.1.9", release.version))
        self.assertEqual(choose_asset(release, "win32").name, "PromptCompanion.exe")

        class FakeResponse:
            def __init__(self, payload: bytes):
                self.payload = payload
                self.used = False

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def read(self, _size=-1):
                if self.used:
                    return b""
                self.used = True
                return self.payload

        with tempfile.TemporaryDirectory() as tmp:
            destination = Path(tmp) / "PromptCompanion.exe"
            downloaded = download_asset(
                "https://github.com/example/app.exe",
                destination,
                opener=lambda *_args, **_kwargs: FakeResponse(b"binary"),
            )
            self.assertEqual(downloaded, destination)
            self.assertEqual(destination.read_bytes(), b"binary")

    def test_fetch_latest_release_parses_github_payload(self):
        payload = json.dumps({
            "tag_name": "v1.2.0",
            "html_url": "https://github.com/SysAdminDoc/PromptCompanion/releases/tag/v1.2.0",
            "assets": [{
                "name": "PromptCompanion.exe",
                "browser_download_url": "https://github.com/example/app.exe",
            }],
        }).encode("utf-8")

        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def read(self):
                return payload

        release = fetch_latest_release(
            "https://api.github.com/repos/example/app/releases/latest",
            opener=lambda *_args, **_kwargs: FakeResponse(),
        )

        self.assertEqual(release.version, "1.2.0")
        self.assertEqual(release.assets[0].name, "PromptCompanion.exe")

    def test_prompt_includes_expand_from_db_refs(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "prompts.db"
            conn = sqlite3.connect(db_path)
            conn.executescript(SCHEMA)
            insert_prompt(
                conn,
                "system-tone-dev",
                "Tone Dev",
                "Use a direct tone for {{audience}}.",
                category="system",
                variables=[{"name": "audience"}],
            )
            insert_prompt(
                conn,
                "writer-wrapper",
                "Wrapper",
                "Before\n{{include:system/tone-dev}}\nAfter {{topic}}.",
                variables=[{"name": "topic"}],
            )
            conn.close()

            db = PromptDB(db_path)
            try:
                expanded = expand_prompt_includes(
                    "X {{include:system/tone-dev}} Y",
                    db.resolve_include_body,
                )
                filled = fill_prompt_body(
                    "X {{include:system-tone-dev}} {{topic}}",
                    {"audience": "operators", "topic": "runbooks"},
                    db.resolve_include_body,
                )
            finally:
                db.close()

            self.assertEqual(expanded, "X Use a direct tone for {{audience}}. Y")
            self.assertEqual(filled, "X Use a direct tone for operators. runbooks")

    def test_front_matter_export_profile_uses_yaml_metadata(self):
        record = {
            "id": "demo-one",
            "title": 'Demo "Prompt"',
            "role": "system",
            "category": "development",
            "tags": ["review", "static-site"],
            "local_tags": [],
            "language": "en",
            "source": "https://example.test/source",
            "author": "Example",
            "license": "MIT",
            "quality": 64,
            "updated": "2026-06-28T00:00:00Z",
        }

        exported = export_markdown_front_matter(record, "Body text")

        self.assertTrue(exported.startswith("---\n"))
        self.assertIn('title: "Demo \\"Prompt\\""', exported)
        self.assertIn("quality: 64", exported)
        self.assertIn('  - "static-site"', exported)
        self.assertIn("\n---\n\nBody text\n", exported)

    def test_compose_prompt_chain_passes_variables_across_steps(self):
        chain = compose_prompt_chain(
            [
                {
                    "title": "Research",
                    "body": "Research {{topic}} for {{audience}}.",
                    "role": "user",
                    "category": "research",
                },
                {
                    "title": "Draft",
                    "body": "Draft for {{audience}} about {{topic}}.",
                    "role": "user",
                    "category": "writing",
                },
            ],
            {"topic": "FTS5", "audience": "developers"},
        )

        self.assertIn("## Step 1: Research", chain)
        self.assertIn("Research FTS5 for developers.", chain)
        self.assertIn("Draft for developers about FTS5.", chain)

    def test_variable_preset_helpers_keep_safe_and_aggressive_profiles(self):
        record = {"variable_presets": []}
        record = set_variable_preset(
            record,
            "Safe defaults",
            {"topic": "release notes", "audience": "maintainers"},
        )
        record = set_variable_preset(
            record,
            "Aggressive",
            {"topic": "launch memo", "audience": "executives"},
        )

        presets = variable_preset_map(record["variable_presets"])

        self.assertEqual(presets["Safe defaults"]["topic"], "release notes")
        self.assertEqual(presets["Aggressive"]["audience"], "executives")
        self.assertEqual(
            fill_prompt_body("Write {{topic}} for {{ audience }}.", presets["Safe defaults"]),
            "Write release notes for maintainers.",
        )

    def test_overlay_persists_variable_presets(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "overlay.jsonl"
            store = OverlayStore(path)
            record = {
                "id": "demo-one",
                "title": "Preset Prompt",
                "body": "Write about {{topic}} for {{audience}}.",
                "role": "user",
                "category": "writing",
                "tags": ["drafting"],
                "local_tags": [],
                "variables": [{"name": "topic"}, {"name": "audience"}],
                "variable_presets": [
                    {
                        "name": "Safe defaults",
                        "values": {"topic": "FTS5", "audience": "developers"},
                    }
                ],
                "target_models": ["any"],
                "language": "en",
                "source": "https://example.test/source",
                "author": "Example",
                "license": "MIT",
                "version": 2,
                "quality": 55,
                "created": "2026-04-18T00:00:00Z",
                "updated": "2026-06-28T00:00:00Z",
            }

            store.save(record)
            reloaded = OverlayStore(path)
            layered = reloaded.apply({"id": "demo-one"})
            presets = variable_preset_map(layered["variable_presets"])

            self.assertEqual(presets["Safe defaults"]["topic"], "FTS5")
            self.assertEqual(layered["variables"], [{"name": "topic"}, {"name": "audience"}])

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

    def test_overlay_notes_and_local_tags_are_searchable(self):
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
                    "title": "Base title",
                    "body": "Base body",
                    "role": "user",
                    "category": "writing",
                    "tags": ["drafting"],
                    "local_tags": ["localtag"],
                    "notes": "Caveat about usage",
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
                tag_results = db.search(query="localtag")
                notes_results = db.search(query="caveat")
            finally:
                db.close()

            self.assertEqual([r["id"] for r in tag_results], ["demo-one"])
            self.assertEqual([r["id"] for r in notes_results], ["demo-one"])

    def test_search_filters_by_language_and_lists_overlay_languages(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            db_path = tmp_path / "prompts.db"
            conn = sqlite3.connect(db_path)
            conn.executescript(SCHEMA)
            insert_prompt(conn, "demo-en", "English", "English body", language="en")
            insert_prompt(conn, "demo-es", "Spanish", "Spanish body", language="es")
            conn.close()

            overlay = OverlayStore(tmp_path / "overlay.jsonl")
            private = make_private_prompt()
            private["language"] = "fr"
            overlay.save(private)

            db = PromptDB(db_path, overlay)
            try:
                es_results = db.search(language="es")
                fr_results = db.search(language="fr")
                languages = db.languages()
            finally:
                db.close()

            self.assertEqual([r["id"] for r in es_results], ["demo-es"])
            self.assertEqual([r["id"] for r in fr_results], [private["id"]])
            self.assertEqual(languages, ["en", "es", "fr"])

    def test_validate_translation_links_checks_original_language(self):
        valid_records = {
            "prompt-en": {"id": "prompt-en", "language": "en"},
            "prompt-es": {
                "id": "prompt-es",
                "language": "es",
                "translation_of": "prompt-en",
                "translated_from": "en",
                "translator": "Example Translator",
            },
        }
        invalid_records = {
            "prompt-en": {"id": "prompt-en", "language": "en"},
            "prompt-bad": {
                "id": "prompt-bad",
                "language": "en",
                "translation_of": "prompt-en",
                "translated_from": "es",
            },
            "prompt-missing": {
                "id": "prompt-missing",
                "language": "fr",
                "translation_of": "missing-original",
                "translated_from": "en",
            },
        }

        self.assertEqual(validate_translation_links(valid_records), [])
        messages = validate_translation_links(invalid_records)

        self.assertTrue(any("translated_from=es does not match" in msg for msg in messages))
        self.assertTrue(any("language=en matches original language" in msg for msg in messages))
        self.assertTrue(any("translation_of=missing-original was not found" in msg for msg in messages))

    def test_overlay_save_appends_local_history_snapshot(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "overlay.jsonl"
            store = OverlayStore(path)
            previous = {
                "id": "demo-one",
                "title": "Original",
                "body": "Old body",
                "role": "user",
                "category": "writing",
                "tags": ["drafting"],
                "local_tags": [],
                "notes": "",
                "variables": [],
                "target_models": ["any"],
                "language": "en",
                "source": "https://example.test/source",
                "author": "Example",
                "license": "MIT",
                "version": 1,
                "quality": 55,
                "created": "2026-04-18T00:00:00Z",
                "updated": "2026-04-18T00:00:00Z",
            }
            updated = dict(previous)
            updated["title"] = "Updated"
            updated["body"] = "New body"
            updated["version"] = 2
            updated["updated"] = "2026-06-27T00:00:00Z"

            store.save(updated, previous=previous)
            reloaded = OverlayStore(path)
            record = reloaded.apply({"id": "demo-one"})

            self.assertEqual(record["history"][0]["title"], "Original")
            diff = format_history_diff(record, record["history"][0])
            self.assertIn("-Title: Original", diff)
            self.assertIn("+Title: Updated", diff)

    def test_markdown_import_front_matter_builds_private_record(self):
        with tempfile.TemporaryDirectory() as tmp:
            import_dir = Path(tmp) / "imports"
            import_dir.mkdir()
            md_path = import_dir / "review.md"
            md_path.write_text(
                "---\n"
                "title: Review Template\n"
                "category: development\n"
                "tags: review, code\n"
                "role: system\n"
                "author: Local User\n"
                "---\n"
                "Review this {{topic}} carefully.\n",
                encoding="utf-8",
            )

            record = markdown_file_record(import_dir, md_path)

            self.assertTrue(record["private"])
            self.assertEqual(record["title"], "Review Template")
            self.assertEqual(record["category"], "development")
            self.assertEqual(record["role"], "system")
            self.assertEqual(record["local_tags"], ["imported", "review", "code"])
            self.assertEqual(record["variables"], [{"name": "topic"}])
            self.assertTrue(record["id"].startswith("import-md-"))

    def test_markdown_import_sync_updates_changed_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            import_dir = tmp_path / "imports"
            import_dir.mkdir()
            md_path = import_dir / "draft.md"
            md_path.write_text("# First Title\n\nFirst body", encoding="utf-8")

            store = OverlayStore(tmp_path / "overlay.jsonl")
            self.assertEqual(store.sync_markdown_imports(import_dir), 1)
            self.assertEqual(store.sync_markdown_imports(import_dir), 0)

            first = store.private_records()[0]
            md_path.write_text("# Second Title\n\nSecond body", encoding="utf-8")
            self.assertEqual(store.sync_markdown_imports(import_dir), 1)
            updated = store.private_records()[0]

            self.assertEqual(first["id"], updated["id"])
            self.assertEqual(updated["title"], "Second Title")
            self.assertEqual(updated["version"], 2)
            self.assertEqual(updated["history"][0]["title"], "First Title")

    def test_private_prompt_is_searchable_without_base_row(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            db_path = tmp_path / "prompts.db"
            conn = sqlite3.connect(db_path)
            conn.executescript(SCHEMA)
            insert_prompt(conn, "demo-one", "Base title", "Base body")
            conn.close()

            overlay = OverlayStore(tmp_path / "overlay.jsonl")
            private = make_private_prompt()
            private["title"] = "Local private draft"
            private["body"] = "privateonly body text"
            overlay.save(private)

            db = PromptDB(db_path, overlay)
            try:
                results = db.search(query="privateonly")
                self.assertEqual(db.total_count(), 2)
            finally:
                db.close()

            self.assertEqual([r["id"] for r in results], [private["id"]])
            self.assertTrue(results[0]["private"])

    @unittest.skipIf(promptcompanion.Fernet is None, "cryptography is not installed")
    def test_private_prompt_can_be_encrypted_in_overlay_jsonl(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "overlay.jsonl"
            with patch.dict(os.environ, {"PROMPTCOMPANION_PRIVATE_PASSPHRASE": "correct horse battery staple"}):
                store = OverlayStore(path)
                private = make_private_prompt()
                private["body"] = "secret private text"
                store.save(private)

                raw = path.read_text(encoding="utf-8")
                self.assertIn('"encrypted":', raw)
                self.assertNotIn("secret private text", raw)

                reloaded = OverlayStore(path)
                records = reloaded.private_records()

            self.assertEqual(records[0]["body"], "secret private text")


if __name__ == "__main__":
    unittest.main()
