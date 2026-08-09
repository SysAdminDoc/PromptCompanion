#!/usr/bin/env python3
"""Small, dependency-free GitHub Releases updater primitives."""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable
from urllib.parse import urlparse
from urllib.request import Request, urlopen


RELEASES_API = "https://api.github.com/repos/SysAdminDoc/PromptCompanion/releases/latest"
_VERSION_RE = re.compile(r"\d+(?:\.\d+)+")


@dataclass(frozen=True)
class ReleaseAsset:
    name: str
    url: str


@dataclass(frozen=True)
class ReleaseInfo:
    tag_name: str
    version: str
    page_url: str
    assets: tuple[ReleaseAsset, ...]


def version_key(version: str) -> tuple[int, ...]:
    match = _VERSION_RE.search(str(version))
    if not match:
        return (0,)
    return tuple(int(part) for part in match.group(0).split("."))


def is_newer_version(current: str, candidate: str) -> bool:
    return version_key(candidate) > version_key(current)


def _https_url(url: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme != "https" or not parsed.netloc:
        raise ValueError("Updater URLs must use HTTPS")
    return url


def fetch_latest_release(
    api_url: str = RELEASES_API,
    opener: Callable = urlopen,
) -> ReleaseInfo:
    request = Request(
        _https_url(api_url),
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "PromptCompanion-updater",
        },
    )
    with opener(request, timeout=10) as response:
        payload = json.loads(response.read().decode("utf-8"))
    tag_name = str(payload.get("tag_name") or "").strip()
    version = _VERSION_RE.search(tag_name)
    if not version:
        raise ValueError("GitHub release did not contain a semantic version tag")
    assets = tuple(
        ReleaseAsset(str(asset.get("name") or ""), _https_url(str(asset.get("browser_download_url") or "")))
        for asset in payload.get("assets", [])
        if asset.get("name") and asset.get("browser_download_url")
    )
    return ReleaseInfo(
        tag_name=tag_name,
        version=version.group(0),
        page_url=str(payload.get("html_url") or "https://github.com/SysAdminDoc/PromptCompanion/releases"),
        assets=assets,
    )


def choose_asset(release: ReleaseInfo, platform: str | None = None) -> ReleaseAsset | None:
    platform = platform or sys.platform
    names = [asset for asset in release.assets if asset.name]
    if platform == "win32":
        preferred = [asset for asset in names if asset.name.casefold().endswith(".exe")]
    elif platform == "darwin":
        preferred = [asset for asset in names if asset.name.casefold().endswith((".dmg", ".zip"))]
    else:
        preferred = [asset for asset in names if asset.name.casefold().endswith((".appimage", ".tar.gz", ".zip"))]
    return (preferred or names or [None])[0]


def download_asset(
    asset_url: str,
    destination: Path,
    opener: Callable = urlopen,
) -> Path:
    """Download an HTTPS release asset atomically into ``destination``."""
    _https_url(asset_url)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temp_path: Path | None = None
    try:
        with opener(Request(asset_url, headers={"User-Agent": "PromptCompanion-updater"}), timeout=30) as response:
            with tempfile.NamedTemporaryFile(
                mode="wb", prefix=f".{destination.name}.", suffix=".download", dir=destination.parent, delete=False
            ) as temp:
                temp_path = Path(temp.name)
                while chunk := response.read(1024 * 1024):
                    temp.write(chunk)
                temp.flush()
                os.fsync(temp.fileno())
        os.replace(temp_path, destination)
        temp_path = None
        return destination
    finally:
        if temp_path:
            temp_path.unlink(missing_ok=True)


def schedule_windows_install(current_executable: Path, downloaded_asset: Path) -> Path:
    """Schedule a replacement after the current process exits."""
    if os.name != "nt":
        raise RuntimeError("Self-install is currently supported on Windows only")
    current = current_executable.resolve()
    downloaded = downloaded_asset.resolve()
    if current.parent != downloaded.parent:
        raise ValueError("Downloaded update must be next to the current executable")
    script = current.with_suffix(".update.cmd")
    script.write_text(
        "@echo off\r\n"
        "timeout /t 2 /nobreak >nul\r\n"
        f'move /y "{downloaded.name}" "{current.name}" >nul\r\n'
        f'start "" "{current.name}"\r\n'
        f'del "%~f0"\r\n',
        encoding="utf-8",
        newline="",
    )
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    subprocess.Popen(["cmd", "/d", "/c", str(script)], cwd=str(current.parent), creationflags=flags)
    return script
