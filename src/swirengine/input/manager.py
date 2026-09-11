class InputManager:
    def __init__(self) -> None:
        self._keys: set[int] = set()
        self._pressed: set[int] = set()
        self._released: set[int] = set()
        self._buttons: set[int] = set()
        self._buttons_pressed: set[int] = set()
        self._buttons_released: set[int] = set()
        self.mouse_x = self.mouse_y = 0.0
        self.mouse_dx = self.mouse_dy = 0.0

    def begin_frame(self) -> None:
        self._pressed.clear()
        self._released.clear()
        self._buttons_pressed.clear()
        self._buttons_released.clear()
        self.mouse_dx = self.mouse_dy = 0.0

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
