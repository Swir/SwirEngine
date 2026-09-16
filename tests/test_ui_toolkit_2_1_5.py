from __future__ import annotations

import pytest

from swirengine.core.scene import Scene
from swirengine.math.types import Color
from swirengine.ui import UIButton, UIPanel
from swirengine.ui15 import (
    UIAlign,
    UIAxis,
    UIInsets,
    UIJustify,
    UINavigationDirection,
    UITheme,
    UIToolkit,
)


class FakeInput:
    def __init__(self) -> None:
        self.mouse_x = 640.0
        self.mouse_y = 360.0
        self.held = False
        self.pressed = False
        self.released = False
        self.keys: set[str] = set()
        self.held_keys: set[str] = set()
        self.pad: set[str] = set()

    def mouse_button(self, button: int) -> bool:
        return button == 0 and self.held

    def mouse_button_pressed(self, button: int) -> bool:
        return button == 0 and self.pressed

    def mouse_button_released(self, button: int) -> bool:
        return button == 0 and self.released

    def key_pressed(self, name: str) -> bool:
        return name in self.keys

    def key(self, name: str) -> bool:
        return name in self.held_keys

    def gamepads(self) -> tuple[int, ...]:
        return (0,)

    def gamepad_button_pressed(self, name: str, gamepad_id: int = 0) -> bool:
        return gamepad_id == 0 and name in self.pad


def build_menu(*, callback=None) -> tuple[UIToolkit, object, object, object]:
    toolkit = UIToolkit(Scene(), min_scale=0.25, max_scale=4.0)
    panel = toolkit.panel(
        "menu",
        480,
        320,
        padding=UIInsets.all(24),
        gap=18,
        justify=UIJustify.CENTER,
    )
    title = toolkit.label("title", "SwirEngine", parent=panel, height=42)
    play = toolkit.button("play", "Play", parent=panel, on_activate=callback)
    quit_button = toolkit.button("quit", "Quit", parent=panel)
    return toolkit, title, play, quit_button


def test_retained_tree_layout_scales_from_reference_resolution() -> None:
    toolkit, title, play, quit_button = build_menu()

    assert toolkit.layout(1280, 720) == pytest.approx(1.0)
    menu = toolkit.find("menu")
    assert menu is not None
    assert menu.rect.width == pytest.approx(480)
    assert menu.rect.height == pytest.approx(320)
    assert menu.rect.x == pytest.approx(0)
    assert menu.rect.y == pytest.approx(0)
    assert title.rect.y > play.rect.y > quit_button.rect.y

    assert toolkit.layout(2560, 1440) == pytest.approx(2.0)
    assert menu.rect.width == pytest.approx(960)
    assert play.rect.width == pytest.approx(480)
    assert title.rect.y > play.rect.y > quit_button.rect.y


def test_horizontal_layout_and_spatial_focus_navigation() -> None:
    toolkit = UIToolkit(Scene())
    row = toolkit.stack("row", 800, 100, axis=UIAxis.HORIZONTAL, gap=30)
    left = toolkit.button("left", "Left", parent=row, width=180)
    middle = toolkit.button("middle", "Middle", parent=row, width=180)
    right = toolkit.button("right", "Right", parent=row, width=180)
    toolkit.layout(1280, 720)

    assert left.rect.x < middle.rect.x < right.rect.x
    assert toolkit.focus(middle) is middle
    assert toolkit.focus_move(UINavigationDirection.RIGHT) is right
    assert toolkit.focus_move(UINavigationDirection.LEFT) is middle
    assert toolkit.focus_move(UINavigationDirection.LEFT) is left


def test_hidden_and_disabled_ancestors_remove_descendants_from_focus() -> None:
    toolkit, _title, play, quit_button = build_menu()
    toolkit.layout(1280, 720)
    assert toolkit.focusable_widgets() == (play, quit_button)

    menu = toolkit.find("menu")
    assert menu is not None
    menu.enabled = False
    toolkit.layout(1280, 720)
    assert toolkit.focusable_widgets() == ()

    menu.enabled = True
    play.visible = False
    toolkit.layout(1280, 720)
    assert toolkit.focusable_widgets() == (quit_button,)
    assert isinstance(play.control, UIButton)
    assert not play.control.visible


def test_pointer_activation_requires_press_and_release_on_same_widget() -> None:
    activated: list[str] = []
    toolkit, _title, play, _quit_button = build_menu(callback=lambda widget: activated.append(widget.id))
    toolkit.layout(1280, 720)

    toolkit.pointer(play.rect.x, play.rect.y, pressed=True, released=False, down=True)
    assert toolkit.focused is play
    assert isinstance(play.control, UIButton)
    assert play.control.pressed

    toolkit.pointer(play.rect.x, play.rect.y, pressed=False, released=True, down=False)
    assert activated == ["play"]
    assert not play.control.pressed
    assert toolkit.diagnostics().activations == 1


def test_pointer_release_on_different_button_does_not_activate() -> None:
    activated: list[str] = []
    toolkit, _title, play, quit_button = build_menu(callback=lambda widget: activated.append(widget.id))
    toolkit.layout(1280, 720)

    toolkit.pointer(play.rect.x, play.rect.y, pressed=True, released=False, down=True)
    toolkit.pointer(quit_button.rect.x, quit_button.rect.y, pressed=False, released=True, down=False)
    assert activated == []


