"""Preview panel — bottom panel showing a device screenshot.

When a live device is connected this panel can display a real screenshot.
In prototype mode it shows a placeholder phone frame.

Pick-tap mode
-------------
When the "📍 Pick Tap Position" button is toggled on, clicking anywhere on the
preview image emits :attr:`tap_position_picked` with the corresponding device
pixel coordinates (scaled from the displayed image size to the assumed device
resolution of 1080 × 1920).  The canvas main window then forwards those
coordinates to a selected ``tap`` block.
"""

from __future__ import annotations

from PyQt6.QtCore import Qt, QPoint, QRect, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QPainter, QPixmap
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)


class _ScreenLabel(QLabel):
    """QLabel that emits clicked pixel coordinates when in pick mode."""

    position_picked = pyqtSignal(int, int)

    def __init__(self) -> None:
        super().__init__()
        self._pick_mode = False
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setStyleSheet("background: #050512; border: none;")

    def set_pick_mode(self, enabled: bool) -> None:
        self._pick_mode = enabled
        self.setCursor(
            Qt.CursorShape.CrossCursor if enabled else Qt.CursorShape.ArrowCursor
        )

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if self._pick_mode and event.button() == Qt.MouseButton.LeftButton:
            pt = event.position().toPoint()
            self.position_picked.emit(pt.x(), pt.y())


class PreviewPanel(QWidget):
    """Bottom panel displaying a device screenshot with optional tap-position picker.

    Signals:
        tap_position_picked: Emitted with ``(device_x, device_y)`` when the
            user clicks the preview while pick mode is active.
    """

    tap_position_picked = pyqtSignal(int, int)

    # Assumed device resolution used for coordinate normalisation.
    DEVICE_W = 1080
    DEVICE_H = 1920

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._build_ui()
        self._show_placeholder()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Title / toolbar bar
        bar = QWidget()
        bar.setStyleSheet("background: #1A1A2E; border-bottom: 1px solid #2A2A4A;")
        bar_row = QHBoxLayout(bar)
        bar_row.setContentsMargins(8, 4, 8, 4)

        title = QLabel("  🔍  Device Preview")
        title.setStyleSheet("color: #E0E0FF; font: bold 11px 'Segoe UI';")
        bar_row.addWidget(title)
        bar_row.addStretch()

        self._pick_btn = QPushButton("📍 Pick Tap Position")
        self._pick_btn.setCheckable(True)
        self._pick_btn.setStyleSheet(
            "QPushButton { background: #1A2A1A; color: #9C9; border: 1px solid #2A4A2A;"
            "border-radius: 4px; padding: 4px 10px; font: 9px 'Segoe UI'; }"
            "QPushButton:checked { background: #1E4D1E; color: #5F5; }"
            "QPushButton:hover { background: #1F3F1F; }"
        )
        self._pick_btn.toggled.connect(self._toggle_pick_mode)
        bar_row.addWidget(self._pick_btn)

        layout.addWidget(bar)

        # Screenshot image label
        self._screen = _ScreenLabel()
        self._screen.position_picked.connect(self._on_raw_click)
        layout.addWidget(self._screen)

        # Status bar
        self._status = QLabel("  No device connected")
        self._status.setStyleSheet(
            "background: #0A0A18; color: #444466; font: 9px 'Segoe UI';"
            "padding: 3px 8px; border-top: 1px solid #1A1A2E;"
        )
        layout.addWidget(self._status)

    # ── Pick mode ─────────────────────────────────────────────────────

    def _toggle_pick_mode(self, checked: bool) -> None:
        self._screen.set_pick_mode(checked)
        if checked:
            self._status.setText(
                "  📍 Click the preview to set a tap position"
            )
        else:
            self._status.setText("  No device connected")

    def _on_raw_click(self, px: int, py: int) -> None:
        """Map label-space coordinates to device-space and emit signal."""
        pix = self._screen.pixmap()
        if pix is None or pix.isNull():
            return

        # Compute the rect occupied by the scaled pixmap inside the label.
        lw, lh = self._screen.width(), self._screen.height()
        pw, ph = pix.width(), pix.height()
        scale = min(lw / max(pw, 1), lh / max(ph, 1))
        dw = int(pw * scale)
        dh = int(ph * scale)
        ox = (lw - dw) // 2
        oy = (lh - dh) // 2

        # Map to device coordinates (relative to native resolution).
        dx = int((px - ox) / scale * self.DEVICE_W / max(pw, 1))
        dy = int((py - oy) / scale * self.DEVICE_H / max(ph, 1))
        dx = max(0, min(dx, self.DEVICE_W))
        dy = max(0, min(dy, self.DEVICE_H))

        # Exit pick mode and notify.
        self._pick_btn.setChecked(False)
        self._status.setText(f"  📍 Tap position set: ({dx}, {dy})")
        self.tap_position_picked.emit(dx, dy)

    # ── Screenshot update ─────────────────────────────────────────────

    def set_screenshot(self, image_data: bytes) -> None:
        """Display a screenshot from raw PNG/JPEG *image_data* bytes."""
        pix = QPixmap()
        pix.loadFromData(image_data)
        if not pix.isNull():
            self._screen.setPixmap(
                pix.scaled(
                    self._screen.size(),
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
            )
            self._status.setText("  Live screenshot")

    def set_status(self, text: str) -> None:
        self._status.setText(f"  {text}")

    # ── Placeholder ───────────────────────────────────────────────────

    def _show_placeholder(self) -> None:
        """Draw a simple phone-outline placeholder graphic."""
        w, h = 200, 340
        pix = QPixmap(w, h)
        pix.fill(Qt.GlobalColor.transparent)

        p = QPainter(pix)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Phone body
        p.setBrush(QColor("#14142A"))
        p.setPen(QColor("#2A2A4A"))
        p.drawRoundedRect(QRect(20, 10, w - 40, h - 20), 16, 16)

        # Screen bezel
        p.setBrush(QColor("#0A0A18"))
        p.setPen(QColor("#1A1A30"))
        p.drawRoundedRect(QRect(30, 40, w - 60, h - 80), 6, 6)

        # Top speaker
        p.setBrush(QColor("#222244"))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawRoundedRect(QRect(w // 2 - 20, 22, 40, 6), 3, 3)

        # Home button indicator
        p.drawEllipse(QRect(w // 2 - 10, h - 38, 20, 20))

        p.setPen(QColor("#333355"))
        p.setFont(QFont("Segoe UI", 9))
        p.drawText(
            QRect(30, 40, w - 60, h - 80),
            Qt.AlignmentFlag.AlignCenter,
            "No screenshot\navailable",
        )
        p.end()

        self._screen.setPixmap(pix)
