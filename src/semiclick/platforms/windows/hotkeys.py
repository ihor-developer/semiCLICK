from __future__ import annotations

import keyboard

from semiclick.core.models import AppSettings


class GlobalHotkeyManager:
    def __init__(self) -> None:
        self._handles: list[int] = []

    def register(
        self,
        settings: AppSettings,
        on_start,
        on_stop,
        on_panic,
        on_toggle_overlay,
    ) -> None:
        self.unregister_all()
        mappings = {
            settings.start_hotkey: on_start,
            settings.stop_hotkey: on_stop,
            settings.panic_hotkey: on_panic,
            settings.toggle_overlay_hotkey: on_toggle_overlay,
        }
        for hotkey, callback in mappings.items():
            handle = keyboard.add_hotkey(
                hotkey,
                callback,
                suppress=False,
                trigger_on_release=True,
            )
            self._handles.append(handle)

    def unregister_all(self) -> None:
        for handle in self._handles:
            keyboard.remove_hotkey(handle)
        self._handles.clear()
