"""Main application window for the Visual Automation Studio.

Assembles the four primary panels into a single :class:`QMainWindow`:

* **Block Palette** (left) — draggable block template tiles
* **Block Canvas** (centre-top) — the drag-and-drop automation flow workspace
* **Device Preview** (centre-bottom) — live / placeholder device screenshot
* **Block Config + Devices** (right) — per-block settings and device list

Also provides a menu bar, toolbar, and status bar with file management
(New / Open / Save / Save As) and export/run actions.
"""

from __future__ import annotations

import json
import os
from typing import Optional

from PyQt6.QtCore import QSize, Qt
from PyQt6.QtGui import QAction, QKeySequence
from PyQt6.QtWidgets import (
    QFileDialog,
    QLabel,
    QMainWindow,
    QMessageBox,
    QSplitter,
    QStatusBar,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from core.block_model import BlockData
from core.script_compiler import ScriptCompiler
from ui.block_config import BlockConfigPanel
from ui.block_palette import BlockPalette
from ui.canvas import CanvasScrollArea
from ui.device_panel import DevicePanel
from ui.preview_panel import PreviewPanel


# ── Application-wide dark stylesheet ────────────────────────────────────────
_STYLE = """
QMainWindow, QWidget {
    background: #0D0D1A;
    color: #DDDDEE;
    font-family: "Segoe UI", Arial, sans-serif;
}
QSplitter::handle {
    background: #1A1A2E;
}
QSplitter::handle:horizontal {
    width: 4px;
}
QSplitter::handle:vertical {
    height: 4px;
}
QMenuBar {
    background: #1A1A2E;
    color: #DDD;
    border-bottom: 1px solid #2A2A4A;
    padding: 2px;
}
QMenuBar::item:selected { background: #2A2A4A; }
QMenu {
    background: #1A1A2E;
    color: #DDD;
    border: 1px solid #2A2A4A;
}
QMenu::item:selected { background: #2A2A4A; }
QToolBar {
    background: #12122A;
    border-bottom: 1px solid #2A2A4A;
    spacing: 2px;
    padding: 2px 4px;
}
QToolButton {
    background: transparent;
    color: #CCC;
    border: 1px solid transparent;
    border-radius: 5px;
    padding: 4px 10px;
    font: 10px "Segoe UI";
}
QToolButton:hover { background: #2A2A4A; border-color: #3A3A6A; }
QToolButton:pressed { background: #1A1A3A; }
QStatusBar {
    background: #1A1A2E;
    color: #666688;
    font: 9px "Segoe UI";
}
QScrollBar:vertical {
    background: #0D0D1A;
    width: 8px;
}
QScrollBar::handle:vertical {
    background: #2A2A4A;
    border-radius: 4px;
    min-height: 20px;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar:horizontal {
    background: #0D0D1A;
    height: 8px;
}
QScrollBar::handle:horizontal {
    background: #2A2A4A;
    border-radius: 4px;
    min-width: 20px;
}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0; }
"""


class MainWindow(QMainWindow):
    """Top-level window for the Visual Automation Studio."""

    def __init__(self) -> None:
        super().__init__()
        self._project_path: Optional[str] = None
        self._compiler = ScriptCompiler()
        self._selected_block: Optional[BlockData] = None

        self._build_ui()
        self._build_menu()
        self._build_toolbar()
        self._build_status_bar()
        self.setStyleSheet(_STYLE)

        # Populate device list with demo entries (real ADB not required).
        self._device_panel.populate_demo()

    # ── UI construction ───────────────────────────────────────────────

    def _build_ui(self) -> None:
        self.setWindowTitle("Visual Automation Studio — MobileVisionBot")
        self.resize(1300, 820)
        self.setMinimumSize(920, 620)

        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Horizontal splitter (palette | centre | right) ────────────
        h_split = QSplitter(Qt.Orientation.Horizontal)
        h_split.setChildrenCollapsible(False)

        # Left panel — block palette
        self._palette = BlockPalette()
        h_split.addWidget(self._palette)

        # Centre — vertical splitter (canvas / preview)
        v_split = QSplitter(Qt.Orientation.Vertical)
        v_split.setChildrenCollapsible(False)

        self._canvas_area = CanvasScrollArea()
        self._canvas = self._canvas_area.canvas
        self._canvas.block_selected.connect(self._on_block_selected)
        self._canvas.blocks_changed.connect(self._on_blocks_changed)
        v_split.addWidget(self._canvas_area)

        self._preview = PreviewPanel()
        self._preview.tap_position_picked.connect(self._on_tap_position_picked)
        v_split.addWidget(self._preview)
        v_split.setSizes([580, 200])

        h_split.addWidget(v_split)

        # Right panel — block config (top) + devices (bottom)
        right_split = QSplitter(Qt.Orientation.Vertical)
        right_split.setChildrenCollapsible(False)

        self._block_config = BlockConfigPanel()
        self._block_config.block_updated.connect(self._on_block_param_changed)
        self._block_config.delete_button.clicked.connect(self._canvas.delete_selected)
        right_split.addWidget(self._block_config)

        self._device_panel = DevicePanel()
        self._device_panel.assign_requested.connect(self._on_assign_to_device)
        right_split.addWidget(self._device_panel)
        right_split.setSizes([360, 180])

        h_split.addWidget(right_split)
        h_split.setSizes([190, 790, 240])

        root.addWidget(h_split)

    def _build_menu(self) -> None:
        mb = self.menuBar()

        # File
        file_menu = mb.addMenu("&File")
        file_menu.addAction(_action("&New Project", "Ctrl+N", self._new_project))
        file_menu.addAction(_action("&Open Project…", "Ctrl+O", self._open_project))
        file_menu.addAction(_action("&Save Project", "Ctrl+S", self._save_project))
        file_menu.addAction(
            _action("Save Project &As…", "Ctrl+Shift+S", self._save_project_as)
        )
        file_menu.addSeparator()
        file_menu.addAction(_action("&Export Rules JSON…", "", self._export_rules))
        file_menu.addSeparator()
        file_menu.addAction(_action("&Quit", "Ctrl+Q", self.close))

        # Edit
        edit_menu = mb.addMenu("&Edit")
        edit_menu.addAction(_action("&Clear Canvas", "", self._clear_canvas))
        edit_menu.addAction(
            _action("&Delete Selected Block", "Del", self._canvas.delete_selected)
        )

        # Help
        help_menu = mb.addMenu("&Help")
        help_menu.addAction(_action("&About", "", self._show_about))

    def _build_toolbar(self) -> None:
        tb: QToolBar = self.addToolBar("Main")
        tb.setMovable(False)
        tb.setIconSize(QSize(16, 16))

        tb.addAction(_action("🆕  New", "", self._new_project))
        tb.addAction(_action("📂  Open", "", self._open_project))
        tb.addAction(_action("💾  Save", "", self._save_project))
        tb.addSeparator()
        tb.addAction(_action("📤  Export JSON", "", self._export_rules))
        tb.addSeparator()
        tb.addAction(_action("🗑  Clear Canvas", "", self._clear_canvas))
        tb.addSeparator()
        tb.addAction(_action("▶  Run on Device", "", self._run_on_device))

    def _build_status_bar(self) -> None:
        sb = QStatusBar()
        self.setStatusBar(sb)
        self._status_lbl = QLabel("Ready")
        sb.addWidget(self._status_lbl)
        self._block_count_lbl = QLabel("Blocks: 0")
        sb.addPermanentWidget(self._block_count_lbl)

    # ── Signal handlers ───────────────────────────────────────────────

    def _on_block_selected(self, block: Optional[BlockData]) -> None:
        self._selected_block = block
        self._block_config.set_block(block)
        if block:
            self._set_status(f"Selected: {block.icon}  {block.label}")
        else:
            self._set_status("Ready")

    def _on_blocks_changed(self) -> None:
        n = len(self._canvas.get_blocks())
        self._block_count_lbl.setText(f"Blocks: {n}")

    def _on_block_param_changed(self, updated: BlockData) -> None:
        self._canvas.update_block(updated)
        self._selected_block = updated

    def _on_tap_position_picked(self, x: int, y: int) -> None:
        """Forward a preview-click tap position to the selected tap block."""
        if self._selected_block and self._selected_block.subtype == "tap":
            import copy

            updated = copy.deepcopy(self._selected_block)
            updated.params["position"] = [x, y]
            self._canvas.update_block(updated)
            self._block_config.set_block(updated)
            self._selected_block = updated
            self._set_status(f"Tap position updated to ({x}, {y})")

    def _on_assign_to_device(self, serial: str) -> None:
        blocks = self._canvas.get_blocks()
        if not blocks:
            QMessageBox.warning(self, "No Blocks", "Add blocks to the canvas first.")
            return

        rules = self._compiler.compile(blocks, rule_name=f"flow_{serial[:8]}")
        preview = self._compiler.to_json(rules)
        if len(preview) > 500:
            preview = preview[:500] + "\n…"

        QMessageBox.information(
            self,
            "Script Compiled",
            f"Device: {serial}\nRules generated: {len(rules)}\n\n{preview}",
        )
        self._set_status(f"Compiled {len(rules)} rule(s) for {serial}")

    # ── File actions ──────────────────────────────────────────────────

    def _new_project(self) -> None:
        if self._canvas.get_blocks():
            reply = QMessageBox.question(
                self,
                "New Project",
                "Clear the canvas and start a new project?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                return
        self._canvas.clear_blocks()
        self._project_path = None
        self.setWindowTitle("Visual Automation Studio — New Project")
        self._set_status("New project")

    def _open_project(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Open Project",
            "",
            "Studio Projects (*.vap);;JSON Files (*.json);;All Files (*)",
        )
        if not path:
            return
        try:
            with open(path, encoding="utf-8") as fh:
                data = json.load(fh)
            blocks = [BlockData.from_dict(b) for b in data.get("blocks", [])]
            self._canvas.set_blocks(blocks)
            self._project_path = path
            self.setWindowTitle(
                f"Visual Automation Studio — {os.path.basename(path)}"
            )
            self._set_status(f"Opened {os.path.basename(path)}")
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "Open Failed", str(exc))

    def _save_project(self) -> None:
        if self._project_path:
            self._write_project(self._project_path)
        else:
            self._save_project_as()

    def _save_project_as(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Save Project As",
            "project.vap",
            "Studio Projects (*.vap);;JSON Files (*.json)",
        )
        if not path:
            return
        self._write_project(path)
        self._project_path = path
        self.setWindowTitle(
            f"Visual Automation Studio — {os.path.basename(path)}"
        )

    def _write_project(self, path: str) -> None:
        data = {"blocks": [b.to_dict() for b in self._canvas.get_blocks()]}
        try:
            with open(path, "w", encoding="utf-8") as fh:
                json.dump(data, fh, indent=2)
            self._set_status(f"Saved → {os.path.basename(path)}")
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "Save Failed", str(exc))

    def _export_rules(self) -> None:
        blocks = self._canvas.get_blocks()
        if not blocks:
            QMessageBox.warning(self, "Nothing to Export", "Add blocks first.")
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Export Rules JSON", "rules.json", "JSON Files (*.json)"
        )
        if not path:
            return
        rules = self._compiler.compile(blocks)
        try:
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(self._compiler.to_json(rules))
            self._set_status(f"Exported {len(rules)} rule(s) → {os.path.basename(path)}")
            QMessageBox.information(
                self,
                "Export Successful",
                f"Exported {len(rules)} rule(s) to:\n{path}",
            )
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "Export Failed", str(exc))

    def _clear_canvas(self) -> None:
        if not self._canvas.get_blocks():
            return
        reply = QMessageBox.question(
            self,
            "Clear Canvas",
            "Remove all blocks from the canvas?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self._canvas.clear_blocks()
            self._set_status("Canvas cleared")

    def _run_on_device(self) -> None:
        blocks = self._canvas.get_blocks()
        if not blocks:
            QMessageBox.warning(self, "Nothing to Run", "Add blocks to the canvas first.")
            return
        rules = self._compiler.compile(blocks)
        import tempfile

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False, encoding="utf-8"
        ) as tmp:
            tmp.write(self._compiler.to_json(rules))
            tmp_path = tmp.name

        self._set_status(f"Running {len(rules)} rule(s) — see console.")
        QMessageBox.information(
            self,
            "Run Automation",
            f"Rules compiled to:\n{tmp_path}\n\n"
            f"To execute:\n  python main.py --rules {tmp_path}\n\n"
            "(Requires a connected ADB device.)",
        )

    def _show_about(self) -> None:
        QMessageBox.about(
            self,
            "About Visual Automation Studio",
            "<b>Visual Automation Studio</b><br>"
            "Version 1.0.0&nbsp;&nbsp;(prototype)<br><br>"
            "A drag-and-drop rule builder for MobileVisionBot.<br><br>"
            "Drag blocks from the palette → configure their parameters<br>"
            "→ export to <tt>rules.json</tt> → run with <tt>main.py</tt>.",
        )

    # ── Helpers ───────────────────────────────────────────────────────

    def _set_status(self, text: str) -> None:
        self._status_lbl.setText(text)


# ── Module-level helpers ──────────────────────────────────────────────────

def _action(label: str, shortcut: str, callback) -> QAction:
    act = QAction(label)
    if shortcut:
        act.setShortcut(QKeySequence(shortcut))
    act.triggered.connect(callback)
    return act
