from swirengine.ui import UIButton
from swirengine.ui_layout import UIAnchor, UIContainer, UILayout, UILayoutDirection
from swirengine.ui_navigation import UIFocusManager


class FakeInput:
    def __init__(self) -> None:
        self.keys: set[str] = set()
        self.buttons: set[str] = set()

    def key_pressed(self, name: str) -> bool:
        return name in self.keys

    def gamepads(self) -> tuple[int, ...]:
        return (0,)

    def gamepad_button_pressed(self, name: str, gamepad_id: int = 0) -> bool:
        return gamepad_id == 0 and name in self.buttons


def test_anchor_positions_follow_viewport_edges() -> None:
    top_left = UILayout(anchor=UIAnchor.TOP_LEFT, offset_x=20, offset_y=-30)
    assert top_left.position_for(800, 600) == (-380.0, 270.0, 1.0)

    bottom_right = UILayout(anchor=UIAnchor.BOTTOM_RIGHT, offset_x=-10, offset_y=15)
    assert bottom_right.position_for(800, 600) == (390.0, -285.0, 1.0)


def test_layout_scaling_uses_reference_resolution_and_clamps() -> None:
    layout = UILayout(scale_with_viewport=True, reference_width=1280, reference_height=720)
    assert layout.scale_for(1920, 1080) == 1.5
    assert layout.scale_for(640, 360) == 0.5

    layout.max_scale = 1.25
    assert layout.scale_for(2560, 1440) == 1.25


def test_vertical_container_arranges_and_scales_buttons() -> None:
    first = UIButton("Play", 0, 0, width=200, height=40)
    second = UIButton("Options", 0, 0, width=200, height=40)
    container = UIContainer(
        first,
        second,
        direction=UILayoutDirection.VERTICAL,
        spacing=20,
        layout=UILayout(scale_with_viewport=True, reference_width=800, reference_height=600),
    )

    container.arrange(1600, 1200)
    assert first.width == 400
    assert first.height == 80
    assert second.width == 400
    assert first.y == 100
    assert second.y == -100

    container.arrange(800, 600)
    assert first.width == 200
    assert first.height == 40
    assert first.y == 50
    assert second.y == -50


def test_horizontal_container_preserves_creator_order() -> None:
    left = UIButton("Left", 0, 0, width=100, height=40)
    right = UIButton("Right", 0, 0, width=100, height=40)
    container = UIContainer(left, right, direction="horizontal", spacing=20)
    container.arrange(800, 600)
    assert left.x == -60
    assert right.x == 60


def test_focus_manager_wraps_and_skips_disabled_buttons() -> None:
    first = UIButton("One", 0, 0)
    second = UIButton("Two", 0, 0)
    third = UIButton("Three", 0, 0)
    second.enabled = False
    focus = UIFocusManager((first, second, third))

    assert focus.move() is first
    assert focus.move() is third
    assert focus.move() is first
    assert focus.move(-1) is third


def test_keyboard_and_gamepad_navigation_can_activate_focused_button() -> None:
    clicks: list[str] = []
    first = UIButton("Play", 0, 0, on_click=lambda button: clicks.append(button.text))
    second = UIButton("Quit", 0, 0, on_click=lambda button: clicks.append(button.text))
    focus = UIFocusManager((first, second))
    input_state = FakeInput()

    input_state.keys = {"tab"}
    assert focus.update(input_state) is first
    input_state.keys = {"down"}
    assert focus.update(input_state) is second
    input_state.keys = {"enter"}
    focus.update(input_state)
    assert clicks == ["Quit"]

    input_state.keys.clear()
    input_state.buttons = {"dpad_up"}
    assert focus.update(input_state) is first
    input_state.buttons = {"a"}
    focus.update(input_state)
    assert clicks == ["Quit", "Play"]
