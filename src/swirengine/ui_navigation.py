from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from .ui import UIButton


class UIFocusManager:
    """Deterministic focus/navigation controller for creator-facing game UI.

    Buttons stay in creator-defined order, disabled/hidden/non-focusable buttons are skipped,
    and activation works with keyboard or any connected standardized gamepad.
    """

    def __init__(self, buttons: Iterable[UIButton] = ()) -> None:
        self._buttons: list[UIButton] = []
        self._focused: UIButton | None = None
        for button in buttons:
            self.add(button)

    @property
    def buttons(self) -> tuple[UIButton, ...]:
        return tuple(self._buttons)

    @property
    def focused(self) -> UIButton | None:
        return self._focused

    def add(self, button: UIButton) -> UIButton:
        if not any(existing is button for existing in self._buttons):
            self._buttons.append(button)
        return button

    def remove(self, button: UIButton) -> bool:
        for index, existing in enumerate(self._buttons):
            if existing is button:
                del self._buttons[index]
                if self._focused is button:
                    self._focused = None
                return True
        return False

    @staticmethod
    def _focusable(button: UIButton) -> bool:
        return bool(
            getattr(button, "enabled", True)
            and getattr(button, "visible", True)
            and getattr(button, "focusable", True)
        )

    def focusable_buttons(self) -> tuple[UIButton, ...]:
        return tuple(button for button in self._buttons if self._focusable(button))

    def focus(self, button: UIButton | None) -> UIButton | None:
        if button is not None and button not in self.focusable_buttons():
            return self._focused
        self._focused = button
        return button

    def move(self, step: int = 1) -> UIButton | None:
        buttons = self.focusable_buttons()
        if not buttons:
            self._focused = None
            return None
        if self._focused not in buttons:
            self._focused = buttons[0] if step >= 0 else buttons[-1]
            return self._focused
        index = buttons.index(self._focused)
        self._focused = buttons[(index + step) % len(buttons)]
        return self._focused

    def activate(self) -> bool:
        button = self._focused
        if button is None or not self._focusable(button):
            return False
        callback = getattr(button, "on_click", None)
        if callback is not None:
            callback(button)
        return True

    @staticmethod
    def _key_pressed(input_manager: Any, name: str) -> bool:
        method = getattr(input_manager, "key_pressed", None)
        return bool(method(name)) if callable(method) else False

    @staticmethod
    def _gamepad_ids(input_manager: Any) -> tuple[int, ...]:
        method = getattr(input_manager, "gamepads", None)
        if callable(method):
            ids = tuple(int(item) for item in method())
            if ids:
                return ids
        return (0,)

    @classmethod
    def _gamepad_pressed(cls, input_manager: Any, name: str) -> bool:
        method = getattr(input_manager, "gamepad_button_pressed", None)
        if not callable(method):
            return False
        for gamepad_id in cls._gamepad_ids(input_manager):
            try:
                if method(name, gamepad_id):
                    return True
            except (KeyError, TypeError, ValueError):
                continue
        return False

    def update(self, input_manager: Any) -> UIButton | None:
        forward = (
            self._key_pressed(input_manager, "tab")
            or self._key_pressed(input_manager, "down")
            or self._key_pressed(input_manager, "right")
            or self._gamepad_pressed(input_manager, "dpad_down")
            or self._gamepad_pressed(input_manager, "dpad_right")
        )
        backward = (
            self._key_pressed(input_manager, "up")
            or self._key_pressed(input_manager, "left")
            or self._gamepad_pressed(input_manager, "dpad_up")
            or self._gamepad_pressed(input_manager, "dpad_left")
        )
        if forward:
            self.move(1)
        elif backward:
            self.move(-1)

        activate = (
            self._key_pressed(input_manager, "enter")
            or self._key_pressed(input_manager, "space")
            or self._gamepad_pressed(input_manager, "a")
        )
        if activate:
            self.activate()
        return self._focused
