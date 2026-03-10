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
    title: str
    class_name: str
    process_name: str


class MinecraftWindowMonitor:
    def __init__(self, match_config: WindowMatchConfig) -> None:
        self._match_config = match_config

    def update_match_config(self, match_config: WindowMatchConfig) -> None:
        self._match_config = match_config

    def is_target_focused(self) -> bool:
        info = self.get_foreground_window_info()
        if info is None:
            return False

        title_contains = self._match_config.title_contains.strip().lower()
        process_names = {name.strip().lower() for name in self._match_config.process_names}
        title_matches = bool(title_contains and title_contains in info.title.lower())
        process_matches = info.process_name.lower() in process_names
        return title_matches or process_matches

    def get_foreground_window_info(self) -> WindowInfo | None:
        hwnd = win32gui.GetForegroundWindow()
        if not hwnd:
            return None

        title = win32gui.GetWindowText(hwnd) or ""
        class_name = win32gui.GetClassName(hwnd) or ""
        process_name = self._get_process_name(hwnd)
        return WindowInfo(title=title, class_name=class_name, process_name=process_name)

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
