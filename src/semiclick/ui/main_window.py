from __future__ import annotations

from dataclasses import replace

from PySide6 import QtCore, QtGui, QtWidgets

from semiclick.core.models import (
    AppSettings,
    KeyTapStep,
    MacroSequence,
    PersistedState,
    RunMode,
    RunnerState,
    SUPPORTED_KEYS,
    WaitStep,
    WindowMatchConfig,
    coerce_run_mode,
)
from semiclick.core.runner import MacroRunner
from semiclick.core.storage import JsonStorage
from semiclick.core.validation import ValidationError, validate_sequence, validate_settings
from semiclick.platforms.windows.hotkeys import GlobalHotkeyManager
from semiclick.platforms.windows.input_sender import DirectInputSender
from semiclick.platforms.windows.overlay import OverlayController
from semiclick.platforms.windows.window_monitor import MinecraftWindowMonitor


class StepDialog(QtWidgets.QDialog):
    def __init__(self, parent: QtWidgets.QWidget, step=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Step")
        self.setModal(True)
        self.resize(320, 170)

        layout = QtWidgets.QVBoxLayout(self)
        form = QtWidgets.QFormLayout()
        layout.addLayout(form)

        self.step_type_combo = QtWidgets.QComboBox()
        self.step_type_combo.addItem("Key tap", "key_tap")
        self.step_type_combo.addItem("Wait", "wait")
        form.addRow("Type", self.step_type_combo)

        self.stack = QtWidgets.QStackedWidget()
        layout.addWidget(self.stack)

        key_page = QtWidgets.QWidget()
        key_form = QtWidgets.QFormLayout(key_page)
        self.key_combo = QtWidgets.QComboBox()
        for key in SUPPORTED_KEYS:
            label = key.upper() if len(key) == 1 and key.isalpha() else key
            self.key_combo.addItem(label, key)
        self.press_spin = QtWidgets.QSpinBox()
        self.press_spin.setRange(1, 5_000)
        self.press_spin.setSuffix(" ms")
        self.press_spin.setValue(50)
        key_form.addRow("Key", self.key_combo)
        key_form.addRow("Press time", self.press_spin)
        self.stack.addWidget(key_page)

        wait_page = QtWidgets.QWidget()
        wait_form = QtWidgets.QFormLayout(wait_page)
        self.wait_spin = QtWidgets.QDoubleSpinBox()
        self.wait_spin.setRange(0.1, 3_600.0)
        self.wait_spin.setDecimals(2)
        self.wait_spin.setSingleStep(0.25)
        self.wait_spin.setSuffix(" s")
        self.wait_spin.setValue(5.0)
        wait_form.addRow("Duration", self.wait_spin)
        self.stack.addWidget(wait_page)

        buttons = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.StandardButton.Ok
            | QtWidgets.QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self.step_type_combo.currentIndexChanged.connect(self.stack.setCurrentIndex)

        if isinstance(step, KeyTapStep):
            self.step_type_combo.setCurrentIndex(0)
            self.key_combo.setCurrentIndex(max(0, self.key_combo.findData(step.key.lower())))
            self.press_spin.setValue(step.press_ms)
        elif isinstance(step, WaitStep):
            self.step_type_combo.setCurrentIndex(1)
            self.wait_spin.setValue(step.duration_ms / 1_000)

    def selected_step(self):
        kind = self.step_type_combo.currentData()
        if kind == "key_tap":
            return KeyTapStep(
                key=str(self.key_combo.currentData()),
                press_ms=self.press_spin.value(),
            )
        return WaitStep(duration_ms=int(self.wait_spin.value() * 1_000))


class UiBridge(QtCore.QObject):
    runner_state_changed = QtCore.Signal(str)
    runner_error = QtCore.Signal(str)
    hotkey_start = QtCore.Signal()
    hotkey_stop = QtCore.Signal()
    hotkey_panic = QtCore.Signal()
    hotkey_toggle_interaction = QtCore.Signal()


class MainWindow(QtWidgets.QWidget):
    def __init__(self, storage: JsonStorage) -> None:
        super().__init__()
        self._storage = storage
        self._persisted_state = self._storage.load()
        self._sequence = self._persisted_state.sequence
        self._settings = self._persisted_state.settings
        self._interactive_mode = True
        self._drag_origin: QtCore.QPoint | None = None
        self._runner_state = RunnerState.IDLE
        self._current_focus = False

        self._bridge = UiBridge()
        self._bridge.runner_state_changed.connect(self._on_runner_state_changed)
        self._bridge.runner_error.connect(self._on_runner_error)
        self._bridge.hotkey_start.connect(self.start_macro)
        self._bridge.hotkey_stop.connect(self.stop_macro)
        self._bridge.hotkey_panic.connect(self.panic_macro)
        self._bridge.hotkey_toggle_interaction.connect(self.toggle_interaction_mode)

        self._window_monitor = MinecraftWindowMonitor(self._settings.minecraft_window_match)
        self._input_sender = DirectInputSender()
        self._runner = MacroRunner(
            input_sender=self._input_sender,
            window_monitor=self._window_monitor,
            on_state_change=lambda state: self._bridge.runner_state_changed.emit(state.value),
            on_error=self._bridge.runner_error.emit,
        )
        self._hotkeys = GlobalHotkeyManager()
        self._overlay_controller = OverlayController(self.winId)

        self._build_window()
        self._populate_from_state()
        try:
            self._register_hotkeys()
        except Exception as exc:
            self._set_message(f"Hotkeys unavailable: {exc}")

        self._focus_timer = QtCore.QTimer(self)
        self._focus_timer.setInterval(250)
        self._focus_timer.timeout.connect(self._poll_focus_state)
        self._focus_timer.start()

        self._update_runner_status(RunnerState.IDLE)
        self._poll_focus_state()

    def _build_window(self) -> None:
        self.setWindowTitle("semiCLICK")
        self.setWindowFlags(
            QtCore.Qt.WindowType.Tool
            | QtCore.Qt.WindowType.FramelessWindowHint
            | QtCore.Qt.WindowType.WindowStaysOnTopHint
        )
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setMinimumSize(820, 620)
        self.move(90, 90)

        root_layout = QtWidgets.QVBoxLayout(self)
        root_layout.setContentsMargins(12, 12, 12, 12)

        self.chrome = QtWidgets.QFrame()
        self.chrome.setObjectName("chrome")
        chrome_layout = QtWidgets.QVBoxLayout(self.chrome)
        chrome_layout.setContentsMargins(18, 18, 18, 18)
        chrome_layout.setSpacing(14)
        root_layout.addWidget(self.chrome)

        header_layout = QtWidgets.QHBoxLayout()
        chrome_layout.addLayout(header_layout)

        title_block = QtWidgets.QVBoxLayout()
        header_layout.addLayout(title_block, stretch=1)

        title = QtWidgets.QLabel("semiCLICK")
        title.setObjectName("title")
        title_block.addWidget(title)

        self.subtitle_label = QtWidgets.QLabel("Always-visible Minecraft macro overlay")
        self.subtitle_label.setObjectName("subtitle")
        title_block.addWidget(self.subtitle_label)

        self.mode_button = QtWidgets.QPushButton()
        self.mode_button.clicked.connect(self.toggle_interaction_mode)
        header_layout.addWidget(self.mode_button)

        close_button = QtWidgets.QPushButton("Close")
        close_button.clicked.connect(self.close)
        header_layout.addWidget(close_button)

        status_layout = QtWidgets.QHBoxLayout()
        chrome_layout.addLayout(status_layout)
        self.state_chip = QtWidgets.QLabel()
        self.focus_chip = QtWidgets.QLabel()
        self.hotkey_chip = QtWidgets.QLabel()
        for widget in (self.state_chip, self.focus_chip, self.hotkey_chip):
            widget.setObjectName("chip")
            status_layout.addWidget(widget)
        status_layout.addStretch(1)

        content_layout = QtWidgets.QHBoxLayout()
        content_layout.setSpacing(14)
        chrome_layout.addLayout(content_layout, stretch=1)

        left_panel = QtWidgets.QVBoxLayout()
        left_panel.setSpacing(10)
        content_layout.addLayout(left_panel, stretch=2)

        step_card = self._build_card("Sequence")
        left_panel.addWidget(step_card)
        step_layout = step_card.layout()

        self.sequence_name_edit = QtWidgets.QLineEdit()
        self.sequence_name_edit.setPlaceholderText("Sequence name")
        self.sequence_name_edit.editingFinished.connect(self._update_sequence_name)
        step_layout.addWidget(self.sequence_name_edit)

        self.step_table = QtWidgets.QTableWidget(0, 3)
        self.step_table.setHorizontalHeaderLabels(["#", "Action", "Details"])
        self.step_table.horizontalHeader().setStretchLastSection(True)
        self.step_table.horizontalHeader().setSectionResizeMode(0, QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
        self.step_table.horizontalHeader().setSectionResizeMode(1, QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
        self.step_table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows)
        self.step_table.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.SingleSelection)
        self.step_table.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
        self.step_table.itemDoubleClicked.connect(lambda _: self.edit_step())
        step_layout.addWidget(self.step_table)

        step_actions = QtWidgets.QHBoxLayout()
        step_layout.addLayout(step_actions)
        self.add_key_button = QtWidgets.QPushButton("Add key")
        self.add_wait_button = QtWidgets.QPushButton("Add wait")
        self.edit_step_button = QtWidgets.QPushButton("Edit")
        self.remove_step_button = QtWidgets.QPushButton("Remove")
        self.move_up_button = QtWidgets.QPushButton("Up")
        self.move_down_button = QtWidgets.QPushButton("Down")
        for button in (
            self.add_key_button,
            self.add_wait_button,
            self.edit_step_button,
            self.remove_step_button,
            self.move_up_button,
            self.move_down_button,
        ):
            step_actions.addWidget(button)

        self.add_key_button.clicked.connect(self.add_key_step)
        self.add_wait_button.clicked.connect(self.add_wait_step)
        self.edit_step_button.clicked.connect(self.edit_step)
        self.remove_step_button.clicked.connect(self.remove_step)
        self.move_up_button.clicked.connect(lambda: self.move_step(-1))
        self.move_down_button.clicked.connect(lambda: self.move_step(1))

        right_panel = QtWidgets.QVBoxLayout()
        right_panel.setSpacing(10)
        content_layout.addLayout(right_panel, stretch=1)

        run_card = self._build_card("Run")
        run_layout = run_card.layout()
        right_panel.addWidget(run_card)

        run_form = QtWidgets.QFormLayout()
        run_layout.addLayout(run_form)

        self.run_mode_combo = QtWidgets.QComboBox()
        self.run_mode_combo.addItem("Run once", RunMode.ONCE.value)
        self.run_mode_combo.addItem("Repeat N times", RunMode.REPEAT_N.value)
        self.run_mode_combo.addItem("Repeat forever", RunMode.REPEAT_FOREVER.value)
        self.run_mode_combo.currentIndexChanged.connect(self._on_run_mode_changed)
        run_form.addRow("Mode", self.run_mode_combo)

        self.repeat_count_spin = QtWidgets.QSpinBox()
        self.repeat_count_spin.setRange(1, 10_000)
        self.repeat_count_spin.setValue(2)
        self.repeat_count_spin.valueChanged.connect(self._update_sequence_run_mode)
        run_form.addRow("Repeat count", self.repeat_count_spin)

        run_buttons = QtWidgets.QHBoxLayout()
        run_layout.addLayout(run_buttons)
        self.start_button = QtWidgets.QPushButton("Start")
        self.stop_button = QtWidgets.QPushButton("Stop")
        self.panic_button = QtWidgets.QPushButton("Panic stop")
        run_buttons.addWidget(self.start_button)
        run_buttons.addWidget(self.stop_button)
        run_buttons.addWidget(self.panic_button)

        self.start_button.clicked.connect(self.start_macro)
        self.stop_button.clicked.connect(self.stop_macro)
        self.panic_button.clicked.connect(self.panic_macro)

        settings_card = self._build_card("Settings")
        right_panel.addWidget(settings_card)
        settings_layout = settings_card.layout()

        settings_form = QtWidgets.QFormLayout()
        settings_layout.addLayout(settings_form)

        self.start_hotkey_edit = QtWidgets.QLineEdit()
        self.stop_hotkey_edit = QtWidgets.QLineEdit()
        self.panic_hotkey_edit = QtWidgets.QLineEdit()
        self.toggle_hotkey_edit = QtWidgets.QLineEdit()
        self.opacity_spin = QtWidgets.QDoubleSpinBox()
        self.opacity_spin.setRange(0.2, 1.0)
        self.opacity_spin.setSingleStep(0.05)
        self.opacity_spin.setDecimals(2)
        self.title_match_edit = QtWidgets.QLineEdit()
        self.process_names_edit = QtWidgets.QLineEdit()

        settings_form.addRow("Start hotkey", self.start_hotkey_edit)
        settings_form.addRow("Stop hotkey", self.stop_hotkey_edit)
        settings_form.addRow("Panic hotkey", self.panic_hotkey_edit)
        settings_form.addRow("Overlay toggle", self.toggle_hotkey_edit)
        settings_form.addRow("Opacity", self.opacity_spin)
        settings_form.addRow("Window title", self.title_match_edit)
        settings_form.addRow("Process names", self.process_names_edit)

        help_label = QtWidgets.QLabel(
            "Edit the overlay only after pressing Esc in Minecraft. "
            "Switch to gameplay mode to make the overlay ignore mouse clicks."
        )
        help_label.setWordWrap(True)
        help_label.setObjectName("help")
        settings_layout.addWidget(help_label)

        self.apply_settings_button = QtWidgets.QPushButton("Apply settings")
        self.apply_settings_button.clicked.connect(self.apply_settings)
        settings_layout.addWidget(self.apply_settings_button)

        self.message_label = QtWidgets.QLabel()
        self.message_label.setObjectName("message")
        self.message_label.setWordWrap(True)
        chrome_layout.addWidget(self.message_label)

        self.setStyleSheet(
            """
            QWidget {
                color: #f3f2ed;
                font-size: 13px;
            }
            QFrame#chrome {
                background: rgba(18, 22, 31, 232);
                border: 1px solid rgba(255, 255, 255, 28);
                border-radius: 18px;
            }
            QLabel#title {
                font-size: 26px;
                font-weight: 700;
                color: #fcfbf8;
            }
            QLabel#subtitle {
                color: #b8c1d1;
            }
            QLabel#chip {
                background: rgba(255, 255, 255, 18);
                border-radius: 11px;
                padding: 6px 10px;
                color: #e6ebf6;
            }
            QLabel#help, QLabel#message {
                color: #cfd6e2;
            }
            QPushButton {
                background: #2e8b57;
                border: none;
                border-radius: 10px;
                padding: 8px 14px;
                color: #ffffff;
                font-weight: 600;
            }
            QPushButton:hover {
                background: #349b62;
            }
            QPushButton:disabled {
                background: #4c5563;
                color: #d5dbe7;
            }
            QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QTableWidget {
                background: rgba(255, 255, 255, 12);
                border: 1px solid rgba(255, 255, 255, 22);
                border-radius: 10px;
                padding: 6px 8px;
            }
            QHeaderView::section {
                background: rgba(255, 255, 255, 10);
                padding: 6px;
                border: none;
                color: #eff3fb;
            }
            QTableWidget {
                gridline-color: rgba(255, 255, 255, 16);
            }
            """
        )

    def _build_card(self, title: str) -> QtWidgets.QFrame:
        card = QtWidgets.QFrame()
        card.setStyleSheet(
            "QFrame { background: rgba(255, 255, 255, 10); border-radius: 16px; padding: 6px; }"
        )
        layout = QtWidgets.QVBoxLayout(card)
        layout.setSpacing(10)
        label = QtWidgets.QLabel(title)
        label.setStyleSheet("font-size: 16px; font-weight: 700;")
        layout.addWidget(label)
        return card

    def _populate_from_state(self) -> None:
        self.sequence_name_edit.setText(self._sequence.name)
        self._refresh_steps()

        run_mode_index = self.run_mode_combo.findData(self._sequence.run_mode.value)
        self.run_mode_combo.setCurrentIndex(max(0, run_mode_index))
        self.repeat_count_spin.setValue(self._sequence.repeat_count or 2)
        self._toggle_repeat_count_visibility()

        self.start_hotkey_edit.setText(self._settings.start_hotkey)
        self.stop_hotkey_edit.setText(self._settings.stop_hotkey)
        self.panic_hotkey_edit.setText(self._settings.panic_hotkey)
        self.toggle_hotkey_edit.setText(self._settings.toggle_overlay_hotkey)
        self.opacity_spin.setValue(self._settings.overlay_opacity)
        self.title_match_edit.setText(self._settings.minecraft_window_match.title_contains)
        self.process_names_edit.setText(
            ", ".join(self._settings.minecraft_window_match.process_names)
        )
        self.setWindowOpacity(self._settings.overlay_opacity)
        self._update_hotkey_summary()
        self._update_interaction_ui()
        self._set_message("Ready.")

    def showEvent(self, event: QtGui.QShowEvent) -> None:
        super().showEvent(event)
        self._overlay_controller.set_click_through(False)

    def mousePressEvent(self, event: QtGui.QMouseEvent) -> None:
        if event.button() == QtCore.Qt.MouseButton.LeftButton:
            self._drag_origin = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QtGui.QMouseEvent) -> None:
        if self._drag_origin is not None and event.buttons() & QtCore.Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_origin)
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QtGui.QMouseEvent) -> None:
        self._drag_origin = None
        super().mouseReleaseEvent(event)

    def closeEvent(self, event: QtGui.QCloseEvent) -> None:
        self._focus_timer.stop()
        self._hotkeys.unregister_all()
        if self._runner.state in {RunnerState.RUNNING, RunnerState.PAUSED}:
            self._runner.stop()
            self._runner.join(timeout=1)
        super().closeEvent(event)

    def add_key_step(self) -> None:
        dialog = StepDialog(self, KeyTapStep(key="m", press_ms=50))
        if dialog.exec() == QtWidgets.QDialog.DialogCode.Accepted:
            self._sequence.steps.append(dialog.selected_step())
            self._refresh_steps()
            self._persist_state()

    def add_wait_step(self) -> None:
        dialog = StepDialog(self, WaitStep(duration_ms=5_000))
        if dialog.exec() == QtWidgets.QDialog.DialogCode.Accepted:
            self._sequence.steps.append(dialog.selected_step())
            self._refresh_steps()
            self._persist_state()

    def edit_step(self) -> None:
        row = self._selected_row()
        if row is None:
            return
        dialog = StepDialog(self, self._sequence.steps[row])
        if dialog.exec() == QtWidgets.QDialog.DialogCode.Accepted:
            self._sequence.steps[row] = dialog.selected_step()
            self._refresh_steps()
            self.step_table.selectRow(row)
            self._persist_state()

    def remove_step(self) -> None:
        row = self._selected_row()
        if row is None:
            return
        self._sequence.steps.pop(row)
        self._refresh_steps()
        self._persist_state()

    def move_step(self, direction: int) -> None:
        row = self._selected_row()
        if row is None:
            return
        target_row = row + direction
        if target_row < 0 or target_row >= len(self._sequence.steps):
            return
        self._sequence.steps[row], self._sequence.steps[target_row] = (
            self._sequence.steps[target_row],
            self._sequence.steps[row],
        )
        self._refresh_steps()
        self.step_table.selectRow(target_row)
        self._persist_state()

    def apply_settings(self) -> None:
        try:
            settings = self._collect_settings()
            validate_settings(settings)
            self._settings = settings
            self._window_monitor.update_match_config(settings.minecraft_window_match)
            self.setWindowOpacity(settings.overlay_opacity)
            self._register_hotkeys()
            self._persist_state()
            self._update_hotkey_summary()
            self._set_message("Settings applied.")
        except ValidationError as exc:
            self._show_warning(str(exc))
        except Exception as exc:
            self._show_warning(f"Could not apply settings: {exc}")

    def start_macro(self) -> None:
        try:
            self._sequence = replace(
                self._sequence,
                name=self.sequence_name_edit.text().strip() or self._sequence.name,
                run_mode=coerce_run_mode(self.run_mode_combo.currentData()),
                repeat_count=self.repeat_count_spin.value()
                if coerce_run_mode(self.run_mode_combo.currentData()) == RunMode.REPEAT_N
                else None,
            )
            validate_sequence(self._sequence)
            self._persist_state()
            self._runner.start(self._sequence)
            self._set_message("Macro started.")
        except (ValidationError, RuntimeError) as exc:
            self._show_warning(str(exc))

    def stop_macro(self) -> None:
        self._runner.stop()
        self._set_message("Macro stopped.")

    def panic_macro(self) -> None:
        self._runner.panic_stop()
        self._set_message("Panic stop sent.")

    def toggle_interaction_mode(self) -> None:
        self._interactive_mode = not self._interactive_mode
        self._overlay_controller.set_click_through(not self._interactive_mode)
        self._update_interaction_ui()
        if self._interactive_mode:
            self.raise_()
            self.activateWindow()

    def _register_hotkeys(self) -> None:
        self._hotkeys.register(
            self._settings,
            self._bridge.hotkey_start.emit,
            self._bridge.hotkey_stop.emit,
            self._bridge.hotkey_panic.emit,
            self._bridge.hotkey_toggle_interaction.emit,
        )

    def _refresh_steps(self) -> None:
        self.step_table.setRowCount(len(self._sequence.steps))
        for index, step in enumerate(self._sequence.steps):
            self.step_table.setItem(index, 0, QtWidgets.QTableWidgetItem(str(index + 1)))
            if isinstance(step, KeyTapStep):
                action = "Key tap"
                key_label = step.key.upper() if len(step.key) == 1 else step.key
                details = f"{key_label} for {step.press_ms} ms"
            else:
                action = "Wait"
                details = f"{step.duration_ms / 1_000:.2f} s"
            self.step_table.setItem(index, 1, QtWidgets.QTableWidgetItem(action))
            self.step_table.setItem(index, 2, QtWidgets.QTableWidgetItem(details))
        self.step_table.resizeRowsToContents()

    def _selected_row(self) -> int | None:
        selected = self.step_table.selectionModel().selectedRows()
        if not selected:
            return None
        return selected[0].row()

    def _collect_settings(self) -> AppSettings:
        process_names = [
            name.strip()
            for name in self.process_names_edit.text().split(",")
            if name.strip()
        ]
        return AppSettings(
            start_hotkey=self.start_hotkey_edit.text().strip().lower(),
            stop_hotkey=self.stop_hotkey_edit.text().strip().lower(),
            panic_hotkey=self.panic_hotkey_edit.text().strip().lower(),
            toggle_overlay_hotkey=self.toggle_hotkey_edit.text().strip().lower(),
            overlay_opacity=self.opacity_spin.value(),
            minecraft_window_match=WindowMatchConfig(
                title_contains=self.title_match_edit.text().strip(),
                process_names=process_names,
            ),
        )

    def _persist_state(self) -> None:
        state = PersistedState(sequence=self._sequence, settings=self._settings)
        self._storage.save(state)

    def _poll_focus_state(self) -> None:
        try:
            focused = self._window_monitor.is_target_focused()
        except Exception as exc:
            self.focus_chip.setText("Focus check unavailable")
            self._set_message(f"Focus detection error: {exc}")
            return

        self._current_focus = focused
        self._runner.set_focus_state(focused)
        focus_text = "Minecraft focused" if focused else "Minecraft not focused"
        self.focus_chip.setText(focus_text)

    def _on_run_mode_changed(self) -> None:
        self._toggle_repeat_count_visibility()
        self._update_sequence_run_mode()

    def _toggle_repeat_count_visibility(self) -> None:
        repeat_visible = coerce_run_mode(self.run_mode_combo.currentData()) == RunMode.REPEAT_N
        self.repeat_count_spin.setVisible(repeat_visible)

    def _update_sequence_run_mode(self) -> None:
        run_mode = coerce_run_mode(self.run_mode_combo.currentData())
        self._sequence.run_mode = run_mode
        self._sequence.repeat_count = (
            self.repeat_count_spin.value() if run_mode == RunMode.REPEAT_N else None
        )
        self._persist_state()

    def _update_sequence_name(self) -> None:
        self._sequence.name = self.sequence_name_edit.text().strip() or self._sequence.name
        self._persist_state()

    def _on_runner_state_changed(self, raw_state: str) -> None:
        self._update_runner_status(RunnerState(raw_state))

    def _on_runner_error(self, message: str) -> None:
        self._show_warning(f"Macro error: {message}")

    def _update_runner_status(self, state: RunnerState) -> None:
        self._runner_state = state
        labels = {
            RunnerState.IDLE: "Idle",
            RunnerState.RUNNING: "Running",
            RunnerState.PAUSED: "Paused (focus lost)",
            RunnerState.STOPPED: "Stopped",
            RunnerState.PANIC_STOPPED: "Panic stopped",
        }
        self.state_chip.setText(f"State: {labels[state]}")
        running = state in {RunnerState.RUNNING, RunnerState.PAUSED}
        self.start_button.setEnabled(not running)
        self.stop_button.setEnabled(running)
        self.panic_button.setEnabled(running)

        for widget in (
            self.sequence_name_edit,
            self.step_table,
            self.add_key_button,
            self.add_wait_button,
            self.edit_step_button,
            self.remove_step_button,
            self.move_up_button,
            self.move_down_button,
            self.run_mode_combo,
            self.repeat_count_spin,
            self.start_hotkey_edit,
            self.stop_hotkey_edit,
            self.panic_hotkey_edit,
            self.toggle_hotkey_edit,
            self.opacity_spin,
            self.title_match_edit,
            self.process_names_edit,
            self.apply_settings_button,
        ):
            widget.setEnabled(not running)

        self.stop_button.setEnabled(running)
        self.panic_button.setEnabled(running)

    def _update_hotkey_summary(self) -> None:
        self.hotkey_chip.setText(
            "Hotkeys: "
            f"start {self._settings.start_hotkey} | "
            f"stop {self._settings.stop_hotkey} | "
            f"panic {self._settings.panic_hotkey}"
        )

    def _update_interaction_ui(self) -> None:
        if self._interactive_mode:
            self.mode_button.setText("Switch to gameplay mode")
            self.subtitle_label.setText(
                "Interactive overlay mode. Press Esc in Minecraft before clicking the UI."
            )
        else:
            self.mode_button.setText("Switch to edit mode")
            self.subtitle_label.setText(
                "Gameplay mode is click-through. Use the toggle hotkey to edit again."
            )

    def _set_message(self, message: str) -> None:
        self.message_label.setText(message)

    def _show_warning(self, message: str) -> None:
        self._set_message(message)
        QtWidgets.QMessageBox.warning(self, "semiCLICK", message)
