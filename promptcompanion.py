#!/usr/bin/env python3
"""PromptCompanion v0.3.1 — Desktop GUI for curated AI prompts.

Three-pane layout: category tree | prompt list | preview + variables.
SQLite FTS5 search. Catppuccin Mocha dark theme. One-click copy.
System tray with global hotkey (Win+Shift+P). Paste-to-active-window.
Export as plain text, markdown, or JSON.
"""

from __future__ import annotations

import json
import re
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

IS_WIN = sys.platform == "win32"


def _bootstrap(packages: list[str]) -> None:
    import importlib.util
    missing = [p for p in packages if importlib.util.find_spec(p.split("[")[0].split(">=")[0].split("==")[0]) is None]
    if not missing:
        return
    def _run(args: list[str]) -> int:
        return subprocess.call([sys.executable, "-m", "pip", "install", *args, *missing])
    if _run([]) != 0 and _run(["--user"]) != 0:
        _run(["--user", "--break-system-packages"])


_bootstrap(["PyQt6"])

from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QThread, QSize
from PyQt6.QtGui import QColor, QFont, QStandardItem, QStandardItemModel, QIcon, QAction
from PyQt6.QtWidgets import (
    QApplication, QComboBox, QHBoxLayout, QHeaderView, QLabel, QLineEdit,
    QMainWindow, QPlainTextEdit, QPushButton, QScrollArea, QSplitter,
    QTreeView, QTableView, QVBoxLayout, QWidget, QAbstractItemView,
    QFormLayout, QFrame, QGroupBox, QSystemTrayIcon, QMenu, QStackedWidget,
    QSizePolicy,
)


# ── Paths ──────────────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parent
DB_PATH = ROOT / "data" / "index" / "prompts.db"
LOGO_PATH = ROOT / "logo.png"

VERSION = "0.3.1"

# ── Catppuccin Mocha ───────────────────────────────────────────────
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

