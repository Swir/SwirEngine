from __future__ import annotations

import json
import os
from collections.abc import Mapping
from pathlib import Path
from typing import Any


class SaveStore:
    """Small JSON save-data store with atomic writes and dict-like helpers."""

    def __init__(
        self,
        path: str | Path = "save.json",
        *,
        defaults: Mapping[str, Any] | None = None,
        autoload: bool = True,
    ) -> None:
        self.path = Path(path).expanduser()
        self._defaults = dict(defaults or {})
        self._data: dict[str, Any] = dict(self._defaults)
        if autoload and self.path.exists():
            self.load()

    def __len__(self) -> int:
        return len(self._data)

    def __contains__(self, key: object) -> bool:
        return key in self._data

    def __getitem__(self, key: str) -> Any:
        return self._data[key]

    def __setitem__(self, key: str, value: Any) -> None:
        self._data[key] = value

    def get(self, key: str, default: Any = None) -> Any:
        return self._data.get(key, default)

    def set(self, key: str, value: Any) -> SaveStore:
        self._data[key] = value
        return self

    def update(self, values: Mapping[str, Any]) -> SaveStore:
        self._data.update(values)
        return self

    def delete(self, key: str) -> bool:
        if key not in self._data:
            return False
        del self._data[key]
        return True

    def clear(self, *, keep_defaults: bool = True) -> SaveStore:
        self._data = dict(self._defaults) if keep_defaults else {}
        return self

    def as_dict(self) -> dict[str, Any]:
        return dict(self._data)

    def load(self) -> SaveStore:
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ValueError(f"invalid save data JSON: {self.path}") from exc
        if not isinstance(raw, dict):
            raise ValueError("save data root must be a JSON object")
        self._data = dict(self._defaults)
        self._data.update(raw)
        return self

    def save(self) -> SaveStore:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(self._data, indent=2, sort_keys=True, ensure_ascii=False)
        temporary = self.path.with_name(f".{self.path.name}.tmp")
        try:
            temporary.write_text(payload + "\n", encoding="utf-8")
            os.replace(temporary, self.path)
        finally:
            if temporary.exists():
                temporary.unlink()
        return self
