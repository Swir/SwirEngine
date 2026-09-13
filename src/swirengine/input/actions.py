from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from .manager import InputManager


@dataclass(frozen=True, slots=True)
class InputBinding:
    """Serializable binding for a named gameplay action.

    ``kind`` supports ``key``, ``mouse_button``, ``gamepad_button`` and ``gamepad_axis``.
    Axis bindings use ``direction`` (-1 or +1), ``threshold`` and optional ``gamepad_id``.
    """

    kind: str
    control: str | int
    gamepad_id: int = 0
    direction: int = 1
    threshold: float = 0.5
    scale: float = 1.0

    def __post_init__(self) -> None:
        allowed = {"key", "mouse_button", "gamepad_button", "gamepad_axis"}
        if self.kind not in allowed:
            raise ValueError(f"Unsupported input binding kind: {self.kind!r}")
        if self.direction not in (-1, 1):
            raise ValueError("direction must be -1 or 1")
        if not 0.0 <= float(self.threshold) <= 1.0:
            raise ValueError("threshold must be between 0.0 and 1.0")

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> InputBinding:
        return cls(
            kind=str(data["kind"]),
            control=data["control"],
            gamepad_id=int(data.get("gamepad_id", 0)),
            direction=int(data.get("direction", 1)),
            threshold=float(data.get("threshold", 0.5)),
            scale=float(data.get("scale", 1.0)),
        )


class InputActions:
    """Named action layer over :class:`InputManager` with rebinding and JSON profiles.

    Games can bind multiple physical controls to one semantic action, query button-like edge
    states, or read an analog value. Bindings are intentionally backend-agnostic and persist as
    plain JSON so a settings menu can safely remap controls without custom serialization code.
    """

    PROFILE_VERSION = 1

    def __init__(self, input_manager: InputManager) -> None:
        self.input = input_manager
        self._bindings: dict[str, list[InputBinding]] = {}

    @staticmethod
    def _normalize_action(action: str) -> str:
        value = str(action).strip().lower()
        if not value:
            raise ValueError("action name cannot be empty")
        return value

    def actions(self) -> tuple[str, ...]:
        return tuple(sorted(self._bindings))

    def bindings(self, action: str) -> tuple[InputBinding, ...]:
        return tuple(self._bindings.get(self._normalize_action(action), ()))

    def bind(self, action: str, binding: InputBinding, *, replace: bool = False) -> None:
        name = self._normalize_action(action)
        if replace:
            self._bindings[name] = [binding]
            return
        values = self._bindings.setdefault(name, [])
        if binding not in values:
            values.append(binding)

    def bind_many(
        self,
        action: str,
        bindings: Iterable[InputBinding],
        *,
        replace: bool = False,
    ) -> None:
        if replace:
            self._bindings[self._normalize_action(action)] = []
        for binding in bindings:
            self.bind(action, binding)

    def unbind(self, action: str, binding: InputBinding | None = None) -> None:
        name = self._normalize_action(action)
        if binding is None:
            self._bindings.pop(name, None)
            return
        values = self._bindings.get(name)
        if not values:
            return
        self._bindings[name] = [value for value in values if value != binding]
        if not self._bindings[name]:
            self._bindings.pop(name, None)

    def clear(self) -> None:
        self._bindings.clear()

    def key(self, action: str, key: str, *, replace: bool = False) -> None:
        self.bind(action, InputBinding("key", key), replace=replace)

    def mouse_button(self, action: str, button: int, *, replace: bool = False) -> None:
        self.bind(action, InputBinding("mouse_button", int(button)), replace=replace)

    def gamepad_button(
        self,
        action: str,
        button: str,
        *,
        gamepad_id: int = 0,
        replace: bool = False,
    ) -> None:
        self.bind(
            action,
            InputBinding("gamepad_button", button, gamepad_id=int(gamepad_id)),
            replace=replace,
        )

    def gamepad_axis(
        self,
        action: str,
        axis: str,
        *,
        gamepad_id: int = 0,
        direction: int = 1,
        threshold: float = 0.5,
        scale: float = 1.0,
        replace: bool = False,
    ) -> None:
        self.bind(
            action,
            InputBinding(
                "gamepad_axis",
                axis,
                gamepad_id=int(gamepad_id),
                direction=int(direction),
                threshold=float(threshold),
                scale=float(scale),
            ),
            replace=replace,
        )

    def _binding_value(self, binding: InputBinding) -> float:
        if binding.kind == "key":
            return float(self.input.key(str(binding.control))) * binding.scale
        if binding.kind == "mouse_button":
            return float(self.input.mouse_button(int(binding.control))) * binding.scale
        if binding.kind == "gamepad_button":
            return float(
                self.input.gamepad_button(str(binding.control), gamepad_id=binding.gamepad_id)
            ) * binding.scale
        axis = self.input.gamepad_axis(str(binding.control), gamepad_id=binding.gamepad_id)
        directed = axis * binding.direction
        if directed <= 0.0:
            return 0.0
        return min(1.0, directed) * binding.scale

    def value(self, action: str) -> float:
        values = [self._binding_value(binding) for binding in self.bindings(action)]
        if not values:
            return 0.0
        return max(values, key=lambda value: abs(value))

    def down(self, action: str, *, threshold: float = 0.5) -> bool:
        return abs(self.value(action)) >= float(threshold)

    def _edge(self, binding: InputBinding, *, pressed: bool) -> bool:
        if binding.kind == "key":
            method = self.input.key_pressed if pressed else self.input.key_released
            return method(str(binding.control))
        if binding.kind == "mouse_button":
            method = (
                self.input.mouse_button_pressed if pressed else self.input.mouse_button_released
            )
            return method(int(binding.control))
        if binding.kind == "gamepad_button":
            method = (
                self.input.gamepad_button_pressed
                if pressed
                else self.input.gamepad_button_released
            )
            return method(str(binding.control), gamepad_id=binding.gamepad_id)
        return False

    def pressed(self, action: str) -> bool:
        return any(self._edge(binding, pressed=True) for binding in self.bindings(action))

    def released(self, action: str) -> bool:
        return any(self._edge(binding, pressed=False) for binding in self.bindings(action))

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.PROFILE_VERSION,
            "actions": {
                action: [asdict(binding) for binding in bindings]
                for action, bindings in sorted(self._bindings.items())
            },
        }

    def load_dict(self, data: dict[str, Any], *, replace: bool = True) -> None:
        version = int(data.get("version", 0))
        if version != self.PROFILE_VERSION:
            raise ValueError(f"Unsupported input profile version: {version}")
        actions = data.get("actions")
        if not isinstance(actions, dict):
            raise TypeError("input profile must contain an 'actions' object")
        if replace:
            self.clear()
        for action, raw_bindings in actions.items():
            if not isinstance(raw_bindings, list):
                raise TypeError(f"bindings for {action!r} must be a list")
            self.bind_many(
                str(action),
                (InputBinding.from_dict(item) for item in raw_bindings),
            )

    def save(self, path: str | Path) -> Path:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(self.to_dict(), indent=2, sort_keys=True), encoding="utf-8")
        return target

    def load(self, path: str | Path, *, replace: bool = True) -> None:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise TypeError("input profile root must be an object")
        self.load_dict(data, replace=replace)
