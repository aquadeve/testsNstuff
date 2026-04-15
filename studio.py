"""studio.py — entry point for the Visual Automation Studio GUI.

Launch the drag-and-drop rule builder with::

    python studio.py

The existing headless automation engine (``main.py``) is unchanged; this
script adds a visual front-end on top of the same core modules.
"""

from __future__ import annotations

import sys

from PyQt6.QtWidgets import QApplication

from ui.main_window import MainWindow


def main() -> None:
    app = QApplication(sys.argv)
    app.setApplicationName("Visual Automation Studio")
    app.setOrganizationName("MobileVisionBot")

    window = MainWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
