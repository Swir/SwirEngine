from pathlib import Path

import pytest

from swirengine.input import InputActions, InputBinding


class StubInput:
    def __init__(self) -> None:
        self.keys = set()
        self.key_edges = set()
        self.key_releases = set()
        self.mouse = set()
        self.mouse_edges = set()
        self.mouse_releases = set()
        self.pad_buttons = set()
        self.pad_edges = set()
        self.pad_releases = set()
        self.axes = {}

    def key(self, name):
        return name in self.keys

    def key_pressed(self, name):
        return name in self.key_edges

    def key_released(self, name):
        return name in self.key_releases

    def mouse_button(self, button):
        return button in self.mouse

    def mouse_button_pressed(self, button):
        return button in self.mouse_edges

    def mouse_button_released(self, button):
        return button in self.mouse_releases

    def gamepad_button(self, name, gamepad_id=0):
        return (gamepad_id, name) in self.pad_buttons

    def gamepad_button_pressed(self, name, gamepad_id=0):
        return (gamepad_id, name) in self.pad_edges

    def gamepad_button_released(self, name, gamepad_id=0):
        return (gamepad_id, name) in self.pad_releases

    def gamepad_axis(self, name, gamepad_id=0):
        return self.axes.get((gamepad_id, name), 0.0)


def test_named_action_combines_keyboard_mouse_and_gamepad():
    backend = StubInput()
    actions = InputActions(backend)
    actions.key("jump", "SPACE")
    actions.mouse_button("fire", 0)
    actions.gamepad_button("jump", "a")

    backend.keys.add("SPACE")
    backend.key_edges.add("SPACE")
    backend.mouse.add(0)

    assert actions.down("jump")
    assert actions.pressed("jump")
    assert actions.down("fire")
    assert actions.actions() == ("fire", "jump")


def test_axis_binding_supports_direction_threshold_and_analog_value():
    backend = StubInput()
    actions = InputActions(backend)
    actions.gamepad_axis("move_left", "left_x", direction=-1, threshold=0.35)
    backend.axes[(0, "left_x")] = -0.75

    assert actions.value("move_left") == pytest.approx(0.75)
    assert actions.down("move_left", threshold=0.35)


def test_rebind_replace_and_unbind():
    backend = StubInput()
    actions = InputActions(backend)
    actions.key("confirm", "ENTER")
    actions.key("confirm", "SPACE", replace=True)

    assert actions.bindings("confirm") == (InputBinding("key", "SPACE"),)
    actions.unbind("confirm", InputBinding("key", "SPACE"))
    assert actions.bindings("confirm") == ()


def test_profile_round_trip(tmp_path: Path):
    backend = StubInput()
    actions = InputActions(backend)
    actions.key("jump", "SPACE")
    actions.gamepad_button("jump", "a")
    actions.gamepad_axis("throttle", "right_trigger", threshold=0.2, scale=0.8)

    profile = actions.save(tmp_path / "controls.json")
    restored = InputActions(backend)
    restored.load(profile)

    assert restored.to_dict() == actions.to_dict()


def test_invalid_profile_version_is_rejected():
    actions = InputActions(StubInput())
    with pytest.raises(ValueError, match="Unsupported input profile version"):
        actions.load_dict({"version": 999, "actions": {}})
