from __future__ import annotations

from semiclick.core.models import (
    AppSettings,
    KeyTapStep,
    MacroSequence,
    RunMode,
    SUPPORTED_KEYS,
    WaitStep,
)

MAX_WAIT_MS = 60 * 60 * 1_000
MAX_PRESS_MS = 5_000


class ValidationError(ValueError):
    """Raised when app configuration is invalid."""


def validate_sequence(sequence: MacroSequence) -> None:
    if not sequence.name.strip():
        raise ValidationError("Sequence name cannot be empty.")
    if not sequence.steps:
        raise ValidationError("Add at least one step before starting the macro.")

    if sequence.run_mode == RunMode.REPEAT_N:
        if sequence.repeat_count is None or sequence.repeat_count <= 0:
            raise ValidationError("Repeat count must be greater than zero.")

    for index, step in enumerate(sequence.steps, start=1):
        if isinstance(step, KeyTapStep):
            key = step.key.strip().lower()
            if key not in SUPPORTED_KEYS:
                raise ValidationError(f"Step {index}: '{step.key}' is not a supported key.")
            if step.press_ms <= 0 or step.press_ms > MAX_PRESS_MS:
                raise ValidationError(
                    f"Step {index}: key press duration must be between 1 and {MAX_PRESS_MS} ms."
                )
            continue

        if isinstance(step, WaitStep):
            if step.duration_ms <= 0 or step.duration_ms > MAX_WAIT_MS:
                raise ValidationError(
                    f"Step {index}: wait duration must be between 1 and {MAX_WAIT_MS} ms."
                )
            continue

        raise ValidationError(f"Step {index}: unsupported step type.")


def validate_settings(settings: AppSettings) -> None:
    hotkeys = [
        settings.start_hotkey.strip().lower(),
        settings.stop_hotkey.strip().lower(),
        settings.panic_hotkey.strip().lower(),
        settings.toggle_overlay_hotkey.strip().lower(),
    ]
    if any(not hotkey for hotkey in hotkeys):
        raise ValidationError("All hotkeys must be filled in.")
    if len(set(hotkeys)) != len(hotkeys):
        raise ValidationError("Each hotkey must be unique.")
    if settings.overlay_opacity < 0.2 or settings.overlay_opacity > 1.0:
        raise ValidationError("Overlay opacity must be between 0.20 and 1.00.")
    if not settings.minecraft_window_match.title_contains.strip():
        raise ValidationError("Minecraft window title match cannot be empty.")
    if not settings.minecraft_window_match.process_names:
        raise ValidationError("Provide at least one process name for Minecraft focus detection.")
