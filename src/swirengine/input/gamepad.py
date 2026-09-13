from __future__ import annotations

from dataclasses import dataclass

GAMEPAD_BUTTONS: dict[str, int] = {
    "A": 0,
    "B": 1,
    "X": 2,
    "Y": 3,
    "LEFT_BUMPER": 4,
    "RIGHT_BUMPER": 5,
    "BACK": 6,
    "START": 7,
    "GUIDE": 8,
    "LEFT_THUMB": 9,
    "RIGHT_THUMB": 10,
    "DPAD_UP": 11,
    "DPAD_RIGHT": 12,
    "DPAD_DOWN": 13,
    "DPAD_LEFT": 14,
}

GAMEPAD_AXES: dict[str, int] = {
    "LEFT_X": 0,
    "LEFT_Y": 1,
    "RIGHT_X": 2,
    "RIGHT_Y": 3,
    "LEFT_TRIGGER": 4,
    "RIGHT_TRIGGER": 5,
}

_BUTTON_ALIASES = {
    "LB": "LEFT_BUMPER",
    "RB": "RIGHT_BUMPER",
    "L1": "LEFT_BUMPER",
    "R1": "RIGHT_BUMPER",
    "SELECT": "BACK",
    "OPTIONS": "START",
    "MENU": "START",
    "L3": "LEFT_THUMB",
    "R3": "RIGHT_THUMB",
    "UP": "DPAD_UP",
    "RIGHT": "DPAD_RIGHT",
    "DOWN": "DPAD_DOWN",
    "LEFT": "DPAD_LEFT",
}

_AXIS_ALIASES = {
    "LX": "LEFT_X",
    "LY": "LEFT_Y",
    "RX": "RIGHT_X",
    "RY": "RIGHT_Y",
    "LT": "LEFT_TRIGGER",
    "RT": "RIGHT_TRIGGER",
    "L2": "LEFT_TRIGGER",
    "R2": "RIGHT_TRIGGER",
}


def normalize_gamepad_button(name: str) -> str:
    key = str(name).strip().upper().replace("-", "_").replace(" ", "_")
    key = _BUTTON_ALIASES.get(key, key)
    if key not in GAMEPAD_BUTTONS:
        raise ValueError(f"unknown gamepad button: {name!r}")
    return key


def normalize_gamepad_axis(name: str) -> str:
    key = str(name).strip().upper().replace("-", "_").replace(" ", "_")
    key = _AXIS_ALIASES.get(key, key)
    if key not in GAMEPAD_AXES:
        raise ValueError(f"unknown gamepad axis: {name!r}")
    return key


def apply_deadzone(value: float, deadzone: float) -> float:
    zone = max(0.0, min(0.95, float(deadzone)))
    value = max(-1.0, min(1.0, float(value)))
    magnitude = abs(value)
    if magnitude <= zone:
        return 0.0
    scaled = (magnitude - zone) / (1.0 - zone)
    return scaled if value >= 0.0 else -scaled


@dataclass(frozen=True, slots=True)
class GamepadSnapshot:
    """One normalized GLFW gamepad snapshot.

    Button and axis indexes follow GLFW's cross-platform gamepad mapping. Stick axes remain in
    GLFW's native -1..1 orientation; trigger helpers convert the native -1..1 trigger range to
    creator-friendly 0..1 values.
    """

    id: int
    name: str
    axes: tuple[float, ...]
    buttons: tuple[bool, ...]
    guid: str | None = None

    def button(self, name: str) -> bool:
        index = GAMEPAD_BUTTONS[normalize_gamepad_button(name)]
        return index < len(self.buttons) and bool(self.buttons[index])

    def axis(self, name: str, *, deadzone: float = 0.0) -> float:
        index = GAMEPAD_AXES[normalize_gamepad_axis(name)]
        value = self.axes[index] if index < len(self.axes) else 0.0
        return apply_deadzone(value, deadzone)

    def stick(self, side: str = "left", *, deadzone: float = 0.15) -> tuple[float, float]:
        side_name = str(side).strip().upper()
        if side_name not in {"LEFT", "RIGHT"}:
            raise ValueError("side must be 'left' or 'right'")
        return (
            self.axis(f"{side_name}_X", deadzone=deadzone),
            self.axis(f"{side_name}_Y", deadzone=deadzone),
        )

    def trigger(self, side: str = "left", *, deadzone: float = 0.02) -> float:
        side_name = str(side).strip().upper()
        if side_name not in {"LEFT", "RIGHT"}:
            raise ValueError("side must be 'left' or 'right'")
        raw = self.axis(f"{side_name}_TRIGGER", deadzone=0.0)
        value = (raw + 1.0) * 0.5
        if value <= deadzone:
            return 0.0
        return min(1.0, (value - deadzone) / (1.0 - deadzone))
