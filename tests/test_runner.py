import threading
import time
import unittest

from semiclick.core.models import KeyTapStep, MacroSequence, RunMode, RunnerState, WaitStep
from semiclick.core.runner import MacroRunner


class FakeInputSender:
    def __init__(self) -> None:
        self.calls: list[tuple[str, int]] = []

    def tap_key(self, key: str, press_ms: int) -> None:
        self.calls.append((key, press_ms))


class FakeWindowMonitor:
    def __init__(self, focused: bool = True) -> None:
        self.focused = focused

    def is_target_focused(self) -> bool:
        return self.focused


class RunnerTests(unittest.TestCase):
    def test_runs_steps_in_order(self) -> None:
        sender = FakeInputSender()
        monitor = FakeWindowMonitor(True)
        runner = MacroRunner(sender, monitor, wait_interval_s=0.001)
        sequence = MacroSequence(
            name="Order",
            steps=[KeyTapStep(key="1", press_ms=25), WaitStep(duration_ms=5), KeyTapStep(key="m", press_ms=25)],
            run_mode=RunMode.ONCE,
        )

        runner.start(sequence)
        runner.join(timeout=1)

        self.assertEqual(sender.calls, [("1", 25), ("m", 25)])
        self.assertEqual(runner.state, RunnerState.STOPPED)

    def test_pauses_on_focus_loss_and_resumes(self) -> None:
        sender = FakeInputSender()
        monitor = FakeWindowMonitor(True)
        states: list[RunnerState] = []
        second_key_sent = threading.Event()

        class PauseAwareSender(FakeInputSender):
            def tap_key(self, key: str, press_ms: int) -> None:
                super().tap_key(key, press_ms)
                if key == "1":
                    monitor.focused = False
                    runner.set_focus_state(False)
                    time.sleep(0.02)
                    monitor.focused = True
                    runner.set_focus_state(True)
                if key == "2":
                    second_key_sent.set()

        pause_sender = PauseAwareSender()
        runner = MacroRunner(
            pause_sender,
            monitor,
            on_state_change=states.append,
            wait_interval_s=0.001,
        )
        sequence = MacroSequence(
            name="Pause",
            steps=[KeyTapStep(key="1"), WaitStep(duration_ms=10), KeyTapStep(key="2")],
            run_mode=RunMode.ONCE,
        )

        runner.start(sequence)
        second_key_sent.wait(timeout=1)
        runner.join(timeout=1)

        self.assertIn(RunnerState.PAUSED, states)
        self.assertIn(RunnerState.RUNNING, states)
        self.assertEqual(pause_sender.calls[-1][0], "2")

    def test_panic_stop_interrupts_infinite_loop(self) -> None:
        sender = FakeInputSender()
        monitor = FakeWindowMonitor(True)
        runner = MacroRunner(sender, monitor, wait_interval_s=0.001)
        sequence = MacroSequence(
            name="Loop",
            steps=[KeyTapStep(key="m"), WaitStep(duration_ms=20)],
            run_mode=RunMode.REPEAT_FOREVER,
        )

        runner.start(sequence)
        time.sleep(0.03)
        runner.panic_stop()
        runner.join(timeout=1)

        self.assertEqual(runner.state, RunnerState.PANIC_STOPPED)
        self.assertGreaterEqual(len(sender.calls), 1)


if __name__ == "__main__":
    unittest.main()
