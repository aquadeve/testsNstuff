"""Block canvas — centre drag-and-drop workspace.

Users drop blocks from the :class:`~ui.block_palette.BlockPalette` onto this
widget to build an automation flow.  Blocks are rendered as colour-coded
rounded rectangles connected by arrow lines showing execution order.

Supported interactions
----------------------
* **Drop from palette** — creates a new block at the insertion point.
* **Click block** — selects it and emits :attr:`block_selected`.
* **Drag existing block** — picks it up, shows a ghost, re-inserts on drop.
* **Delete key** — removes the selected block.
* **Escape** — deselects.

Signals
-------
block_selected : emitted with the selected :class:`~core.block_model.BlockData`
    or ``None`` when selection is cleared.
blocks_changed : emitted whenever the block list is modified.
"""

from __future__ import annotations

import os
from typing import Dict, List, Optional

from PyQt6.QtCore import QByteArray, QMimeData, QPoint, QRect, Qt, pyqtSignal
from PyQt6.QtGui import (
    QColor,
    QDrag,
    QFont,
    QLinearGradient,
    QPainter,
    QPen,
    QPixmap,
    QPolygon,
)
from PyQt6.QtWidgets import QScrollArea, QSizePolicy, QWidget

from core.block_model import BlockData


class BlockCanvas(QWidget):
    """Custom-painted drag-and-drop block canvas.

    The canvas maintains an ordered list of :class:`~core.block_model.BlockData`
    objects, draws them with :class:`QPainter`, and handles all mouse and
    drop interactions itself.
    """

    block_selected = pyqtSignal(object)   # BlockData | None
    blocks_changed = pyqtSignal()

    # ── Layout constants ──────────────────────────────────────────────
    BLOCK_W = 296
    BLOCK_H = 90
    BLOCK_X = 52          # horizontal offset of block left edge
    SPACING = 16          # gap between block bottom and connector top
    CONNECTOR_H = 34      # height of the arrow connector zone

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._blocks: List[BlockData] = []
        self._selected_id: Optional[str] = None

        # Internal drag state
        self._drag_start: Optional[QPoint] = None
        self._drag_src_idx: Optional[int] = None
        # Cache for block data during an internal drag so params survive.
        self._drag_cache: Dict[str, BlockData] = {}

        # Drop indicator (insert-before index, or len(blocks) for append)
        self._drop_indicator: Optional[int] = None

        self.setAcceptDrops(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._refresh_size()

    # ── Geometry helpers ─────────────────────────────────────────────

    def _block_top(self, index: int) -> int:
        """Y coordinate of the top edge of block *index*."""
        return 40 + index * (self.BLOCK_H + self.CONNECTOR_H + self.SPACING)

    def _block_rect(self, index: int) -> QRect:
        return QRect(self.BLOCK_X, self._block_top(index), self.BLOCK_W, self.BLOCK_H)

    def _index_at(self, pos: QPoint) -> Optional[int]:
        for i in range(len(self._blocks)):
            if self._block_rect(i).contains(pos):
                return i
        return None

    def _insert_index_for(self, pos: QPoint) -> int:
        """Return the insertion index (0 … len) for a drop at *pos*."""
        for i in range(len(self._blocks)):
            if pos.y() < self._block_rect(i).center().y():
                return i
        return len(self._blocks)

    def _refresh_size(self) -> None:
        n = len(self._blocks)
        h = max(500, 80 + n * (self.BLOCK_H + self.CONNECTOR_H + self.SPACING) + 120)
        self.setMinimumHeight(h)

    # ── Painting ─────────────────────────────────────────────────────

    def paintEvent(self, _event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Background
        painter.fillRect(self.rect(), QColor("#0D0D1A"))

        # Dot grid
        painter.setPen(QPen(QColor("#18183A"), 1))
        for gx in range(0, self.width(), 24):
            for gy in range(0, self.height(), 24):
                painter.drawPoint(gx, gy)

        # Connectors between consecutive blocks
        for i in range(len(self._blocks) - 1):
            self._draw_connector(painter, i)

        # Blocks
        for i, block in enumerate(self._blocks):
            self._draw_block(painter, block, i)

        # Drop indicator
        if self._drop_indicator is not None:
            self._draw_drop_indicator(painter, self._drop_indicator)

        # Empty-state hint
        if not self._blocks:
            self._draw_empty_hint(painter)

    def _draw_block(self, painter: QPainter, block: BlockData, index: int) -> None:
        rect = self._block_rect(index)
        selected = block.block_id == self._selected_id

        # Drop shadow
        shadow = rect.adjusted(4, 4, 4, 4)
        painter.setBrush(QColor(0, 0, 0, 65))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(shadow, 13, 13)

        # Block gradient fill
        base = QColor(block.color) if block.enabled else QColor(55, 55, 70)
        grad = QLinearGradient(rect.topLeft(), rect.bottomLeft())
        grad.setColorAt(0.0, base.lighter(122))
        grad.setColorAt(1.0, base.darker(115))
        painter.setBrush(grad)
        if selected:
            painter.setPen(QPen(QColor("#FFFFFF"), 2.5))
        else:
            painter.setPen(QPen(base.darker(145), 1.2))
        painter.drawRoundedRect(rect, 13, 13)

        # Left accent stripe (category colour hint)
        stripe = QRect(rect.left(), rect.top() + 13, 5, rect.height() - 26)
        painter.setBrush(base.darker(170))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRect(stripe)

        # Icon
        painter.setFont(QFont("Segoe UI Emoji", 20))
        painter.setPen(QColor(255, 255, 255, 220))
        icon_r = QRect(rect.left() + 14, rect.top(), 36, rect.height())
        painter.drawText(icon_r, Qt.AlignmentFlag.AlignVCenter, block.icon)

        # Label
        painter.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
        painter.setPen(Qt.GlobalColor.white)
        label_r = QRect(rect.left() + 58, rect.top() + 6, rect.width() - 68, 28)
        painter.drawText(label_r, Qt.AlignmentFlag.AlignVCenter, block.label)

        # Params summary (second line)
        summary = _params_summary(block)
        painter.setFont(QFont("Segoe UI", 8))
        painter.setPen(QColor(255, 255, 255, 165))
        summary_r = QRect(rect.left() + 58, rect.top() + 36, rect.width() - 68, 46)
        painter.drawText(
            summary_r,
            Qt.AlignmentFlag.AlignTop | Qt.TextFlag.TextWordWrap,
            summary,
        )

        # "DISABLED" badge
        if not block.enabled:
            badge = QRect(rect.right() - 74, rect.top() + 6, 68, 18)
            painter.setBrush(QColor(0, 0, 0, 100))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRoundedRect(badge, 9, 9)
            painter.setPen(QColor(200, 200, 200))
            painter.setFont(QFont("Segoe UI", 7, QFont.Weight.Bold))
            painter.drawText(badge, Qt.AlignmentFlag.AlignCenter, "DISABLED")

    def _draw_connector(self, painter: QPainter, from_idx: int) -> None:
        """Draw a dashed line + arrowhead between block *from_idx* and the next."""
        fr = self._block_rect(from_idx)
        to_rect = self._block_rect(from_idx + 1)
        cx = fr.left() + self.BLOCK_W // 2
        y1 = fr.bottom() + 4
        y2 = to_rect.top() - 4

        painter.setPen(QPen(QColor("#3A3A60"), 2, Qt.PenStyle.DashLine))
        painter.drawLine(cx, y1, cx, y2)

        # Arrowhead
        tip = y2 + 2
        arrow = QPolygon(
            [QPoint(cx, tip), QPoint(cx - 7, tip - 12), QPoint(cx + 7, tip - 12)]
        )
        painter.setBrush(QColor("#5555A0"))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawPolygon(arrow)

    def _draw_drop_indicator(self, painter: QPainter, index: int) -> None:
        """Draw a horizontal insertion line at the *index* position."""
        if index < len(self._blocks):
            y = self._block_rect(index).top() - self.SPACING // 2 - 4
        elif self._blocks:
            y = self._block_rect(len(self._blocks) - 1).bottom() + self.SPACING // 2 + 4
        else:
            y = 60

        x0, x1 = self.BLOCK_X, self.BLOCK_X + self.BLOCK_W
        painter.setPen(QPen(QColor("#00E5FF"), 3))
        painter.drawLine(x0, y, x1, y)
        painter.setBrush(QColor("#00E5FF"))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(x0 - 5, y - 5, 10, 10)
        painter.drawEllipse(x1 - 5, y - 5, 10, 10)

    def _draw_empty_hint(self, painter: QPainter) -> None:
        painter.setPen(QColor("#2E2E50"))
        painter.setFont(QFont("Segoe UI", 13))
        painter.drawText(
            self.rect(),
            Qt.AlignmentFlag.AlignCenter,
            "✦   Drag blocks here to build your automation flow   ✦",
        )

    # ── Drop from palette (external) ─────────────────────────────────

    def dragEnterEvent(self, event) -> None:  # noqa: N802
        if event.mimeData().hasFormat("application/x-block-type"):
            event.acceptProposedAction()

    def dragMoveEvent(self, event) -> None:  # noqa: N802
        if event.mimeData().hasFormat("application/x-block-type"):
            self._drop_indicator = self._insert_index_for(event.position().toPoint())
            self.update()
            event.acceptProposedAction()

    def dragLeaveEvent(self, _event) -> None:  # noqa: N802
        self._drop_indicator = None
        self.update()

    def dropEvent(self, event) -> None:  # noqa: N802
        mime = event.mimeData()
        if not mime.hasFormat("application/x-block-type"):
            return

        subtype = mime.data("application/x-block-type").data().decode()
        is_internal = mime.hasFormat("application/x-block-internal-id")

        if is_internal:
            # Recover the full BlockData (with its existing params) from cache.
            block_id = mime.data("application/x-block-internal-id").data().decode()
            block = self._drag_cache.pop(block_id, BlockData.from_subtype(subtype))
        else:
            block = BlockData.from_subtype(subtype)

        idx = self._insert_index_for(event.position().toPoint())
        self._blocks.insert(idx, block)
        self._selected_id = block.block_id
        self._drop_indicator = None
        self._refresh_size()
        self.update()
        self.block_selected.emit(block)
        self.blocks_changed.emit()
        event.acceptProposedAction()

    # ── Mouse events (selection + internal drag) ──────────────────────

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            idx = self._index_at(event.position().toPoint())
            if idx is not None:
                self._selected_id = self._blocks[idx].block_id
                self._drag_src_idx = idx
                self._drag_start = event.position().toPoint()
                self.block_selected.emit(self._blocks[idx])
            else:
                self._selected_id = None
                self._drag_src_idx = None
                self.block_selected.emit(None)
            self.update()

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        if (
            self._drag_src_idx is not None
            and self._drag_start is not None
            and (event.position().toPoint() - self._drag_start).manhattanLength() > 10
        ):
            self._start_internal_drag(self._drag_src_idx)

    def _start_internal_drag(self, index: int) -> None:
        """Remove the block at *index*, cache it, and begin a QDrag."""
        block = self._blocks[index]

        # Cache the full BlockData so dropEvent can restore it with params.
        self._drag_cache[block.block_id] = block

        self._blocks.pop(index)
        self._drag_src_idx = None
        self._drag_start = None
        self._selected_id = None
        self._refresh_size()
        self.update()

        drag = QDrag(self)
        mime = QMimeData()
        mime.setData("application/x-block-type", QByteArray(block.subtype.encode()))
        mime.setData(
            "application/x-block-internal-id", QByteArray(block.block_id.encode())
        )
        drag.setMimeData(mime)
        drag.setPixmap(_make_drag_pixmap(block))
        drag.setHotSpot(QPoint(self.BLOCK_W // 2, self.BLOCK_H // 2))

        result = drag.exec(Qt.DropAction.MoveAction | Qt.DropAction.CopyAction)

        if result == Qt.DropAction.IgnoreAction:
            # Drag was cancelled — restore the block at its original position.
            restored = self._drag_cache.pop(block.block_id, block)
            self._blocks.insert(index, restored)
            self._selected_id = restored.block_id
            self._refresh_size()
            self.update()

        self.blocks_changed.emit()

    # ── Keyboard ──────────────────────────────────────────────────────

    def keyPressEvent(self, event) -> None:  # noqa: N802
        if event.key() == Qt.Key.Key_Delete and self._selected_id:
            self.delete_selected()
        elif event.key() == Qt.Key.Key_Escape:
            self._selected_id = None
            self.block_selected.emit(None)
            self.update()

    # ── Public API ────────────────────────────────────────────────────

    def get_blocks(self) -> List[BlockData]:
        """Return a shallow copy of the current block list."""
        return list(self._blocks)

    def set_blocks(self, blocks: List[BlockData]) -> None:
        """Replace canvas contents with *blocks*."""
        self._blocks = list(blocks)
        self._selected_id = None
        self._refresh_size()
        self.update()
        self.blocks_changed.emit()

    def clear_blocks(self) -> None:
        self.set_blocks([])

    def delete_selected(self) -> None:
        if not self._selected_id:
            return
        self._blocks = [b for b in self._blocks if b.block_id != self._selected_id]
        self._selected_id = None
        self._refresh_size()
        self.update()
        self.block_selected.emit(None)
        self.blocks_changed.emit()

    def update_block(self, block: BlockData) -> None:
        """Replace the block with the same ``block_id`` with *block*."""
        for i, b in enumerate(self._blocks):
            if b.block_id == block.block_id:
                self._blocks[i] = block
                self.update()
                self.blocks_changed.emit()
                return


# ── Module-level helpers ──────────────────────────────────────────────────

def _params_summary(block: BlockData) -> str:
    """Return a short human-readable summary of a block's parameters."""
    p = block.params
    s = block.subtype
    if s in ("image_appears", "image_not_appears"):
        img = os.path.basename(p.get("image", "")) or "(no image)"
        thr = p.get("threshold", 0.85)
        return f"Image: {img}   Threshold: {thr:.0%}"
    if s == "tap":
        pos = p.get("position", [0, 0])
        return f"Position: ({pos[0]}, {pos[1]})" if isinstance(pos, list) else f"Position: {pos}"
    if s == "wait":
        return f"Duration: {p.get('seconds', 2.0)} s"
    if s == "swipe":
        return f"From {p.get('from', [0, 0])} → To {p.get('to', [0, 0])}"
    if s == "restart_app":
        return f"Package: {p.get('package', '')}"
    if s == "color_detected":
        return f"HSV: {p.get('color_hsv', [0, 0, 0])}   Tolerance: {p.get('tolerance', 20)}"
    if s == "screen_unchanged":
        return f"Window: {p.get('window', 15.0)} s"
    if s == "loop":
        r = p.get("repeat", 0)
        return f"Repeat: {'∞ (forever)' if r == 0 else r}"
    if s == "wait_until":
        return f"Timeout: {p.get('timeout', 30.0)} s"
    return ""


def _make_drag_pixmap(block: BlockData) -> QPixmap:
    """Build a semi-transparent pixmap for the drag cursor."""
    w, h = 296, 60
    pix = QPixmap(w, h)
    pix.fill(Qt.GlobalColor.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    color = QColor(block.color)
    p.setBrush(color)
    p.setPen(Qt.PenStyle.NoPen)
    p.setOpacity(0.80)
    p.drawRoundedRect(2, 2, w - 4, h - 4, 13, 13)
    p.setOpacity(1.0)
    p.setPen(Qt.GlobalColor.white)
    p.setFont(QFont("Segoe UI Emoji", 16))
    p.drawText(10, 0, 32, h, Qt.AlignmentFlag.AlignVCenter, block.icon)
    p.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
    p.drawText(48, 0, w - 56, h, Qt.AlignmentFlag.AlignVCenter, block.label)
    p.end()
    return pix


class CanvasScrollArea(QScrollArea):
    """A :class:`QScrollArea` wrapping :class:`BlockCanvas`."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._canvas = BlockCanvas()
        self.setWidget(self._canvas)
        self.setWidgetResizable(True)
        self.setStyleSheet("QScrollArea { border: none; background: #0D0D1A; }")

    @property
    def canvas(self) -> BlockCanvas:
        return self._canvas
