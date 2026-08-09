#!/usr/bin/env python3
"""Headless PromptCompanion search and clipboard CLI."""

from __future__ import annotations

import argparse
import json
import re
import shutil
import sqlite3
import subprocess
import sys
from pathlib import Path

from tools.plugins import discover_importers
from tools.mcp_server import PromptMcpServer, serve_stdio
from tools.sync import (
    SyncError,
    export_bundle,
    import_bundle,
    merge_overlay,
    overlay_records,
)


ROOT = Path(__file__).resolve().parent
DEFAULT_DB = ROOT / "data" / "index" / "prompts.db"


def search_prompts(
    db_path: Path = DEFAULT_DB,
    query: str = "",
    category: str = "",
    limit: int = 10,
    include_deprecated: bool = False,
) -> list[dict]:
    terms = [term for term in re.sub(r"[^\w\s]", " ", query.strip()).split() if term]
    conditions = ["COALESCE(p.deprecated, 0) = 1" if include_deprecated else "COALESCE(p.deprecated, 0) = 0"]
    params: list[object] = []
    if category:
        conditions.append("p.category = ?")
        params.append(category)

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        if terms:
            conditions.append("prompts_fts MATCH ?")
            params.append(" ".join(f'"{term}"*' for term in terms))
            sql = """
                SELECT p.id, p.title, p.body, p.category, p.quality, p.deprecated
                FROM prompts p
                JOIN prompts_fts ON prompts_fts.rowid = p.rowid
                WHERE """ + " AND ".join(conditions) + """
                ORDER BY bm25(prompts_fts, 10.0, 1.0, 5.0, 2.0), p.quality DESC
                LIMIT ?
            """
        else:
            sql = """
                SELECT p.id, p.title, p.body, p.category, p.quality, p.deprecated
                FROM prompts p
                WHERE """ + " AND ".join(conditions) + """
                ORDER BY p.quality DESC, p.title COLLATE NOCASE
                LIMIT ?
            """
        params.append(max(1, min(int(limit), 100)))
        return [dict(row) for row in conn.execute(sql, params).fetchall()]
    finally:
        conn.close()


def copy_to_clipboard(text: str) -> bool:
    if sys.platform == "win32":
        command = shutil.which("clip") or shutil.which("clip.exe")
    elif sys.platform == "darwin":
        command = shutil.which("pbcopy")
    else:
        command = shutil.which("wl-copy") or shutil.which("xclip")
    if not command:
        return False
    args = [command]
    if Path(command).name.casefold() == "xclip":
        args.extend(["-selection", "clipboard"])
    try:
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        subprocess.run(args, input=text, text=True, check=True, creationflags=flags)
    except (OSError, subprocess.CalledProcessError):
        return False
    return True


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="promptcompanion")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB, help="Path to a PromptCompanion SQLite index")
    subparsers = parser.add_subparsers(dest="command", required=True)

    search_parser = subparsers.add_parser("search", help="Search prompts and copy the best match")
    search_parser.add_argument("query")
    search_parser.add_argument("--category", default="")
    search_parser.add_argument("--limit", type=int, default=10)
    search_parser.add_argument("--no-copy", action="store_false", dest="copy")

    subparsers.add_parser("plugins", help="List installed custom importer plugins")
    subparsers.add_parser("mcp", help="Serve the prompt index over MCP-compatible stdio")
    sync_parser = subparsers.add_parser(
        "sync",
        help="Export or import a Git-friendly local overlay bundle",
    )
    sync_parser.add_argument("action", choices=("export", "import", "status"))
    sync_parser.add_argument(
        "--directory",
        type=Path,
        required=True,
        help="Directory containing the Git-managed PromptCompanion bundle",
    )
    sync_parser.add_argument(
        "--overlay",
        type=Path,
        default=ROOT / "data" / "user" / "overlay.jsonl",
        help="Local overlay JSONL path",
    )
    sync_parser.add_argument(
        "--include-private",
        action="store_true",
        help="Include private records in export/import operations",
    )
    args = parser.parse_args(argv)

    if args.command == "plugins":
        plugins = discover_importers()
        for name in sorted(plugins):
            print(name)
        return 0

    if args.command == "mcp":
        return serve_stdio(PromptMcpServer(args.db))

    if args.command == "sync":
        try:
            if args.action == "export":
                count = export_bundle(
                    overlay_records(args.overlay),
                    args.directory,
                    include_private=args.include_private,
                )
                print(f"Exported {count} records to {args.directory}")
                return 0
            if args.action == "import":
                incoming = import_bundle(args.directory, include_private=args.include_private)
                result = merge_overlay(
                    args.overlay,
                    incoming,
                    include_private=args.include_private,
                )
                if result.conflicts:
                    print(
                        "Conflicts (same id/version/timestamp): "
                        + ", ".join(result.conflicts),
                        file=sys.stderr,
                    )
                    return 2
                print(f"Imported {result.changed} records ({result.skipped} unchanged/skipped)")
                return 0

            local = {_record["id"]: _record for _record in overlay_records(args.overlay)}
            remote = {
                _record["id"]: _record
                for _record in import_bundle(args.directory, include_private=args.include_private)
            }
            same = sum(1 for prompt_id in local.keys() & remote.keys() if local[prompt_id] == remote[prompt_id])
            print(json.dumps({
                "local_records": len(local),
                "bundle_records": len(remote),
                "local_only": len(local.keys() - remote.keys()),
                "bundle_only": len(remote.keys() - local.keys()),
                "identical": same,
            }, indent=2))
            return 0
        except (OSError, SyncError, json.JSONDecodeError) as exc:
            print(f"Sync failed: {exc}", file=sys.stderr)
            return 2

    results = search_prompts(args.db, args.query, args.category, args.limit)
    if not results:
        print("No prompts found.", file=sys.stderr)
        return 1
    selected = results[0]
    if args.copy and copy_to_clipboard(selected["body"]):
        print(f"Copied: {selected['title']}")
    else:
        print(json.dumps(selected, ensure_ascii=False, indent=2) if not args.copy else selected["body"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