STYLESHEET = f"""
/* ── Base ────────────────────────────────────────────────────── */
QMainWindow, QWidget {{
    background-color: {C['base']};
    color: {C['text']};
    font-family: "Segoe UI", "Inter", -apple-system, sans-serif;
    font-size: 13px;
}}

/* ── Inputs ──────────────────────────────────────────────────── */
QLineEdit {{
    background-color: {C['surface0']};
    color: {C['text']};
    border: 1px solid transparent;
    border-radius: 8px;
    padding: 7px 12px;
    selection-background-color: {C['lavender']};
    selection-color: {C['crust']};
}}
QLineEdit:focus {{
    border: 1px solid {C['lavender']};
    background-color: {C['surface0']};
}}
QLineEdit#searchInput {{
    background-color: {C['surface0']};
    padding: 8px 14px 8px 14px;
    font-size: 13px;
    border-radius: 10px;
}}
QLineEdit#searchInput:focus {{
    border: 1px solid {C['lavender']};
}}

/* ── Combos ──────────────────────────────────────────────────── */
QComboBox {{
    background-color: {C['surface0']};
    color: {C['subtext1']};
    border: 1px solid transparent;
    border-radius: 8px;
    padding: 6px 28px 6px 10px;
    font-size: 12px;
}}
QComboBox:hover {{
    border: 1px solid {C['surface2']};
}}
QComboBox:focus {{
    border: 1px solid {C['lavender']};
}}
QComboBox::drop-down {{
    border: none;
    width: 20px;
}}
QComboBox::down-arrow {{
    image: none;
    border-left: 4px solid transparent;
    border-right: 4px solid transparent;
    border-top: 4px solid {C['overlay0']};
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

/* ── Buttons ─────────────────────────────────────────────────── */
QPushButton {{
    background-color: {C['surface0']};
    color: {C['subtext1']};
    border: 1px solid transparent;
    border-radius: 8px;
    padding: 7px 18px;
    font-weight: 500;
    font-size: 12px;
}}
QPushButton:hover {{
    background-color: {C['surface1']};
    color: {C['text']};
}}
QPushButton:pressed {{
    background-color: {C['surface2']};
}}
QPushButton:disabled {{
    background-color: {C['surface0']};
    color: {C['overlay0']};
}}
QPushButton#primaryBtn {{
    background-color: {C['lavender']};
    color: {C['crust']};
    border: none;
    font-weight: 600;
    padding: 8px 22px;
}}
QPushButton#primaryBtn:hover {{
    background-color: {C['blue']};
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
    padding: 8px 22px;
}}
QPushButton#accentBtn:hover {{
    background-color: {C['green']};
}}
QPushButton#accentBtn:disabled {{
    background-color: {C['surface1']};
    color: {C['overlay0']};
}}
/* ── Tree & Table ────────────────────────────────────────────── */
QTreeView, QTableView {{
    background-color: {C['mantle']};
    color: {C['text']};
    border: none;
    outline: none;
    alternate-background-color: {C['crust']};
}}
QTreeView::item {{
    padding: 6px 12px;
    border-radius: 0px;
}}
QTableView::item {{
    padding: 5px 8px;
}}
QTreeView::item:selected, QTableView::item:selected {{
    background-color: {C['surface0']};
    color: {C['lavender']};
}}
QTreeView::item:hover, QTableView::item:hover {{
    background-color: rgba(49, 50, 68, 0.5);
}}
QTreeView::branch {{
    background-color: {C['mantle']};
}}
QTreeView::branch:selected {{
    background-color: {C['surface0']};
}}
QHeaderView::section {{
    background-color: {C['crust']};
    color: {C['overlay0']};
    border: none;
    border-bottom: 1px solid {C['surface0']};
    padding: 6px 8px;
    font-weight: 600;
    font-size: 11px;
    letter-spacing: 0.5px;
}}

/* ── Scrollbars ──────────────────────────────────────────────── */
QScrollBar:vertical {{
    background: transparent;
    width: 6px;
    margin: 2px;
}}
QScrollBar::handle:vertical {{
    background: {C['surface1']};
    border-radius: 3px;
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
    height: 6px;
    margin: 2px;
}}
QScrollBar::handle:horizontal {{
    background: {C['surface1']};
    border-radius: 3px;
    min-width: 40px;
}}
QScrollBar::handle:horizontal:hover {{
    background: {C['surface2']};
}}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal,
QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {{
    width: 0px;
}}

/* ── Splitter ────────────────────────────────────────────────── */
QSplitter::handle {{
    background-color: {C['crust']};
    width: 1px;
}}

/* ── Status bar ──────────────────────────────────────────────── */
QStatusBar {{
    background-color: {C['crust']};
    color: {C['overlay0']};
    font-size: 11px;
    padding: 2px 8px;
}}

/* ── Body editor ─────────────────────────────────────────────── */
QPlainTextEdit#bodyEditor {{
    background-color: {C['mantle']};
    color: {C['subtext1']};
    border: 1px solid {C['surface0']};
    border-radius: 8px;
    padding: 12px;
    selection-background-color: {C['lavender']};
    selection-color: {C['crust']};
}}

/* ── Groups ──────────────────────────────────────────────────── */
QGroupBox {{
    color: {C['overlay0']};
    border: 1px solid {C['surface0']};
    border-radius: 8px;
    margin-top: 14px;
    padding: 20px 12px 12px 12px;
    font-weight: 600;
    font-size: 11px;
    letter-spacing: 0.3px;
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    subcontrol-position: top left;
    padding: 2px 10px;
}}

/* ── Labels ──────────────────────────────────────────────────── */
QLabel#titleLabel {{
    color: {C['text']};
    font-size: 17px;
    font-weight: 700;
    letter-spacing: -0.2px;
}}
QLabel#metaLabel {{
    color: {C['overlay1']};
    font-size: 11px;
    letter-spacing: 0.2px;
}}
QLabel#tagPill {{
    background-color: {C['surface0']};
    color: {C['subtext0']};
    border-radius: 4px;
    padding: 2px 8px;
    font-size: 11px;
}}
QLabel#qualityPill {{
    border-radius: 4px;
    padding: 2px 8px;
    font-size: 11px;
    font-weight: 700;
}}
QLabel#emptyTitle {{
    color: {C['overlay1']};
    font-size: 15px;
    font-weight: 600;
}}
QLabel#emptySubtitle {{
    color: {C['overlay0']};
    font-size: 12px;
}}

/* ── Divider ─────────────────────────────────────────────────── */
QFrame#divider {{
    background-color: {C['surface0']};
    max-height: 1px;
    margin: 4px 0px;
}}

/* ── Menus ────────────────────────────────────────────────────── */
QMenu {{
    background-color: {C['surface0']};
    color: {C['text']};
    border: 1px solid {C['surface1']};
    border-radius: 8px;
    padding: 4px;
}}
QMenu::item {{
    padding: 6px 24px 6px 12px;
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

/* ── Tooltips ────────────────────────────────────────────────── */
QToolTip {{
    background-color: {C['surface0']};
    color: {C['text']};
    border: 1px solid {C['surface1']};
    border-radius: 6px;
    padding: 6px 10px;
    font-size: 12px;
}}
"""

