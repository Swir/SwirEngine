from swirengine import (
    UIAnchor,
    UIButton,
    UIContainer,
    UIFocusManager,
    UILabel,
    UILayout,
    UILayoutDirection,
    UIManager,
    UIPanel,
    UIProgressBar,
)
from swirengine.core.scene import Scene


class FakeInput:
    def __init__(self) -> None:
        self.keys: set[str] = set()
        self.buttons: set[str] = set()
        self.mouse_x = -1000.0
        self.mouse_y = -1000.0
        self.held = False
        self.pressed = False
        self.released = False

    def key_pressed(self, name: str) -> bool:
        return name in self.keys

    def gamepads(self) -> tuple[int, ...]:
        return (0,)

    def gamepad_button_pressed(self, name: str, gamepad_id: int = 0) -> bool:
        return gamepad_id == 0 and name in self.buttons

    def mouse_button(self, button: int) -> bool:
        return button == 0 and self.held

    def mouse_button_pressed(self, button: int) -> bool:
        return button == 0 and self.pressed

    def mouse_button_released(self, button: int) -> bool:
        return button == 0 and self.released


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


def test_vertical_container_arranges_and_scales_buttons_and_text() -> None:
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
    assert first.label.scale == 2.0
    assert second.width == 400
    assert first.y == 60
    assert second.y == -60

    container.arrange(800, 600)
    assert first.width == 200
    assert first.height == 40
    assert first.label.scale == 1.0
    assert first.y == 30
    assert second.y == -30


def test_horizontal_container_preserves_creator_order() -> None:
    left = UIButton("Left", 0, 0, width=100, height=40)
    right = UIButton("Right", 0, 0, width=100, height=40)
    container = UIContainer(left, right, direction="horizontal", spacing=20)
    container.arrange(800, 600)
    assert left.x == -60
    assert right.x == 60


def test_layout_syncs_panel_label_and_progress_geometry() -> None:
    panel = UIPanel(0, 0, 300, 120)
    label = UILabel("Ready", 0, 0, scale=1.25)
    bar = UIProgressBar(0, 0, width=200, height=20, value=0.25)
    layout = UILayout(scale_with_viewport=True, reference_width=800, reference_height=600)

    UIContainer(panel, direction="vertical", layout=layout).arrange(1600, 1200)
    UIContainer(label, direction="vertical", layout=layout).arrange(1600, 1200)
    UIContainer(bar, direction="vertical", layout=layout).arrange(1600, 1200)

    assert panel.background.width == 600
    assert panel.background.height == 240
    assert label.text_object.scale == 2.5
    assert bar.width == 400
    assert bar.fill.width == 100
    assert bar.fill.height == 40
    assert bar.fill.x == -150


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


def test_ui_manager_integrates_layout_focus_and_activation() -> None:
    scene = Scene()
    ui = UIManager(scene)
    clicks: list[str] = []
    play = ui.button("Play", 0, 0, width=180, height=48, on_click=lambda b: clicks.append(b.text))
    quit_button = ui.button(
        "Quit", 0, 0, width=180, height=48, on_click=lambda b: clicks.append(b.text)
    )
    ui.container(
        play,
        quit_button,
        spacing=16,
        layout=UILayout(
            anchor=UIAnchor.CENTER,
            scale_with_viewport=True,
            reference_width=800,
            reference_height=600,
        ),
    )
    input_state = FakeInput()

    input_state.keys = {"tab"}
    ui.update(input_state, 1600, 1200)
    assert ui.focus.focused is play
    assert play.focused
    assert play.width == 360
    assert quit_button.width == 360

    input_state.keys = {"down"}
    ui.update(input_state, 1600, 1200)
    assert ui.focus.focused is quit_button
    assert quit_button.focused
    assert not play.focused

    input_state.keys = {"enter"}
    ui.update(input_state, 1600, 1200)
    assert clicks == ["Quit"]


def test_mouse_hover_transfers_focus_without_breaking_pointer_clicks() -> None:
    ui = UIManager(Scene())
    clicks: list[str] = []
    first = ui.button("One", -120, 0, 160, 50, on_click=lambda b: clicks.append(b.text))
    second = ui.button("Two", 120, 0, 160, 50, on_click=lambda b: clicks.append(b.text))
    input_state = FakeInput()
    input_state.mouse_x = 520
    input_state.mouse_y = 300

    ui.update(input_state, 800, 600)
    assert ui.focus.focused is second
    assert second.focused
    assert not first.focused

    input_state.pressed = True
    input_state.held = True
    ui.update(input_state, 800, 600)
    input_state.pressed = False
    input_state.held = False
    input_state.released = True
    ui.update(input_state, 800, 600)
    assert clicks == ["Two"]
