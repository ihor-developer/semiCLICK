from __future__ import annotations

import win32con
import win32gui


class OverlayController:
    def __init__(self, hwnd_getter) -> None:
        self._hwnd_getter = hwnd_getter

    def set_click_through(self, enabled: bool) -> None:
        hwnd = int(self._hwnd_getter())
        ex_style = win32gui.GetWindowLong(hwnd, win32con.GWL_EXSTYLE)
        ex_style |= win32con.WS_EX_LAYERED
        if enabled:
            ex_style |= win32con.WS_EX_TRANSPARENT
        else:
            ex_style &= ~win32con.WS_EX_TRANSPARENT

        win32gui.SetWindowLong(hwnd, win32con.GWL_EXSTYLE, ex_style)
        win32gui.SetWindowPos(
            hwnd,
            win32con.HWND_TOPMOST,
            0,
            0,
            0,
            0,
            win32con.SWP_NOMOVE | win32con.SWP_NOSIZE | win32con.SWP_NOACTIVATE,
        )
