#!/usr/bin/env python3
"""PromptCompanion v0.8.1 — Desktop GUI for curated AI prompts.

Three-pane layout: category tree | prompt list | preview + variables.
SQLite FTS5 search with bm25 ranking. Catppuccin Mocha dark theme.
Favorites, history, system tray, global hotkey (Win+Shift+P).
Paste-to-active-window. Personal overlay edits. Export as plain text, markdown, or JSON.
"""

from __future__ import annotations

import multiprocessing

multiprocessing.freeze_support()

import base64
import difflib
import hashlib
import json
import os
import re
import sqlite3
import subprocess
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote  # noqa: E402

try:
    from cryptography.fernet import Fernet, InvalidToken
except ImportError:  # Optional: only needed when private prompt encryption is enabled.
    Fernet = None
    InvalidToken = Exception

try:
    import tiktoken
except ImportError:  # Optional local tokenizer; the dependency-free estimate remains available.
    tiktoken = None

try:
    from pynput import keyboard as pynput_keyboard
except ImportError:  # Optional cross-platform global hotkey backend.
    pynput_keyboard = None

IS_WIN = sys.platform == "win32"


def _is_frozen() -> bool:
    return getattr(sys, "frozen", False) or hasattr(sys, "_MEIPASS")


def _bootstrap(packages: list[str]) -> None:
    if _is_frozen():
        return
    import importlib.util
    missing = [p for p in packages if importlib.util.find_spec(p.split("[")[0].split(">=")[0].split("==")[0]) is None]
    if not missing:
        return
    def _run(args: list[str]) -> int:
        return subprocess.call([sys.executable, "-m", "pip", "install", *args, *missing])
    if _run([]) != 0 and _run(["--user"]) != 0:
        _run(["--user", "--break-system-packages"])


_bootstrap(["PyQt6"])

from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QThread, QSettings, QUrl
from PyQt6.QtGui import QColor, QFont, QStandardItem, QStandardItemModel, QIcon, QAction, QShortcut, QKeySequence, QDesktopServices
from PyQt6.QtWidgets import (
    QApplication, QComboBox, QHBoxLayout, QHeaderView, QLabel, QLineEdit,
    QMainWindow, QPlainTextEdit, QPushButton, QScrollArea, QSplitter,
    QTreeView, QTableView, QVBoxLayout, QWidget, QAbstractItemView,
    QFormLayout, QFrame, QGroupBox, QSystemTrayIcon, QMenu, QStackedWidget,
    QSizePolicy,
)
from tools.updater import (  # noqa: E402
    ReleaseInfo,
    choose_asset,
    download_asset,
    fetch_latest_release,
    is_newer_version,
    schedule_windows_install,
)


# -- Paths -----------------------------------------------------------------
def resolve_runtime_paths(
    is_frozen: bool,
    executable_dir: Path,
    bundle_root: Path,
    portable: bool,
) -> tuple[Path, Path, Path]:
    """Resolve bundled resources, user data, and the portable database location."""
    if not is_frozen:
        root = bundle_root
        return root, root / "data" / "user", root / "data" / "index" / "prompts.db"
    if portable:
        root = executable_dir
        portable_db = root / "data" / "index" / "prompts.db"
        db = portable_db if portable_db.exists() else bundle_root / "data" / "index" / "prompts.db"
        return root, root / "data" / "user", db
    return bundle_root, Path.home() / ".promptcompanion", bundle_root / "data" / "index" / "prompts.db"


def _env_flag(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes", "on"}


_SOURCE_ROOT = Path(__file__).resolve().parent
_EXECUTABLE_DIR = Path(sys.executable).resolve().parent
PORTABLE_MODE = _env_flag("PROMPTCOMPANION_PORTABLE") or (_EXECUTABLE_DIR / "portable.flag").exists()
AUTO_UPDATE_ENABLED = _env_flag("PROMPTCOMPANION_AUTO_UPDATE")
ROOT, USER_DIR, DB_PATH = resolve_runtime_paths(
    _is_frozen(), _EXECUTABLE_DIR, Path(getattr(sys, "_MEIPASS", _SOURCE_ROOT)), PORTABLE_MODE
)
LOGO_PATH = ROOT / "logo.png"
if not LOGO_PATH.exists() and _is_frozen():
    LOGO_PATH = Path(getattr(sys, "_MEIPASS", ROOT)) / "logo.png"
USER_DIR.mkdir(parents=True, exist_ok=True)
USER_DB_PATH = USER_DIR / "user.db"
OVERLAY_PATH = USER_DIR / "overlay.jsonl"
IMPORT_DIR = USER_DIR / "imports"

VERSION = "0.8.1"

# -- Catppuccin Mocha ------------------------------------------------------
C = {
    "base": "#1E1E2E", "mantle": "#181825", "crust": "#11111B",
    "surface0": "#313244", "surface1": "#45475A", "surface2": "#585B70",
    "overlay0": "#6C7086", "overlay1": "#7F849C",
    "subtext0": "#A6ADC8", "subtext1": "#BAC2DE", "text": "#CDD6F4",
    "lavender": "#B4BEFE", "blue": "#89B4FA", "sapphire": "#74C7EC",
    "teal": "#94E2D5", "green": "#A6E3A1", "yellow": "#F9E2AF",
    "peach": "#FAB387", "red": "#F38BA8", "mauve": "#CBA6F7",
    "pink": "#F5C2E7", "flamingo": "#F2CDCD", "rosewater": "#F5E0DC",
}

# -- Design tokens ---------------------------------------------------------
# Radius:  6px small (pills, tags)  8px medium (inputs, buttons, cards)  10px large (search)
# Type:    11px caption  12px small  13px body  14px subhead  16px title  20px display
# Space:   4  8  12  16  20  24  32

STYLESHEET = f"""
/* -- Base -- */
QMainWindow, QWidget {{
    background-color: {C['base']};
    color: {C['text']};
    font-family: "Segoe UI", "Inter", "SF Pro Display", -apple-system, sans-serif;
    font-size: 13px;
}}

/* -- Inputs -- */
QLineEdit {{
    background-color: {C['surface0']};
    color: {C['text']};
    border: 1px solid transparent;
    border-radius: 8px;
    padding: 7px 12px;
    selection-background-color: {C['lavender']};
    selection-color: {C['crust']};
}}
QLineEdit:hover {{
    border: 1px solid {C['surface1']};
}}
QLineEdit:focus {{
    border: 1px solid {C['lavender']};
    background-color: {C['mantle']};
}}
QLineEdit#searchInput {{
    padding: 9px 16px;
    font-size: 13px;
    border-radius: 10px;
    background-color: {C['surface0']};
}}
QLineEdit#searchInput:focus {{
    border: 1px solid {C['lavender']};
    background-color: {C['mantle']};
}}

/* -- Combos -- */
QComboBox {{
    background-color: {C['surface0']};
    color: {C['subtext1']};
    border: 1px solid transparent;
    border-radius: 8px;
    padding: 6px 28px 6px 10px;
    font-size: 12px;
    min-height: 20px;
}}
QComboBox:hover {{
    border: 1px solid {C['surface2']};
    color: {C['text']};
}}
QComboBox:focus {{
    border: 1px solid {C['lavender']};
}}
QComboBox::drop-down {{
    border: none;
    width: 22px;
}}
QComboBox::down-arrow {{
    image: none;
    border-left: 4px solid transparent;
    border-right: 4px solid transparent;
    border-top: 5px solid {C['overlay0']};
    margin-right: 8px;
}}
QComboBox QAbstractItemView {{
    background-color: {C['surface0']};
    color: {C['text']};
    border: 1px solid {C['surface1']};
    border-radius: 8px;
    padding: 4px;
    selection-background-color: {C['surface1']};
    selection-color: {C['lavender']};
    outline: none;
}}

/* -- Buttons -- */
QPushButton {{
    background-color: {C['surface0']};
    color: {C['subtext1']};
    border: 1px solid transparent;
    border-radius: 8px;
    padding: 8px 20px;
    font-weight: 500;
    font-size: 12px;
}}
QPushButton:hover {{
    background-color: {C['surface1']};
    color: {C['text']};
    border: 1px solid {C['surface2']};
}}
QPushButton:pressed {{
    background-color: {C['surface2']};
}}
QPushButton:disabled {{
    background-color: {C['surface0']};
    color: {C['overlay0']};
    border: 1px solid transparent;
}}
QPushButton#primaryBtn {{
    background-color: {C['lavender']};
    color: {C['crust']};
    border: none;
    font-weight: 600;
    padding: 8px 24px;
}}
QPushButton#primaryBtn:hover {{
    background-color: {C['blue']};
}}
QPushButton#primaryBtn:pressed {{
    background-color: #7B8FF0;
}}
QPushButton#primaryBtn:disabled {{
    background-color: {C['surface1']};
    color: {C['overlay0']};
}}
QPushButton#accentBtn {{
    background-color: {C['teal']};
    color: {C['crust']};
    border: none;
    font-weight: 600;
    padding: 8px 24px;
}}
QPushButton#accentBtn:hover {{
    background-color: {C['green']};
}}
QPushButton#accentBtn:pressed {{
    background-color: #7DD99B;
}}
QPushButton#accentBtn:disabled {{
    background-color: {C['surface1']};
    color: {C['overlay0']};
}}
QPushButton#favBtn {{
    background-color: transparent;
    border: none;
    font-size: 20px;
    padding: 2px 6px;
    border-radius: 6px;
}}
QPushButton#favBtn:hover {{
    background-color: {C['surface0']};
}}
QLabel#overlayBadge {{
    background-color: rgba(148,226,213,0.14);
    color: {C['teal']};
    border: 1px solid rgba(148,226,213,0.28);
    border-radius: 6px;
    padding: 3px 8px;
    font-size: 11px;
    font-weight: 600;
}}

/* -- Tree & Table -- */
QTreeView, QTableView {{
    background-color: {C['mantle']};
    color: {C['text']};
    border: none;
    outline: none;
}}
QTreeView::item {{
    padding: 7px 14px;
    border-radius: 0px;
}}
QTableView::item {{
    padding: 6px 10px;
}}
QTreeView::item:selected {{
    background-color: {C['surface0']};
    color: {C['lavender']};
}}
QTreeView::item:hover:!selected {{
    background-color: rgba(49, 50, 68, 0.4);
}}
QTableView::item:selected {{
    background-color: {C['surface0']};
    color: {C['lavender']};
}}
QTableView::item:hover:!selected {{
    background-color: rgba(49, 50, 68, 0.3);
}}
QTreeView::branch {{
    background-color: {C['mantle']};
}}
QTreeView::branch:selected {{
    background-color: {C['surface0']};
}}
QHeaderView::section {{
    background-color: {C['crust']};
    color: {C['overlay1']};
    border: none;
    border-bottom: 1px solid {C['surface0']};
    padding: 8px 10px;
    font-weight: 600;
    font-size: 11px;
    text-transform: uppercase;
    letter-spacing: 0.5px;
}}

/* -- Scrollbars -- */
QScrollBar:vertical {{
    background: transparent;
    width: 8px;
    margin: 4px 2px;
}}
QScrollBar::handle:vertical {{
    background: {C['surface1']};
    border-radius: 4px;
    min-height: 40px;
}}
QScrollBar::handle:vertical:hover {{
    background: {C['surface2']};
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical,
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
    height: 0px;
}}
QScrollBar:horizontal {{
    background: transparent;
    height: 8px;
    margin: 2px 4px;
}}
QScrollBar::handle:horizontal {{
    background: {C['surface1']};
    border-radius: 4px;
    min-width: 40px;
}}
QScrollBar::handle:horizontal:hover {{
    background: {C['surface2']};
}}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal,
QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {{
    width: 0px;
}}

/* -- Splitter -- */
QSplitter::handle {{
    background-color: {C['surface0']};
    width: 1px;
}}
QSplitter::handle:hover {{
    background-color: {C['surface2']};
}}

/* -- Status bar -- */
QStatusBar {{
    background-color: {C['crust']};
    color: {C['overlay1']};
    font-size: 11px;
    padding: 4px 12px;
    border-top: 1px solid {C['surface0']};
}}

/* -- Body editor -- */
QPlainTextEdit#bodyEditor {{
    background-color: {C['mantle']};
    color: {C['subtext1']};
    border: 1px solid {C['surface0']};
    border-radius: 8px;
    padding: 14px 16px;
    selection-background-color: {C['lavender']};
    selection-color: {C['crust']};
    line-height: 1.5;
}}
QPlainTextEdit#bodyEditor:focus {{
    border: 1px solid {C['surface1']};
}}

/* -- Group box -- */
QGroupBox {{
    color: {C['overlay1']};
    border: 1px solid {C['surface0']};
    border-radius: 8px;
    margin-top: 16px;
    padding: 20px 14px 14px 14px;
    font-weight: 600;
    font-size: 11px;
    text-transform: uppercase;
    letter-spacing: 0.5px;
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    subcontrol-position: top left;
    padding: 2px 10px;
}}

/* -- Named labels -- */
QLabel#titleLabel {{
    color: {C['text']};
    font-size: 16px;
    font-weight: 700;
    letter-spacing: -0.3px;
}}
QLabel#metaLabel {{
    color: {C['overlay1']};
    font-size: 12px;
    letter-spacing: 0.1px;
}}
QLabel#qualityPill {{
    border-radius: 6px;
    padding: 3px 10px;
    font-size: 11px;
    font-weight: 700;
}}
QLabel#emptyIcon {{
    color: {C['surface2']};
    font-size: 36px;
}}
QLabel#emptyTitle {{
    color: {C['subtext0']};
    font-size: 15px;
    font-weight: 600;
}}
QLabel#emptySubtitle {{
    color: {C['overlay0']};
    font-size: 12px;
    line-height: 1.6;
}}
QLabel#sectionSep {{
    background-color: {C['surface0']};
    max-height: 1px;
    margin: 4px 14px;
}}
QLabel#countBadge {{
    color: {C['overlay0']};
    font-size: 11px;
    font-weight: 600;
    padding: 4px 10px;
    background-color: {C['surface0']};
    border-radius: 6px;
}}
QLabel#toolbarSep {{
    background-color: {C['surface0']};
    max-width: 1px;
    min-height: 24px;
    margin: 0px 6px;
}}

/* -- Divider -- */
QFrame#divider {{
    background-color: {C['surface0']};
    max-height: 1px;
    margin: 6px 0px;
}}

/* -- Menu -- */
QMenu {{
    background-color: {C['surface0']};
    color: {C['text']};
    border: 1px solid {C['surface1']};
    border-radius: 8px;
    padding: 4px;
}}
QMenu::item {{
    padding: 8px 24px 8px 12px;
    border-radius: 4px;
}}
QMenu::item:selected {{
    background-color: {C['surface1']};
    color: {C['lavender']};
}}
QMenu::separator {{
    height: 1px;
    background: {C['surface1']};
    margin: 4px 8px;
}}

/* -- Tooltip -- */
QToolTip {{
    background-color: {C['surface0']};
    color: {C['text']};
    border: 1px solid {C['surface1']};
    border-radius: 6px;
    padding: 6px 10px;
    font-size: 12px;
}}
"""

VAR_RE = re.compile(r"\{\{\s*([a-zA-Z_][a-zA-Z0-9_]{0,63})\s*\}\}")
INCLUDE_RE = re.compile(r"\{\{\s*include:([a-zA-Z0-9_.:/-]{1,180})\s*\}\}")
TOKEN_RE = re.compile(r"\w+|[^\w\s]", re.UNICODE)
_TIKTOKEN_ENCODER = None

PROVIDER_HANDOFF_ENV = "PROMPTCOMPANION_PROVIDER_HANDOFF"
PROVIDER_HANDOFF_ENABLED = os.environ.get(PROVIDER_HANDOFF_ENV, "").strip().lower() in {"1", "true", "yes", "on"}
MODEL_PROVIDERS = ("OpenAI", "Anthropic", "Local")


def model_provider(model: str) -> str:
    value = str(model).strip().casefold()
    if not value or value == "any":
        return "any"
    if any(token in value for token in ("gpt", "o1", "o3", "o4", "openai")):
        return "openai"
    if "claude" in value or "anthropic" in value:
        return "anthropic"
    if any(token in value for token in ("ollama", "llama", "mistral", "mixtral", "qwen", "phi", "gemma", "local")):
        return "local"
    return ""


def model_compatible(record: dict, provider: str) -> bool:
    wanted = str(provider or "").strip().casefold()
    if not wanted:
        return True
    models = parse_json_list(record.get("target_models"), ["any"])
    return any(model_provider(model) in {"any", wanted} for model in models)


def provider_handoff_url(provider: str, prompt: str) -> str:
    encoded = quote(str(prompt), safe="")
    key = str(provider).strip().casefold()
    if key == "chatgpt":
        return f"https://chatgpt.com/?q={encoded}"
    if key == "claude":
        return f"https://claude.ai/new?q={encoded}"
    if key == "ollama":
        base = os.environ.get("PROMPTCOMPANION_OLLAMA_URL", "http://localhost:11434/")
        separator = "&" if "?" in base else "?"
        return f"{base}{separator}prompt={encoded}"
    raise ValueError(f"Unknown provider: {provider}")

# -- Special category keys -------------------------------------------------
CAT_FAVORITES = "__favorites__"
CAT_RECENT = "__recent__"
CAT_PRIVATE = "__private__"


# -- Win32 helpers ----------------------------------------------------------
if IS_WIN:
    import ctypes
    import ctypes.wintypes
    user32 = ctypes.windll.user32
    MOD_SHIFT, MOD_WIN, MOD_NOREPEAT = 0x0004, 0x0008, 0x4000
    HOTKEY_ID, VK_P = 0xBFFF, 0x50
    INPUT_KEYBOARD, KEYEVENTF_KEYUP, VK_CONTROL, VK_V = 1, 0x0002, 0xA2, 0x56

    class KEYBDINPUT(ctypes.Structure):
        _fields_ = [("wVk", ctypes.wintypes.WORD), ("wScan", ctypes.wintypes.WORD),
                     ("dwFlags", ctypes.wintypes.DWORD), ("time", ctypes.wintypes.DWORD),
                     ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong))]
    class INPUT(ctypes.Structure):
        class _INPUT(ctypes.Union):
            _fields_ = [("ki", KEYBDINPUT)]
        _fields_ = [("type", ctypes.wintypes.DWORD), ("_input", _INPUT)]

    def _send_ctrl_v():
        inputs = (INPUT * 4)()
        for i, (vk, flags) in enumerate([(VK_CONTROL, 0), (VK_V, 0), (VK_V, KEYEVENTF_KEYUP), (VK_CONTROL, KEYEVENTF_KEYUP)]):
            inputs[i].type = INPUT_KEYBOARD
            inputs[i]._input.ki.wVk = vk
            inputs[i]._input.ki.dwFlags = flags
        user32.SendInput(4, ctypes.pointer(inputs[0]), ctypes.sizeof(INPUT))


