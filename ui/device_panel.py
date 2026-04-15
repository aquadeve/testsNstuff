"""Device panel — right-side panel listing connected ADB devices.

In a live deployment this panel queries ``adb devices`` to populate the list.
When no ADB is available (e.g. during UI development) it falls back to a set
of demo devices so the rest of the UI can be tested without hardware.
"""

from __future__ import annotations

from typing import Dict

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


class DevicePanel(QWidget):
    """Panel listing connected ADB devices and providing run controls.

    Signals:
        assign_requested: Emitted with the device serial when the user
            clicks the Run button.
    """

    assign_requested = pyqtSignal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setMinimumWidth(180)
        self.setMaximumWidth(260)
        self._devices: Dict[str, str] = {}   # serial → status string
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Title bar
        title = QLabel("  📱  Devices")
        title.setStyleSheet(
            "background: #1A1A2E; color: #E0E0FF; font: bold 12px 'Segoe UI';"
            "padding: 10px 4px; border-bottom: 1px solid #333;"
        )
        layout.addWidget(title)

        # Device list
        self._list = QListWidget()
        self._list.setStyleSheet(
            "QListWidget { background: #0D0D1A; color: #CCC; border: none;"
            "font: 10px 'Segoe UI'; }"
            "QListWidget::item { padding: 6px 8px; border-bottom: 1px solid #1A1A2E; }"
            "QListWidget::item:selected { background: #1E1E3A; color: white; }"
        )
        layout.addWidget(self._list)

        # Action buttons
        btn_row = QWidget()
        btn_row.setStyleSheet(
            "background: #0D0D1A; border-top: 1px solid #1A1A2E;"
        )
        br = QHBoxLayout(btn_row)
        br.setContentsMargins(6, 6, 6, 6)
        br.setSpacing(4)

        self._refresh_btn = QPushButton("⟳  Refresh")
        self._refresh_btn.setStyleSheet(_btn_style())
        self._refresh_btn.clicked.connect(self._refresh_devices)

        self._run_btn = QPushButton("▶  Run")
        self._run_btn.setStyleSheet(_btn_style(accent="#1B3B1B"))
        self._run_btn.clicked.connect(self._on_run)

        br.addWidget(self._refresh_btn)
        br.addWidget(self._run_btn)
        layout.addWidget(btn_row)

    # ── Device discovery ──────────────────────────────────────────────

    def _refresh_devices(self) -> None:
        """Query ``adb devices``; fall back to demo entries on failure."""
        try:
            import subprocess

            result = subprocess.run(
                ["adb", "devices"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            lines = result.stdout.strip().splitlines()
            serials: Dict[str, str] = {}
            for line in lines[1:]:
                parts = line.strip().split()
                if len(parts) == 2 and parts[1] in ("device", "online"):
                    serials[parts[0]] = parts[1]
            self._devices = serials if serials else {"demo-device-1": "demo (no ADB)"}
        except Exception:  # noqa: BLE001
            self._devices = {"demo-device-1": "demo (no ADB)"}

        self._populate_list()

    def populate_demo(self) -> None:
        """Populate the list with placeholder demo devices."""
        self._devices = {
            "emulator-5554": "device",
            "emulator-5556": "offline",
            "192.168.1.10:5555": "device",
        }
        self._populate_list()

    def _populate_list(self) -> None:
        self._list.clear()
        for serial, status in self._devices.items():
            dot = "🟢" if status in ("device", "online") else "🔴"
            item = QListWidgetItem(f"  {dot}  {serial}\n       {status}")
            self._list.addItem(item)

    # ── Run ───────────────────────────────────────────────────────────

    def _on_run(self) -> None:
        # Use the first device if nothing is selected.
        if self._list.currentItem() is None and self._list.count() > 0:
            self._list.setCurrentRow(0)
        item = self._list.currentItem()
        if item is None:
            return
        # Extract serial from the first line of the item text.
        serial = item.text().strip().splitlines()[0]
        # Strip the status dot and whitespace.
        for ch in ("🟢", "🔴", " "):
            serial = serial.replace(ch, "")
        self.assign_requested.emit(serial.strip())


# ── Style helpers ─────────────────────────────────────────────────────────

def _btn_style(accent: str = "#1A1A2E") -> str:
    return (
        f"QPushButton {{ background: {accent}; color: #CCC; border: 1px solid #2A2A4A;"
        "border-radius: 4px; padding: 5px 8px; font: 9px 'Segoe UI'; }"
        "QPushButton:hover { background: #2A2A4A; color: white; }"
    )
