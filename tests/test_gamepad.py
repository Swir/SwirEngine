from __future__ import annotations

from types import SimpleNamespace

import pytest

from swirengine.input.gamepad import GamepadSnapshot, apply_deadzone
from swirengine.input.manager import InputManager


class FakeGLFW:
    JOYSTICK_1 = 0
    JOYSTICK_LAST = 2

    def __init__(self) -> None:
        self.states: dict[int, tuple[tuple[float, ...], tuple[int, ...]]] = {}
        self.names: dict[int, str] = {}
        self.guids: dict[int, str] = {}
        self.non_gamepads: set[int] = set()

    def joystick_present(self, gamepad_id: int) -> bool:
        return gamepad_id in self.states

    def joystick_is_gamepad(self, gamepad_id: int) -> bool:
        return gamepad_id in self.states and gamepad_id not in self.non_gamepads

    def get_gamepad_state(self, gamepad_id: int):
        return self.states.get(gamepad_id)

    def get_gamepad_name(self, gamepad_id: int):
        return self.names.get(gamepad_id)

    def get_joystick_name(self, gamepad_id: int):
        return self.names.get(gamepad_id)

    def get_joystick_guid(self, gamepad_id: int):
        return self.guids.get(gamepad_id)


def buttons(*pressed: int) -> tuple[int, ...]:
    values = [0] * 15
    for index in pressed:
        values[index] = 1
    return tuple(values)


def test_gamepad_snapshot_aliases_deadzone_and_triggers():
    snapshot = GamepadSnapshot(
        0,
        "Controller",
        axes=(0.10, -0.50, 0.75, 0.0, -1.0, 1.0),
        buttons=tuple(bool(value) for value in buttons(0, 4, 11)),
    )

    assert snapshot.button("A")
    assert snapshot.button("LB")
    assert snapshot.button("up")
    assert snapshot.axis("LX", deadzone=0.15) == 0.0
    assert snapshot.axis("LY", deadzone=0.0) == pytest.approx(-0.5)
    assert snapshot.stick("right", deadzone=0.0) == pytest.approx((0.75, 0.0))
    assert snapshot.trigger("left") == 0.0
    assert snapshot.trigger("right") == 1.0


def test_deadzone_rescales_remaining_range():
    assert apply_deadzone(0.2, 0.2) == 0.0
    assert apply_deadzone(-0.2, 0.2) == 0.0
    assert apply_deadzone(0.6, 0.2) == pytest.approx(0.5)
    assert apply_deadzone(-0.6, 0.2) == pytest.approx(-0.5)


def test_frame_poll_tracks_hotplug_button_edges_and_previous_axes():
    glfw = FakeGLFW()
    manager = InputManager(gamepad_deadzone=0.2)
    glfw.states[0] = ((0.6, -0.4, 0.0, 0.0, -1.0, 0.0), buttons(0))
    glfw.names[0] = "Test Pad"
    glfw.guids[0] = "guid-0"

    manager.begin_frame()
    manager.poll_gamepads(glfw)

    assert manager.gamepads() == (0,)
    assert manager.gamepad_connected(0)
    assert manager.gamepad_just_connected(0)
    assert manager.gamepad_name(0) == "Test Pad"
    assert manager.gamepad_button("A", 0)
    assert manager.gamepad_button_pressed("A", 0)
    assert manager.gamepad_axis("LEFT_X", 0) == pytest.approx(0.5)
    assert manager.gamepad_axis_previous("LEFT_X", 0) == 0.0
    assert manager.gamepad_stick("left", 0) == pytest.approx((0.5, -0.25))

    glfw.states[0] = ((0.0, 0.0, 0.0, 0.0, 1.0, -1.0), buttons(1))
    manager.begin_frame()
    manager.poll_gamepads(glfw)

    assert not manager.gamepad_button("A", 0)
    assert manager.gamepad_button("B", 0)
    assert manager.gamepad_button_pressed("B", 0)
    assert manager.gamepad_button_released("A", 0)
    assert not manager.gamepad_just_connected(0)
    assert manager.gamepad_axis_previous("LEFT_X", 0) == pytest.approx(0.5)
    assert manager.gamepad_trigger("left", 0) == 1.0
    assert manager.gamepad_trigger("right", 0) == 0.0

    del glfw.states[0]
    manager.begin_frame()
    manager.poll_gamepads(glfw)

    assert not manager.gamepad_connected(0)
    assert manager.gamepad_just_disconnected(0)
    assert manager.gamepad_axis_previous("LEFT_TRIGGER", 0) == 1.0
    assert manager.gamepads() == ()


def test_begin_frame_only_resets_edges_previous_axes_and_keeps_snapshot():
    glfw = FakeGLFW()
    glfw.states[0] = ((0.6, 0.0, 0.0, 0.0, -1.0, -1.0), buttons(0))
    manager = InputManager(gamepad_deadzone=0.2)
    manager.poll_gamepads(glfw)

    assert manager.gamepad_just_connected(0)
    assert manager.gamepad_button_pressed("A", 0)

    glfw.states[0] = ((0.0,) * 6, buttons(0))
    manager.begin_frame()
    manager.poll_gamepads(glfw)
    assert manager.gamepad_axis_previous("LEFT_X", 0) == pytest.approx(0.5)

    manager.begin_frame()

    assert manager.gamepad_connected(0)
    assert not manager.gamepad_just_connected(0)
    assert not manager.gamepad_button_pressed("A", 0)
    assert manager.gamepad_axis_previous("LEFT_X", 0) == 0.0


def test_poll_ignores_non_gamepad_joysticks():
    glfw = FakeGLFW()
    glfw.states[1] = ((0.0,) * 6, buttons())
    glfw.non_gamepads.add(1)
    manager = InputManager()

    manager.poll_gamepads(glfw)

    assert manager.gamepads() == ()


def test_coerce_supports_object_shaped_glfw_state():
    raw = SimpleNamespace(axes=[0.1, -0.2], buttons=[1, 0])

    assert InputManager._coerce_gamepad_state(raw) == ((0.1, -0.2), (True, False))


def test_invalid_button_and_axis_names_are_explicit():
    snapshot = GamepadSnapshot(0, "Pad", (0.0,) * 6, (False,) * 15)

    with pytest.raises(ValueError, match="unknown gamepad button"):
        snapshot.button("fire-laser")
    with pytest.raises(ValueError, match="unknown gamepad axis"):
        snapshot.axis("throttle")
