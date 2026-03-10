from __future__ import annotations

import threading
import time
from collections.abc import Callable
from typing import Protocol

from semiclick.core.models import (
    KeyTapStep,
    MacroSequence,
    RunMode,
    RunnerState,
    WaitStep,
)
from semiclick.core.validation import validate_sequence


class InputSender(Protocol):
    def tap_key(self, key: str, press_ms: int) -> None: ...


class WindowMonitor(Protocol):
    def is_target_focused(self) -> bool: ...


class MacroRunner:
    def __init__(
        self,
        input_sender: InputSender,
        window_monitor: WindowMonitor | None = None,
        on_state_change: Callable[[RunnerState], None] | None = None,
        on_error: Callable[[str], None] | None = None,
        wait_interval_s: float = 0.05,
    ) -> None:
        self._input_sender = input_sender
        self._window_monitor = window_monitor
        self._on_state_change = on_state_change
        self._on_error = on_error
        self._wait_interval_s = wait_interval_s

        self._state = RunnerState.IDLE
        self._focus_allowed = True
        self._thread: threading.Thread | None = None
        self._lock = threading.RLock()
        self._stop_event = threading.Event()
        self._panic_event = threading.Event()

    @property
    def state(self) -> RunnerState:
        with self._lock:
            return self._state

    def start(self, sequence: MacroSequence) -> None:
        validate_sequence(sequence)
        with self._lock:
            if self._thread and self._thread.is_alive():
                raise RuntimeError("A macro is already running.")
            self._stop_event.clear()
            self._panic_event.clear()
            if self._window_monitor is not None:
                self._focus_allowed = self._window_monitor.is_target_focused()
            self._set_state(
                RunnerState.RUNNING if self._focus_allowed else RunnerState.PAUSED
            )
            self._thread = threading.Thread(
                target=self._run_sequence,
                args=(sequence,),
                name="macro-runner",
                daemon=True,
            )
            self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self.state != RunnerState.PANIC_STOPPED:
            self._set_state(RunnerState.STOPPED)

    def panic_stop(self) -> None:
        self._panic_event.set()
        self._stop_event.set()
        self._set_state(RunnerState.PANIC_STOPPED)

    def set_focus_state(self, focused: bool) -> None:
        with self._lock:
            self._focus_allowed = focused
            if not self._thread or not self._thread.is_alive():
                return
            if focused and self._state == RunnerState.PAUSED:
                self._set_state(RunnerState.RUNNING)
            elif not focused and self._state == RunnerState.RUNNING:
                self._set_state(RunnerState.PAUSED)

    def join(self, timeout: float | None = None) -> None:
        thread = self._thread
        if thread is not None:
            thread.join(timeout=timeout)

    def _run_sequence(self, sequence: MacroSequence) -> None:
        remaining_loops = self._loop_count(sequence)
        try:
            while remaining_loops is None or remaining_loops > 0:
                if not self._wait_for_focus_and_stop():
                    return

                for step in sequence.steps:
                    if isinstance(step, KeyTapStep):
                        if not self._wait_for_focus_and_stop():
                            return
                        self._input_sender.tap_key(step.key, step.press_ms)
                    elif isinstance(step, WaitStep):
                        if not self._wait_duration(step.duration_ms / 1_000):
                            return

                if remaining_loops is not None:
                    remaining_loops -= 1
        except Exception as exc:
            self._emit_error(str(exc))
            self._set_state(RunnerState.STOPPED)
            return

        if self.state != RunnerState.PANIC_STOPPED:
            self._set_state(RunnerState.STOPPED)

    def _wait_for_focus_and_stop(self) -> bool:
        while True:
            if self._panic_event.is_set():
                self._set_state(RunnerState.PANIC_STOPPED)
                return False
            if self._stop_event.is_set():
                if self.state != RunnerState.PANIC_STOPPED:
                    self._set_state(RunnerState.STOPPED)
                return False
            if self._window_monitor is not None:
                self.set_focus_state(self._window_monitor.is_target_focused())
            if self._focus_allowed:
                return True
            self._set_state(RunnerState.PAUSED)
            time.sleep(self._wait_interval_s)

    def _wait_duration(self, duration_s: float) -> bool:
        deadline = time.monotonic() + duration_s
        while time.monotonic() < deadline:
            if not self._wait_for_focus_and_stop():
                return False
            time.sleep(min(self._wait_interval_s, max(0.0, deadline - time.monotonic())))
        return True

    def _loop_count(self, sequence: MacroSequence) -> int | None:
        if sequence.run_mode == RunMode.REPEAT_FOREVER:
            return None
        if sequence.run_mode == RunMode.REPEAT_N:
            return sequence.repeat_count or 0
        return 1

    def _set_state(self, state: RunnerState) -> None:
        with self._lock:
            if self._state == state:
                return
            self._state = state
        if self._on_state_change is not None:
            self._on_state_change(state)

    def _emit_error(self, message: str) -> None:
        if self._on_error is not None:
            self._on_error(message)