def test_keyboard_and_gamepad_navigation_share_the_same_focus_model() -> None:
    toolkit, _title, play, quit_button = build_menu()
    input_state = FakeInput()

    input_state.keys = {"tab"}
    toolkit.update(input_state, 1280, 720)
    assert toolkit.focused is play

    input_state.keys = set()
    input_state.pad = {"dpad_down"}
    toolkit.update(input_state, 1280, 720)
    assert toolkit.focused is quit_button


def test_theme_propagates_to_stable_renderer_controls() -> None:
    toolkit, _title, play, _quit_button = build_menu()
    toolkit.layout(1280, 720)
    theme = UITheme(
        panel=Color(0.1, 0.2, 0.3, 1.0),
        text=Color(0.9, 0.8, 0.7, 1.0),
        button=Color(0.2, 0.3, 0.4, 1.0),
        button_hover=Color(0.3, 0.4, 0.5, 1.0),
        button_pressed=Color(0.1, 0.1, 0.2, 1.0),
        button_focused=Color(0.5, 0.6, 0.7, 1.0),
        progress_background=Color(0.05, 0.05, 0.05, 1.0),
        progress_fill=Color(0.2, 0.8, 0.4, 1.0),
    )
    toolkit.set_theme(theme)

    panel = toolkit.find("menu")
    assert panel is not None and isinstance(panel.control, UIPanel)
    assert panel.control.background.color == theme.panel
    assert isinstance(play.control, UIButton)
    assert play.control.color == theme.button
    assert play.control.label.color == theme.text


def test_progress_value_and_theme_are_synced() -> None:
    toolkit = UIToolkit(Scene())
    panel = toolkit.panel("hud", 500, 120)
    bar = toolkit.progress("health", parent=panel, value=0.25)
    toolkit.layout(1280, 720)
    assert bar.control is not None
    assert bar.control.value == pytest.approx(0.25)

    bar.value = 0.75
    toolkit.layout(1280, 720)
    assert bar.control.value == pytest.approx(0.75)
    assert bar.control.fill.width == pytest.approx(bar.rect.width * 0.75)


def test_reparent_rejects_cycles_and_preserves_registry() -> None:
    toolkit = UIToolkit(Scene())
    outer = toolkit.stack("outer", 600, 500)
    inner = toolkit.stack("inner", 400, 300, parent=outer)
    button = toolkit.button("action", "Action", parent=inner)

    with pytest.raises(ValueError, match="cycles"):
        toolkit.reparent(outer, inner)

    assert toolkit.reparent(button, outer) is button
    assert button.parent is outer
    assert toolkit.find("action") is button


def test_duplicate_ids_are_rejected_without_mutating_tree() -> None:
    toolkit = UIToolkit(Scene())
    toolkit.stack("menu", 500, 400)
    before = toolkit.fingerprint()
    with pytest.raises(ValueError, match="duplicate widget id"):
        toolkit.button("menu", "Duplicate")
    assert toolkit.fingerprint() == before


def test_remove_recursively_detaches_scene_controls_and_focus() -> None:
    scene = Scene()
    toolkit = UIToolkit(scene)
    panel = toolkit.panel("panel", 400, 240)
    button = toolkit.button("button", "Delete", parent=panel)
    toolkit.layout(1280, 720)
    toolkit.focus(button)
    assert button.control is not None
    rendered_children = tuple(button.control.children)
    assert all(child in scene for child in rendered_children)

    assert toolkit.remove(panel)
    assert toolkit.find("panel") is None
    assert toolkit.find("button") is None
    assert toolkit.focused is None
    assert all(child not in scene for child in rendered_children)


def test_fingerprint_is_deterministic_and_ignores_callback_identity() -> None:
    first, *_ = build_menu(callback=lambda _widget: None)
    second, *_ = build_menu(callback=lambda _widget: 123)
    assert first.snapshot() == second.snapshot()
    assert first.fingerprint() == second.fingerprint()

    second.find("play").text = "Continue"  # type: ignore[union-attr]
    assert first.fingerprint() != second.fingerprint()


def test_input_validation_rejects_non_finite_geometry() -> None:
    toolkit = UIToolkit(Scene())
    with pytest.raises(ValueError, match="finite"):
        toolkit.stack("bad", float("nan"), 100)
    with pytest.raises(ValueError, match="positive"):
        toolkit.layout(0, 720)


def test_diagnostics_report_real_layout_and_focus_state() -> None:
    toolkit, _title, play, _quit_button = build_menu()
    toolkit.layout(1920, 1080)
    toolkit.focus(play)
    diagnostics = toolkit.diagnostics()
    assert diagnostics.nodes == 4
    assert diagnostics.visible_nodes == 4
    assert diagnostics.focusable_nodes == 2
    assert diagnostics.layout_generation == 1
    assert diagnostics.focused_id == "play"
    assert diagnostics.scale == pytest.approx(1.5)
    assert diagnostics.viewport == (1920, 1080)


def test_stretch_alignment_uses_parent_inner_cross_axis() -> None:
    toolkit = UIToolkit(Scene())
    panel = toolkit.panel(
        "panel",
        600,
        300,
        padding=20,
        align=UIAlign.STRETCH,
        justify=UIJustify.START,
    )
    button = toolkit.button("wide", "Wide", parent=panel, width=100)
    toolkit.layout(1280, 720)
    assert button.rect.width == pytest.approx(560)
