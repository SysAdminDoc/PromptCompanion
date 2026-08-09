#!/usr/bin/env python3
"""Dependency-free MCP-style stdio server for the PromptCompanion index.

The transport is newline-delimited JSON-RPC 2.0, which keeps the server usable
from MCP clients that launch local commands without requiring a Python MCP SDK.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import sqlite3
from pathlib import Path
from typing import TextIO


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DB = ROOT / "data" / "index" / "prompts.db"
MCP_PROTOCOL_VERSION = "2024-11-05"
SERVER_VERSION = "0.9.0"
_INCLUDE_RE = re.compile(r"\{\{\s*include:([a-zA-Z0-9_.:/-]{1,180})\s*\}\}")
_SLUG_RE = re.compile(r"[^a-z0-9]+")


TOOLS = [
    {
        "name": "search_prompts",
        "description": "Search the offline PromptCompanion library using SQLite FTS5.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Words to search for."},
                "category": {"type": "string"},
                "source": {"type": "string"},
                "language": {"type": "string"},
                "provider": {"type": "string", "description": "openai, anthropic, or local."},
                "include_deprecated": {"type": "boolean", "default": False},
                "limit": {"type": "integer", "minimum": 1, "maximum": 50, "default": 10},
            },
        },
    },
    {
        "name": "get_prompt",
        "description": "Fetch one prompt record by its stable id.",
        "inputSchema": {
            "type": "object",
            "required": ["prompt_id"],
            "properties": {"prompt_id": {"type": "string"}},
        },
    },
    {
        "name": "render_prompt",
        "description": "Resolve includes and substitute variables in a prompt body.",
        "inputSchema": {
            "type": "object",
            "required": ["prompt_id"],
            "properties": {
                "prompt_id": {"type": "string"},
                "variables": {"type": "object", "additionalProperties": {"type": "string"}},
            },
        },
    },
]


def _json_list(value) -> list:
    if isinstance(value, list):
        return value
    try:
        parsed = json.loads(value or "[]")
    except (TypeError, ValueError):
        return []
    return parsed if isinstance(parsed, list) else []


def _slug(value: str) -> str:
    return _SLUG_RE.sub("-", value.casefold()).strip("-")


def _provider_for_model(model: str) -> str:
    value = str(model).casefold().strip()
    if value in {"any", ""}:
        return "any"
    if value.startswith(("gpt-", "o1", "o3", "o4", "openai")):
        return "openai"
    if value.startswith(("claude-", "anthropic")):
        return "anthropic"
    if value.startswith(("llama", "mistral", "qwen", "ollama", "local")):
        return "local"
    return value


def _model_matches(record: dict, provider: str) -> bool:
    wanted = str(provider or "").casefold().strip()
    if not wanted:
        return True
    return any(_provider_for_model(model) in {"any", wanted} for model in record.get("target_models", []))


class PromptMcpServer:
    """Read-only JSON-RPC request handler backed by one PromptCompanion index."""

    def __init__(self, db_path: Path = DEFAULT_DB):
        self.db_path = Path(db_path)

    def _connect(self) -> sqlite3.Connection:
        if not self.db_path.exists():
            raise FileNotFoundError(f"Prompt index not found: {self.db_path}")
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        return conn

    @staticmethod
    def _record(row: sqlite3.Row | dict) -> dict:
        record = dict(row)
        for key in ("tags", "variables", "target_models"):
            if key in record:
                record[key] = _json_list(record[key])
        for key in ("deprecated",):
            if key in record:
                record[key] = bool(record[key])
        return record

    def _get_by_id(self, prompt_id: str) -> dict | None:
        conn = self._connect()
        try:
            row = conn.execute("SELECT * FROM prompts WHERE id = ?", (prompt_id,)).fetchone()
            return self._record(row) if row else None
        finally:
            conn.close()

    def _search(self, arguments: dict) -> list[dict]:
        query = str(arguments.get("query") or "").strip()
        terms = [term for term in re.sub(r"[^\w\s]", " ", query).split() if term]
        category = str(arguments.get("category") or "").strip()
        source = str(arguments.get("source") or "").strip()
        language = str(arguments.get("language") or "").strip()
        provider = str(arguments.get("provider") or "").strip()
        include_deprecated = bool(arguments.get("include_deprecated", False))
        try:
            limit = max(1, min(int(arguments.get("limit", 10)), 50))
        except (TypeError, ValueError):
            limit = 10

        conditions: list[str] = []
        params: list[object] = []
        if terms:
            conditions.append("prompts_fts MATCH ?")
            params.append(" ".join(f'"{term}"*' for term in terms))
        if category:
            conditions.append("p.category = ?")
            params.append(category)
        if source:
            conditions.append("p.id LIKE ?")
            params.append(f"{source}-%")
        if language:
            conditions.append("p.language = ?")
            params.append(language)
        if not include_deprecated:
            conditions.append("COALESCE(p.deprecated, 0) = 0")

        where = " AND ".join(conditions) or "1 = 1"
        if terms:
            sql = f"""
                SELECT p.*
                FROM prompts p
                JOIN prompts_fts ON prompts_fts.rowid = p.rowid
                WHERE {where}
                ORDER BY bm25(prompts_fts, 10.0, 1.0, 5.0, 2.0), p.quality DESC
                LIMIT ?
            """
        else:
            sql = f"""
                SELECT p.*
                FROM prompts p
                WHERE {where}
                ORDER BY p.quality DESC, p.title COLLATE NOCASE
                LIMIT ?
            """
        params.append(max(limit, 500) if provider else limit)
        conn = self._connect()
        try:
            records = [self._record(row) for row in conn.execute(sql, params).fetchall()]
        finally:
            conn.close()
        if provider:
            records = [record for record in records if _model_matches(record, provider)]
        return records[:limit]

    def _resolve_include(self, reference: str, seen: set[str], depth: int = 0) -> str:
        if depth >= 10:
            return ""
        ref = reference.strip().strip("/")
        if not ref:
            return ""
        record = self._get_by_id(ref)
        if not record and "/" in ref:
            category, wanted = ref.split("/", 1)
            wanted_slug = _slug(wanted)
            conn = self._connect()
            try:
                rows = conn.execute(
                    "SELECT * FROM prompts WHERE category = ?",
                    (category.casefold(),),
                ).fetchall()
            finally:
                conn.close()
            candidates = [
                self._record(row)
                for row in rows
                if wanted_slug in {_slug(str(row["id"])), _slug(str(row["title"]))}
                or _slug(str(row["id"])).endswith("-" + wanted_slug)
            ]
            if candidates:
                candidates.sort(key=lambda item: (-int(item.get("quality") or 0), item.get("title", "").casefold()))
                record = candidates[0]
        if not record or record["id"] in seen:
            return ""
        return self._expand(str(record.get("body") or ""), seen | {record["id"]}, depth + 1)

    def _expand(self, body: str, seen: set[str] | None = None, depth: int = 0) -> str:
        seen = seen or set()
        return _INCLUDE_RE.sub(
            lambda match: self._resolve_include(match.group(1), seen, depth),
            body,
        )

    def _tool_result(self, value, *, is_error: bool = False) -> dict:
        return {
            "content": [{"type": "text", "text": json.dumps(value, ensure_ascii=False, indent=2)}],
            "structuredContent": value,
            "isError": is_error,
        }

    def _call_tool(self, name: str, arguments: dict) -> dict:
        if name == "search_prompts":
            return self._tool_result(self._search(arguments))
        if name == "get_prompt":
            prompt_id = str(arguments.get("prompt_id") or "").strip()
            if not prompt_id:
                return self._tool_result({"error": "prompt_id is required"}, is_error=True)
            record = self._get_by_id(prompt_id)
            if record is None:
                return self._tool_result({"error": f"Prompt not found: {prompt_id}"}, is_error=True)
            return self._tool_result(record)
        if name == "render_prompt":
            prompt_id = str(arguments.get("prompt_id") or "").strip()
            record = self._get_by_id(prompt_id) if prompt_id else None
            if record is None:
                return self._tool_result({"error": f"Prompt not found: {prompt_id}"}, is_error=True)
            variables = arguments.get("variables") or {}
            if not isinstance(variables, dict):
                return self._tool_result({"error": "variables must be an object"}, is_error=True)
            body = self._expand(str(record.get("body") or ""), {prompt_id})
            body = re.sub(
                r"\{\{\s*([a-zA-Z_][a-zA-Z0-9_]{0,63})\s*\}\}",
                lambda match: str(variables.get(match.group(1), match.group(0))),
                body,
            )
            return self._tool_result({"id": prompt_id, "title": record.get("title", ""), "body": body})
        return self._tool_result({"error": f"Unknown tool: {name}"}, is_error=True)

    def handle(self, request: dict) -> dict | None:
        """Handle one JSON-RPC request; return ``None`` for notifications."""
        request_id = request.get("id")
        if request.get("jsonrpc") != "2.0" or not isinstance(request.get("method"), str):
            return {"jsonrpc": "2.0", "id": request_id, "error": {"code": -32600, "message": "Invalid Request"}}
        method = request["method"]
        params = request.get("params") or {}
        try:
            if method == "initialize":
                result = {
                    "protocolVersion": MCP_PROTOCOL_VERSION,
                    "capabilities": {"tools": {}},
                    "serverInfo": {"name": "PromptCompanion", "version": SERVER_VERSION},
                }
            elif method == "notifications/initialized":
                return None
            elif method == "ping":
                result = {}
            elif method == "tools/list":
                result = {"tools": TOOLS}
            elif method == "tools/call":
                if not isinstance(params, dict):
                    raise ValueError("params must be an object")
                result = self._call_tool(str(params.get("name") or ""), params.get("arguments") or {})
            else:
                return {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "error": {"code": -32601, "message": f"Method not found: {method}"},
                }
        except (FileNotFoundError, OSError, sqlite3.Error, TypeError, ValueError, json.JSONDecodeError) as exc:
            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "error": {"code": -32000, "message": str(exc)},
            }
        if request_id is None:
            return None
        return {"jsonrpc": "2.0", "id": request_id, "result": result}


def serve_stdio(
    server: PromptMcpServer,
    input_stream: TextIO | None = None,
    output_stream: TextIO | None = None,
) -> int:
    input_stream = input_stream or sys.stdin
    output_stream = output_stream or sys.stdout
    for line in input_stream:
        if not line.strip():
            continue
        try:
            request = json.loads(line)
            response = server.handle(request)
        except (TypeError, json.JSONDecodeError) as exc:
            response = {
                "jsonrpc": "2.0",
                "id": None,
                "error": {"code": -32700, "message": f"Parse error: {exc}"},
            }
        if response is not None:
            output_stream.write(json.dumps(response, ensure_ascii=False) + "\n")
            output_stream.flush()
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Serve the PromptCompanion index over MCP-style stdio")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    args = parser.parse_args(argv)
    return serve_stdio(PromptMcpServer(args.db))


if __name__ == "__main__":
    raise SystemExit(main())
