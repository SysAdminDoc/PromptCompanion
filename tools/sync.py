#!/usr/bin/env python3
"""Git-friendly import/export helpers for the local PromptCompanion overlay."""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import read_jsonl, write_jsonl  # noqa: E402


SYNC_FORMAT = "promptcompanion-sync-v1"
BUNDLE_NAME = "prompts.jsonl"
MANIFEST_NAME = "manifest.json"


class SyncError(RuntimeError):
    """Raised when a sync bundle is malformed or cannot be merged safely."""


@dataclass(frozen=True)
class SyncResult:
    changed: int
    skipped: int = 0
    conflicts: tuple[str, ...] = ()


def _is_private(record: dict) -> bool:
    return bool(record.get("private"))


def _record_key(record: dict) -> str:
    prompt_id = str(record.get("id") or "").strip()
    if not prompt_id:
        raise SyncError("Every sync record must have a non-empty id")
    return prompt_id


def _record_payload(record: dict) -> str:
    return json.dumps(record, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _same_record(left: dict, right: dict) -> bool:
    return _record_payload(left) == _record_payload(right)


def _record_version(record: dict) -> int:
    try:
        return int(record.get("version") or 1)
    except (TypeError, ValueError):
        return 1


def _record_updated(record: dict) -> str:
    return str(record.get("updated") or "")


def _read_plain_records(path: Path) -> list[dict]:
    if not path.exists():
        return []
    records = read_jsonl(path)
    encrypted = [record for record in records if record.get("encrypted")]
    if encrypted:
        raise SyncError(
            "Encrypted overlay lines cannot be exported by the headless sync command; "
            "use a plaintext overlay or decrypt it through the desktop app first"
        )
    result: list[dict] = []
    seen: set[str] = set()
    for record in records:
        prompt_id = _record_key(record)
        if prompt_id in seen:
            raise SyncError(f"Duplicate overlay id: {prompt_id}")
        seen.add(prompt_id)
        result.append(record)
    return result


def export_bundle(
    records: list[dict],
    directory: Path,
    *,
    include_private: bool = False,
) -> int:
    """Write a deterministic JSONL bundle and return the number of records."""
    selected: list[dict] = []
    for record in records:
        _record_key(record)
        if _is_private(record) and not include_private:
            continue
        if record.get("encrypted"):
            raise SyncError("Encrypted records cannot be exported as plaintext sync data")
        selected.append(dict(record))

    directory.mkdir(parents=True, exist_ok=True)
    write_jsonl(directory / BUNDLE_NAME, selected)
    manifest = {
        "format": SYNC_FORMAT,
        "record_count": len(selected),
        "private_records": sum(1 for record in selected if _is_private(record)),
    }
    manifest_path = directory / MANIFEST_NAME
    temp_path = manifest_path.with_suffix(".json.tmp")
    temp_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temp_path.replace(manifest_path)
    return len(selected)


def import_bundle(directory: Path, *, include_private: bool = False) -> list[dict]:
    """Read and validate a sync bundle without changing the local overlay."""
    manifest_path = directory / MANIFEST_NAME
    bundle_path = directory / BUNDLE_NAME
    if not manifest_path.exists() or not bundle_path.exists():
        raise SyncError(f"Not a PromptCompanion sync bundle: {directory}")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SyncError(f"Malformed sync manifest: {exc}") from exc
    if manifest.get("format") != SYNC_FORMAT:
        raise SyncError(f"Unsupported sync format: {manifest.get('format', '<missing>')}")

    records = _read_plain_records(bundle_path)
    selected = [
        record for record in records
        if include_private or not _is_private(record)
    ]
    expected = manifest.get("record_count")
    if isinstance(expected, int) and expected != len(records):
        raise SyncError(
            f"Sync manifest expects {expected} records but bundle contains {len(records)}"
        )
    return selected


def merge_overlay(
    overlay_path: Path,
    incoming: list[dict],
    *,
    include_private: bool = False,
) -> SyncResult:
    """Merge incoming records using versions and refuse same-version conflicts."""
    local = _read_plain_records(overlay_path)
    by_id = {_record_key(record): dict(record) for record in local}
    changed = 0
    skipped = 0
    conflicts: list[str] = []

    for record in incoming:
        prompt_id = _record_key(record)
        if _is_private(record) and not include_private:
            skipped += 1
            continue
        remote = dict(record)
        current = by_id.get(prompt_id)
        if current is None:
            by_id[prompt_id] = remote
            changed += 1
            continue
        if _same_record(current, remote):
            skipped += 1
            continue

        local_version = _record_version(current)
        remote_version = _record_version(remote)
        if remote_version > local_version or (
            remote_version == local_version
            and _record_updated(remote) > _record_updated(current)
        ):
            by_id[prompt_id] = remote
            changed += 1
        elif remote_version == local_version and _record_updated(remote) == _record_updated(current):
            conflicts.append(prompt_id)
        else:
            skipped += 1

    if conflicts:
        return SyncResult(changed=0, skipped=skipped, conflicts=tuple(sorted(conflicts)))
    if changed:
        write_jsonl(overlay_path, list(by_id.values()))
    return SyncResult(changed=changed, skipped=skipped)


def overlay_records(path: Path) -> list[dict]:
    """Public read helper used by the CLI and tests."""
    return _read_plain_records(path)
