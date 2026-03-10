from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pywintypes
import win32api
import win32con
import win32gui
import win32process

from semiclick.core.models import WindowMatchConfig


@dataclass(slots=True)
class WindowInfo:
    hwnd: int
    title: str
    class_name: str
    process_name: str
    rect: tuple[int, int, int, int]


class MinecraftWindowMonitor:
    def __init__(self, match_config: WindowMatchConfig) -> None:
        self._match_config = match_config
        self._selected_hwnd: int | None = None

    def update_match_config(self, match_config: WindowMatchConfig) -> None:
        self._match_config = match_config

    def set_target_window(self, hwnd: int | None) -> None:
        self._selected_hwnd = hwnd

    def clear_target_window(self) -> None:
        self._selected_hwnd = None

    @property
    def selected_target_hwnd(self) -> int | None:
        return self._selected_hwnd

    def is_target_focused(self) -> bool:
        info = self.get_foreground_window_info()
        if info is None:
            return False
        if self._selected_hwnd is not None:
            return info.hwnd == self._selected_hwnd
        return self.matches_config(info)

    def matches_config(self, info: WindowInfo) -> bool:
        title_contains = self._match_config.title_contains.strip().lower()
        process_names = {name.strip().lower() for name in self._match_config.process_names}
        title_matches = bool(title_contains and title_contains in info.title.lower())
        process_matches = info.process_name.lower() in process_names
        return title_matches or process_matches

    def list_candidate_windows(self) -> list[WindowInfo]:
        windows: list[WindowInfo] = []

        def callback(hwnd: int, _) -> bool:
            if not self._is_candidate_window(hwnd):
                return True

            title = win32gui.GetWindowText(hwnd) or ""
            class_name = win32gui.GetClassName(hwnd) or ""
            process_name = self._get_process_name(hwnd)
            rect = win32gui.GetWindowRect(hwnd)
            windows.append(
                WindowInfo(
                    hwnd=hwnd,
                    title=title,
                    class_name=class_name,
                    process_name=process_name,
                    rect=rect,
                )
            )
            return True

        win32gui.EnumWindows(callback, None)
        windows.sort(key=lambda item: (item.process_name.lower(), item.title.lower()))
        return windows

    def find_matching_window(self) -> WindowInfo | None:
        candidates = self.list_candidate_windows()
        if self._selected_hwnd is not None:
            for info in candidates:
                if info.hwnd == self._selected_hwnd:
                    return info
        for info in candidates:
            if self.matches_config(info):
                return info
        return None

    def get_foreground_window_info(self) -> WindowInfo | None:
        hwnd = win32gui.GetForegroundWindow()
        if not hwnd:
            return None

        title = win32gui.GetWindowText(hwnd) or ""
        class_name = win32gui.GetClassName(hwnd) or ""
        process_name = self._get_process_name(hwnd)
        rect = win32gui.GetWindowRect(hwnd)
        return WindowInfo(
            hwnd=hwnd,
            title=title,
            class_name=class_name,
            process_name=process_name,
            rect=rect,
        )

    def _is_candidate_window(self, hwnd: int) -> bool:
        if not win32gui.IsWindowVisible(hwnd) or win32gui.IsIconic(hwnd):
            return False
        title = (win32gui.GetWindowText(hwnd) or "").strip()
        if not title:
            return False
        if "semiclick" in title.lower():
            return False
        left, top, right, bottom = win32gui.GetWindowRect(hwnd)
        width = max(0, right - left)
        height = max(0, bottom - top)
        return width >= 300 and height >= 200

    def _get_process_name(self, hwnd: int) -> str:
        try:
            _, process_id = win32process.GetWindowThreadProcessId(hwnd)
            if not process_id:
                return ""
            process_handle = win32api.OpenProcess(
                win32con.PROCESS_QUERY_INFORMATION | win32con.PROCESS_VM_READ,
                False,
                process_id,
            )
        except pywintypes.error:
            return ""

        try:
            executable_path = win32process.GetModuleFileNameEx(process_handle, 0)
            return Path(executable_path).name
        except pywintypes.error:
            return ""
        finally:
            win32api.CloseHandle(process_handle)
