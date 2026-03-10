from __future__ import annotations

import json
import os
from pathlib import Path

from semiclick.core.models import PersistedState, default_state


def default_state_path() -> Path:
    local_app_data = os.environ.get("LOCALAPPDATA")
    base_path = Path(local_app_data) if local_app_data else Path.home()
    return base_path / "semiCLICK" / "state.json"


class JsonStorage:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or default_state_path()

    def load(self) -> PersistedState:
        if not self.path.exists():
            state = default_state()
            self.save(state)
            return state

        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError, ValueError):
            state = default_state()
            self.save(state)
            return state

        return PersistedState.from_dict(payload if isinstance(payload, dict) else None)

    def save(self, state: PersistedState) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = self.path.with_suffix(".tmp")
        temp_path.write_text(
            json.dumps(state.to_dict(), indent=2, sort_keys=True),
            encoding="utf-8",
        )
        temp_path.replace(self.path)
