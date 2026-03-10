from __future__ import annotations

import sys

from PySide6 import QtWidgets

from semiclick.core.storage import JsonStorage
from semiclick.ui.main_window import MainWindow


def main() -> int:
    if sys.platform != "win32":
        raise RuntimeError("semiCLICK only supports Windows.")

    app = QtWidgets.QApplication(sys.argv)
    app.setApplicationName("semiCLICK")
    app.setQuitOnLastWindowClosed(True)

    window = MainWindow(JsonStorage())
    window.show()

    return app.exec()
