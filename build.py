#!/usr/bin/env python3
"""Build PromptCompanion into a single Windows exe via PyInstaller.

Usage:
    python build.py

Output:
    dist/PromptCompanion.exe
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def _bootstrap(packages: list[str]) -> None:
    import importlib.util
    missing = [p for p in packages if importlib.util.find_spec(p.split("[")[0].split(">=")[0].split("==")[0]) is None]
    if not missing:
        return
    subprocess.call([sys.executable, "-m", "pip", "install", *missing])


def main() -> int:
    root = Path(__file__).resolve().parent
    db_path = root / "data" / "index" / "prompts.db"
    logo_path = root / "logo.png"

    if not db_path.exists():
        print("Database not found. Run `python tools/build_index.py` first.")
        return 1

    _bootstrap(["pyinstaller"])

    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--onefile",
        "--windowed",
        "--name", "PromptCompanion",
        "--add-data", f"{db_path};data/index",
    ]

    if logo_path.exists():
        cmd.extend(["--add-data", f"{logo_path};."])
        ico = root / "logo.ico"
        if ico.exists():
            cmd.extend(["--icon", str(ico)])

    cmd.append(str(root / "promptcompanion.py"))

    print(f"Building: {' '.join(cmd)}")
    rc = subprocess.call(cmd)
    if rc == 0:
        exe = root / "dist" / "PromptCompanion.exe"
        if exe.exists():
            print(f"\nBuilt: {exe} ({exe.stat().st_size / 1024 / 1024:.1f} MB)")
    return rc


if __name__ == "__main__":
    sys.exit(main())