class HotkeyThread(QThread):
    triggered = pyqtSignal()
    unavailable = pyqtSignal(str)
    def __init__(self):
        super().__init__()
        self._running = True
        self._listener = None

    @staticmethod
    def binding_label() -> str:
        return "Win+Shift+P" if IS_WIN else "Cmd+Shift+P" if sys.platform == "darwin" else "Ctrl+Shift+P"

    def run(self):
        if IS_WIN:
            user32.RegisterHotKey(None, HOTKEY_ID, MOD_WIN | MOD_SHIFT | MOD_NOREPEAT, VK_P)
            msg = ctypes.wintypes.MSG()
            while self._running:
                if user32.PeekMessageW(ctypes.byref(msg), None, 0, 0, 1):
                    if msg.message == 0x0312 and msg.wParam == HOTKEY_ID:
                        self.triggered.emit()
                else:
                    self.msleep(50)
            user32.UnregisterHotKey(None, HOTKEY_ID)
            return
        if pynput_keyboard is None:
            self.unavailable.emit(
                f"{self.binding_label()} requires optional pynput support on this platform"
            )
            return
        modifier = pynput_keyboard.Key.cmd if sys.platform == "darwin" else pynput_keyboard.Key.ctrl
        pressed: set[object] = set()
        fired = False

        def on_press(key):
            nonlocal fired
            if not self._running:
                return False
            pressed.add(key)
            char = getattr(key, "char", "")
            if modifier in pressed and pynput_keyboard.Key.shift in pressed and str(char).lower() == "p":
                if not fired:
                    fired = True
                    self.triggered.emit()

        def on_release(key):
            nonlocal fired
            pressed.discard(key)
            if str(getattr(key, "char", "")).lower() == "p":
                fired = False

        try:
            self._listener = pynput_keyboard.Listener(on_press=on_press, on_release=on_release)
            self._listener.start()
            while self._running and self._listener.is_alive():
                self.msleep(100)
        except (OSError, RuntimeError) as exc:
            self.unavailable.emit(f"Global hotkey unavailable: {exc}")
        finally:
            if self._listener:
                self._listener.stop()
                self._listener = None

    def stop(self):
        self._running = False
        if self._listener:
            self._listener.stop()
        self.wait(2000)


class UpdateThread(QThread):
    checked = pyqtSignal(object, object, object)
    failed = pyqtSignal(str)

    def __init__(self, current_version: str, auto_download: bool = False):
        super().__init__()
        self.current_version = current_version
        self.auto_download = auto_download

    def run(self):
        try:
            release = fetch_latest_release()
            if not is_newer_version(self.current_version, release.version):
                self.checked.emit(release, None, None)
                return
            asset = choose_asset(release)
            downloaded = None
            if self.auto_download and _is_frozen() and asset and IS_WIN:
                current = Path(sys.executable).resolve()
                downloaded = download_asset(
                    asset.url,
                    current.with_name(f".{asset.name}.download"),
                )
            self.checked.emit(release, asset, downloaded)
        except (OSError, RuntimeError, ValueError, json.JSONDecodeError) as exc:
            self.failed.emit(str(exc))


PROMPT_FIELDS = (
    "id", "title", "body", "role", "category", "tags", "variables",
    "target_models", "language", "source", "author", "license",
    "translation_of", "translated_from", "translator", "version",
    "quality", "author_rank", "review_score", "review_votes", "deprecated",
    "deprecation_reason", "created", "updated",
)
PROMPT_EXTRA_FIELDS = (
    "private", "notes", "local_tags", "variable_presets", "history",
    "import_path", "import_sha256",
)
TREE_SETTINGS_KEY = "category_tree/expanded"
EDITOR_EXPORT_DIR = USER_DIR / "editor"
PRIVATE_ENCRYPTION_ENV = "PROMPTCOMPANION_PRIVATE_PASSPHRASE"
PRIVATE_ENCRYPTION_SCHEME = "fernet-pbkdf2-sha256-v1"
PRESET_SAFE = "Safe defaults"
PRESET_AGGRESSIVE = "Aggressive"
VARIABLE_PRESET_NAMES = (PRESET_SAFE, PRESET_AGGRESSIVE)


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def parse_json_list(value, fallback: list | None = None) -> list:
    if fallback is None:
        fallback = []
    if value is None:
        return list(fallback)
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return [value] if value else list(fallback)
        return parsed if isinstance(parsed, list) else list(fallback)
    return list(fallback)


def parse_tag_input(value: str) -> list[str]:
    tags: list[str] = []
    seen: set[str] = set()
    for raw in re.split(r"[,;\s]+", value):
        tag = re.sub(r"[^a-z0-9-]", "-", raw.strip().lower()).strip("-")
        if tag and tag not in seen:
            tags.append(tag[:32])
            seen.add(tag)
        if len(tags) >= 12:
            break
    return tags


