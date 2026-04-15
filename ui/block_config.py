"""Block configuration panel — right-side form for editing a block's params.

When the user selects a block on the canvas, this panel populates with the
appropriate form controls for that block type.  Every change immediately
emits :attr:`block_updated` so the canvas can refresh its summary text.
"""

from __future__ import annotations

import copy
from typing import Optional

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QDoubleSpinBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSlider,
    QSpinBox,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from core.block_model import BlockData


class BlockConfigPanel(QWidget):
    """Right-side panel that shows and edits a selected block's parameters.

    Signals:
        block_updated: Emitted with the modified :class:`~core.block_model.BlockData`
            whenever any parameter changes.
    """

    block_updated = pyqtSignal(object)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._block: Optional[BlockData] = None
        self.setMinimumWidth(200)
        self.setMaximumWidth(265)
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Title bar
        self._title = QLabel("  ⚙  Block Properties")
        self._title.setStyleSheet(
            "background: #1A1A2E; color: #E0E0FF; font: bold 12px 'Segoe UI';"
            "padding: 10px 4px; border-bottom: 1px solid #333;"
        )
        layout.addWidget(self._title)

        # Stacked widget: placeholder (0) vs. form (1)
        self._stack = QStackedWidget()
        layout.addWidget(self._stack)

        # Page 0 — no selection
        no_sel = QLabel("Click a block\nto edit its settings")
        no_sel.setAlignment(Qt.AlignmentFlag.AlignCenter)
        no_sel.setStyleSheet(
            "color: #333355; font: 12px 'Segoe UI'; background: #0D0D1A;"
        )
        self._stack.addWidget(no_sel)

        # Page 1 — scrollable form
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; background: #0D0D1A; }")
        self._form_container = QWidget()
        self._form_container.setStyleSheet("background: #0D0D1A;")
        self._form_layout = QVBoxLayout(self._form_container)
        self._form_layout.setContentsMargins(10, 10, 10, 10)
        self._form_layout.setSpacing(6)
        scroll.setWidget(self._form_container)
        self._stack.addWidget(scroll)

        # Delete button at the bottom
        self._delete_btn = QPushButton("🗑  Delete Block")
        self._delete_btn.setStyleSheet(
            "QPushButton { background: #3A0F0F; color: #EEA; border: none; padding: 8px;"
            "font: 10px 'Segoe UI'; border-top: 1px solid #2A1A1A; }"
            "QPushButton:hover { background: #5C1A1A; }"
        )
        layout.addWidget(self._delete_btn)

    # ── Public API ────────────────────────────────────────────────────

    def set_block(self, block: Optional[BlockData]) -> None:
        """Populate the form for *block*, or show the placeholder if ``None``."""
        self._block = block
        if block is None:
            self._stack.setCurrentIndex(0)
            return

        # Clear previous widgets
        while self._form_layout.count():
            item = self._form_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        # Colour header with block icon + label
        header = QLabel(f"{block.icon}  {block.label}")
        header.setStyleSheet(
            f"background: {block.color}; color: white; font: bold 13px 'Segoe UI';"
            "padding: 10px 8px; border-radius: 8px; margin-bottom: 6px;"
        )
        self._form_layout.addWidget(header)

        # Build controls specific to this block type
        self._build_form(block)
        self._form_layout.addStretch()
        self._stack.setCurrentIndex(1)

    @property
    def delete_button(self) -> QPushButton:
        return self._delete_btn

    # ── Form builder ──────────────────────────────────────────────────

    def _build_form(self, block: BlockData) -> None:
        s = block.subtype
        p = block.params

        if s in ("image_appears", "image_not_appears"):
            self._add_image_picker("Image File", "image", p.get("image", ""))
            self._add_threshold("Match Threshold", "threshold", float(p.get("threshold", 0.85)))

        elif s == "tap":
            pos = p.get("position", [540, 960])
            if isinstance(pos, list):
                self._add_coord_pair("Position (x, y)", "position", pos)
            else:
                self._add_section_label("Position")
                self._add_field_label(str(pos))

        elif s == "swipe":
            self._add_coord_pair("From (x, y)", "from", p.get("from", [0, 0]))
            self._add_coord_pair("To (x, y)", "to", p.get("to", [0, 0]))
            self._add_int_spin("Duration (ms)", "duration", int(p.get("duration", 300)), 50, 10000)

        elif s == "wait":
            self._add_float_spin("Duration (seconds)", "seconds", float(p.get("seconds", 2.0)), 0.1, 300.0)

        elif s == "restart_app":
            self._add_text_field("App Package", "package", p.get("package", ""))

        elif s == "color_detected":
            self._add_hsv("Color (H / S / V)", p.get("color_hsv", [120, 100, 100]))
            self._add_int_spin("Tolerance", "tolerance", int(p.get("tolerance", 30)), 0, 180)

        elif s == "screen_unchanged":
            self._add_float_spin("Window (seconds)", "window", float(p.get("window", 15.0)), 1.0, 300.0)

        elif s == "loop":
            self._add_int_spin("Repeat (0 = ∞)", "repeat", int(p.get("repeat", 0)), 0, 9999)

        elif s == "wait_until":
            self._add_float_spin("Timeout (seconds)", "timeout", float(p.get("timeout", 30.0)), 1.0, 600.0)

    # ── Widget factories ──────────────────────────────────────────────

    def _add_section_label(self, text: str) -> None:
        lbl = QLabel(text)
        lbl.setStyleSheet("color: #666688; font: bold 9px 'Segoe UI'; padding-top: 8px;")
        self._form_layout.addWidget(lbl)

    def _add_field_label(self, text: str) -> None:
        lbl = QLabel(text)
        lbl.setStyleSheet("color: #AAAACC; font: 10px 'Segoe UI';")
        self._form_layout.addWidget(lbl)

    def _add_separator(self) -> None:
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setStyleSheet("color: #222244; max-height: 1px; margin: 4px 0;")
        self._form_layout.addWidget(line)

    def _add_image_picker(self, label: str, key: str, current: str) -> None:
        self._add_section_label(label)
        row = QWidget()
        row.setStyleSheet("background: transparent;")
        rl = QHBoxLayout(row)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.setSpacing(4)
        field = QLineEdit(current)
        field.setPlaceholderText("path/to/image.png")
        field.setStyleSheet(_field_style())
        browse = QPushButton("Browse")
        browse.setFixedWidth(56)
        browse.setStyleSheet(_btn_style())

        def _browse() -> None:
            path, _ = QFileDialog.getOpenFileName(
                self, "Select Template Image", "", "Images (*.png *.jpg *.bmp)"
            )
            if path:
                field.setText(path)
                self._update_param(key, path)

        browse.clicked.connect(_browse)
        field.textChanged.connect(lambda t: self._update_param(key, t))
        rl.addWidget(field)
        rl.addWidget(browse)
        self._form_layout.addWidget(row)

    def _add_threshold(self, label: str, key: str, value: float) -> None:
        self._add_section_label(label)
        row = QWidget()
        row.setStyleSheet("background: transparent;")
        rl = QHBoxLayout(row)
        rl.setContentsMargins(0, 0, 0, 0)

        slider = QSlider(Qt.Orientation.Horizontal)
        slider.setRange(50, 100)
        slider.setValue(int(value * 100))
        slider.setStyleSheet(
            "QSlider::groove:horizontal { background: #222244; height: 4px; border-radius: 2px; }"
            "QSlider::handle:horizontal { background: #2196F3; width: 14px; height: 14px;"
            "margin: -5px 0; border-radius: 7px; }"
        )

        val_lbl = QLabel(f"{value:.0%}")
        val_lbl.setFixedWidth(36)
        val_lbl.setStyleSheet("color: #AACCFF; font: 10px 'Segoe UI';")

        def _on_change(v: int) -> None:
            fv = v / 100.0
            val_lbl.setText(f"{fv:.0%}")
            self._update_param(key, fv)

        slider.valueChanged.connect(_on_change)
        rl.addWidget(slider)
        rl.addWidget(val_lbl)
        self._form_layout.addWidget(row)

    def _add_coord_pair(self, label: str, key: str, coords: list) -> None:
        self._add_section_label(label)
        row = QWidget()
        row.setStyleSheet("background: transparent;")
        rl = QHBoxLayout(row)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.setSpacing(4)

        sx = QSpinBox()
        sx.setRange(0, 9999)
        sx.setValue(int(coords[0]))
        sx.setPrefix("X: ")
        sx.setStyleSheet(_spin_style())

        sy = QSpinBox()
        sy.setRange(0, 9999)
        sy.setValue(int(coords[1]))
        sy.setPrefix("Y: ")
        sy.setStyleSheet(_spin_style())

        def _on_change() -> None:
            self._update_param(key, [sx.value(), sy.value()])

        sx.valueChanged.connect(_on_change)
        sy.valueChanged.connect(_on_change)
        rl.addWidget(sx)
        rl.addWidget(sy)
        self._form_layout.addWidget(row)

    def _add_int_spin(self, label: str, key: str, value: int, mn: int, mx: int) -> None:
        self._add_section_label(label)
        spin = QSpinBox()
        spin.setRange(mn, mx)
        spin.setValue(value)
        spin.setStyleSheet(_spin_style())
        spin.valueChanged.connect(lambda v: self._update_param(key, v))
        self._form_layout.addWidget(spin)

    def _add_float_spin(
        self, label: str, key: str, value: float, mn: float, mx: float
    ) -> None:
        self._add_section_label(label)
        spin = QDoubleSpinBox()
        spin.setRange(mn, mx)
        spin.setSingleStep(0.5)
        spin.setValue(value)
        spin.setStyleSheet(_spin_style())
        spin.valueChanged.connect(lambda v: self._update_param(key, v))
        self._form_layout.addWidget(spin)

    def _add_text_field(self, label: str, key: str, value: str) -> None:
        self._add_section_label(label)
        field = QLineEdit(value)
        field.setStyleSheet(_field_style())
        field.textChanged.connect(lambda t: self._update_param(key, t))
        self._form_layout.addWidget(field)

    def _add_hsv(self, label: str, hsv: list) -> None:
        self._add_section_label(label)
        row = QWidget()
        row.setStyleSheet("background: transparent;")
        rl = QHBoxLayout(row)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.setSpacing(3)

        ranges = [(0, 179), (0, 255), (0, 255)]
        prefixes = ["H:", "S:", "V:"]
        spins = []
        for i, (pfx, rng) in enumerate(zip(prefixes, ranges)):
            sp = QSpinBox()
            sp.setPrefix(pfx)
            sp.setRange(*rng)
            sp.setValue(int(hsv[i]) if i < len(hsv) else 0)
            sp.setStyleSheet(_spin_style())
            spins.append(sp)
            rl.addWidget(sp)

        def _on_change() -> None:
            self._update_param("color_hsv", [s.value() for s in spins])

        for sp in spins:
            sp.valueChanged.connect(_on_change)
        self._form_layout.addWidget(row)

    # ── Internal ──────────────────────────────────────────────────────

    def _update_param(self, key: str, value: object) -> None:
        """Update *key* in the current block's params and emit the signal."""
        if self._block is None:
            return
        updated = copy.deepcopy(self._block)
        updated.params[key] = value
        self._block = updated
        self.block_updated.emit(updated)


# ── Shared style helpers ──────────────────────────────────────────────────

def _field_style() -> str:
    return (
        "QLineEdit { background: #1A1A2E; color: #CCCCEE; border: 1px solid #2A2A4A;"
        "border-radius: 4px; padding: 4px; font: 10px 'Segoe UI'; }"
        "QLineEdit:focus { border-color: #2196F3; }"
    )


def _spin_style() -> str:
    return (
        "QSpinBox, QDoubleSpinBox { background: #1A1A2E; color: #CCCCEE;"
        "border: 1px solid #2A2A4A; border-radius: 4px; padding: 3px;"
        "font: 10px 'Segoe UI'; }"
        "QSpinBox:focus, QDoubleSpinBox:focus { border-color: #2196F3; }"
    )


def _btn_style() -> str:
    return (
        "QPushButton { background: #222244; color: #AAAACC; border: 1px solid #2A2A4A;"
        "border-radius: 4px; padding: 4px; font: 9px 'Segoe UI'; }"
        "QPushButton:hover { background: #2A2A5A; color: white; }"
    )
