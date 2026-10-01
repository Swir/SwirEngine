from __future__ import annotations

import hashlib
import json

import pytest

from swirengine.core.scene import Scene
from swirengine.graphics.primitives import Rectangle2D
from swirengine.ui import UIButton
from swirengine.ui15 import UIToolkit
from swirengine.ui_designer22 import (
    EditorUIDesignerError22,
    UIAnimationKeyframeSpec22,
    UIAnimationSpec22,
    UIAnimationTrackSpec22,
    UIDesignAsset22,
    UIStyleSpec22,
    UIWidgetSpec22,
    build_ui_runtime22,
)


class InputFrame:
    mouse_x = -10_000.0
    mouse_y = -10_000.0

    def __init__(self) -> None:
        self.keys: set[str] = set()
        self.pad: set[str] = set()

    def mouse_button_pressed(self, _button: int) -> bool:
        return False

    def mouse_button_released(self, _button: int) -> bool:
        return False

    def mouse_button(self, _button: int) -> bool:
        return False

    def key_pressed(self, name: str) -> bool:
        return name in self.keys

    def key(self, _name: str) -> bool:
        return False

    def gamepads(self) -> tuple[int, ...]:
        return (0,)

    def gamepad_button_pressed(self, name: str, _device: int = 0) -> bool:
        return name in self.pad


def runtime_asset() -> UIDesignAsset22:
    return UIDesignAsset22(
        styles=(
            UIStyleSpec22(
                "primary",
                text=(1.0, 0.8, 0.6, 0.8),
                button=(0.2, 0.4, 0.6, 0.8),
                button_hover=(0.3, 0.5, 0.7, 0.8),
                font_size=30,
            ),
        ),
        widgets=(
            UIWidgetSpec22(
                "menu",
                "panel",
                width=500,
                height=320,
                padding=20,
                anchor="top_right",
                opacity=0.5,
            ),
            UIWidgetSpec22(
                "play",
                "button",
                parent="menu",
                order=0,
                width=200,
                height=60,
                text="Play",
                style="primary",
                action="start",
                opacity=0.5,
            ),
            UIWidgetSpec22(
                "options",
                "button",
                parent="menu",
                order=1,
                width=200,
                height=60,
                text="Options",
            ),
            UIWidgetSpec22(
                "badge",
                "label",
                parent="menu",
                width=80,
                height=30,
                text="NEW",
                anchor="bottom_right",
            ),
        ),
        animations=(
            UIAnimationSpec22(
                "pulse",
                1.0,
                (
                    UIAnimationTrackSpec22(
                        "play",
                        "opacity",
                        (
                            UIAnimationKeyframeSpec22(0.0, 1.0),
                            UIAnimationKeyframeSpec22(1.0, 0.0),
                        ),
                    ),
                    UIAnimationTrackSpec22(
                        "play",
                        "width",
                        (
                            UIAnimationKeyframeSpec22(0.0, 200.0),
                            UIAnimationKeyframeSpec22(1.0, 300.0),
                        ),
                    ),
                ),
            ),
        ),
    )


def test_top_level_anchor_uses_viewport_and_nested_anchor_uses_parent() -> None:
    runtime = build_ui_runtime22(runtime_asset(), handlers={"start": lambda _widget: None})
    runtime.layout(1920, 720)
    menu = runtime.toolkit.find("menu")
    badge = runtime.toolkit.find("badge")
    assert menu is not None and badge is not None
    assert menu.rect.right == pytest.approx(960.0)
    assert menu.rect.top == pytest.approx(360.0)
    assert badge.rect.right == pytest.approx(menu.rect.right - 20.0)
    assert badge.rect.bottom == pytest.approx(menu.rect.bottom + 20.0)

    runtime.layout(720, 1280)
    assert menu.rect.right == pytest.approx(360.0)
    assert menu.rect.top == pytest.approx(640.0)
    assert badge.rect.right == pytest.approx(menu.rect.right - 20.0 * 0.5625)
    runtime.close()


