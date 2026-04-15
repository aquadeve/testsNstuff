"""Block palette — left-side panel containing draggable block template tiles.

Users drag tiles from here onto the :class:`~ui.canvas.BlockCanvas` to add
blocks to their automation flow.

Each tile starts a ``QDrag`` carrying MIME type
``"application/x-block-type"`` with the block's subtype key as the payload.
The canvas reads this on drop to create a new :class:`~core.block_model.BlockData`.
"""

from __future__ import annotations

from PyQt6.QtCore import QByteArray, QMimeData, QPoint, Qt
from PyQt6.QtGui import QColor, QDrag, QFont, QLinearGradient, QPainter, QPen, QPixmap
from PyQt6.QtWidgets import (
    QFrame,
    QLabel,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from core.block_model import BLOCK_DEFINITIONS, CATEGORY_LABELS


class _DraggableBlockTile(QWidget):
    """A single colour-coded, draggable block tile shown in the palette."""

    TILE_H = 52
    TILE_W = 164

    def __init__(self, subtype: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._subtype = subtype
        self._defn = BLOCK_DEFINITIONS[subtype]
        self._pressing = False
        self._drag_start: QPoint | None = None

        self.setFixedHeight(self.TILE_H)
        self.setMinimumWidth(self.TILE_W)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        self.setToolTip(self._defn.get("description", ""))

    # ── Painting ─────────────────────────────────────────────────────

    def paintEvent(self, _event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        rect = self.rect().adjusted(4, 3, -4, -3)
        color = QColor(self._defn["color"])

        grad = QLinearGradient(rect.topLeft(), rect.bottomLeft())
        if self._pressing:
            grad.setColorAt(0, color.darker(130))
            grad.setColorAt(1, color.darker(150))
        else:
            grad.setColorAt(0, color.lighter(125))
            grad.setColorAt(1, color.darker(105))

        painter.setBrush(grad)
        painter.setPen(QPen(color.darker(140), 1))
        painter.drawRoundedRect(rect, 10, 10)

        # Icon
        painter.setPen(Qt.GlobalColor.white)
        icon_rect = rect.adjusted(8, 0, -rect.width() + 36, 0)
        painter.setFont(QFont("Segoe UI Emoji", 15))
        painter.drawText(
            icon_rect,
            Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
            self._defn.get("icon", ""),
        )

        # Label
        label_rect = rect.adjusted(40, 0, -6, 0)
        painter.setFont(QFont("Segoe UI", 9, QFont.Weight.DemiBold))
        painter.drawText(
            label_rect,
            Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
            self._defn["label"],
        )

    # ── Mouse / drag ──────────────────────────────────────────────────

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self._pressing = True
            self._drag_start = event.position().toPoint()
            self.update()

    def mouseReleaseEvent(self, _event) -> None:  # noqa: N802
        self._pressing = False
        self._drag_start = None
        self.update()

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        if (
            self._drag_start is not None
            and (event.position().toPoint() - self._drag_start).manhattanLength() > 8
        ):
            self._pressing = False
            self._drag_start = None
            self.update()
            self._start_drag()

    def _start_drag(self) -> None:
        """Begin a QDrag carrying the block's subtype key."""
        drag = QDrag(self)
        mime = QMimeData()
        mime.setData(
            "application/x-block-type", QByteArray(self._subtype.encode())
        )
        drag.setMimeData(mime)
        drag.setPixmap(_make_tile_pixmap(self._defn))
        drag.setHotSpot(QPoint(self.TILE_W // 2, self.TILE_H // 2))
        drag.exec(Qt.DropAction.CopyAction)


class BlockPalette(QWidget):
    """Left-side panel listing all block types grouped by category.

    Each block is rendered as a :class:`_DraggableBlockTile` that can be
    dragged to the :class:`~ui.canvas.BlockCanvas`.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setMinimumWidth(188)
        self.setMaximumWidth(220)
        self._build_ui()

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # Title bar
        title = QLabel("  🧱  Block Palette")
        title.setStyleSheet(
            "background:#1A1A2E; color:#E0E0FF; font:bold 12px 'Segoe UI';"
            "padding:10px 4px; border-bottom:1px solid #333;"
        )
        outer.addWidget(title)

        # Scrollable block list
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet("QScrollArea { border: none; background: #111125; }")

        content = QWidget()
        content.setStyleSheet("background: #111125;")
        layout = QVBoxLayout(content)
        layout.setContentsMargins(8, 8, 8, 12)
        layout.setSpacing(4)

        # Group tiles by category order
        for cat in ("condition", "action", "control"):
            # Section header
            header = QLabel(CATEGORY_LABELS.get(cat, cat).upper())
            header.setStyleSheet(
                "color: #555577; font: bold 9px 'Segoe UI';"
                "padding: 10px 4px 4px 4px; letter-spacing: 1px;"
            )
            layout.addWidget(header)

            # Thin separator
            line = QFrame()
            line.setFrameShape(QFrame.Shape.HLine)
            line.setStyleSheet("color: #252540; max-height: 1px;")
            layout.addWidget(line)

            # Tile for each block in this category
            for subtype, defn in BLOCK_DEFINITIONS.items():
                if defn["category"] == cat:
                    layout.addWidget(_DraggableBlockTile(subtype))

            layout.addSpacing(4)

        layout.addStretch()
        scroll.setWidget(content)
        outer.addWidget(scroll)


# ── Helpers ───────────────────────────────────────────────────────────────

def _make_tile_pixmap(defn: dict) -> QPixmap:
    """Build a semi-transparent drag ghost pixmap for *defn*."""
    w, h = _DraggableBlockTile.TILE_W, _DraggableBlockTile.TILE_H
    pix = QPixmap(w, h)
    pix.fill(Qt.GlobalColor.transparent)

    p = QPainter(pix)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    color = QColor(defn["color"])
    p.setBrush(color)
    p.setPen(Qt.PenStyle.NoPen)
    p.setOpacity(0.82)
    p.drawRoundedRect(2, 2, w - 4, h - 4, 10, 10)
    p.setOpacity(1.0)
    p.setPen(Qt.GlobalColor.white)
    p.setFont(QFont("Segoe UI Emoji", 15))
    p.drawText(8, 0, 30, h, Qt.AlignmentFlag.AlignVCenter, defn.get("icon", ""))
    p.setFont(QFont("Segoe UI", 9, QFont.Weight.DemiBold))
    p.drawText(42, 0, w - 48, h, Qt.AlignmentFlag.AlignVCenter, defn["label"])
    p.end()
    return pix