VAR_RE = re.compile(r"\{\{\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*\}\}")


# ── Win32 helpers (Windows only) ──────────────────────────────────
if IS_WIN:
    import ctypes
    import ctypes.wintypes

    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32

    MOD_SHIFT = 0x0004
    MOD_WIN = 0x0008
    MOD_NOREPEAT = 0x4000
    HOTKEY_ID = 0xBFFF
    VK_P = 0x50

    INPUT_KEYBOARD = 1
    KEYEVENTF_KEYUP = 0x0002
    VK_CONTROL = 0xA2
    VK_V = 0x56

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
        for i, (vk, flags) in enumerate([
            (VK_CONTROL, 0), (VK_V, 0),
            (VK_V, KEYEVENTF_KEYUP), (VK_CONTROL, KEYEVENTF_KEYUP),
        ]):
            inputs[i].type = INPUT_KEYBOARD
            inputs[i]._input.ki.wVk = vk
            inputs[i]._input.ki.dwFlags = flags
        user32.SendInput(4, ctypes.pointer(inputs[0]), ctypes.sizeof(INPUT))


class HotkeyThread(QThread):
    triggered = pyqtSignal()

    def __init__(self):
        super().__init__()
        self._running = True

    def run(self):
        if not IS_WIN:
            return
        user32.RegisterHotKey(None, HOTKEY_ID, MOD_WIN | MOD_SHIFT | MOD_NOREPEAT, VK_P)
        msg = ctypes.wintypes.MSG()
        while self._running:
            if user32.PeekMessageW(ctypes.byref(msg), None, 0, 0, 1):
                if msg.message == 0x0312 and msg.wParam == HOTKEY_ID:
                    self.triggered.emit()
            else:
                self.msleep(50)
        user32.UnregisterHotKey(None, HOTKEY_ID)

    def stop(self):
        self._running = False
        self.wait(2000)


# ── Database layer ─────────────────────────────────────────────────
class PromptDB:
    def __init__(self, db_path: Path):
        self.conn = sqlite3.connect(str(db_path))
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")

    def close(self):
        self.conn.close()

    def categories(self) -> list[tuple[str, int]]:
        rows = self.conn.execute(
            "SELECT category, COUNT(*) AS cnt FROM prompts GROUP BY category ORDER BY cnt DESC"
        ).fetchall()
        return [(r["category"], r["cnt"]) for r in rows]

    def total_count(self) -> int:
        return self.conn.execute("SELECT COUNT(*) FROM prompts").fetchone()[0]

    def search(self, query: str = "", category: str = "", role: str = "",
               min_quality: int = 0, source: str = "", limit: int = 500) -> list[dict]:
        conditions: list[str] = []
        params: list = []
        if query.strip():
            safe_q = re.sub(r'[^\w\s]', ' ', query.strip())
            terms = [t for t in safe_q.split() if t]
            if terms:
                conditions.append("p.rowid IN (SELECT rowid FROM prompts_fts WHERE prompts_fts MATCH ?)")
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
        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        sql = f"""
            SELECT p.rowid, p.id, p.title, p.body, p.role, p.category,
                   p.tags, p.variables, p.target_models, p.language,
                   p.source, p.author, p.license, p.version, p.quality,
                   p.created, p.updated
            FROM prompts p {where}
            ORDER BY p.quality DESC, p.title ASC
            LIMIT ?
        """
        params.append(limit)
        rows = self.conn.execute(sql, params).fetchall()
        return [dict(r) for r in rows]

    def sources(self) -> list[str]:
        rows = self.conn.execute(
            "SELECT DISTINCT substr(id, 1, instr(id, '-') - 1) AS src FROM prompts ORDER BY src"
        ).fetchall()
        return [r["src"] for r in rows]