def slugify_ref(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", str(value).strip().lower()).strip("-")


def _canonical_preset_name(name: str) -> str | None:
    lookup = {preset.casefold(): preset for preset in VARIABLE_PRESET_NAMES}
    return lookup.get(str(name).strip().casefold())


def normalize_variable_presets(value) -> list[dict]:
    by_name: dict[str, dict[str, str]] = {}
    for preset in parse_json_list(value):
        if not isinstance(preset, dict):
            continue
        name = _canonical_preset_name(str(preset.get("name", "")))
        raw_values = preset.get("values")
        if not name or not isinstance(raw_values, dict):
            continue
        values: dict[str, str] = {}
        for raw_key, raw_value in raw_values.items():
            key = str(raw_key).strip()
            value_text = str(raw_value).strip()
            if key and value_text:
                values[key[:80]] = value_text[:1000]
        if values:
            by_name[name] = values
    return [{"name": name, "values": by_name[name]} for name in VARIABLE_PRESET_NAMES if name in by_name]


def variable_preset_map(value) -> dict[str, dict[str, str]]:
    return {preset["name"]: dict(preset["values"]) for preset in normalize_variable_presets(value)}


def set_variable_preset(record: dict, preset_name: str, values: dict[str, str]) -> dict:
    name = _canonical_preset_name(preset_name)
    if not name:
        raise ValueError(f"Unknown variable preset: {preset_name}")
    presets = variable_preset_map(record.get("variable_presets"))
    cleaned = {
        str(key).strip()[:80]: str(value).strip()[:1000]
        for key, value in values.items()
        if str(key).strip() and str(value).strip()
    }
    if cleaned:
        presets[name] = cleaned
    else:
        presets.pop(name, None)
    updated = dict(record)
    updated["variable_presets"] = [
        {"name": preset, "values": presets[preset]}
        for preset in VARIABLE_PRESET_NAMES
        if preset in presets
    ]
    return updated


def import_prompt_id(root: Path, path: Path) -> str:
    rel = path.resolve().relative_to(root.resolve()).as_posix().lower()
    digest = hashlib.sha256(rel.encode("utf-8")).hexdigest()[:20]
    return f"import-md-{digest}"


def split_front_matter(text: str) -> tuple[dict[str, str], str]:
    if not text.startswith("---\n") and not text.startswith("---\r\n"):
        return {}, text
    normalized = text.replace("\r\n", "\n")
    marker = normalized.find("\n---\n", 4)
    if marker < 0:
        return {}, text
    raw_meta = normalized[4:marker]
    body = normalized[marker + 5:].lstrip("\n")
    meta: dict[str, str] = {}
    for line in raw_meta.splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        meta[key.strip().lower()] = value.strip().strip("'\"")
    return meta, body


def title_from_markdown(path: Path, body: str, meta: dict[str, str]) -> str:
    if meta.get("title"):
        return meta["title"][:200]
    for line in body.splitlines():
        stripped = line.strip()
        if stripped.startswith("# "):
            return stripped[2:].strip()[:200] or path.stem
    return path.stem.replace("_", " ").replace("-", " ").title()[:200]


def markdown_file_record(root: Path, path: Path) -> dict:
    text = path.read_text(encoding="utf-8-sig")
    meta, body = split_front_matter(text)
    content_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
    now = utc_now()
    category = meta.get("category", "uncategorized").lower().strip()
    if category not in {
        "development", "writing", "research", "creative", "business",
        "productivity", "system", "roleplay", "translation", "specialized",
        "uncategorized",
    }:
        category = "uncategorized"
    tags = parse_tag_input(meta.get("tags", ""))
    if "imported" not in tags:
        tags.insert(0, "imported")
    prompt_id = import_prompt_id(root, path)
    try:
        source = path.resolve().as_uri()
    except ValueError:
        source = f"file:///{path.resolve().as_posix()}"
    record = {
        "id": prompt_id,
        "title": title_from_markdown(path, body, meta),
        "body": body.strip() or text.strip(),
        "role": meta.get("role", "user").lower() if meta.get("role", "user").lower() in {"system", "user", "assistant"} else "user",
        "category": category,
        "tags": ["private"],
        "local_tags": tags[:12],
        "variables": extract_variables(body or text),
        "variable_presets": [],
        "target_models": ["any"],
        "language": meta.get("language", "en"),
        "source": source,
        "author": meta.get("author", "Imported Markdown"),
        "license": "Unknown",
        "version": 1,
        "quality": 0,
        "created": now,
        "updated": now,
        "notes": f"Imported from {path.name}",
        "private": True,
        "import_path": path.resolve().as_posix(),
        "import_sha256": content_hash,
    }
    for key in ("translation_of", "translated_from", "translator"):
        if meta.get(key):
            record[key] = meta[key]
    return record


def extract_variables(body: str) -> list[dict]:
    seen: set[str] = set()
    variables: list[dict] = []
    for name in VAR_RE.findall(body):
        if name not in seen:
            variables.append({"name": name})
            seen.add(name)
    return variables


def merge_variables(*groups: list[dict]) -> list[dict]:
    seen: set[str] = set()
    merged: list[dict] = []
    for group in groups:
        for var in group:
            name = str(var.get("name", "")).strip()
            if name and name not in seen:
                merged.append({"name": name, **{k: v for k, v in var.items() if k != "name"}})
                seen.add(name)
    return merged


def expand_prompt_includes(
    body: str,
    resolver,
    max_depth: int = 5,
    seen: set[str] | None = None,
) -> str:
    if max_depth <= 0:
        return body
    if seen is None:
        seen = set()

    def replace(match: re.Match) -> str:
        ref = match.group(1).strip()
        key = ref.casefold()
        if key in seen:
            return match.group(0)
        included = resolver(ref)
        if not included:
            return match.group(0)
        return expand_prompt_includes(str(included), resolver, max_depth - 1, seen | {key}).strip()

    return INCLUDE_RE.sub(replace, body)


def fill_prompt_body(body: str, values: dict[str, str], include_resolver=None) -> str:
    filled = expand_prompt_includes(body, include_resolver) if include_resolver else body
    for name, value in values.items():
        if not value:
            continue
        filled = filled.replace("{{" + name + "}}", value)
        filled = re.sub(r"\{\{\s*" + re.escape(name) + r"\s*\}\}", value, filled)
    return filled


def _estimate_tokens_heuristic(text: str) -> int:
    if not text.strip():
        return 0
    return len(TOKEN_RE.findall(text))


def estimate_token_count(text: str) -> int:
    """Estimate local token usage with tiktoken when available."""
    if not text.strip():
        return 0
    global _TIKTOKEN_ENCODER
    if tiktoken is not None:
        try:
            if _TIKTOKEN_ENCODER is None:
                _TIKTOKEN_ENCODER = tiktoken.get_encoding("cl100k_base")
            return len(_TIKTOKEN_ENCODER.encode(text, disallowed_special=()))
        except (AttributeError, KeyError, RuntimeError, ValueError):
            _TIKTOKEN_ENCODER = False
    return _estimate_tokens_heuristic(text)


def recency_boost(updated: str, now: datetime | None = None, half_life_days: int = 180) -> float:
    """Return a bounded recency score used to break BM25 ties."""
    try:
        timestamp = datetime.fromisoformat(str(updated).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return 0.0
    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=timezone.utc)
    current = now or datetime.now(timezone.utc)
    age_days = max(0.0, (current - timestamp).total_seconds() / 86400)
    return 1.0 / (1.0 + age_days / max(1, half_life_days))


def format_prompt_stats(text: str) -> str:
    return f"{len(text):,} chars / ~{estimate_token_count(text):,} tokens"


def export_prompt_bundle(records: list[dict], format_name: str = "Markdown") -> str:
    """Serialize selected prompt records as one JSON or Markdown bundle."""
    normalized: list[dict] = []
    for record in records:
        item = dict(record)
        for key in ("tags", "variables", "target_models"):
            item[key] = parse_json_list(item.get(key))
        for key in ("_overlay", "_overlay_updated", "private"):
            item.pop(key, None)
        normalized.append(item)
    if format_name.casefold() == "json":
        return json.dumps({"prompts": normalized}, indent=2, ensure_ascii=False)

    lines = ["# Prompt Bundle", ""]
    for index, record in enumerate(normalized, start=1):
        lines.extend([
            f"## {index}. {record.get('title', 'Untitled Prompt')}",
            "",
            "  /  ".join([
                f"Role: {record.get('role', 'user')}",
                f"Category: {str(record.get('category', 'uncategorized')).replace('_', ' ').title()}",
                f"Language: {record.get('language', 'en')}",
            ]),
            "",
            str(record.get("body", "")).strip(),
            "",
            "---",
            "",
        ])
    return "\n".join(lines).rstrip() + "\n"


def write_editor_draft(record: dict, body: str, directory: Path = EDITOR_EXPORT_DIR) -> Path:
    """Write an atomic Markdown draft and return its stable path."""
    directory.mkdir(parents=True, exist_ok=True)
    prompt_id = slugify_ref(record.get("id") or record.get("title") or "prompt") or "prompt"
    path = directory / f"{prompt_id}.md"
    tmp = path.with_suffix(".md.tmp")
    tmp.write_text(export_markdown(record, body), encoding="utf-8", newline="\n")
    tmp.replace(path)
    return path


def compose_prompt_chain(records: list[dict], values: dict[str, str] | None = None, include_resolver=None) -> str:
    if values is None:
        values = {}
    lines = ["# Prompt Chain", ""]
    for idx, rec in enumerate(records, start=1):
        lines.extend([
            f"## Step {idx}: {rec.get('title', 'Untitled Prompt')}",
            "",
            f"Role: {rec.get('role', 'user')}",
            f"Category: {str(rec.get('category', 'uncategorized')).replace('_', ' ').title()}",
            "",
            fill_prompt_body(str(rec.get("body", "")), values, include_resolver).strip(),
            "",
        ])
    return "\n".join(lines).strip() + "\n"


def make_private_prompt() -> dict:
    now = utc_now()
    return {
        "id": f"private-{uuid.uuid4().hex[:16]}",
        "title": "Untitled Private Prompt",
        "body": "Write your private prompt here.",
        "role": "user",
        "category": "uncategorized",
        "tags": ["private"],
        "local_tags": [],
        "variables": [],
        "variable_presets": [],
        "target_models": ["any"],
        "language": "en",
        "source": "private://local",
        "author": "Private",
        "license": "Unknown",
        "version": 1,
        "quality": 0,
        "created": now,
        "updated": now,
        "notes": "",
        "private": True,
    }


def history_snapshot(record: dict) -> dict:
    return {
        "title": record.get("title", ""),
        "body": record.get("body", ""),
        "notes": record.get("notes", ""),
        "local_tags": parse_json_list(record.get("local_tags")),
        "version": int(record.get("version") or 1),
        "updated": record.get("updated") or utc_now(),
    }


def history_changed(before: dict, after: dict) -> bool:
    return any(
        before.get(key) != after.get(key)
        for key in ("title", "body", "notes", "local_tags")
    )


def format_history_diff(current: dict, previous: dict) -> str:
    prev_lines = [
        f"Title: {previous.get('title', '')}",
        f"Local Tags: {', '.join(parse_json_list(previous.get('local_tags')))}",
        f"Notes: {previous.get('notes', '')}",
        "",
        previous.get("body", ""),
    ]
    curr_lines = [
        f"Title: {current.get('title', '')}",
        f"Local Tags: {', '.join(parse_json_list(current.get('local_tags')))}",
        f"Notes: {current.get('notes', '')}",
        "",
        current.get("body", ""),
    ]
    diff = difflib.unified_diff(
        "\n".join(prev_lines).splitlines(),
        "\n".join(curr_lines).splitlines(),
        fromfile=f"v{previous.get('version', '?')} {previous.get('updated', '')}".strip(),
        tofile=f"v{current.get('version', '?')} {current.get('updated', '')}".strip(),
        lineterm="",
    )
    return "\n".join(diff) or "No text changes in the latest local revision."


def _derive_private_key(passphrase: str, salt: bytes) -> bytes:
    key = hashlib.pbkdf2_hmac("sha256", passphrase.encode("utf-8"), salt, 600_000, dklen=32)
    return base64.urlsafe_b64encode(key)


def _encrypt_private_record(record: dict, passphrase: str) -> dict:
    if Fernet is None:
        raise RuntimeError("cryptography is not installed")
    salt = os.urandom(16)
    key = _derive_private_key(passphrase, salt)
    payload = json.dumps(record, ensure_ascii=False, sort_keys=True).encode("utf-8")
    token = Fernet(key).encrypt(payload)
    return {
        "id": record["id"],
        "private": True,
        "encrypted": PRIVATE_ENCRYPTION_SCHEME,
        "salt": base64.urlsafe_b64encode(salt).decode("ascii"),
        "payload": token.decode("ascii"),
    }


def _decrypt_private_record(envelope: dict, passphrase: str) -> dict:
    if Fernet is None:
        raise RuntimeError("cryptography is not installed")
    salt = base64.urlsafe_b64decode(envelope["salt"].encode("ascii"))
    key = _derive_private_key(passphrase, salt)
    payload = Fernet(key).decrypt(envelope["payload"].encode("ascii"))
    return json.loads(payload.decode("utf-8"))


class OverlayStore:
    """JSONL prompt overlay layered over immutable bundled records."""

    def __init__(self, path: Path):
        self.path = path
        self._records: dict[str, dict] = {}
        self._passphrase = os.environ.get(PRIVATE_ENCRYPTION_ENV, "")
        self.encryption_enabled = bool(self._passphrase and Fernet is not None)
        self.encryption_warning = ""
        if self._passphrase and Fernet is None:
            self.encryption_warning = "Private prompt encryption requested, but cryptography is not installed."
        self.load()

    def load(self) -> None:
        self._records.clear()
        if not self.path.exists():
            return
        for line_no, line in enumerate(self.path.read_text(encoding="utf-8").splitlines(), start=1):
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError as exc:
                print(f"Skipping malformed overlay line {line_no}: {exc}", file=sys.stderr)
                continue
            if rec.get("encrypted") == PRIVATE_ENCRYPTION_SCHEME:
                if not self._passphrase:
                    self.encryption_warning = "Encrypted private prompts are hidden until the passphrase environment variable is set."
                    continue
                try:
                    rec = _decrypt_private_record(rec, self._passphrase)
                except (InvalidToken, KeyError, RuntimeError, ValueError) as exc:
                    self.encryption_warning = f"Encrypted private prompt on line {line_no} could not be opened."
                    print(f"Skipping encrypted overlay line {line_no}: {exc}", file=sys.stderr)
                    continue
            prompt_id = rec.get("id")
            if isinstance(prompt_id, str) and prompt_id:
                self._records[prompt_id] = self._normal_record(rec)

    def count(self) -> int:
        return len(self._records)

    def ids(self) -> set[str]:
        return set(self._records)

    def records(self) -> list[dict]:
        return [dict(r) for r in self._records.values()]

    def private_records(self) -> list[dict]:
        return [dict(r) for r in self._records.values() if r.get("private")]

    def private_count(self) -> int:
        return len(self.private_records())

    def is_overridden(self, prompt_id: str) -> bool:
        return prompt_id in self._records

    def apply(self, record: dict) -> dict:
        prompt_id = record.get("id")
        override = self._records.get(prompt_id)
        if not override:
            return dict(record)
        layered = dict(record)
        layered.update(override)
        layered["_overlay"] = True
        layered["_overlay_updated"] = override.get("updated", "")
        return layered

    def apply_many(self, records: list[dict]) -> list[dict]:
        return [self.apply(r) for r in records]

    def save(self, record: dict, previous: dict | None = None) -> None:
        prompt_id = record["id"]
        if previous is None:
            previous = self._records.get(prompt_id)
        if previous and history_changed(history_snapshot(previous), history_snapshot(record)):
            history = parse_json_list(record.get("history") or previous.get("history"))
            history.append(history_snapshot(previous))
            record["history"] = history[-25:]
        self._records[prompt_id] = self._normal_record(record)
        self._write()

    def sync_markdown_imports(self, import_dir: Path) -> int:
        import_dir.mkdir(parents=True, exist_ok=True)
        changed = 0
        for path in sorted(import_dir.rglob("*.md")):
            if not path.is_file():
                continue
            try:
                record = markdown_file_record(import_dir, path)
            except OSError as exc:
                print(f"Skipping markdown import {path}: {exc}", file=sys.stderr)
                continue
            previous = self._records.get(record["id"])
            if previous and previous.get("import_sha256") == record["import_sha256"]:
                continue
            if previous:
                record["created"] = previous.get("created", record["created"])
                record["version"] = int(previous.get("version") or 1) + 1
                record["history"] = parse_json_list(previous.get("history"))
            self.save(record, previous=previous)
            changed += 1
        return changed

    def remove(self, prompt_id: str) -> None:
        if prompt_id in self._records:
            del self._records[prompt_id]
            self._write()

    def _normal_record(self, record: dict) -> dict:
        normalized = {k: record[k] for k in PROMPT_FIELDS if k in record}
        for key in PROMPT_EXTRA_FIELDS:
            if key in record:
                normalized[key] = record[key]
        normalized["tags"] = parse_json_list(normalized.get("tags"))
        normalized["local_tags"] = parse_json_list(normalized.get("local_tags"))
        normalized["history"] = parse_json_list(normalized.get("history"))[-25:]
        normalized["variables"] = parse_json_list(normalized.get("variables"))
        normalized["variable_presets"] = normalize_variable_presets(normalized.get("variable_presets"))
        normalized["target_models"] = parse_json_list(normalized.get("target_models"), ["any"])
        normalized["notes"] = str(normalized.get("notes") or "")
        normalized["version"] = int(normalized.get("version") or 1)
        normalized["quality"] = int(normalized.get("quality") or 0)
        normalized["private"] = bool(normalized.get("private"))
        return normalized

    def _write(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self._records:
            self.path.unlink(missing_ok=True)
            return
        tmp = self.path.with_suffix(".jsonl.tmp")
        lines = []
        for prompt_id in sorted(self._records):
            rec = self._records[prompt_id]
            if rec.get("private") and self.encryption_enabled:
                rec = _encrypt_private_record(rec, self._passphrase)
            lines.append(json.dumps(rec, ensure_ascii=False, sort_keys=True))
        tmp.write_text("\n".join(lines) + "\n", encoding="utf-8")
        tmp.replace(self.path)


# -- User database (favorites + history) ------------------------------------
class UserDB:
    def __init__(self, db_path: Path):
        self.conn = sqlite3.connect(str(db_path))
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.executescript("""
            CREATE TABLE IF NOT EXISTS favorites (
                prompt_id TEXT PRIMARY KEY,
                added TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                prompt_id TEXT NOT NULL,
                action TEXT NOT NULL,
                timestamp TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_history_ts ON history(timestamp DESC);
        """)

    def _now(self) -> str:
        return utc_now()

    def is_favorite(self, prompt_id: str) -> bool:
        return self.conn.execute("SELECT 1 FROM favorites WHERE prompt_id=?", (prompt_id,)).fetchone() is not None

    def toggle_favorite(self, prompt_id: str) -> bool:
        if self.is_favorite(prompt_id):
            self.conn.execute("DELETE FROM favorites WHERE prompt_id=?", (prompt_id,))
            self.conn.commit()
            return False
        self.conn.execute("INSERT INTO favorites (prompt_id, added) VALUES (?,?)", (prompt_id, self._now()))
        self.conn.commit()
        return True

    def favorite_ids(self) -> set[str]:
        return {r[0] for r in self.conn.execute("SELECT prompt_id FROM favorites").fetchall()}

    def favorite_count(self) -> int:
        return self.conn.execute("SELECT COUNT(*) FROM favorites").fetchone()[0]

    def record_action(self, prompt_id: str, action: str):
        self.conn.execute("INSERT INTO history (prompt_id, action, timestamp) VALUES (?,?,?)", (prompt_id, action, self._now()))
        self.conn.execute("DELETE FROM history WHERE id NOT IN (SELECT id FROM history ORDER BY timestamp DESC LIMIT 500)")
        self.conn.commit()

    def recent_ids(self, limit: int = 100) -> list[str]:
        rows = self.conn.execute(
            "SELECT prompt_id, MAX(timestamp) AS last_used FROM history GROUP BY prompt_id ORDER BY last_used DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [r[0] for r in rows]

    def recent_count(self) -> int:
        return self.conn.execute("SELECT COUNT(DISTINCT prompt_id) FROM history").fetchone()[0]

    def close(self):
        self.conn.close()


# -- Prompt database --------------------------------------------------------
class PromptDB:
    def __init__(self, db_path: Path, overlay: OverlayStore | None = None):
        self.conn = sqlite3.connect(str(db_path))
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.overlay = overlay
        self.prompt_columns = {
            row["name"] for row in self.conn.execute("PRAGMA table_info(prompts)").fetchall()
        }

    def close(self):
        self.conn.close()

    def categories(self) -> list[tuple[str, int]]:
        if not self.overlay or self.overlay.count() == 0:
            rows = self.conn.execute("SELECT category, COUNT(*) AS cnt FROM prompts GROUP BY category ORDER BY cnt DESC").fetchall()
            return [(r["category"], r["cnt"]) for r in rows]
        counts: dict[str, int] = {}
        rows = self.conn.execute("SELECT id, category FROM prompts").fetchall()
        for row in rows:
            rec = self.overlay.apply(dict(row))
            cat = rec.get("category") or "uncategorized"
            counts[cat] = counts.get(cat, 0) + 1
        for rec in self.overlay.private_records():
            cat = rec.get("category") or "uncategorized"
            counts[cat] = counts.get(cat, 0) + 1
        return sorted(counts.items(), key=lambda item: (-item[1], item[0]))

    def total_count(self) -> int:
        base_count = self.conn.execute("SELECT COUNT(*) FROM prompts").fetchone()[0]
        return base_count + (self.overlay.private_count() if self.overlay else 0)

    def _select_sql(self, prefix: str = "p") -> str:
        fields = [
            "rowid", "id", "title", "body", "role", "category", "tags",
            "variables", "target_models", "language", "source", "author",
            "license", "translation_of", "translated_from", "translator",
            "version", "quality", "author_rank", "review_score", "review_votes",
            "deprecated", "deprecation_reason", "created", "updated",
        ]
        select_parts = []
        for field in fields:
            if field == "rowid" or field in self.prompt_columns:
                select_parts.append(f"{prefix}.{field}")
            else:
                select_parts.append(f"'' AS {field}")
        return ", ".join(select_parts)

    def _matches_filters(
        self,
        rec: dict,
        category: str,
        role: str,
        min_quality: int,
        source: str,
        language: str,
        include_deprecated: bool = False,
        provider: str = "",
    ) -> bool:
        if category == CAT_PRIVATE:
            if not rec.get("private"):
                return False
        elif category and rec.get("category") != category:
            return False
        if role and rec.get("role") != role:
            return False
        if min_quality > 0 and int(rec.get("quality") or 0) < min_quality:
            return False
        if source and not str(rec.get("id", "")).startswith(f"{source}-"):
            return False
        if language and rec.get("language") != language:
            return False
        if not include_deprecated and rec.get("deprecated"):
            return False
        if provider and not model_compatible(rec, provider):
            return False
        return True

    def _matches_query(self, rec: dict, query: str) -> bool:
        terms = [t.lower() for t in re.sub(r"[^\w\s]", " ", query.strip()).split() if t]
        if not terms:
            return True
        tags = " ".join(str(t) for t in parse_json_list(rec.get("tags")))
        local_tags = " ".join(str(t) for t in parse_json_list(rec.get("local_tags")))
        haystack = " ".join(
            str(rec.get(k, "")) for k in ("title", "body", "author", "category", "role", "notes")
        )
        haystack = f"{haystack} {tags} {local_tags}".lower()
        return all(term in haystack for term in terms)

    def _base_by_id(self, prompt_id: str) -> dict | None:
        row = self.conn.execute(
            f"SELECT {self._select_sql('p')} FROM prompts p WHERE p.id = ?",
            (prompt_id,),
        ).fetchone()
        return dict(row) if row else None

    def _all_records(self) -> list[dict]:
        rows = self.conn.execute(f"SELECT {self._select_sql('p')} FROM prompts p").fetchall()
        records = [dict(r) for r in rows]
        if self.overlay:
            records.extend(self.overlay.private_records())
        return records

    def _layered_records(self) -> list[dict]:
        records = self._all_records()
        return self.overlay.apply_many(records) if self.overlay else records

    def private_records(self) -> list[dict]:
        if not self.overlay:
            return []
        return sorted(
            self.overlay.private_records(),
            key=lambda r: (str(r.get("title", "")).casefold(), str(r.get("id", ""))),
        )

    def search(self, query: str = "", category: str = "", role: str = "",
               min_quality: int = 0, source: str = "", language: str = "",
               include_deprecated: bool = False, limit: int = 500,
               provider: str = "") -> list[dict]:
        fts_active = False
        conditions: list[str] = []
        params: list = []

        if query.strip():
            safe_q = re.sub(r'[^\w\s]', ' ', query.strip())
            terms = [t for t in safe_q.split() if t]
            if terms:
                fts_active = True
                fts_query = " ".join(f'"{t}"*' for t in terms)
                params.append(fts_query)

        if category:
            conditions.append("p.category = ?")
            params.append(category)
        if role:
            conditions.append("p.role = ?")
            params.append(role)
        if min_quality > 0:
            conditions.append("p.quality >= ?")
            params.append(min_quality)
        if source:
            conditions.append("p.id LIKE ?")
            params.append(f"{source}-%")
        if language:
            conditions.append("p.language = ?")
            params.append(language)
        if not include_deprecated and "deprecated" in self.prompt_columns:
            conditions.append("COALESCE(p.deprecated, 0) = 0")

        where_extra = f"AND {' AND '.join(conditions)}" if conditions else ""

        if fts_active:
            params.append(max(limit, 5000) if provider else limit)
            sql = f"""
                SELECT {self._select_sql('p')},
                       bm25(prompts_fts, 10.0, 1.0, 5.0, 2.0)
                       - 0.15 * (1.0 / (1.0 + MAX(0.0, julianday('now') - julianday(p.updated)) / 180.0)) AS rank
                FROM prompts p
                JOIN prompts_fts ON p.rowid = prompts_fts.rowid
                WHERE prompts_fts MATCH ? {where_extra}
                ORDER BY rank, p.quality DESC
                LIMIT ?
            """
            rows = self.conn.execute(sql, params).fetchall()
            results = self.overlay.apply_many([dict(r) for r in rows]) if self.overlay else [dict(r) for r in rows]
            if not self.overlay and provider:
                results = [
                    r for r in results
                    if self._matches_filters(r, category, role, min_quality, source, language, include_deprecated, provider)
                ]
            if self.overlay:
                results = [
                    r for r in results
                    if self._matches_filters(r, category, role, min_quality, source, language, include_deprecated, provider)
                    and self._matches_query(r, query)
                ]
                seen = {r["id"] for r in results}
                for prompt_id in sorted(self.overlay.ids() - seen):
                    base = self._base_by_id(prompt_id)
                    rec = self.overlay.apply(base) if base else next(
                        (r for r in self.overlay.private_records() if r.get("id") == prompt_id),
                        None,
                    )
                    if not rec:
                        continue
                    if self._matches_filters(rec, category, role, min_quality, source, language, include_deprecated, provider) and self._matches_query(rec, query):
                        results.append(rec)
            return results[:limit]

        records = self._all_records()
        if self.overlay:
            records = self.overlay.apply_many(records)
        results = [
            rec for rec in records
            if self._matches_filters(rec, category, role, min_quality, source, language, include_deprecated, provider)
        ]
        results.sort(key=lambda r: (-int(r.get("quality") or 0), str(r.get("title", "")).casefold()))
        return results[:limit]

    def get_by_ids(self, ids: list[str]) -> list[dict]:
        if not ids:
            return []
        placeholders = ",".join("?" * len(ids))
        rows = self.conn.execute(
            f"SELECT {self._select_sql('p')} FROM prompts p WHERE id IN ({placeholders})", ids
        ).fetchall()
        records = self.overlay.apply_many([dict(r) for r in rows]) if self.overlay else [dict(r) for r in rows]
        if self.overlay:
            found = {r["id"] for r in records}
            records.extend([r for r in self.overlay.private_records() if r["id"] in ids and r["id"] not in found])
        by_id = {r["id"]: r for r in records}
        return [by_id[i] for i in ids if i in by_id]

    def resolve_include_body(self, ref: str) -> str | None:
        ref = ref.strip().strip("/")
        if not ref:
            return None
        exact = self.get_by_ids([ref])
        if exact:
            return str(exact[0].get("body", ""))

        category = ""
        slug = slugify_ref(ref)
        if "/" in ref:
            category, slug = ref.split("/", 1)
            category = category.strip().lower()
            slug = slugify_ref(slug)
        if not slug:
            return None

        candidates = []
        for rec in self._layered_records():
            if category and str(rec.get("category", "")).lower() != category:
                continue
            rec_id = str(rec.get("id", ""))
            rec_title = str(rec.get("title", ""))
            if slug in {slugify_ref(rec_id), slugify_ref(rec_title)} or slugify_ref(rec_id).endswith(f"-{slug}"):
                candidates.append(rec)
        if not candidates:
            return None
        candidates.sort(key=lambda r: (-int(r.get("quality") or 0), str(r.get("title", "")).casefold()))
        return str(candidates[0].get("body", ""))

    def sources(self) -> list[str]:
        rows = self.conn.execute("SELECT DISTINCT substr(id, 1, instr(id, '-') - 1) AS src FROM prompts ORDER BY src").fetchall()
        sources = [r["src"] for r in rows]
        if self.overlay and self.overlay.private_count() and "private" not in sources:
            sources.append("private")
        return sources

    def languages(self) -> list[str]:
        rows = self.conn.execute("SELECT DISTINCT language FROM prompts ORDER BY language").fetchall()
        languages = {str(r["language"]) for r in rows if r["language"]}
        if self.overlay:
            languages.update(
                str(rec.get("language", "")).strip()
                for rec in self.overlay.records()
                if str(rec.get("language", "")).strip()
            )
        return sorted(languages)


# -- Export formatters ------------------------------------------------------
def export_plain(rec: dict, body: str) -> str:
    return body

def export_markdown(rec: dict, body: str) -> str:
    tags = json.loads(rec.get("tags", "[]")) if isinstance(rec.get("tags"), str) else rec.get("tags", [])
    lines = [f"# {rec['title']}", ""]
    meta = []
    if rec.get("author"):
        meta.append(f"**Author:** {rec['author']}")
    meta.append(f"**Role:** {rec['role']}")
    meta.append(f"**Category:** {rec['category']}")
    meta.append(f"**Language:** {rec.get('language', 'en')}")
    if rec.get("translation_of"):
        meta.append(f"**Translation of:** {rec['translation_of']}")
    if tags:
        meta.append(f"**Tags:** {', '.join(tags)}")
    lines.append(" | ".join(meta))
    lines.extend(["", "---", "", body, ""])
    return "\n".join(lines)


def _yaml_scalar(value) -> str:
    text = str(value or "").replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
    return f'"{text}"'


def _yaml_list(values: list) -> list[str]:
    cleaned = [str(v).strip() for v in values if str(v).strip()]
    if not cleaned:
        return [" []"]
    return [""] + [f"  - {_yaml_scalar(item)}" for item in cleaned]


def export_markdown_front_matter(rec: dict, body: str) -> str:
    tags = parse_json_list(rec.get("tags"))
    local_tags = parse_json_list(rec.get("local_tags"))
    front_matter: list[str] = [
        "---",
        f"title: {_yaml_scalar(rec.get('title'))}",
        f"prompt_id: {_yaml_scalar(rec.get('id'))}",
        f"role: {_yaml_scalar(rec.get('role'))}",
        f"category: {_yaml_scalar(rec.get('category'))}",
        f"quality: {int(rec.get('quality') or 0)}",
        f"language: {_yaml_scalar(rec.get('language'))}",
    ]
    for key in ("translation_of", "translated_from", "translator"):
        if rec.get(key):
            front_matter.append(f"{key}: {_yaml_scalar(rec.get(key))}")
    front_matter.extend([
        f"source: {_yaml_scalar(rec.get('source'))}",
        f"author: {_yaml_scalar(rec.get('author'))}",
        f"license: {_yaml_scalar(rec.get('license'))}",
        f"updated: {_yaml_scalar(rec.get('updated'))}",
        "tags:" + "\n".join(_yaml_list(tags)),
        "local_tags:" + "\n".join(_yaml_list(local_tags)),
        "---",
        "",
        body,
        "",
    ])
    return "\n".join(front_matter)


def export_json(rec: dict, body: str) -> str:
    obj = {
        "title": rec["title"],
        "body": body,
        "role": rec["role"],
        "category": rec["category"],
        "language": rec.get("language", "en"),
    }
    if rec.get("author"):
        obj["author"] = rec["author"]
    for key in ("translation_of", "translated_from", "translator"):
        if rec.get(key):
            obj[key] = rec[key]
    tags = json.loads(rec.get("tags", "[]")) if isinstance(rec.get("tags"), str) else rec.get("tags", [])
    if tags:
        obj["tags"] = tags
    return json.dumps(obj, indent=2, ensure_ascii=False)

EXPORTERS = {
    "Plain Text": export_plain,
    "Markdown": export_markdown,
    "Front Matter": export_markdown_front_matter,
    "JSON": export_json,
}


# -- Empty state ------------------------------------------------------------
class EmptyState(QWidget):
    def __init__(self, icon: str = "", title: str = "", subtitle: str = "", parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setSpacing(12)
        layout.setContentsMargins(48, 60, 48, 60)

        self._icon = QLabel(icon)
        self._icon.setObjectName("emptyIcon")
        self._icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._icon)

        layout.addSpacing(4)

        self._title = QLabel(title)
        self._title.setObjectName("emptyTitle")
        self._title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._title.setWordWrap(True)
        layout.addWidget(self._title)

        self._subtitle = QLabel(subtitle)
        self._subtitle.setObjectName("emptySubtitle")
        self._subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._subtitle.setWordWrap(True)
        layout.addWidget(self._subtitle)

    def set_text(self, icon: str, title: str, subtitle: str):
        self._icon.setText(icon)
        self._title.setText(title)
        self._subtitle.setText(subtitle)


# -- Category tree ----------------------------------------------------------
class CategoryTree(QTreeView):
    category_selected = pyqtSignal(str)
    search_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setHeaderHidden(True)
        self.setRootIsDecorated(True)
        self.setFixedWidth(220)
        self.setAlternatingRowColors(False)
        self.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
        self.setIndentation(12)
        self._settings = QSettings("SysAdminDoc", "PromptCompanion")
        self._model = QStandardItemModel()
        self.setModel(self._model)
        self.clicked.connect(self._on_click)

    def load(self, categories: list[tuple[str, int]], total: int, fav_count: int = 0, recent_count: int = 0, private_count: int = 0):
        self._model.clear()

        collections = QStandardItem("Collections")
        collections.setData("collections", Qt.ItemDataRole.UserRole + 1)
        collections.setEditable(False)
        collections_font = collections.font()
        collections_font.setBold(True)
        collections.setFont(collections_font)
        self._model.appendRow(collections)

        def add_collection(label: str, category: str, count: int, color: str | None = None) -> None:
            item = QStandardItem(f"{label}  ({count:,})")
            item.setData(category, Qt.ItemDataRole.UserRole)
            item.setEditable(False)
            if color:
                item.setForeground(QColor(C[color]))
            collections.appendRow(item)

        add_collection("All Prompts", "", total)
        add_collection("Favorites", CAT_FAVORITES, fav_count, "yellow")
        add_collection("Recent", CAT_RECENT, recent_count, "sapphire")
        add_collection("Private", CAT_PRIVATE, private_count, "teal")

        category_root = QStandardItem("Categories")
        category_root.setData("categories", Qt.ItemDataRole.UserRole + 1)
        category_root.setEditable(False)
        category_font = category_root.font()
        category_font.setBold(True)
        category_root.setFont(category_font)
        self._model.appendRow(category_root)
        for cat, count in categories:
            label = cat.replace("_", " ").title()
            item = QStandardItem(f"  {label}  ({count:,})")
            item.setData(cat, Qt.ItemDataRole.UserRole)
            item.setEditable(False)
            item.setForeground(QColor(C["subtext0"]))
            category_root.appendRow(item)

        saved = set(str(self._settings.value(TREE_SETTINGS_KEY, "")).split(","))
        for row, key in enumerate(("collections", "categories")):
            index = self._model.index(row, 0)
            self.setExpanded(index, key in saved or not saved)
        self.setCurrentIndex(self._model.index(0, 0, self._model.index(0, 0)))

    def _on_click(self, index):
        item = self._model.itemFromIndex(index)
        if item and item.isEnabled() and item.data(Qt.ItemDataRole.UserRole) is not None:
            self.category_selected.emit(item.data(Qt.ItemDataRole.UserRole) or "")

    def save_expanded_state(self) -> None:
        expanded = []
        for row in range(self._model.rowCount()):
            item = self._model.item(row)
            if item and self.isExpanded(item.index()):
                key = item.data(Qt.ItemDataRole.UserRole + 1)
                if key:
                    expanded.append(str(key))
        self._settings.setValue(TREE_SETTINGS_KEY, ",".join(expanded))

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Slash and not event.text().isspace():
            self.search_requested.emit()
            event.accept()
            return
        super().keyPressEvent(event)


# -- Prompt list table ------------------------------------------------------
class PromptTable(QTableView):
    prompt_selected = pyqtSignal(dict)
    keyboard_action = pyqtSignal(str, dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._model = QStandardItemModel()
        self._model.setHorizontalHeaderLabels(["Score", "Title", "Category"])
        self.setModel(self._model)
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.setAlternatingRowColors(False)
        self.verticalHeader().setVisible(False)
        self.setShowGrid(False)
        self.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
        self.verticalHeader().setDefaultSectionSize(34)
        hdr = self.horizontalHeader()
        hdr.setStretchLastSection(False)
        hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        hdr.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        hdr.setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        self.setColumnWidth(0, 52)
        self.setColumnWidth(2, 110)
        self.selectionModel().currentRowChanged.connect(self._on_row)
        self._data: list[dict] = []

    def load(self, records: list[dict]):
        self._model.removeRows(0, self._model.rowCount())
        self._data = records
        for rec in records:
            q = rec.get("quality", 0)
            q_item = QStandardItem(str(q))
            q_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            if q >= 60:
                q_item.setForeground(QColor(C["green"]))
            elif q >= 35:
                q_item.setForeground(QColor(C["yellow"]))
            else:
                q_item.setForeground(QColor(C["overlay0"]))

            title_item = QStandardItem(rec["title"])
            title_item.setToolTip(rec["title"])

            cat_item = QStandardItem(rec["category"].replace("_", " ").title())
            cat_item.setForeground(QColor(C["overlay0"]))

            for it in (q_item, title_item, cat_item):
                it.setEditable(False)
            self._model.appendRow([q_item, title_item, cat_item])

    def _on_row(self, current, _previous):
        row = current.row()
        if 0 <= row < len(self._data):
            self.prompt_selected.emit(self._data[row])

    def selected_records(self) -> list[dict]:
        rows = sorted({index.row() for index in self.selectionModel().selectedRows()})
        return [self._data[row] for row in rows if 0 <= row < len(self._data)]

    def keyPressEvent(self, event):
        row = self.currentIndex().row()
        current = self._data[row] if 0 <= row < len(self._data) else None
        if event.key() == Qt.Key.Key_Slash:
            self.keyboard_action.emit("search", current or {})
            event.accept()
            return
        if current and event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self.keyboard_action.emit("copy", current)
            event.accept()
            return
        if current and event.key() == Qt.Key.Key_Space:
            self.keyboard_action.emit("preview", current)
            event.accept()
            return
        super().keyPressEvent(event)


# -- Quality pill -----------------------------------------------------------
def _quality_pill(q: int) -> QLabel:
    lbl = QLabel(str(q))
    lbl.setObjectName("qualityPill")
    lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
    lbl.setFixedHeight(24)
    lbl.setMinimumWidth(40)
    if q >= 60:
        lbl.setStyleSheet(f"background-color: rgba(166,227,161,0.18); color: {C['green']};")
        lbl.setToolTip(f"High quality ({q}/100)")
    elif q >= 35:
        lbl.setStyleSheet(f"background-color: rgba(249,226,175,0.15); color: {C['yellow']};")
        lbl.setToolTip(f"Good quality ({q}/100)")
    else:
        lbl.setStyleSheet(f"background-color: rgba(108,112,134,0.15); color: {C['overlay0']};")
        lbl.setToolTip(f"Fair quality ({q}/100)")
    return lbl


# -- Preview pane -----------------------------------------------------------
class PreviewPane(QWidget):
    paste_requested = pyqtSignal(str)
    action_performed = pyqtSignal(str, str)  # prompt_id, action
    favorite_toggled = pyqtSignal(str, bool)  # prompt_id, is_now_fav
    edit_saved = pyqtSignal(dict)
    preset_saved = pyqtSignal(dict)
    overlay_reset = pyqtSignal(str)
    status_requested = pyqtSignal(str, int)
    editor_requested = pyqtSignal(dict, str)
    provider_requested = pyqtSignal(str, str)
    chain_step_requested = pyqtSignal(dict, dict)
    chain_copy_requested = pyqtSignal()
    chain_clear_requested = pyqtSignal()

    def __init__(self, user_db: UserDB, include_resolver=None, parent=None):
        super().__init__(parent)
        self._current: dict | None = None
        self._var_inputs: dict[str, QLineEdit] = {}
        self._preset_values: dict[str, dict[str, str]] = {}
        self._loading_prompt = False
        self._user_db = user_db
        self._include_resolver = include_resolver
        self._edit_mode = False
        self._showing_history = False
        self._chain_count = 0

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        self.stack = QStackedWidget()
        outer.addWidget(self.stack, stretch=1)

        # -- Empty / welcome state
        self.empty = EmptyState(
            icon="\u2750",
            title="Select a prompt",
            subtitle="Browse the list or use search to find a prompt.\nThe full preview will appear here."
        )
        self.stack.addWidget(self.empty)

        # -- Content state
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(24, 20, 24, 16)
        layout.setSpacing(0)

        # Header row: fav button + title + quality pill
        header = QHBoxLayout()
        header.setSpacing(10)

        self.fav_btn = QPushButton()
        self.fav_btn.setObjectName("favBtn")
        self.fav_btn.setFixedSize(34, 34)
        self.fav_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.fav_btn.setToolTip("Add to favorites")
        self.fav_btn.clicked.connect(self._toggle_fav)
        header.addWidget(self.fav_btn)

        self.title_label = QLabel("")
        self.title_label.setObjectName("titleLabel")
        self.title_label.setWordWrap(True)
        self.title_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        header.addWidget(self.title_label)

        self.title_edit = QLineEdit()
        self.title_edit.setVisible(False)
        self.title_edit.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        header.addWidget(self.title_edit)

        self.quality_pill_container = QWidget()
        qpc_layout = QHBoxLayout(self.quality_pill_container)
        qpc_layout.setContentsMargins(0, 0, 0, 0)
        qpc_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        header.addWidget(self.quality_pill_container)
        layout.addLayout(header)

        layout.addSpacing(6)

        # Meta line
        self.meta_label = QLabel("")
        self.meta_label.setObjectName("metaLabel")
        self.meta_label.setWordWrap(True)
        layout.addWidget(self.meta_label)

        self.overlay_badge = QLabel("Edited locally")
        self.overlay_badge.setObjectName("overlayBadge")
        self.overlay_badge.setVisible(False)
        layout.addWidget(self.overlay_badge, alignment=Qt.AlignmentFlag.AlignLeft)

        layout.addSpacing(8)

        # Tags
        self.tags_label = QLabel("")
        self.tags_label.setWordWrap(True)
        self.tags_label.setVisible(False)
        layout.addWidget(self.tags_label)

        self.local_group = QGroupBox("Local Details")
        self.local_layout = QFormLayout(self.local_group)
        self.local_layout.setContentsMargins(14, 10, 14, 10)
        self.local_layout.setSpacing(8)

        self.local_tags_edit = QLineEdit()
        self.local_tags_edit.setPlaceholderText("comma-separated local tags")
        self.local_layout.addRow(QLabel("Local Tags"), self.local_tags_edit)

        self.notes_edit = QPlainTextEdit()
        self.notes_edit.setPlaceholderText("Private notes, caveats, or usage reminders")
        self.notes_edit.setMaximumHeight(84)
        self.local_layout.addRow(QLabel("Notes"), self.notes_edit)
        self.local_group.setVisible(False)
        layout.addWidget(self.local_group)

        layout.addSpacing(12)

        # Divider
        div = QFrame()
        div.setObjectName("divider")
        div.setFrameShape(QFrame.Shape.HLine)
        layout.addWidget(div)

        layout.addSpacing(12)

        # Body
        self.body_text = QPlainTextEdit()
        self.body_text.setObjectName("bodyEditor")
        self.body_text.setReadOnly(True)
        self.body_text.setLineWrapMode(QPlainTextEdit.LineWrapMode.WidgetWidth)
        bf = QFont()
        bf.setFamilies(["Cascadia Code", "Fira Code", "JetBrains Mono", "Consolas", "monospace"])
        bf.setPointSize(10)
        bf.setStyleHint(QFont.StyleHint.Monospace)
        self.body_text.setFont(bf)
        layout.addWidget(self.body_text, stretch=1)

        self.body_stats_label = QLabel("0 chars / ~0 tokens")
        self.body_stats_label.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.body_stats_label.setStyleSheet(f"color: {C['overlay1']}; font-size: 11px;")
        self.body_text.textChanged.connect(self._update_body_stats)
        layout.addWidget(self.body_stats_label)

        # Variable panel
        self.vars_group = QGroupBox("Variables")
        self.vars_layout = QVBoxLayout(self.vars_group)
        self.vars_layout.setContentsMargins(14, 10, 14, 10)
        self.vars_layout.setSpacing(8)

        preset_bar = QWidget()
        preset_bar.setStyleSheet("background: transparent;")
        preset_row = QHBoxLayout(preset_bar)
        preset_row.setContentsMargins(0, 0, 0, 0)
        preset_row.setSpacing(8)

        preset_label = QLabel("Preset")
        preset_label.setStyleSheet(f"color: {C['subtext0']}; font-size: 12px;")
        preset_row.addWidget(preset_label)

        self.preset_combo = QComboBox()
        self.preset_combo.addItems(["Manual", *VARIABLE_PRESET_NAMES])
        self.preset_combo.setToolTip("Apply saved variable values for this prompt")
        self.preset_combo.currentTextChanged.connect(self._apply_variable_preset)
        preset_row.addWidget(self.preset_combo, stretch=1)

        self.save_safe_btn = QPushButton("Save Safe")
        self.save_safe_btn.setToolTip("Save current variable values as this prompt's safe defaults")
        self.save_safe_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.save_safe_btn.clicked.connect(lambda: self._save_variable_preset(PRESET_SAFE))
        preset_row.addWidget(self.save_safe_btn)

        self.save_aggressive_btn = QPushButton("Save Agg")
        self.save_aggressive_btn.setToolTip("Save current variable values as this prompt's aggressive profile")
        self.save_aggressive_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.save_aggressive_btn.clicked.connect(lambda: self._save_variable_preset(PRESET_AGGRESSIVE))
        preset_row.addWidget(self.save_aggressive_btn)

        self.clear_preset_btn = QPushButton("Clear")
        self.clear_preset_btn.setToolTip("Clear the selected preset for this prompt")
        self.clear_preset_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.clear_preset_btn.clicked.connect(self._clear_variable_preset)
        preset_row.addWidget(self.clear_preset_btn)

        self.vars_layout.addWidget(preset_bar)

        self.vars_form = QFormLayout()
        self.vars_form.setContentsMargins(0, 0, 0, 0)
        self.vars_form.setSpacing(8)
        self.vars_layout.addLayout(self.vars_form)
        self.vars_group.setVisible(False)
        layout.addWidget(self.vars_group)

        layout.addSpacing(12)

        # Action bar
        action_bar = QHBoxLayout()
        action_bar.setSpacing(8)

        self.export_combo = QComboBox()
        self.export_combo.addItems(list(EXPORTERS.keys()))
        self.export_combo.setFixedWidth(120)
        self.export_combo.setToolTip("Export format for copy and paste actions")
        action_bar.addWidget(self.export_combo)

        action_bar.addStretch()

        self.add_chain_btn = QPushButton("Add")
        self.add_chain_btn.setToolTip("Add this prompt to the current chain")
        self.add_chain_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.add_chain_btn.setEnabled(False)
        self.add_chain_btn.clicked.connect(self._add_chain_step)
        action_bar.addWidget(self.add_chain_btn)

        self.copy_chain_btn = QPushButton("Chain")
        self.copy_chain_btn.setToolTip("Copy the current prompt chain")
        self.copy_chain_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.copy_chain_btn.setVisible(False)
        self.copy_chain_btn.clicked.connect(self.chain_copy_requested.emit)
        action_bar.addWidget(self.copy_chain_btn)

        self.clear_chain_btn = QPushButton("Clear")
        self.clear_chain_btn.setToolTip("Clear the current prompt chain")
        self.clear_chain_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.clear_chain_btn.setVisible(False)
        self.clear_chain_btn.clicked.connect(self.chain_clear_requested.emit)
        action_bar.addWidget(self.clear_chain_btn)

        self.history_btn = QPushButton("History")
        self.history_btn.setToolTip("Show the latest local revision diff")
        self.history_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.history_btn.setVisible(False)
        self.history_btn.clicked.connect(self._toggle_history)
        action_bar.addWidget(self.history_btn)

        self.editor_btn = QPushButton("Editor")
        self.editor_btn.setToolTip("Open an editable Markdown draft in the system text editor")
        self.editor_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.editor_btn.setVisible(False)
        self.editor_btn.clicked.connect(self._open_editor)
        action_bar.addWidget(self.editor_btn)

        if PROVIDER_HANDOFF_ENABLED:
            self.send_btn = QPushButton("Send")
            self.send_btn.setObjectName("accentBtn")
            self.send_btn.setToolTip("Open this prompt in an external provider")
            self.send_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            send_menu = QMenu(self.send_btn)
            for provider in ("ChatGPT", "Claude", "Ollama"):
                action = QAction(provider, self)
                action.triggered.connect(lambda _checked=False, name=provider: self._send_to_provider(name))
                send_menu.addAction(action)
            self.send_btn.setMenu(send_menu)
            action_bar.addWidget(self.send_btn)

        self.edit_btn = QPushButton("Edit")
        self.edit_btn.setToolTip("Edit this prompt in your local overlay")
        self.edit_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.edit_btn.setEnabled(False)
        self.edit_btn.clicked.connect(self._start_edit)
        action_bar.addWidget(self.edit_btn)

        self.save_edit_btn = QPushButton("Save")
        self.save_edit_btn.setObjectName("primaryBtn")
        self.save_edit_btn.setToolTip("Save the local overlay edit")
        self.save_edit_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.save_edit_btn.setVisible(False)
        self.save_edit_btn.clicked.connect(self._save_edit)
        action_bar.addWidget(self.save_edit_btn)

        self.cancel_edit_btn = QPushButton("Cancel")
        self.cancel_edit_btn.setToolTip("Discard unsaved changes")
        self.cancel_edit_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.cancel_edit_btn.setVisible(False)
        self.cancel_edit_btn.clicked.connect(self._cancel_edit)
        action_bar.addWidget(self.cancel_edit_btn)

        self.reset_overlay_btn = QPushButton("Revert")
        self.reset_overlay_btn.setToolTip("Remove this local overlay edit")
        self.reset_overlay_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.reset_overlay_btn.setVisible(False)
        self.reset_overlay_btn.clicked.connect(self._reset_overlay)
        action_bar.addWidget(self.reset_overlay_btn)

        self.copy_btn = QPushButton("Copy")
        self.copy_btn.setToolTip("Copy prompt body to clipboard")
        self.copy_btn.setEnabled(False)
        self.copy_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.copy_btn.clicked.connect(self._copy_exported)
        action_bar.addWidget(self.copy_btn)

        self.copy_filled_btn = QPushButton("Copy Vars")
        self.copy_filled_btn.setObjectName("primaryBtn")
        self.copy_filled_btn.setToolTip("Copy prompt with variable placeholders filled in")
        self.copy_filled_btn.setVisible(False)
        self.copy_filled_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.copy_filled_btn.clicked.connect(self._copy_filled)
        action_bar.addWidget(self.copy_filled_btn)

        if IS_WIN:
            self.paste_btn = QPushButton("Paste to App")
            self.paste_btn.setObjectName("accentBtn")
            self.paste_btn.setToolTip("Copy and paste into the previously active window")
            self.paste_btn.setEnabled(False)
            self.paste_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            self.paste_btn.clicked.connect(self._paste_to_window)
            action_bar.addWidget(self.paste_btn)

        layout.addLayout(action_bar)
        self.stack.addWidget(content)

    def _update_fav_btn(self):
        if self._current and self._user_db.is_favorite(self._current["id"]):
            self.fav_btn.setText("\u2605")
            self.fav_btn.setStyleSheet(
                f"color: {C['yellow']}; font-size: 20px; background: transparent; border: none;"
            )
            self.fav_btn.setToolTip("Remove from favorites")
        else:
            self.fav_btn.setText("\u2606")
            self.fav_btn.setStyleSheet(
                f"color: {C['overlay0']}; font-size: 20px; background: transparent; border: none;"
            )
            self.fav_btn.setToolTip("Add to favorites")

    def _toggle_fav(self):
        if not self._current:
            return
        is_fav = self._user_db.toggle_favorite(self._current["id"])
        self._update_fav_btn()
        self.favorite_toggled.emit(self._current["id"], is_fav)

    def _set_edit_mode(self, editing: bool):
        self._edit_mode = editing
        has_prompt = self._current is not None
        is_overlay = bool(self._current and self._current.get("_overlay"))
        is_private = bool(self._current and self._current.get("private"))

        self.title_label.setVisible(not editing)
        self.title_edit.setVisible(editing)
        self.body_text.setReadOnly(not editing)
        self.local_tags_edit.setReadOnly(not editing)
        self.notes_edit.setReadOnly(not editing)
        has_local_details = bool(
            editing or (
                self._current and (
                    parse_json_list(self._current.get("local_tags")) or self._current.get("notes")
                )
            )
        )
        has_history = bool(self._current and parse_json_list(self._current.get("history")))
        self.local_group.setVisible(has_local_details)
        self.export_combo.setEnabled(not editing and not is_private)
        self.add_chain_btn.setEnabled(has_prompt and not editing)
        self.copy_chain_btn.setVisible(not editing and self._chain_count > 0)
        self.clear_chain_btn.setVisible(not editing and self._chain_count > 0)
        self.history_btn.setVisible(not editing and has_history)
        self.editor_btn.setVisible(not editing and has_prompt)
        if hasattr(self, "send_btn"):
            self.send_btn.setVisible(not editing and has_prompt)
        self.edit_btn.setVisible(not editing)
        self.edit_btn.setEnabled(has_prompt)
        self.save_edit_btn.setVisible(editing)
        self.cancel_edit_btn.setVisible(editing)
        self.reset_overlay_btn.setVisible(not editing and (is_overlay or is_private))
        self.reset_overlay_btn.setText("Delete" if is_private else "Revert")
        self.reset_overlay_btn.setToolTip("Delete this private prompt" if is_private else "Remove this local overlay edit")
        self.copy_btn.setEnabled(has_prompt and not editing)
        self.copy_filled_btn.setEnabled(has_prompt and not editing)
        if IS_WIN and hasattr(self, "paste_btn"):
            self.paste_btn.setEnabled(has_prompt and not editing)
        self._set_preset_controls_enabled()

    def _start_edit(self):
        if not self._current:
            return
        if self._showing_history:
            self._showing_history = False
            self.body_text.setPlainText(self._current.get("body", ""))
        self.title_edit.setText(self._current.get("title", ""))
        self.body_text.setPlainText(self._current.get("body", ""))
        self._set_edit_mode(True)
        self.title_edit.setFocus()
        self.title_edit.selectAll()

    def _cancel_edit(self):
        if self._current:
            self.show_prompt(self._current)

    def _save_edit(self):
        if not self._current:
            return
        title = self.title_edit.text().strip()
        body = self.body_text.toPlainText()
        if not title:
            self.status_requested.emit("Prompt title is required", 3000)
            return
        if not body.strip():
            self.status_requested.emit("Prompt body is required", 3000)
            return
        updated = dict(self._current)
        updated["title"] = title
        updated["body"] = body
        updated["variables"] = extract_variables(body)
        updated["local_tags"] = parse_tag_input(self.local_tags_edit.text())
        updated["notes"] = self.notes_edit.toPlainText().strip()
        updated["updated"] = utc_now()
        updated["version"] = int(updated.get("version") or 1) + 1
        updated["_previous_record"] = dict(self._current)
        self.edit_saved.emit(updated)

    def _reset_overlay(self):
        if self._current:
            self.overlay_reset.emit(self._current["id"])

    def _chain_variable_values(self) -> dict[str, str]:
        values: dict[str, str] = {}
        for name, inp in self._var_inputs.items():
            values[name] = inp.text() or inp.placeholderText()
        return values

    def _typed_variable_values(self) -> dict[str, str]:
        values: dict[str, str] = {}
        for name, inp in self._var_inputs.items():
            value = inp.text().strip()
            if value:
                values[name] = value
        return values

    def _set_preset_controls_enabled(self):
        enabled = bool(self._current and self._var_inputs and not self._edit_mode)
        for widget in (self.preset_combo, self.save_safe_btn, self.save_aggressive_btn):
            widget.setEnabled(enabled)
        selected = self.preset_combo.currentText()
        self.clear_preset_btn.setEnabled(enabled and selected in self._preset_values)

    def _reset_preset_combo(self):
        self.preset_combo.blockSignals(True)
        self.preset_combo.setCurrentText("Manual")
        self.preset_combo.blockSignals(False)
        self._set_preset_controls_enabled()

    def _apply_variable_preset(self, preset_name: str):
        if self._loading_prompt or preset_name == "Manual":
            self._set_preset_controls_enabled()
            return
        values = self._preset_values.get(preset_name)
        if not values:
            self.status_requested.emit(f"No {preset_name.lower()} preset saved", 3000)
            self._reset_preset_combo()
            return
        for name, inp in self._var_inputs.items():
            inp.setText(values.get(name, ""))
        self._set_preset_controls_enabled()
        self.status_requested.emit(f"Applied {preset_name.lower()} preset", 2500)

    def _save_variable_preset(self, preset_name: str):
        if not self._current:
            return
        values = self._typed_variable_values()
        if not values:
            self.status_requested.emit(f"Fill at least one variable before saving {preset_name.lower()}", 3000)
            return
        updated = set_variable_preset(self._current, preset_name, values)
        updated["updated"] = utc_now()
        updated["version"] = int(updated.get("version") or 1) + 1
        updated["_previous_record"] = dict(self._current)
        self.preset_saved.emit(updated)

    def _clear_variable_preset(self):
        if not self._current:
            return
        preset_name = self.preset_combo.currentText()
        if preset_name == "Manual":
            self.status_requested.emit("Choose a preset before clearing it", 3000)
            return
        if preset_name not in self._preset_values:
            self.status_requested.emit(f"No {preset_name.lower()} preset saved", 3000)
            self._reset_preset_combo()
            return
        updated = set_variable_preset(self._current, preset_name, {})
        updated["updated"] = utc_now()
        updated["version"] = int(updated.get("version") or 1) + 1
        updated["_previous_record"] = dict(self._current)
        self.preset_saved.emit(updated)

    def _add_chain_step(self):
        if self._current:
            self.chain_step_requested.emit(dict(self._current), self._chain_variable_values())

    def set_chain_count(self, count: int):
        self._chain_count = count
        self.copy_chain_btn.setText(f"Chain ({count})" if count else "Chain")
        self._set_edit_mode(self._edit_mode)

    def _toggle_history(self):
        if not self._current:
            return
        if self._showing_history:
            self._showing_history = False
            self.show_prompt(self._current)
            return
        history = parse_json_list(self._current.get("history"))
        if not history:
            return
        self._showing_history = True
        self.history_btn.setText("Hide History")
        self.body_text.setReadOnly(True)
        self.body_text.setPlainText(format_history_diff(self._current, history[-1]))
        self.local_group.setVisible(False)
        self.vars_group.setVisible(False)
        self.copy_btn.setEnabled(False)
        self.copy_filled_btn.setEnabled(False)
        self.add_chain_btn.setEnabled(False)
        if IS_WIN and hasattr(self, "paste_btn"):
            self.paste_btn.setEnabled(False)

    def _open_editor(self):
        if self._current and not self._edit_mode:
            self.editor_requested.emit(dict(self._current), self._resolved_body())

    def _send_to_provider(self, provider: str):
        if self._current and not self._edit_mode:
            body = self._get_filled_body() if self._var_inputs else self._resolved_body()
            self.provider_requested.emit(provider, body)

    def show_prompt(self, rec: dict):
        self._current = rec
        self._showing_history = False
        self.history_btn.setText("History")
        self.stack.setCurrentIndex(1)

        self._update_fav_btn()
        self.title_label.setText(rec["title"])
        self.title_edit.setText(rec["title"])
        self.overlay_badge.setVisible(bool(rec.get("_overlay")))
        if rec.get("private"):
            self.export_combo.setCurrentText("Plain Text")

        # Quality pill
        qpc = self.quality_pill_container.layout()
        while qpc.count():
            child = qpc.takeAt(0)
            if child.widget():
                child.widget().deleteLater()
        qpc.addWidget(_quality_pill(rec.get("quality", 0)))

        # Meta line
        parts = []
        if rec.get("author"):
            parts.append(rec["author"])
        parts.append(rec["role"])
        parts.append(rec["category"].replace("_", " ").title())
        parts.append(rec.get("language", "en"))
        if rec.get("translation_of"):
            parts.append(f"translation of {rec['translation_of']}")
        parts.append(rec["license"])
        self.meta_label.setText("  /  ".join(parts))

        # Tags
        tags = json.loads(rec.get("tags", "[]")) if isinstance(rec.get("tags"), str) else rec.get("tags", [])
        local_tags = parse_json_list(rec.get("local_tags"))
        if tags:
            spans = []
            for tag in tags[:12]:
                spans.append(
                    f'<span style="background-color:{C["surface0"]}; color:{C["subtext0"]}; '
                    f'padding:2px 8px; font-size:11px; margin-right:4px;">{tag}</span>'
                )
            self.tags_label.setText("  ".join(spans))
            self.tags_label.setVisible(True)
        else:
            self.tags_label.setVisible(False)

        self.local_tags_edit.setText(", ".join(local_tags))
        self.notes_edit.setPlainText(str(rec.get("notes") or ""))

        # Body
        resolved_body = self._resolved_body(rec)
        self.body_text.setPlainText(resolved_body)

        # Variables
        self._loading_prompt = True
        self._var_inputs.clear()
        self._preset_values = variable_preset_map(rec.get("variable_presets"))
        self._reset_preset_combo()
        while self.vars_form.rowCount() > 0:
            self.vars_form.removeRow(0)
        record_variables = json.loads(rec.get("variables", "[]")) if isinstance(rec.get("variables"), str) else rec.get("variables", [])
        variables = merge_variables(record_variables, extract_variables(resolved_body))
        if variables:
            self.vars_group.setVisible(True)
            safe_values = self._preset_values.get(PRESET_SAFE, {})
            for var in variables:
                name = var.get("name", "")
                if not name:
                    continue
                inp = QLineEdit()
                inp.setPlaceholderText(safe_values.get(name, var.get("default", name)))
                inp.textChanged.connect(self._update_preview)
                self._var_inputs[name] = inp
                lbl = QLabel(name.replace("_", " ").title())
                lbl.setStyleSheet(f"color: {C['subtext0']}; font-size: 12px;")
                self.vars_form.addRow(lbl, inp)
            self.copy_filled_btn.setVisible(True)
        else:
            self.vars_group.setVisible(False)
            self.copy_filled_btn.setVisible(False)
        self._loading_prompt = False

        self._set_edit_mode(False)

    def show_no_results(self):
        self._current = None
        self._set_edit_mode(False)
        self.copy_btn.setEnabled(False)
        if IS_WIN and hasattr(self, "paste_btn"):
            self.paste_btn.setEnabled(False)
        self.empty.set_text(
            "\u2717",
            "No prompts found",
            "Try a different search term or adjust your filters."
        )
        self.stack.setCurrentIndex(0)

    def show_welcome(self):
        self._current = None
        self._set_edit_mode(False)
        self.empty.set_text(
            "\u2750",
            "Select a prompt",
            "Browse the list or use search to find a prompt.\nThe full preview will appear here."
        )
        self.stack.setCurrentIndex(0)

    def _update_body_stats(self):
        self.body_stats_label.setText(format_prompt_stats(self.body_text.toPlainText()))

    def _resolved_body(self, rec: dict | None = None) -> str:
        target = rec or self._current
        if not target:
            return ""
        body = str(target.get("body", ""))
        return expand_prompt_includes(body, self._include_resolver) if self._include_resolver else body

    def _get_filled_body(self) -> str:
        if not self._current:
            return ""
        return fill_prompt_body(self._current["body"], self._chain_variable_values(), self._include_resolver)

    def _get_export_text(self, body: str) -> str:
        if not self._current:
            return body
        if self._current.get("private"):
            return export_plain(self._current, body)
        return EXPORTERS.get(self.export_combo.currentText(), export_plain)(self._current, body)

    def _update_preview(self):
        if self._current:
            self.body_text.setPlainText(self._get_filled_body())

    def _flash_button(self, btn: QPushButton, original_text: str):
        saved = btn.styleSheet()
        btn.setStyleSheet(
            f"background-color: {C['green']}; color: {C['crust']}; border: none; "
            f"font-weight: 600; border-radius: 8px; padding: 8px 24px;"
        )
        btn.setText("Copied!")
        QTimer.singleShot(1400, lambda: (btn.setStyleSheet(saved), btn.setText(original_text)))

    def _copy_exported(self):
        if not self._current:
            return
        QApplication.clipboard().setText(self._get_export_text(self._resolved_body()))
        self._flash_button(self.copy_btn, "Copy")
        self.action_performed.emit(self._current["id"], "copy")

    def _copy_filled(self):
        if not self._current:
            return
        QApplication.clipboard().setText(self._get_export_text(self._get_filled_body()))
        self._flash_button(self.copy_filled_btn, "Copy Vars")
        self.action_performed.emit(self._current["id"], "copy")

    def _paste_to_window(self):
        if not self._current:
            return
        body = self._get_filled_body() if self._var_inputs else self._resolved_body()
        self.paste_requested.emit(self._get_export_text(body))
        self.action_performed.emit(self._current["id"], "paste")


# -- Main window ------------------------------------------------------------
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"PromptCompanion v{VERSION}")
        self.resize(1340, 820)
        self._prev_hwnd = None
        self._hotkey_thread = None
        self._update_thread = None
        self._chain_steps: list[dict] = []
        self._chain_values: dict[str, str] = {}

        if LOGO_PATH.exists():
            self.setWindowIcon(QIcon(str(LOGO_PATH)))

        self.overlay = OverlayStore(OVERLAY_PATH)
        self._imported_on_launch = self.overlay.sync_markdown_imports(IMPORT_DIR)
        self.db = PromptDB(DB_PATH, self.overlay)
        self.user_db = UserDB(USER_DB_PATH)
        self._total = self.db.total_count()

        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # -- Toolbar --------------------------------------------------------
        toolbar = QWidget()
        toolbar.setStyleSheet(f"background-color: {C['crust']};")
        tb = QHBoxLayout(toolbar)
        tb.setContentsMargins(16, 12, 16, 12)
        tb.setSpacing(10)

        self.search_input = QLineEdit()
        self.search_input.setObjectName("searchInput")
        self.search_input.setPlaceholderText(f"Search {self._total:,} prompts...   (Ctrl+K)")
        self.search_input.setMinimumWidth(280)
        self.search_input.setClearButtonEnabled(True)
        tb.addWidget(self.search_input, stretch=1)

        # Visual separator between search and filters
        sep1 = QLabel()
        sep1.setObjectName("toolbarSep")
        tb.addWidget(sep1)

        self.role_combo = QComboBox()
        self.role_combo.addItems(["Any Role", "system", "user", "assistant"])
        self.role_combo.setFixedWidth(110)
        self.role_combo.setToolTip("Filter by prompt role")
        tb.addWidget(self.role_combo)

        self.quality_combo = QComboBox()
        self.quality_combo.addItems(["Any Score", "High (60+)", "Good (40+)", "Fair (20+)"])
        self.quality_combo.setFixedWidth(110)
        self.quality_combo.setToolTip("Minimum quality score")
        tb.addWidget(self.quality_combo)

        self.source_combo = QComboBox()
        self.source_combo.addItem("Any Source")
        for src in self.db.sources():
            self.source_combo.addItem(src)
        self.source_combo.setFixedWidth(110)
        self.source_combo.setToolTip("Filter by upstream source")
        tb.addWidget(self.source_combo)

        self.language_combo = QComboBox()
        self.language_combo.addItem("Any Lang")
        for lang in self.db.languages():
            self.language_combo.addItem(lang)
        self.language_combo.setFixedWidth(95)
        self.language_combo.setToolTip("Filter by prompt language")
        tb.addWidget(self.language_combo)

        self.model_combo = QComboBox()
        self.model_combo.addItem("Any Model")
        self.model_combo.addItems(MODEL_PROVIDERS)
        self.model_combo.setFixedWidth(105)
        self.model_combo.setToolTip("Filter by target model provider")
        tb.addWidget(self.model_combo)

        self.status_combo = QComboBox()
        self.status_combo.addItems(["Current", "Include Deprecated"])
        self.status_combo.setFixedWidth(125)
        self.status_combo.setToolTip("Hide or include prompts flagged as deprecated")
        tb.addWidget(self.status_combo)

        self.new_private_btn = QPushButton("New Private")
        self.new_private_btn.setToolTip("Create a local-only private prompt")
        self.new_private_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.new_private_btn.clicked.connect(self._new_private_prompt)
        tb.addWidget(self.new_private_btn)

        self.bundle_export_btn = QPushButton("Export")
        self.bundle_export_btn.setToolTip("Copy the selected prompts as a JSON or Markdown bundle")
        self.bundle_export_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        bundle_menu = QMenu(self.bundle_export_btn)
        bundle_json_action = QAction("Selected as JSON", self)
        bundle_json_action.triggered.connect(lambda: self._export_bundle("JSON"))
        bundle_menu.addAction(bundle_json_action)
        bundle_markdown_action = QAction("Selected as Markdown", self)
        bundle_markdown_action.triggered.connect(lambda: self._export_bundle("Markdown"))
        bundle_menu.addAction(bundle_markdown_action)
        self.bundle_export_btn.setMenu(bundle_menu)
        tb.addWidget(self.bundle_export_btn)

        tb.addSpacing(4)

        # Count badge
        self.count_label = QLabel("")
        self.count_label.setObjectName("countBadge")
        self.count_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        tb.addWidget(self.count_label)

        main_layout.addWidget(toolbar)

        # -- Three-pane splitter --------------------------------------------
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setHandleWidth(3)
        splitter.setChildrenCollapsible(False)

        self.cat_tree = CategoryTree()
        splitter.addWidget(self.cat_tree)

        self.prompt_table = PromptTable()
        splitter.addWidget(self.prompt_table)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.preview = PreviewPane(self.user_db, self.db.resolve_include_body)
        scroll.setWidget(self.preview)
        splitter.addWidget(scroll)

        splitter.setSizes([220, 420, 700])
        main_layout.addWidget(splitter, stretch=1)

        # -- Status bar -----------------------------------------------------
        src_count = len(self.db.sources())
        hotkey_hint = f"  |  {HotkeyThread.binding_label()} to summon  |  Ctrl+K to search"
        overlay_hint = f"  |  {self.overlay.count():,} local edit{'s' if self.overlay.count() != 1 else ''}" if self.overlay.count() else ""
        import_hint = f"  |  {self._imported_on_launch:,} markdown import{'s' if self._imported_on_launch != 1 else ''} refreshed" if self._imported_on_launch else ""
        self.statusBar().showMessage(f"{self._total:,} prompts from {src_count} sources{overlay_hint}{import_hint}{hotkey_hint}")

        self._setup_tray()
        self._refresh_tree()

        # -- Keyboard shortcuts ---------------------------------------------
        search_shortcut = QShortcut(QKeySequence("Ctrl+K"), self)
        search_shortcut.activated.connect(self._focus_search)
        search_shortcut2 = QShortcut(QKeySequence("Ctrl+F"), self)
        search_shortcut2.activated.connect(self._focus_search)
        esc_shortcut = QShortcut(QKeySequence("Escape"), self)
        esc_shortcut.activated.connect(self._clear_search)

        # -- Connections ----------------------------------------------------
        self.cat_tree.category_selected.connect(self._on_filter_changed)
        self.cat_tree.search_requested.connect(self._focus_search)
        self.prompt_table.prompt_selected.connect(self.preview.show_prompt)
        self.prompt_table.keyboard_action.connect(self._handle_table_keyboard)
        self.preview.paste_requested.connect(self._do_paste_to_window)
        self.preview.action_performed.connect(self._on_action)
        self.preview.favorite_toggled.connect(self._on_fav_toggled)
        self.preview.edit_saved.connect(self._on_edit_saved)
        self.preview.preset_saved.connect(self._on_preset_saved)
        self.preview.overlay_reset.connect(self._on_overlay_reset)
        self.preview.editor_requested.connect(self._open_editor)
        self.preview.provider_requested.connect(self._send_to_provider)
        self.preview.status_requested.connect(self.statusBar().showMessage)
        self.preview.chain_step_requested.connect(self._add_chain_step)
        self.preview.chain_copy_requested.connect(self._copy_chain)
        self.preview.chain_clear_requested.connect(self._clear_chain)
        self.role_combo.currentIndexChanged.connect(self._on_filter_changed)
        self.quality_combo.currentIndexChanged.connect(self._on_filter_changed)
        self.source_combo.currentIndexChanged.connect(self._on_filter_changed)
        self.language_combo.currentIndexChanged.connect(self._on_filter_changed)
        self.model_combo.currentIndexChanged.connect(self._on_filter_changed)
        self.status_combo.currentIndexChanged.connect(self._on_filter_changed)

        self._search_timer = QTimer()
        self._search_timer.setSingleShot(True)
        self._search_timer.setInterval(200)
        self._search_timer.timeout.connect(self._on_filter_changed)
        self.search_input.textChanged.connect(lambda: self._search_timer.start())

        self._current_category = ""
        self._on_filter_changed()

        self._hotkey_thread = HotkeyThread()
        self._hotkey_thread.triggered.connect(self._on_hotkey)
        self._hotkey_thread.unavailable.connect(lambda message: self.statusBar().showMessage(message, 6000))
        self._hotkey_thread.start()
        if AUTO_UPDATE_ENABLED:
            QTimer.singleShot(3000, self._check_for_updates)

    def _focus_search(self):
        self.search_input.setFocus()
        self.search_input.selectAll()

    def _clear_search(self):
        if self.search_input.hasFocus() and self.search_input.text():
            self.search_input.clear()
        elif self.search_input.hasFocus():
            self.search_input.clearFocus()

    def _handle_table_keyboard(self, action: str, record: dict):
        if action == "search":
            self._focus_search()
            return
        if not record:
            return
        if action == "preview":
            self.preview.show_prompt(record)
        elif action == "copy":
            self.preview.show_prompt(record)
            self.preview._copy_exported()

    def _export_bundle(self, format_name: str):
        records = self.prompt_table.selected_records()
        if not records:
            self.statusBar().showMessage("Select at least one prompt to export", 3000)
            return
        expanded: list[dict] = []
        for record in records:
            item = dict(record)
            item["body"] = expand_prompt_includes(
                str(item.get("body", "")), self.db.resolve_include_body
            )
            expanded.append(item)
        QApplication.clipboard().setText(export_prompt_bundle(expanded, format_name))
        self.statusBar().showMessage(
            f"Copied {len(expanded)}-prompt {format_name.lower()} bundle", 3000
        )

    def _open_editor(self, record: dict, body: str):
        path = write_editor_draft(record, body)
        if QDesktopServices.openUrl(QUrl.fromLocalFile(str(path))):
            self.statusBar().showMessage(f"Opened editor draft: {path.name}", 3000)
        else:
            self.statusBar().showMessage(f"Editor draft saved to {path}", 5000)

    def _send_to_provider(self, provider: str, body: str):
        url = provider_handoff_url(provider, body)
        if QDesktopServices.openUrl(QUrl(url)):
            self.statusBar().showMessage(f"Opened {provider} handoff", 3000)
        else:
            QApplication.clipboard().setText(body)
            self.statusBar().showMessage(
                f"Could not open {provider}; prompt copied to clipboard", 5000
            )

    def _refresh_tree(self):
        cats = self.db.categories()
        self._total = self.db.total_count()
        self.cat_tree.load(
            cats,
            self._total,
            self.user_db.favorite_count(),
            self.user_db.recent_count(),
            self.overlay.private_count(),
        )
        if hasattr(self, "search_input"):
            self.search_input.setPlaceholderText(f"Search {self._total:,} prompts...   (Ctrl+K)")

    def _new_private_prompt(self):
        rec = make_private_prompt()
        self.overlay.save(rec)
        if self.source_combo.findText("private") < 0:
            self.source_combo.addItem("private")
        if self.language_combo.findText(rec["language"]) < 0:
            self.language_combo.addItem(rec["language"])
        self._current_category = CAT_PRIVATE
        self._refresh_tree()
        self._on_filter_changed(CAT_PRIVATE)
        loaded = self.db.get_by_ids([rec["id"]])
        if loaded:
            self.preview.show_prompt(loaded[0])
            self.preview._start_edit()
        self.statusBar().showMessage("Created private prompt draft", 3000)

    def _on_action(self, prompt_id: str, action: str):
        self.user_db.record_action(prompt_id, action)
        self._refresh_tree()

    def _on_fav_toggled(self, prompt_id: str, is_fav: bool):
        self._refresh_tree()
        if self._current_category == CAT_FAVORITES:
            self._on_filter_changed()

    def _on_edit_saved(self, record: dict):
        previous = record.pop("_previous_record", None)
        self.overlay.save(record, previous=previous)
        updated = self.db.get_by_ids([record["id"]])
        self._on_filter_changed()
        if updated:
            self.preview.show_prompt(updated[0])
        self.statusBar().showMessage("Saved local edit to overlay.jsonl", 3000)

    def _on_preset_saved(self, record: dict):
        previous = record.pop("_previous_record", None)
        self.overlay.save(record, previous=previous)
        updated = self.db.get_by_ids([record["id"]])
        self._on_filter_changed()
        if updated:
            self.preview.show_prompt(updated[0])
        self.statusBar().showMessage("Saved variable preset to overlay.jsonl", 3000)

    def _on_overlay_reset(self, prompt_id: str):
        was_private = any(r.get("id") == prompt_id and r.get("private") for r in self.overlay.private_records())
        self.overlay.remove(prompt_id)
        restored = self.db.get_by_ids([prompt_id])
        self._on_filter_changed()
        if restored:
            self.preview.show_prompt(restored[0])
        elif was_private:
            self.preview.show_welcome()
        self.statusBar().showMessage("Deleted private prompt" if was_private else "Removed local edit", 3000)

    def _add_chain_step(self, record: dict, values: dict):
        self._chain_steps.append(record)
        for key, value in values.items():
            if value:
                self._chain_values[key] = value
        self.preview.set_chain_count(len(self._chain_steps))
        self.statusBar().showMessage(f"Added step {len(self._chain_steps)} to prompt chain", 3000)

    def _copy_chain(self):
        if not self._chain_steps:
            self.statusBar().showMessage("Prompt chain is empty", 3000)
            return
        QApplication.clipboard().setText(compose_prompt_chain(
            self._chain_steps,
            self._chain_values,
            self.db.resolve_include_body,
        ))
        self.statusBar().showMessage(f"Copied {len(self._chain_steps)}-step prompt chain", 3000)

    def _clear_chain(self):
        self._chain_steps.clear()
        self._chain_values.clear()
        self.preview.set_chain_count(0)
        self.statusBar().showMessage("Cleared prompt chain", 3000)

    def _setup_tray(self):
        self._tray_available = QSystemTrayIcon.isSystemTrayAvailable()
        if not self._tray_available:
            self.tray = None
            return
        self.tray = QSystemTrayIcon(self)
        self.tray.setIcon(QIcon(str(LOGO_PATH)) if LOGO_PATH.exists() else self.windowIcon())
        self.tray.setToolTip(f"PromptCompanion v{VERSION}")
        menu = QMenu()
        show_action = QAction("Show PromptCompanion", self)
        show_action.triggered.connect(self._show_from_tray)
        menu.addAction(show_action)
        update_action = QAction("Check for Updates", self)
        update_action.triggered.connect(self._check_for_updates)
        menu.addAction(update_action)
        menu.addSeparator()
        quit_action = QAction("Quit", self)
        quit_action.triggered.connect(self._quit_app)
        menu.addAction(quit_action)
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(self._on_tray_activated)
        self.tray.show()

    def _check_for_updates(self):
        if self._update_thread and self._update_thread.isRunning():
            return
        self.statusBar().showMessage("Checking GitHub Releases for updates...", 3000)
        self._update_thread = UpdateThread(VERSION, auto_download=AUTO_UPDATE_ENABLED)
        self._update_thread.checked.connect(self._on_update_checked)
        self._update_thread.failed.connect(self._on_update_failed)
        self._update_thread.start()

    def _on_update_checked(self, release: ReleaseInfo, asset, downloaded):
        if not is_newer_version(VERSION, release.version):
            self.statusBar().showMessage(f"PromptCompanion v{VERSION} is up to date", 4000)
            return
        if downloaded:
            try:
                script = schedule_windows_install(Path(sys.executable), downloaded)
            except (OSError, RuntimeError, ValueError) as exc:
                self.statusBar().showMessage(f"Update downloaded but could not schedule install: {exc}", 6000)
            else:
                self.statusBar().showMessage(
                    f"v{release.version} downloaded; quit to install ({script.name})", 6000
                )
            return
        asset_name = asset.name if asset else "no compatible asset"
        self.statusBar().showMessage(
            f"PromptCompanion v{release.version} is available ({asset_name})", 6000
        )

    def _on_update_failed(self, message: str):
        self.statusBar().showMessage(f"Update check unavailable: {message}", 6000)

    def _on_tray_activated(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self._show_from_tray()

    def _show_from_tray(self):
        self.showNormal()
        self.activateWindow()
        self.raise_()

    def _quit_app(self):
        if self._hotkey_thread:
            self._hotkey_thread.stop()
        if self.tray:
            self.tray.hide()
        self.user_db.close()
        self.db.close()
        QApplication.quit()

    def _on_hotkey(self):
        if IS_WIN:
            self._prev_hwnd = user32.GetForegroundWindow()
        if self.isMinimized() or not self.isVisible():
            self.showNormal()
        self.activateWindow()
        self.raise_()
        self.search_input.setFocus()
        self.search_input.selectAll()

    def _do_paste_to_window(self, text: str):
        if not IS_WIN or not self._prev_hwnd:
            QApplication.clipboard().setText(text)
            self.statusBar().showMessage("Copied to clipboard (no target window detected)", 3000)
            return
        QApplication.clipboard().setText(text)
        hwnd = self._prev_hwnd
        self.showMinimized()
        QApplication.processEvents()
        time.sleep(0.15)
        user32.SetForegroundWindow(hwnd)
        time.sleep(0.2)
        _send_ctrl_v()
        self.statusBar().showMessage("Pasted to previous window", 3000)

    def _on_filter_changed(self, *_args):
        sender = self.sender()
        if isinstance(sender, CategoryTree):
            self._current_category = _args[0] if _args else ""

        query = self.search_input.text()
        category = self._current_category
        role = "" if self.role_combo.currentText() == "Any Role" else self.role_combo.currentText()
        min_quality = 60 if "60" in self.quality_combo.currentText() else 40 if "40" in self.quality_combo.currentText() else 20 if "20" in self.quality_combo.currentText() else 0
        source = "" if self.source_combo.currentText() == "Any Source" else self.source_combo.currentText()
        language = "" if self.language_combo.currentText() == "Any Lang" else self.language_combo.currentText()
        provider = "" if self.model_combo.currentText() == "Any Model" else self.model_combo.currentText().casefold()
        include_deprecated = self.status_combo.currentText() == "Include Deprecated"

        if category == CAT_FAVORITES:
            fav_ids = list(self.user_db.favorite_ids())
            results = self.db.get_by_ids(fav_ids) if fav_ids else []
            results = [
                rec for rec in results
                if self.db._matches_filters(rec, "", role, min_quality, source, language, include_deprecated, provider)
            ]
        elif category == CAT_RECENT:
            recent_ids = self.user_db.recent_ids(100)
            results = self.db.get_by_ids(recent_ids) if recent_ids else []
            results = [
                rec for rec in results
                if self.db._matches_filters(rec, "", role, min_quality, source, language, include_deprecated, provider)
            ]
        elif category == CAT_PRIVATE:
            results = self.db.search(
                query=query, category=CAT_PRIVATE, role=role, min_quality=min_quality,
                source=source, language=language, include_deprecated=include_deprecated,
                provider=provider,
            )
        else:
            results = self.db.search(
                query=query, category=category, role=role, min_quality=min_quality,
                source=source, language=language, include_deprecated=include_deprecated,
                provider=provider,
            )

        self.prompt_table.load(results)
        n = len(results)
        self.count_label.setText(f"{n:,} result{'s' if n != 1 else ''}")

        if n == 0 and category == CAT_FAVORITES:
            self.preview.empty.set_text(
                "\u2606",
                "No favorites yet",
                "Click the star next to any prompt title\nto save it here for quick access."
            )
            self.preview.stack.setCurrentIndex(0)
        elif n == 0 and category == CAT_RECENT:
            self.preview.empty.set_text(
                "\u29D6",
                "No recent prompts",
                "Prompts you copy or paste will\nautomatically appear here."
            )
            self.preview.stack.setCurrentIndex(0)
        elif n == 0 and category == CAT_PRIVATE:
            self.preview.empty.set_text(
                "\u2726",
                "No private prompts",
                "Create one from the toolbar to keep it local."
            )
            self.preview.stack.setCurrentIndex(0)
        elif n == 0 and (query or role or min_quality or source or language or provider or include_deprecated):
            self.preview.show_no_results()
        elif n == 0:
            self.preview.show_welcome()

        parts = [f"{n:,} prompt{'s' if n != 1 else ''}"]
        if query:
            parts.append(f'matching "{query}"')
        if category and category not in (CAT_FAVORITES, CAT_RECENT, CAT_PRIVATE):
            parts.append(f"in {category}")
        if category == CAT_PRIVATE:
            parts.append("in private prompts")
        if language:
            parts.append(f"language {language}")
        if provider:
            parts.append(f"for {provider}")
        if include_deprecated:
            parts.append("including deprecated")
        self.statusBar().showMessage("  ".join(parts), 5000)

    def closeEvent(self, event):
        self.cat_tree.save_expanded_state()
        if not self._tray_available:
            self._quit_app()
            event.accept()
            return
        event.ignore()
        self.hide()
        msg = "Still running in the system tray."
        if IS_WIN:
            msg += " Press Win+Shift+P to summon."
        else:
            msg += " Double-click the tray icon to show."
        self.tray.showMessage("PromptCompanion", msg, QSystemTrayIcon.MessageIcon.Information, 2500)


# -- Entry point ------------------------------------------------------------
def main():
    if not DB_PATH.exists():
        print(f"Database not found at {DB_PATH}")
        print("Run `python tools/build_index.py` first to generate it.")
        return 1

    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setStyleSheet(STYLESHEET)
    app.setQuitOnLastWindowClosed(False)
    if LOGO_PATH.exists():
        app.setWindowIcon(QIcon(str(LOGO_PATH)))

    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    # multiprocessing.freeze_support() MUST be called before anything else
    # in a PyInstaller --onefile build, or the exe will restart in an infinite loop.
    import multiprocessing
    multiprocessing.freeze_support()
    sys.exit(main())
