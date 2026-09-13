from __future__ import annotations

from typing import Any

from .gamepad import GAMEPAD_BUTTONS, GamepadSnapshot, normalize_gamepad_button


class InputManager:
    def __init__(self, *, gamepad_deadzone: float = 0.15) -> None:
        self._keys: set[int] = set()
        self._pressed: set[int] = set()
        self._released: set[int] = set()
        self._buttons: set[int] = set()
        self._buttons_pressed: set[int] = set()
        self._buttons_released: set[int] = set()
        self.mouse_x = self.mouse_y = 0.0
        self.mouse_dx = self.mouse_dy = 0.0

        self.gamepad_deadzone = max(0.0, min(0.95, float(gamepad_deadzone)))
        self._gamepads: dict[int, GamepadSnapshot] = {}
        self._gamepad_pressed: dict[int, set[int]] = {}
        self._gamepad_released: dict[int, set[int]] = {}
        self._gamepads_connected: set[int] = set()
        self._gamepads_disconnected: set[int] = set()

    def begin_frame(self) -> None:
        self._pressed.clear()
        self._released.clear()
        self._buttons_pressed.clear()
        self._buttons_released.clear()
        self._gamepad_pressed.clear()
        self._gamepad_released.clear()
        self._gamepads_connected.clear()
        self._gamepads_disconnected.clear()
        self.mouse_dx = self.mouse_dy = 0.0
        self._poll_runtime_gamepads()

    def _poll_runtime_gamepads(self) -> None:
        """Refresh gamepad state when running inside an initialized GLFW game window."""
        try:
            import glfw
        except ImportError:
            return
        try:
            get_context = getattr(glfw, "get_current_context", None)
            if get_context is not None and get_context() is None:
                return
        except (AttributeError, RuntimeError):
            return
        self.poll_gamepads(glfw)

    @staticmethod
    def _named_key(name: str) -> int | None:
        try:
            import glfw

            return int(getattr(glfw, f"KEY_{name.upper()}"))
        except (ImportError, AttributeError):
            return None

    def key(self, name: str) -> bool:
        code = self._named_key(name)
        return code is not None and code in self._keys

    def key_pressed(self, name: str) -> bool:
        code = self._named_key(name)
        return code is not None and code in self._pressed

    def key_released(self, name: str) -> bool:
        code = self._named_key(name)
        return code is not None and code in self._released

    def key_code(self, code: int) -> bool:
        return code in self._keys

    def key_pressed_code(self, code: int) -> bool:
        return code in self._pressed

    def key_released_code(self, code: int) -> bool:
        return code in self._released

    def mouse_button(self, button: int) -> bool:
        return button in self._buttons

    def mouse_button_pressed(self, button: int) -> bool:
        return button in self._buttons_pressed

    def mouse_button_released(self, button: int) -> bool:
        return button in self._buttons_released

    def gamepads(self) -> tuple[int, ...]:
        """Return connected standardized gamepad IDs in deterministic order."""
        return tuple(sorted(self._gamepads))

    def gamepad(self, gamepad_id: int = 0) -> GamepadSnapshot | None:
        """Return the latest normalized gamepad snapshot, or ``None`` when unavailable."""
        return self._gamepads.get(int(gamepad_id))

    def gamepad_connected(self, gamepad_id: int = 0) -> bool:
        return int(gamepad_id) in self._gamepads

    def gamepad_just_connected(self, gamepad_id: int = 0) -> bool:
        return int(gamepad_id) in self._gamepads_connected

    def gamepad_just_disconnected(self, gamepad_id: int = 0) -> bool:
        return int(gamepad_id) in self._gamepads_disconnected

    def gamepads_just_connected(self) -> tuple[int, ...]:
        return tuple(sorted(self._gamepads_connected))

    def gamepads_just_disconnected(self) -> tuple[int, ...]:
        return tuple(sorted(self._gamepads_disconnected))

    def gamepad_name(self, gamepad_id: int = 0) -> str | None:
        state = self.gamepad(gamepad_id)
        return state.name if state is not None else None

    def gamepad_button(self, name: str, gamepad_id: int = 0) -> bool:
        state = self.gamepad(gamepad_id)
        return state is not None and state.button(name)

    def gamepad_button_pressed(self, name: str, gamepad_id: int = 0) -> bool:
        index = GAMEPAD_BUTTONS[normalize_gamepad_button(name)]
        return index in self._gamepad_pressed.get(int(gamepad_id), set())

    def gamepad_button_released(self, name: str, gamepad_id: int = 0) -> bool:
        index = GAMEPAD_BUTTONS[normalize_gamepad_button(name)]
        return index in self._gamepad_released.get(int(gamepad_id), set())

    def gamepad_axis(
        self,
        name: str,
        gamepad_id: int = 0,
        *,
        deadzone: float | None = None,
    ) -> float:
        state = self.gamepad(gamepad_id)
        if state is None:
            return 0.0
        zone = self.gamepad_deadzone if deadzone is None else float(deadzone)
        return state.axis(name, deadzone=zone)

    def gamepad_stick(
        self,
        side: str = "left",
        gamepad_id: int = 0,
        *,
        deadzone: float | None = None,
    ) -> tuple[float, float]:
        state = self.gamepad(gamepad_id)
        if state is None:
            return (0.0, 0.0)
        zone = self.gamepad_deadzone if deadzone is None else float(deadzone)
        return state.stick(side, deadzone=zone)

    def gamepad_trigger(
        self,
        side: str = "left",
        gamepad_id: int = 0,
        *,
        deadzone: float = 0.02,
    ) -> float:
        state = self.gamepad(gamepad_id)
        if state is None:
            return 0.0
        return state.trigger(side, deadzone=deadzone)

    @staticmethod
    def _coerce_gamepad_state(raw: Any) -> tuple[tuple[float, ...], tuple[bool, ...]] | None:
        if raw is None:
            return None
        if hasattr(raw, "axes") and hasattr(raw, "buttons"):
            axes = raw.axes
            buttons = raw.buttons
        elif isinstance(raw, (tuple, list)) and len(raw) == 2:
            axes, buttons = raw
        else:
            return None
        return (
            tuple(float(value) for value in axes),
            tuple(bool(value) for value in buttons),
        )

    def poll_gamepads(self, glfw_module: Any | None = None) -> None:
        """Poll GLFW's standardized gamepad mapping exactly once for the current frame.

        This intentionally ignores non-gamepad joysticks. Standardized mapping gives the same
        button/axis names across Xbox, PlayStation and compatible controllers when GLFW has a
        mapping for the device.
        """
        if glfw_module is None:
            try:
                import glfw as glfw_module
            except ImportError:
                return

        first = int(getattr(glfw_module, "JOYSTICK_1", 0))
        last = int(getattr(glfw_module, "JOYSTICK_LAST", 15))
        previous = self._gamepads
        current: dict[int, GamepadSnapshot] = {}

        for gamepad_id in range(first, last + 1):
            try:
                if not glfw_module.joystick_present(gamepad_id):
                    continue
                if hasattr(glfw_module, "joystick_is_gamepad") and not glfw_module.joystick_is_gamepad(
                    gamepad_id
                ):
                    continue
                values = self._coerce_gamepad_state(glfw_module.get_gamepad_state(gamepad_id))
            except (AttributeError, TypeError, ValueError):
                continue
            if values is None:
                continue

            axes, buttons = values
            try:
                name = glfw_module.get_gamepad_name(gamepad_id) or glfw_module.get_joystick_name(
                    gamepad_id
                )
            except (AttributeError, TypeError):
                name = None
            try:
                guid = glfw_module.get_joystick_guid(gamepad_id)
            except (AttributeError, TypeError):
                guid = None
            current[gamepad_id] = GamepadSnapshot(
                id=gamepad_id,
                name=str(name or f"Gamepad {gamepad_id}"),
                axes=axes,
                buttons=buttons,
                guid=str(guid) if guid else None,
            )

        old_ids = set(previous)
        new_ids = set(current)
        self._gamepads_connected.update(new_ids - old_ids)
        self._gamepads_disconnected.update(old_ids - new_ids)

        for gamepad_id in old_ids & new_ids:
            old_buttons = previous[gamepad_id].buttons
            new_buttons = current[gamepad_id].buttons
            count = max(len(old_buttons), len(new_buttons))
            pressed: set[int] = set()
            released: set[int] = set()
            for index in range(count):
                before = old_buttons[index] if index < len(old_buttons) else False
                after = new_buttons[index] if index < len(new_buttons) else False
                if after and not before:
                    pressed.add(index)
                elif before and not after:
                    released.add(index)
            if pressed:
                self._gamepad_pressed[gamepad_id] = pressed
            if released:
                self._gamepad_released[gamepad_id] = released

        for gamepad_id in new_ids - old_ids:
            pressed = {index for index, value in enumerate(current[gamepad_id].buttons) if value}
            if pressed:
                self._gamepad_pressed[gamepad_id] = pressed

        self._gamepads = current

    def _on_key(self, key: int, action: int) -> None:
        import glfw

        if action == glfw.PRESS:
            self._keys.add(key)
            self._pressed.add(key)
        elif action == glfw.RELEASE:
            self._keys.discard(key)
            self._released.add(key)

    def _on_cursor(self, x: float, y: float) -> None:
        self.mouse_dx += x - self.mouse_x
        self.mouse_dy += y - self.mouse_y
        self.mouse_x, self.mouse_y = x, y

    def _on_button(self, button: int, action: int) -> None:
        import glfw

        if action == glfw.PRESS:
            self._buttons.add(button)
            self._buttons_pressed.add(button)
        elif action == glfw.RELEASE:
            self._buttons.discard(button)
            self._buttons_released.add(button)
