import unittest

from semiclick.core.models import AppSettings, KeyTapStep, MacroSequence, RunMode, WaitStep
from semiclick.core.validation import ValidationError, validate_sequence, validate_settings


class ValidationTests(unittest.TestCase):
    def test_rejects_unsupported_keys(self) -> None:
        sequence = MacroSequence(name="Bad", steps=[KeyTapStep(key="mouse1")])

        with self.assertRaises(ValidationError):
            validate_sequence(sequence)

    def test_rejects_repeat_n_without_count(self) -> None:
        sequence = MacroSequence(name="Bad", steps=[WaitStep(duration_ms=100)], run_mode=RunMode.REPEAT_N)

        with self.assertRaises(ValidationError):
            validate_sequence(sequence)

    def test_accepts_valid_sequence(self) -> None:
        sequence = MacroSequence(
            name="Good",
            steps=[KeyTapStep(key="m"), WaitStep(duration_ms=100)],
            run_mode=RunMode.REPEAT_N,
            repeat_count=3,
        )

        validate_sequence(sequence)

    def test_rejects_duplicate_hotkeys(self) -> None:
        settings = AppSettings(
            start_hotkey="ctrl+1",
            stop_hotkey="ctrl+1",
            panic_hotkey="ctrl+3",
            toggle_overlay_hotkey="ctrl+4",
        )

        with self.assertRaises(ValidationError):
            validate_settings(settings)


if __name__ == "__main__":
    unittest.main()
