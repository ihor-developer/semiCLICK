from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import TypeAlias


LETTER_KEYS = [chr(code) for code in range(ord("a"), ord("z") + 1)]
DIGIT_KEYS = [str(number) for number in range(10)]
FUNCTION_KEYS = [f"f{number}" for number in range(1, 13)]
CONTROL_KEYS = [
    "esc",
    "tab",
    "space",
    "enter",
    "backspace",
    "left",
    "right",
    "up",
    "down",
    "shift",
    "ctrl",
    "alt",
    "home",
    "end",
    "pageup",
    "pagedown",
]

SUPPORTED_KEYS = tuple(LETTER_KEYS + DIGIT_KEYS + FUNCTION_KEYS + CONTROL_KEYS)


class RunMode(str, Enum):
    ONCE = "once"
    REPEAT_N = "repeat_n"
    REPEAT_FOREVER = "repeat_forever"


class RunnerState(str, Enum):
    IDLE = "idle"
    RUNNING = "running"
    PAUSED = "paused"
    STOPPED = "stopped"
    PANIC_STOPPED = "panic_stopped"


@dataclass(slots=True)
class KeyTapStep:
    key: str
    press_ms: int = 50
    kind: str = field(default="key_tap", init=False)


@dataclass(slots=True)
class WaitStep:
    duration_ms: int
    kind: str = field(default="wait", init=False)


MacroStep: TypeAlias = KeyTapStep | WaitStep


@dataclass(slots=True)
class WindowMatchConfig:
    title_contains: str = "Minecraft"
    process_names: list[str] = field(
        default_factory=lambda: ["javaw.exe", "Minecraft.Windows.exe"]
    )

    def to_dict(self) -> dict[str, object]:
        return {
            "title_contains": self.title_contains,
            "process_names": list(self.process_names),
        }

    @classmethod
    def from_dict(cls, data: dict[str, object] | None) -> "WindowMatchConfig":
        data = data or {}
        title_contains = str(data.get("title_contains", "Minecraft")).strip() or "Minecraft"
        raw_process_names = data.get("process_names", ["javaw.exe", "Minecraft.Windows.exe"])
        process_names = [str(name).strip() for name in raw_process_names if str(name).strip()]
        if not process_names:
            process_names = ["javaw.exe", "Minecraft.Windows.exe"]
        return cls(title_contains=title_contains, process_names=process_names)


@dataclass(slots=True)
class MacroSequence:
    name: str
    steps: list[MacroStep]
    run_mode: RunMode = RunMode.ONCE
    repeat_count: int | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "steps": [step_to_dict(step) for step in self.steps],
            "run_mode": self.run_mode.value,
            "repeat_count": self.repeat_count,
        }

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> "MacroSequence":
        steps = [step_from_dict(raw_step) for raw_step in data.get("steps", [])]
        run_mode = RunMode(str(data.get("run_mode", RunMode.ONCE.value)))
        repeat_count = data.get("repeat_count")
        repeat_number = int(repeat_count) if repeat_count is not None else None
        return cls(
            name=str(data.get("name", "My macro")).strip() or "My macro",
            steps=steps,
            run_mode=run_mode,
            repeat_count=repeat_number,
        )


@dataclass(slots=True)
class AppSettings:
    start_hotkey: str = "ctrl+shift+f5"
    stop_hotkey: str = "ctrl+shift+f6"
    panic_hotkey: str = "ctrl+shift+f7"
    toggle_overlay_hotkey: str = "ctrl+shift+f8"
    overlay_opacity: float = 0.9
    minecraft_window_match: WindowMatchConfig = field(default_factory=WindowMatchConfig)

    def to_dict(self) -> dict[str, object]:
        return {
            "start_hotkey": self.start_hotkey,
            "stop_hotkey": self.stop_hotkey,
            "panic_hotkey": self.panic_hotkey,
            "toggle_overlay_hotkey": self.toggle_overlay_hotkey,
            "overlay_opacity": self.overlay_opacity,
            "minecraft_window_match": self.minecraft_window_match.to_dict(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, object] | None) -> "AppSettings":
        data = data or {}
        return cls(
            start_hotkey=str(data.get("start_hotkey", "ctrl+shift+f5")).strip() or "ctrl+shift+f5",
            stop_hotkey=str(data.get("stop_hotkey", "ctrl+shift+f6")).strip() or "ctrl+shift+f6",
            panic_hotkey=str(data.get("panic_hotkey", "ctrl+shift+f7")).strip() or "ctrl+shift+f7",
            toggle_overlay_hotkey=str(data.get("toggle_overlay_hotkey", "ctrl+shift+f8")).strip()
            or "ctrl+shift+f8",
            overlay_opacity=float(data.get("overlay_opacity", 0.9)),
            minecraft_window_match=WindowMatchConfig.from_dict(
                data.get("minecraft_window_match") if isinstance(data, dict) else None
            ),
        )


@dataclass(slots=True)
class PersistedState:
    sequence: MacroSequence
    settings: AppSettings

    def to_dict(self) -> dict[str, object]:
        return {"sequence": self.sequence.to_dict(), "settings": self.settings.to_dict()}

    @classmethod
    def from_dict(cls, data: dict[str, object] | None) -> "PersistedState":
        data = data or {}
        raw_sequence = data.get("sequence")
        raw_settings = data.get("settings")
        sequence = (
            MacroSequence.from_dict(raw_sequence)
            if isinstance(raw_sequence, dict)
            else default_sequence()
        )
        settings = AppSettings.from_dict(raw_settings if isinstance(raw_settings, dict) else None)
        return cls(sequence=sequence, settings=settings)


def default_sequence() -> MacroSequence:
    return MacroSequence(
        name="Minecraft example",
        steps=[
            KeyTapStep(key="1"),
            KeyTapStep(key="m"),
            WaitStep(duration_ms=5_000),
            KeyTapStep(key="2"),
            KeyTapStep(key="m"),
            WaitStep(duration_ms=5_000),
        ],
        run_mode=RunMode.REPEAT_FOREVER,
        repeat_count=None,
    )


def default_state() -> PersistedState:
    return PersistedState(sequence=default_sequence(), settings=AppSettings())


def step_to_dict(step: MacroStep) -> dict[str, object]:
    if isinstance(step, KeyTapStep):
        return {"kind": step.kind, "key": step.key, "press_ms": step.press_ms}
    return {"kind": step.kind, "duration_ms": step.duration_ms}


def step_from_dict(data: dict[str, object]) -> MacroStep:
    kind = str(data.get("kind", "")).strip()
    if kind == "key_tap":
        return KeyTapStep(
            key=str(data.get("key", "")).strip().lower(),
            press_ms=int(data.get("press_ms", 50)),
        )
    if kind == "wait":
        return WaitStep(duration_ms=int(data.get("duration_ms", 1_000)))
    raise ValueError(f"Unsupported step type: {kind}")
