import tempfile
import unittest
from pathlib import Path

from semiclick.core.models import KeyTapStep, MacroSequence, PersistedState, RunMode, WaitStep
from semiclick.core.storage import JsonStorage


class StorageTests(unittest.TestCase):
    def test_save_and_load_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            storage = JsonStorage(Path(temp_dir) / "state.json")
            state = PersistedState(
                sequence=MacroSequence(
                    name="Round trip",
                    steps=[KeyTapStep(key="1"), WaitStep(duration_ms=250)],
                    run_mode=RunMode.REPEAT_N,
                    repeat_count=2,
                ),
                settings=storage.load().settings,
            )

            storage.save(state)
            restored = storage.load()

        self.assertEqual(restored.sequence.name, "Round trip")
        self.assertEqual(restored.sequence.run_mode, RunMode.REPEAT_N)
        self.assertEqual(restored.sequence.repeat_count, 2)
        self.assertEqual(len(restored.sequence.steps), 2)


if __name__ == "__main__":
    unittest.main()
