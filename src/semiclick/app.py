from __future__ import annotations

import signal
import sys

from PySide6 import QtCore, QtWidgets

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

    signal.signal(signal.SIGINT, lambda *_: _request_shutdown(window, app))

    keepalive_timer = QtCore.QTimer()
    keepalive_timer.start(250)

    try:
        return app.exec()
    except KeyboardInterrupt:
        _request_shutdown(window, app)
        return 0
    finally:
        keepalive_timer.stop()


def _request_shutdown(window: MainWindow, app: QtWidgets.QApplication) -> None:
    if window.isVisible():
        window.close()
    app.quit()
