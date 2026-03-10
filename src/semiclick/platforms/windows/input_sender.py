from __future__ import annotations

import time

import pydirectinput


class DirectInputSender:
    def __init__(self) -> None:
        pydirectinput.FAILSAFE = False
        pydirectinput.PAUSE = 0

    def tap_key(self, key: str, press_ms: int) -> None:
        normalized_key = key.strip().lower()
        pydirectinput.keyDown(normalized_key)
        time.sleep(press_ms / 1_000)
        pydirectinput.keyUp(normalized_key)