# ── Export formatters ─────────────────────────────────────────────
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
    if tags:
        meta.append(f"**Tags:** {', '.join(tags)}")
    lines.append(" | ".join(meta))
    lines.extend(["", "---", "", body, ""])
    return "\n".join(lines)

def export_json(rec: dict, body: str) -> str:
    obj = {"title": rec["title"], "body": body, "role": rec["role"], "category": rec["category"]}
    if rec.get("author"):
        obj["author"] = rec["author"]
    tags = json.loads(rec.get("tags", "[]")) if isinstance(rec.get("tags"), str) else rec.get("tags", [])
    if tags:
        obj["tags"] = tags
    return json.dumps(obj, indent=2, ensure_ascii=False)

EXPORTERS = {"Plain Text": export_plain, "Markdown": export_markdown, "JSON": export_json}


# ── Empty state ───────────────────────────────────────────────────
class EmptyState(QWidget):
    def __init__(self, title: str = "", subtitle: str = "", parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setSpacing(8)
        layout.setContentsMargins(40, 40, 40, 40)

        t = QLabel(title)
        t.setObjectName("emptyTitle")
        t.setAlignment(Qt.AlignmentFlag.AlignCenter)
        t.setWordWrap(True)
        layout.addWidget(t)
        self._title = t

        s = QLabel(subtitle)
        s.setObjectName("emptySubtitle")
        s.setAlignment(Qt.AlignmentFlag.AlignCenter)
        s.setWordWrap(True)
        layout.addWidget(s)
        self._subtitle = s

    def set_text(self, title: str, subtitle: str):
        self._title.setText(title)
        self._subtitle.setText(subtitle)


# ── Category tree ─────────────────────────────────────────────────
class CategoryTree(QTreeView):
    category_selected = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setHeaderHidden(True)
        self.setRootIsDecorated(False)
        self.setFixedWidth(210)
        self.setAlternatingRowColors(False)
        self.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
        self._model = QStandardItemModel()
        self.setModel(self._model)
        self.clicked.connect(self._on_click)

    def load(self, categories: list[tuple[str, int]], total: int):
        self._model.clear()
        all_item = QStandardItem(f"All Prompts ({total:,})")
        all_item.setData("", Qt.ItemDataRole.UserRole)
        all_item.setEditable(False)
        font = all_item.font()
        font.setBold(True)
        all_item.setFont(font)
        self._model.appendRow(all_item)

        for cat, count in categories:
            label = cat.replace("_", " ").title()
            item = QStandardItem(f"{label} ({count:,})")
            item.setData(cat, Qt.ItemDataRole.UserRole)
            item.setEditable(False)
            item.setForeground(QColor(C["subtext1"]))
            self._model.appendRow(item)

        self.setCurrentIndex(self._model.index(0, 0))

    def _on_click(self, index):
        item = self._model.itemFromIndex(index)
        if item:
            self.category_selected.emit(item.data(Qt.ItemDataRole.UserRole) or "")


# ── Prompt list table ─────────────────────────────────────────────
class PromptTable(QTableView):
    prompt_selected = pyqtSignal(dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._model = QStandardItemModel()
        self._model.setHorizontalHeaderLabels(["Score", "Title", "Category"])
        self.setModel(self._model)
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.setAlternatingRowColors(True)
        self.verticalHeader().setVisible(False)
        self.setShowGrid(False)
        self.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
        hdr = self.horizontalHeader()
        hdr.setStretchLastSection(False)
        hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        hdr.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        hdr.setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        self.setColumnWidth(0, 48)
        self.setColumnWidth(2, 100)
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
            cat_item.setForeground(QColor(C["overlay1"]))

            for it in (q_item, title_item, cat_item):
                it.setEditable(False)
            self._model.appendRow([q_item, title_item, cat_item])

    def _on_row(self, current, _previous):
        row = current.row()
        if 0 <= row < len(self._data):
            self.prompt_selected.emit(self._data[row])

    def current_record(self) -> dict | None:
        idx = self.currentIndex()
        if idx.isValid() and 0 <= idx.row() < len(self._data):
            return self._data[idx.row()]
        return None


# ── Quality pill ──────────────────────────────────────────────────
def _quality_pill(q: int) -> QLabel:
    lbl = QLabel(str(q))
    lbl.setObjectName("qualityPill")
    lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
    lbl.setFixedHeight(22)
    lbl.setMinimumWidth(36)
    if q >= 60:
        lbl.setStyleSheet(f"background-color: rgba(166,227,161,0.15); color: {C['green']};")
        lbl.setToolTip(f"High quality ({q}/100)")
    elif q >= 35:
        lbl.setStyleSheet(f"background-color: rgba(249,226,175,0.12); color: {C['yellow']};")
        lbl.setToolTip(f"Good quality ({q}/100)")
    else:
        lbl.setStyleSheet(f"background-color: rgba(108,112,134,0.12); color: {C['overlay0']};")
        lbl.setToolTip(f"Fair quality ({q}/100)")
    return lbl


# ── Preview pane ──────────────────────────────────────────────────
class PreviewPane(QWidget):
    paste_requested = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._current: dict | None = None
        self._var_inputs: dict[str, QLineEdit] = {}

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # Stacked: empty state (0) / content (1)
        self.stack = QStackedWidget()
        outer.addWidget(self.stack, stretch=1)

        # ── Empty state ───────────────────────────────────────────
        self.empty = EmptyState(
            "Select a prompt",
            "Browse the list or search to find a prompt.\nThe full preview will appear here.",
        )
        self.stack.addWidget(self.empty)

        # ── Content pane ──────────────────────────────────────────
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(20, 16, 20, 12)
        layout.setSpacing(6)

        # Header row: title + quality pill
        header = QHBoxLayout()
        header.setSpacing(10)
        self.title_label = QLabel("")
        self.title_label.setObjectName("titleLabel")
        self.title_label.setWordWrap(True)
        self.title_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        header.addWidget(self.title_label)
        self.quality_pill_container = QWidget()
        qpc_layout = QHBoxLayout(self.quality_pill_container)
        qpc_layout.setContentsMargins(0, 0, 0, 0)
        qpc_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        header.addWidget(self.quality_pill_container)
        layout.addLayout(header)

        # Meta line
        self.meta_label = QLabel("")
        self.meta_label.setObjectName("metaLabel")
        self.meta_label.setWordWrap(True)
        layout.addWidget(self.meta_label)

        # Tags (wrapping label)
        self.tags_label = QLabel("")
        self.tags_label.setWordWrap(True)
        self.tags_label.setVisible(False)
        layout.addWidget(self.tags_label)

        layout.addSpacing(4)

        # Divider
        div = QFrame()
        div.setObjectName("divider")
        div.setFrameShape(QFrame.Shape.HLine)
        layout.addWidget(div)

        layout.addSpacing(2)

        # Body
        self.body_text = QPlainTextEdit()
        self.body_text.setObjectName("bodyEditor")
        self.body_text.setReadOnly(True)
        self.body_text.setLineWrapMode(QPlainTextEdit.LineWrapMode.WidgetWidth)
        body_font = QFont("Cascadia Code", 11)
        body_font.setStyleHint(QFont.StyleHint.Monospace)
        self.body_text.setFont(body_font)
        layout.addWidget(self.body_text, stretch=1)

        # Variables
        self.vars_group = QGroupBox("Template Variables")
        self.vars_layout = QFormLayout(self.vars_group)
        self.vars_layout.setContentsMargins(12, 8, 12, 8)
        self.vars_layout.setSpacing(6)
        self.vars_group.setVisible(False)
        layout.addWidget(self.vars_group)

        layout.addSpacing(4)

        # ── Action bar ────────────────────────────────────────────
        action_bar = QHBoxLayout()
        action_bar.setSpacing(8)

        # Left: export format
        self.export_combo = QComboBox()
        self.export_combo.addItems(list(EXPORTERS.keys()))
        self.export_combo.setFixedWidth(110)
        self.export_combo.setToolTip("Export format for copy and paste")
        action_bar.addWidget(self.export_combo)

        action_bar.addStretch()

        # Right: action buttons
        self.copy_btn = QPushButton("Copy")
        self.copy_btn.setToolTip("Copy prompt to clipboard")
        self.copy_btn.setEnabled(False)
        self.copy_btn.clicked.connect(self._copy_exported)
        action_bar.addWidget(self.copy_btn)

        self.copy_filled_btn = QPushButton("Copy Filled")
        self.copy_filled_btn.setObjectName("primaryBtn")
        self.copy_filled_btn.setToolTip("Copy with variables filled in")
        self.copy_filled_btn.setVisible(False)
        self.copy_filled_btn.clicked.connect(self._copy_filled)
        action_bar.addWidget(self.copy_filled_btn)

        if IS_WIN:
            self.paste_btn = QPushButton("Paste to App")
            self.paste_btn.setObjectName("accentBtn")
            self.paste_btn.setToolTip("Paste into the previously active window")
            self.paste_btn.setEnabled(False)
            self.paste_btn.clicked.connect(self._paste_to_window)
            action_bar.addWidget(self.paste_btn)

        layout.addLayout(action_bar)
        self.stack.addWidget(content)

    def show_prompt(self, rec: dict):
        self._current = rec
        self.stack.setCurrentIndex(1)
        self.copy_btn.setEnabled(True)
        if IS_WIN and hasattr(self, "paste_btn"):
            self.paste_btn.setEnabled(True)

        # Title
        self.title_label.setText(rec["title"])

        # Quality pill
        qpc = self.quality_pill_container.layout()
        while qpc.count():
            child = qpc.takeAt(0)
            if child.widget():
                child.widget().deleteLater()
        qpc.addWidget(_quality_pill(rec.get("quality", 0)))

        # Meta
        parts = []
        if rec.get("author"):
            parts.append(rec["author"])
        parts.append(rec["role"])
        parts.append(rec["license"])
        parts.append(rec["category"])
        self.meta_label.setText("  /  ".join(parts))

        # Tags as inline styled text
        tags = json.loads(rec.get("tags", "[]")) if isinstance(rec.get("tags"), str) else rec.get("tags", [])
        if tags:
            spans = []
            for tag in tags[:10]:
                spans.append(
                    f'<span style="background-color:{C["surface0"]}; color:{C["subtext0"]}; '
                    f'padding:1px 6px; font-size:11px;">{tag}</span>'
                )
            self.tags_label.setText("&nbsp; ".join(spans))
            self.tags_label.setVisible(True)
        else:
            self.tags_label.setVisible(False)

        # Body
        self.body_text.setPlainText(rec["body"])

        # Variables
        self._var_inputs.clear()
        while self.vars_layout.rowCount() > 0:
            self.vars_layout.removeRow(0)

        variables = json.loads(rec.get("variables", "[]")) if isinstance(rec.get("variables"), str) else rec.get("variables", [])
        if variables:
            self.vars_group.setVisible(True)
            for var in variables:
                name = var.get("name", "")
                display = name.replace("_", " ").title()
                inp = QLineEdit()
                inp.setPlaceholderText(var.get("default", name))
                inp.textChanged.connect(self._update_preview)
                self._var_inputs[name] = inp
                label = QLabel(display)
                label.setStyleSheet(f"color: {C['subtext0']}; font-size: 12px;")
                self.vars_layout.addRow(label, inp)
            self.copy_filled_btn.setVisible(True)
        else:
            self.vars_group.setVisible(False)
            self.copy_filled_btn.setVisible(False)

    def show_no_results(self):
        self._current = None
        self.copy_btn.setEnabled(False)
        if IS_WIN and hasattr(self, "paste_btn"):
            self.paste_btn.setEnabled(False)
        self.empty.set_text("No prompts found", "Try a different search term or clear your filters.")
        self.stack.setCurrentIndex(0)

    def show_welcome(self):
        self.empty.set_text("Select a prompt", "Browse the list or search to find a prompt.\nThe full preview will appear here.")
        self.stack.setCurrentIndex(0)

    def _get_filled_body(self) -> str:
        if not self._current:
            return ""
        body = self._current["body"]
        for name, inp in self._var_inputs.items():
            value = inp.text() or inp.placeholderText()
            body = body.replace("{{" + name + "}}", value)
            body = re.sub(r"\{\{\s*" + re.escape(name) + r"\s*\}\}", value, body)
        return body

    def _get_export_text(self, body: str) -> str:
        if not self._current:
            return body
        fmt = self.export_combo.currentText()
        return EXPORTERS.get(fmt, export_plain)(self._current, body)

    def _update_preview(self):
        if self._current:
            self.body_text.setPlainText(self._get_filled_body())

    def _flash_button(self, btn: QPushButton, original_text: str):
        saved_ss = btn.styleSheet()
        btn.setStyleSheet(f"background-color: {C['green']}; color: {C['crust']}; border: none; font-weight: 600;")
        btn.setText("Copied")
        def _reset():
            btn.setStyleSheet(saved_ss)
            btn.setText(original_text)
        QTimer.singleShot(1200, _reset)

    def _copy_exported(self):
        if self._current:
            QApplication.clipboard().setText(self._get_export_text(self._current["body"]))
            self._flash_button(self.copy_btn, "Copy")

    def _copy_filled(self):
        QApplication.clipboard().setText(self._get_export_text(self._get_filled_body()))
        self._flash_button(self.copy_filled_btn, "Copy Filled")

    def _paste_to_window(self):
        body = self._get_filled_body() if self._var_inputs else (self._current["body"] if self._current else "")
        self.paste_requested.emit(self._get_export_text(body))


# ── Main window ───────────────────────────────────────────────────
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"PromptCompanion v{VERSION}")
        self.resize(1300, 800)
        self._prev_hwnd = None
        self._hotkey_thread = None

        if LOGO_PATH.exists():
            self.setWindowIcon(QIcon(str(LOGO_PATH)))

        self.db = PromptDB(DB_PATH)
        self._total = self.db.total_count()

        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # ── Toolbar ────────────────────────────────────────────────
        toolbar = QWidget()
        toolbar.setStyleSheet(f"background-color: {C['crust']};")
        tb_layout = QHBoxLayout(toolbar)
        tb_layout.setContentsMargins(14, 10, 14, 10)
        tb_layout.setSpacing(8)

        self.search_input = QLineEdit()
        self.search_input.setObjectName("searchInput")
        self.search_input.setPlaceholderText(f"Search {self._total:,} prompts...")
        self.search_input.setMinimumWidth(300)
        self.search_input.setClearButtonEnabled(True)
        tb_layout.addWidget(self.search_input, stretch=1)

        tb_layout.addSpacing(4)

        self.role_combo = QComboBox()
        self.role_combo.addItems(["Any Role", "system", "user", "assistant"])
        self.role_combo.setFixedWidth(105)
        self.role_combo.setToolTip("Filter by prompt role")
        tb_layout.addWidget(self.role_combo)

        self.quality_combo = QComboBox()
        self.quality_combo.addItems(["Any Score", "High (60+)", "Good (40+)", "Fair (20+)"])
        self.quality_combo.setFixedWidth(115)
        self.quality_combo.setToolTip("Filter by quality score")
        tb_layout.addWidget(self.quality_combo)

        self.source_combo = QComboBox()
        self.source_combo.addItem("Any Source")
        for src in self.db.sources():
            self.source_combo.addItem(src)
        self.source_combo.setFixedWidth(120)
        self.source_combo.setToolTip("Filter by upstream source")
        tb_layout.addWidget(self.source_combo)

        tb_layout.addSpacing(4)

        self.count_label = QLabel("")
        self.count_label.setStyleSheet(f"color: {C['overlay0']}; font-size: 11px;")
        self.count_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.count_label.setMinimumWidth(80)
        tb_layout.addWidget(self.count_label)

        main_layout.addWidget(toolbar)

        # ── Three-pane splitter ────────────────────────────────────
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setHandleWidth(1)

        self.cat_tree = CategoryTree()
        splitter.addWidget(self.cat_tree)

        self.prompt_table = PromptTable()
        splitter.addWidget(self.prompt_table)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.preview = PreviewPane()
        scroll.setWidget(self.preview)
        splitter.addWidget(scroll)

        splitter.setSizes([210, 400, 690])
        main_layout.addWidget(splitter, stretch=1)

        # ── Status bar ─────────────────────────────────────────────
        hotkey = "Win+Shift+P to summon" if IS_WIN else ""
        self.statusBar().showMessage(
            f"{self._total:,} prompts from 4 sources" +
            (f"   |   {hotkey}" if hotkey else "")
        )

        # ── System tray ────────────────────────────────────────────
        self._setup_tray()

        # ── Load data ──────────────────────────────────────────────
        cats = self.db.categories()
        self.cat_tree.load(cats, self._total)

        # ── Connections ────────────────────────────────────────────
        self.cat_tree.category_selected.connect(self._on_filter_changed)
        self.prompt_table.prompt_selected.connect(self.preview.show_prompt)
        self.preview.paste_requested.connect(self._do_paste_to_window)
        self.role_combo.currentIndexChanged.connect(self._on_filter_changed)
        self.quality_combo.currentIndexChanged.connect(self._on_filter_changed)
        self.source_combo.currentIndexChanged.connect(self._on_filter_changed)

        self._search_timer = QTimer()
        self._search_timer.setSingleShot(True)
        self._search_timer.setInterval(200)
        self._search_timer.timeout.connect(self._on_filter_changed)
        self.search_input.textChanged.connect(lambda: self._search_timer.start())

        self._current_category = ""
        self._on_filter_changed()

        if IS_WIN:
            self._hotkey_thread = HotkeyThread()
            self._hotkey_thread.triggered.connect(self._on_hotkey)
            self._hotkey_thread.start()

    def _setup_tray(self):
        self._tray_available = QSystemTrayIcon.isSystemTrayAvailable()
        if not self._tray_available:
            self.tray = None
            return

        self.tray = QSystemTrayIcon(self)
        if LOGO_PATH.exists():
            self.tray.setIcon(QIcon(str(LOGO_PATH)))
        else:
            self.tray.setIcon(self.windowIcon())
        self.tray.setToolTip(f"PromptCompanion v{VERSION}")

        menu = QMenu()
        show_action = QAction("Show PromptCompanion", self)
        show_action.triggered.connect(self._show_from_tray)
        menu.addAction(show_action)
        menu.addSeparator()
        quit_action = QAction("Quit", self)
        quit_action.triggered.connect(self._quit_app)
        menu.addAction(quit_action)

        self.tray.setContextMenu(menu)
        self.tray.activated.connect(self._on_tray_activated)
        self.tray.show()

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
            self.statusBar().showMessage("Copied (no target window detected)", 3000)
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
            cat = _args[0] if _args else ""
            self._current_category = cat

        query = self.search_input.text()
        category = self._current_category

        role_text = self.role_combo.currentText()
        role = "" if role_text == "Any Role" else role_text

        q_text = self.quality_combo.currentText()
        min_quality = 0
        if "60" in q_text:
            min_quality = 60
        elif "40" in q_text:
            min_quality = 40
        elif "20" in q_text:
            min_quality = 20

        src_text = self.source_combo.currentText()
        source = "" if src_text == "Any Source" else src_text

        results = self.db.search(query=query, category=category, role=role,
                                 min_quality=min_quality, source=source)
        self.prompt_table.load(results)

        n = len(results)
        self.count_label.setText(f"{n:,} result{'s' if n != 1 else ''}")

        if n == 0 and (query or role or min_quality or source):
            self.preview.show_no_results()
        elif n == 0:
            self.preview.show_welcome()

        parts = [f"{n:,} prompt{'s' if n != 1 else ''}"]
        if query:
            parts.append(f'for "{query}"')
        if category:
            parts.append(f"in {category}")
        self.statusBar().showMessage("  ".join(parts), 5000)

    def closeEvent(self, event):
        if not self._tray_available:
            # No system tray — close normally
            self._quit_app()
            event.accept()
            return
        event.ignore()
        self.hide()
        self.tray.showMessage(
            "PromptCompanion",
            "Still running. " + ("Win+Shift+P to summon." if IS_WIN else "Double-click tray icon to show."),
            QSystemTrayIcon.MessageIcon.Information,
            2000,
        )


# ── Entry point ───────────────────────────────────────────────────
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
    sys.exit(main())
