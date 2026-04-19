#!/usr/bin/env python3
"""Clone (or update) upstream prompt sources into data/sources/upstream/<key>/."""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import UPSTREAM_DIR, load_registry, log


def git(*args: str, cwd: Path | None = None) -> int:
    return subprocess.call(["git", *args], cwd=str(cwd) if cwd else None)


def clone_or_update(key: str, repo_url: str) -> None:
    dest = UPSTREAM_DIR / key
    if dest.exists() and (dest / ".git").exists():
        log(f"Updating {key} -> {dest}")
        rc = git("pull", "--ff-only", cwd=dest)
        if rc != 0:
            log(f"  pull failed, leaving {key} as-is")
        return
    if dest.exists():
        shutil.rmtree(dest)
    UPSTREAM_DIR.mkdir(parents=True, exist_ok=True)
    log(f"Cloning {key} <- {repo_url}")
    rc = git("clone", "--depth", "1", repo_url, str(dest))
    if rc != 0:
        raise SystemExit(f"Failed to clone {repo_url}")


def main() -> int:
    registry = load_registry()
    for src in registry["sources"]:
        if src["license"] not in registry["license_allowlist"]:
            log(f"SKIP {src['key']} (license {src['license']} not in allowlist)")
            continue
        clone_or_update(src["key"], src["repo"])
    log("done.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
