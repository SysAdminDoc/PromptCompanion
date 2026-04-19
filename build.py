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
    subprocess.check_call([sys.executable, "-m", "pip", "install", *missing])


def main() -> int:
    root = Path(__file__).resolve().parent
    db_path = root / "data" / "index" / "prompts.db"
    logo_path = root / "logo.png"

    if not db_path.exists():
        print("Database not found. Run `python tools/build_index.py` first.")
        return 1

    _bootstrap(["pyinstaller", "Pillow"])

    # Generate .ico from logo.png if it doesn't exist
    ico_path = root / "logo.ico"
    if logo_path.exists() and not ico_path.exists():
        print("Generating logo.ico from logo.png...")
        from PIL import Image
        img = Image.open(logo_path)
        img.save(str(ico_path), format="ICO", sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
        print(f"Created: {ico_path}")

    # Clean previous build artifacts to avoid stale spec conflicts
    for p in [root / "build", root / "dist", root / "PromptCompanion.spec"]:
        if p.is_file():
            p.unlink()
        elif p.is_dir():
            import shutil
            shutil.rmtree(p, ignore_errors=True)

    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--onefile",
        "--windowed",
        "--name", "PromptCompanion",
        "--add-data", f"{db_path};data/index",
        # Hidden imports that PyInstaller misses for PyQt6
        "--hidden-import", "PyQt6.QtCore",
        "--hidden-import", "PyQt6.QtGui",
        "--hidden-import", "PyQt6.QtWidgets",
        "--hidden-import", "PyQt6.sip",
        # Exclude unnecessary large modules to reduce exe size
        "--exclude-module", "matplotlib",
        "--exclude-module", "numpy",
        "--exclude-module", "pandas",
        "--exclude-module", "PIL",
        "--exclude-module", "tkinter",
        "--exclude-module", "unittest",
        "--exclude-module", "xmlrpc",
        "--exclude-module", "pydoc",
        "--exclude-module", "doctest",
        "--noconfirm",
    ]

    if logo_path.exists():
        cmd.extend(["--add-data", f"{logo_path};."])

    if ico_path.exists():
        cmd.extend(["--icon", str(ico_path)])

    cmd.append(str(root / "promptcompanion.py"))

    print(f"Building with PyInstaller...")
    print(f"Command: {' '.join(cmd)}")
    rc = subprocess.call(cmd)
    if rc == 0:
        exe = root / "dist" / "PromptCompanion.exe"
        if exe.exists():
            size_mb = exe.stat().st_size / 1024 / 1024
            print(f"\nBuild successful: {exe}")
            print(f"Size: {size_mb:.1f} MB")
    else:
        print(f"\nBuild failed with exit code {rc}")
    return rc


if __name__ == "__main__":
    sys.exit(main())
