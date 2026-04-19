#!/usr/bin/env python3
"""PromptCompanion v0.2.0 — Desktop GUI for curated AI prompts.

Three-pane layout: category tree | prompt list | preview + variables.
SQLite FTS5 search. Catppuccin Mocha dark theme. One-click copy.
"""

from __future__ import annotations

import json
import re
import sqlite3
import subprocess
import sys
from pathlib import Path


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

from PyQt6.QtCore import Qt, QSortFilterProxyModel, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QStandardItem, QStandardItemModel, QIcon, QPixmap, QPainter
from PyQt6.QtWidgets import (
    QApplication, QComboBox, QHBoxLayout, QHeaderView, QLabel, QLineEdit,
    QMainWindow, QPlainTextEdit, QPushButton, QScrollArea, QSplitter,
    QStatusBar, QTreeView, QTableView, QVBoxLayout, QWidget, QAbstractItemView,
    QFormLayout, QFrame, QGroupBox, QSizePolicy,
)


# ── Paths ──────────────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parent
DB_PATH = ROOT / "data" / "index" / "prompts.db"
LOGO_PATH = ROOT / "logo.png"

VERSION = "0.2.0"

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
QMainWindow, QWidget {{
    background-color: {C['base']};
    color: {C['text']};
    font-family: "Segoe UI", "Inter", sans-serif;
    font-size: 13px;
}}
QLineEdit, QComboBox, QPlainTextEdit {{
    background-color: {C['surface0']};
    color: {C['text']};
    border: 1px solid {C['surface1']};
    border-radius: 6px;
    padding: 6px 10px;
    selection-background-color: {C['lavender']};
    selection-color: {C['crust']};
}}
QLineEdit:focus, QComboBox:focus {{
    border: 1px solid {C['lavender']};
}}
QComboBox::drop-down {{
    border: none;
    padding-right: 8px;
}}
QComboBox::down-arrow {{
    image: none;
    border-left: 4px solid transparent;
    border-right: 4px solid transparent;
    border-top: 5px solid {C['subtext0']};
    margin-right: 6px;
}}
QComboBox QAbstractItemView {{
    background-color: {C['surface0']};
    color: {C['text']};
    border: 1px solid {C['surface1']};
    selection-background-color: {C['surface1']};
    selection-color: {C['lavender']};
    outline: none;
}}
QPushButton {{
    background-color: {C['surface0']};
    color: {C['text']};
    border: 1px solid {C['surface1']};
    border-radius: 6px;
    padding: 6px 16px;
    font-weight: 500;
}}
QPushButton:hover {{
    background-color: {C['surface1']};
    border-color: {C['lavender']};
}}
QPushButton:pressed {{
    background-color: {C['surface2']};
}}
QPushButton#copyBtn {{
    background-color: {C['lavender']};
    color: {C['crust']};
    border: none;
    font-weight: 600;
    padding: 8px 24px;
}}
QPushButton#copyBtn:hover {{
    background-color: {C['blue']};
}}
QTreeView, QTableView {{
    background-color: {C['mantle']};
    color: {C['text']};
    border: none;
    outline: none;
    alternate-background-color: {C['crust']};
    gridline-color: {C['surface0']};
}}
QTreeView::item, QTableView::item {{
    padding: 4px 6px;
}}
QTreeView::item:selected, QTableView::item:selected {{
    background-color: {C['surface0']};
    color: {C['lavender']};
}}
QTreeView::item:hover, QTableView::item:hover {{
    background-color: {C['surface0']};
}}
QTreeView::branch {{
    background-color: {C['mantle']};
}}
QTreeView::branch:selected {{
    background-color: {C['surface0']};
}}
QHeaderView::section {{
    background-color: {C['crust']};
    color: {C['subtext0']};
    border: none;
    border-right: 1px solid {C['surface0']};
    padding: 5px 8px;
    font-weight: 600;
    font-size: 11px;
    text-transform: uppercase;
}}
QScrollBar:vertical {{
    background: {C['mantle']};
    width: 8px;
    border: none;
}}
QScrollBar::handle:vertical {{
    background: {C['surface1']};
    border-radius: 4px;
    min-height: 30px;
}}
QScrollBar::handle:vertical:hover {{
    background: {C['surface2']};
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical,
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
    background: none;
    border: none;
    height: 0px;
}}
QScrollBar:horizontal {{
    background: {C['mantle']};
    height: 8px;
    border: none;
}}
QScrollBar::handle:horizontal {{
    background: {C['surface1']};
    border-radius: 4px;
    min-width: 30px;
}}
QScrollBar::handle:horizontal:hover {{
    background: {C['surface2']};
}}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal,
QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {{
    background: none;
    border: none;
    width: 0px;
}}
QSplitter::handle {{
    background-color: {C['surface0']};
    width: 2px;
}}
QStatusBar {{
    background-color: {C['crust']};
    color: {C['subtext0']};
    font-size: 11px;
}}
QGroupBox {{
    color: {C['subtext0']};
    border: 1px solid {C['surface0']};
    border-radius: 6px;
    margin-top: 12px;
    padding-top: 16px;
    font-weight: 600;
    font-size: 11px;
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    subcontrol-position: top left;
    padding: 2px 8px;
}}
QLabel#sectionLabel {{
    color: {C['subtext0']};
    font-size: 11px;
    font-weight: 600;
    text-transform: uppercase;
    padding-bottom: 2px;
}}
QLabel#titleLabel {{
    color: {C['lavender']};
    font-size: 18px;
    font-weight: 700;
}}
QLabel#metaLabel {{
    color: {C['overlay1']};
    font-size: 11px;
}}
QLabel#tagLabel {{
    background-color: {C['surface0']};
    color: {C['subtext1']};
    border-radius: 4px;
    padding: 2px 8px;
    font-size: 11px;
}}
QLabel#qualityHigh {{
    color: {C['green']};
    font-weight: 700;
}}
QLabel#qualityMid {{
    color: {C['yellow']};
    font-weight: 700;
}}
QLabel#qualityLow {{
    color: {C['overlay0']};
    font-weight: 700;
}}
QFrame#divider {{
    background-color: {C['surface0']};
    max-height: 1px;
}}
"""

# ── Var regex ──────────────────────────────────────────────────────
VAR_RE = re.compile(r"\{\{\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*\}\}")


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
            conditions.append("p.rowid IN (SELECT rowid FROM prompts_fts WHERE prompts_fts MATCH ?)")
            # Escape FTS5 special chars and add prefix matching
            safe_q = re.sub(r'[^\w\s]', ' ', query.strip())
            terms = safe_q.split()
            fts_query = " ".join(f'"{t}"*' for t in terms if t)
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
            FROM prompts p
            {where}
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


# ── Quality badge helper ──────────────────────────────────────────
def quality_label(q: int) -> QLabel:
    lbl = QLabel(str(q))
    if q >= 60:
        lbl.setObjectName("qualityHigh")
    elif q >= 35:
        lbl.setObjectName("qualityMid")
    else:
        lbl.setObjectName("qualityLow")
    lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
    lbl.setFixedWidth(32)
    return lbl


# ── Category tree ─────────────────────────────────────────────────
class CategoryTree(QTreeView):
    category_selected = pyqtSignal(str)  # "" = all

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setHeaderHidden(True)
        self.setRootIsDecorated(False)
        self.setFixedWidth(200)
        self.setAlternatingRowColors(True)
        self._model = QStandardItemModel()
        self.setModel(self._model)
        self.clicked.connect(self._on_click)

    def load(self, categories: list[tuple[str, int]], total: int):
        self._model.clear()
        all_item = QStandardItem(f"All Prompts  ({total})")
        all_item.setData("", Qt.ItemDataRole.UserRole)
        all_item.setEditable(False)
        font = all_item.font()
        font.setBold(True)
        all_item.setFont(font)
        self._model.appendRow(all_item)

        for cat, count in categories:
            label = cat.replace("_", " ").title()
            item = QStandardItem(f"{label}  ({count})")
            item.setData(cat, Qt.ItemDataRole.UserRole)
            item.setEditable(False)
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
        self._model.setHorizontalHeaderLabels(["Q", "Title", "Category", "Role", "Source"])
        self.setModel(self._model)
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.setAlternatingRowColors(True)
        self.verticalHeader().setVisible(False)
        self.setShowGrid(False)
        self.horizontalHeader().setStretchLastSection(True)
        self.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        self.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        self.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)
        self.setColumnWidth(0, 36)
        self.setColumnWidth(2, 110)
        self.setColumnWidth(3, 60)
        self.selectionModel().currentRowChanged.connect(self._on_row)
        self._data: list[dict] = []

    def load(self, records: list[dict]):
        self._model.removeRows(0, self._model.rowCount())
        self._data = records
        for rec in records:
            q_item = QStandardItem(str(rec.get("quality", 0)))
            q_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            q = rec.get("quality", 0)
            if q >= 60:
                q_item.setForeground(QColor(C["green"]))
            elif q >= 35:
                q_item.setForeground(QColor(C["yellow"]))
            else:
                q_item.setForeground(QColor(C["overlay0"]))

            title_item = QStandardItem(rec["title"])
            cat_item = QStandardItem(rec["category"].replace("_", " ").title())
            role_item = QStandardItem(rec["role"])
            # Extract source key from id
            src_key = rec["id"].split("-")[0] if "-" in rec["id"] else ""
            src_item = QStandardItem(src_key)

            for it in (q_item, title_item, cat_item, role_item, src_item):
                it.setEditable(False)

            self._model.appendRow([q_item, title_item, cat_item, role_item, src_item])

    def _on_row(self, current, _previous):
        row = current.row()
        if 0 <= row < len(self._data):
            self.prompt_selected.emit(self._data[row])

    def current_record(self) -> dict | None:
        idx = self.currentIndex()
        if idx.isValid() and 0 <= idx.row() < len(self._data):
            return self._data[idx.row()]
        return None


# ── Preview pane ──────────────────────────────────────────────────
class PreviewPane(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._current: dict | None = None
        self._var_inputs: dict[str, QLineEdit] = {}
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(8)

        # Title
        self.title_label = QLabel("Select a prompt")
        self.title_label.setObjectName("titleLabel")
        self.title_label.setWordWrap(True)
        layout.addWidget(self.title_label)

        # Meta line
        self.meta_label = QLabel("")
        self.meta_label.setObjectName("metaLabel")
        self.meta_label.setWordWrap(True)
        layout.addWidget(self.meta_label)

        # Tags row
        self.tags_widget = QWidget()
        self.tags_layout = QHBoxLayout(self.tags_widget)
        self.tags_layout.setContentsMargins(0, 0, 0, 0)
        self.tags_layout.setSpacing(4)
        self.tags_layout.addStretch()
        layout.addWidget(self.tags_widget)

        # Divider
        div = QFrame()
        div.setObjectName("divider")
        div.setFrameShape(QFrame.Shape.HLine)
        layout.addWidget(div)

        # Body
        self.body_text = QPlainTextEdit()
        self.body_text.setReadOnly(True)
        self.body_text.setLineWrapMode(QPlainTextEdit.LineWrapMode.WidgetWidth)
        font = QFont("Consolas", 12)
        font.setStyleHint(QFont.StyleHint.Monospace)
        self.body_text.setFont(font)
        layout.addWidget(self.body_text, stretch=1)

        # Variables group
        self.vars_group = QGroupBox("Variables")
        self.vars_layout = QFormLayout(self.vars_group)
        self.vars_group.setVisible(False)
        layout.addWidget(self.vars_group)

        # Bottom bar: copy button
        bottom = QHBoxLayout()
        bottom.setSpacing(8)

        self.quality_display = QLabel("")
        self.quality_display.setFixedWidth(60)
        bottom.addWidget(self.quality_display)

        bottom.addStretch()

        self.copy_raw_btn = QPushButton("Copy Raw")
        self.copy_raw_btn.clicked.connect(self._copy_raw)
        bottom.addWidget(self.copy_raw_btn)

        self.copy_btn = QPushButton("Copy with Variables")
        self.copy_btn.setObjectName("copyBtn")
        self.copy_btn.clicked.connect(self._copy_filled)
        bottom.addWidget(self.copy_btn)

        layout.addLayout(bottom)

    def show_prompt(self, rec: dict):
        self._current = rec
        self.title_label.setText(rec["title"])

        # Meta
        parts = []
        if rec.get("author"):
            parts.append(f"by {rec['author']}")
        parts.append(rec["role"])
        parts.append(rec["license"])
        parts.append(rec["category"])
        self.meta_label.setText("  ·  ".join(parts))

        # Tags
        while self.tags_layout.count() > 1:
            child = self.tags_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()
        tags = json.loads(rec.get("tags", "[]")) if isinstance(rec.get("tags"), str) else rec.get("tags", [])
        for tag in tags[:8]:
            lbl = QLabel(tag)
            lbl.setObjectName("tagLabel")
            self.tags_layout.insertWidget(self.tags_layout.count() - 1, lbl)

        # Body
        self.body_text.setPlainText(rec["body"])

        # Quality
        q = rec.get("quality", 0)
        self.quality_display.setText(f"Q: {q}")
        if q >= 60:
            self.quality_display.setStyleSheet(f"color: {C['green']}; font-weight: 700; font-size: 13px;")
        elif q >= 35:
            self.quality_display.setStyleSheet(f"color: {C['yellow']}; font-weight: 700; font-size: 13px;")
        else:
            self.quality_display.setStyleSheet(f"color: {C['overlay0']}; font-weight: 700; font-size: 13px;")

        # Variables
        self._var_inputs.clear()
        while self.vars_layout.rowCount() > 0:
            self.vars_layout.removeRow(0)

        variables = json.loads(rec.get("variables", "[]")) if isinstance(rec.get("variables"), str) else rec.get("variables", [])
        if variables:
            self.vars_group.setVisible(True)
            for var in variables:
                name = var.get("name", "")
                inp = QLineEdit()
                inp.setPlaceholderText(var.get("default", name))
                inp.textChanged.connect(self._update_preview)
                self._var_inputs[name] = inp
                self.vars_layout.addRow(name, inp)
            self.copy_btn.setVisible(True)
        else:
            self.vars_group.setVisible(False)
            self.copy_btn.setVisible(False)

    def _get_filled_body(self) -> str:
        if not self._current:
            return ""
        body = self._current["body"]
        for name, inp in self._var_inputs.items():
            value = inp.text() or inp.placeholderText()
            body = body.replace("{{" + name + "}}", value)
            body = re.sub(r"\{\{\s*" + re.escape(name) + r"\s*\}\}", value, body)
        return body

    def _update_preview(self):
        if self._current:
            self.body_text.setPlainText(self._get_filled_body())

    def _copy_raw(self):
        if self._current:
            QApplication.clipboard().setText(self._current["body"])
            self.copy_raw_btn.setText("Copied!")
            QTimer.singleShot(1500, lambda: self.copy_raw_btn.setText("Copy Raw"))

    def _copy_filled(self):
        text = self._get_filled_body()
        QApplication.clipboard().setText(text)
        self.copy_btn.setText("Copied!")
        QTimer.singleShot(1500, lambda: self.copy_btn.setText("Copy with Variables"))


# ── Main window ───────────────────────────────────────────────────
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"PromptCompanion v{VERSION}")
        self.resize(1280, 780)

        if LOGO_PATH.exists():
            self.setWindowIcon(QIcon(str(LOGO_PATH)))

        # DB
        self.db = PromptDB(DB_PATH)

        # Central widget
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # ── Toolbar ────────────────────────────────────────────────
        toolbar = QWidget()
        toolbar.setStyleSheet(f"background-color: {C['crust']}; padding: 6px 12px;")
        tb_layout = QHBoxLayout(toolbar)
        tb_layout.setContentsMargins(12, 8, 12, 8)
        tb_layout.setSpacing(10)

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search prompts (FTS5)...")
        self.search_input.setMinimumWidth(280)
        tb_layout.addWidget(self.search_input, stretch=1)

        self.role_combo = QComboBox()
        self.role_combo.addItems(["All Roles", "system", "user", "assistant"])
        self.role_combo.setFixedWidth(110)
        tb_layout.addWidget(self.role_combo)

        self.quality_combo = QComboBox()
        self.quality_combo.addItems(["Any Quality", "60+ (High)", "40+ (Mid)", "20+ (Low)"])
        self.quality_combo.setFixedWidth(120)
        tb_layout.addWidget(self.quality_combo)

        self.source_combo = QComboBox()
        self.source_combo.addItem("All Sources")
        for src in self.db.sources():
            self.source_combo.addItem(src)
        self.source_combo.setFixedWidth(120)
        tb_layout.addWidget(self.source_combo)

        self.count_label = QLabel("")
        self.count_label.setStyleSheet(f"color: {C['overlay1']}; font-size: 11px;")
        self.count_label.setFixedWidth(100)
        self.count_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        tb_layout.addWidget(self.count_label)

        main_layout.addWidget(toolbar)

        # ── Three-pane splitter ────────────────────────────────────
        splitter = QSplitter(Qt.Orientation.Horizontal)

        self.cat_tree = CategoryTree()
        splitter.addWidget(self.cat_tree)

        self.prompt_table = PromptTable()
        splitter.addWidget(self.prompt_table)

        # Preview in scroll area
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.preview = PreviewPane()
        scroll.setWidget(self.preview)
        splitter.addWidget(scroll)

        splitter.setSizes([200, 420, 660])
        main_layout.addWidget(splitter, stretch=1)

        # ── Status bar ─────────────────────────────────────────────
        self.statusBar().showMessage(f"PromptCompanion v{VERSION}")

        # ── Load data ──────────────────────────────────────────────
        cats = self.db.categories()
        total = self.db.total_count()
        self.cat_tree.load(cats, total)

        # ── Connections ────────────────────────────────────────────
        self.cat_tree.category_selected.connect(self._on_filter_changed)
        self.prompt_table.prompt_selected.connect(self.preview.show_prompt)
        self.role_combo.currentIndexChanged.connect(self._on_filter_changed)
        self.quality_combo.currentIndexChanged.connect(self._on_filter_changed)
        self.source_combo.currentIndexChanged.connect(self._on_filter_changed)

        # Debounce search
        self._search_timer = QTimer()
        self._search_timer.setSingleShot(True)
        self._search_timer.setInterval(250)
        self._search_timer.timeout.connect(self._on_filter_changed)
        self.search_input.textChanged.connect(lambda: self._search_timer.start())

        # Initial load
        self._current_category = ""
        self._on_filter_changed()

    def _on_filter_changed(self, *_args):
        # If called from category tree signal, update tracked category
        sender = self.sender()
        if isinstance(sender, CategoryTree):
            cat = _args[0] if _args else ""
            self._current_category = cat

        query = self.search_input.text()
        category = self._current_category

        role_text = self.role_combo.currentText()
        role = "" if role_text == "All Roles" else role_text

        q_text = self.quality_combo.currentText()
        min_quality = 0
        if q_text.startswith("60"):
            min_quality = 60
        elif q_text.startswith("40"):
            min_quality = 40
        elif q_text.startswith("20"):
            min_quality = 20

        src_text = self.source_combo.currentText()
        source = "" if src_text == "All Sources" else src_text

        results = self.db.search(query=query, category=category, role=role,
                                 min_quality=min_quality, source=source)
        self.prompt_table.load(results)
        self.count_label.setText(f"{len(results)} prompts")
        self.statusBar().showMessage(
            f"{len(results)} prompts" +
            (f' matching "{query}"' if query else "") +
            (f" in {category}" if category else "")
        )

    def closeEvent(self, event):
        self.db.close()
        super().closeEvent(event)


# ── Entry point ───────────────────────────────────────────────────
def main():
    if not DB_PATH.exists():
        print(f"Database not found at {DB_PATH}")
        print("Run `python tools/build_index.py` first to generate it.")
        return 1

    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setStyleSheet(STYLESHEET)

    if LOGO_PATH.exists():
        app.setWindowIcon(QIcon(str(LOGO_PATH)))

    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