def test_style_and_opacity_are_opt_in_and_inherited() -> None:
    runtime = build_ui_runtime22(runtime_asset(), handlers={"start": lambda _widget: None})
    runtime.layout(1280, 720)
    play = runtime.toolkit.find("play")
    assert play is not None and isinstance(play.control, UIButton)
    assert play.effective_opacity == pytest.approx(0.25)
    assert play.control.color.a == pytest.approx(0.2)
    assert play.control.hover_color.a == pytest.approx(0.2)
    assert play.control.label.color.a == pytest.approx(0.2)
    assert play.control.label.font_size == 30
    runtime.close()


def test_animation_uses_animation15_and_separates_manual_step_from_update() -> None:
    runtime = build_ui_runtime22(runtime_asset(), handlers={"start": lambda _widget: None})
    runtime.layout(1280, 720)
    play = runtime.toolkit.find("play")
    assert play is not None
    runtime.play("pulse")
    runtime.seek(0.25)
    assert play.opacity == pytest.approx(0.75)
    assert play.width == pytest.approx(225.0)

    runtime.pause()
    runtime.update(0.25)
    assert runtime.time == pytest.approx(0.25)
    runtime.step(0.25)
    assert runtime.time == pytest.approx(0.5)
    assert runtime.paused
    assert play.opacity == pytest.approx(0.5)

    runtime.stop(restore=False)
    assert play.opacity == pytest.approx(0.5)
    runtime.play("pulse")
    runtime.seek(1.0)
    assert not runtime.playing and play.opacity == pytest.approx(0.0)
    runtime.stop(restore=True)
    assert play.opacity == pytest.approx(0.5)
    assert play.width == pytest.approx(200.0)
    runtime.close()


def test_handlers_are_explicit_and_input_uses_unchanged_focus_model() -> None:
    asset = runtime_asset()
    with pytest.raises(EditorUIDesignerError22, match="handlers"):
        build_ui_runtime22(asset)
    with pytest.raises(EditorUIDesignerError22, match="unknown"):
        build_ui_runtime22(
            asset,
            handlers={"start": lambda _widget: None, "typo": lambda _widget: None},
        )
    with pytest.raises(EditorUIDesignerError22, match="names must be strings"):
        build_ui_runtime22(asset, handlers={1: lambda _widget: None})  # type: ignore[dict-item]
    with pytest.raises(EditorUIDesignerError22, match="values must be callable"):
        build_ui_runtime22(asset, handlers={"start": object()})  # type: ignore[dict-item]

    activated: list[str] = []
    runtime = build_ui_runtime22(
        asset,
        handlers={"start": lambda widget: activated.append(widget.id)},
    )
    input_frame = InputFrame()
    input_frame.keys = {"tab"}
    runtime.update(input_frame, 1280, 720, dt=0.0)
    assert runtime.toolkit.focused is runtime.toolkit.find("play")
    input_frame.keys.clear()
    input_frame.pad = {"dpad_down"}
    runtime.update(input_frame, 1280, 720, dt=0.0)
    assert runtime.toolkit.focused is runtime.toolkit.find("options")
    input_frame.pad = {"dpad_up"}
    runtime.update(input_frame, 1280, 720, dt=0.0)
    input_frame.pad = {"a"}
    runtime.update(input_frame, 1280, 720, dt=0.0)
    assert activated == ["play"]
    runtime.close()


def test_close_removes_only_owned_controls_and_is_idempotent() -> None:
    scene = Scene()
    unrelated = Rectangle2D(0, 0, 1, 1)
    scene.add(unrelated)
    runtime = build_ui_runtime22(
        runtime_asset(),
        scene,
        handlers={"start": lambda _widget: None},
    )
    assert len(scene.objects) > 1
    runtime.close()
    runtime.close()
    assert scene.objects == (unrelated,)
    with pytest.raises(EditorUIDesignerError22, match="closed"):
        runtime.layout(1280, 720)


def test_legacy_ui_snapshot_and_fingerprint_do_not_gain_opt_in_fields() -> None:
    toolkit = UIToolkit(Scene())
    toolkit.button("play", "Play")
    snapshot = toolkit.snapshot()
    node = snapshot["nodes"][0]
    assert "anchor" not in node
    assert "style" not in node
    assert "opacity" not in node
    payload = json.dumps(snapshot, sort_keys=True, separators=(",", ":"), allow_nan=False)
    assert toolkit.fingerprint() == hashlib.sha256(payload.encode("utf-8")).hexdigest()
