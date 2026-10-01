from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from swirengine.editor_app21 import EditorProjectSession
from swirengine.editor_asset_app21 import TkIntegratedEditorApp21, run_editor_session21
from swirengine.editor_asset_drop21 import TkNativeDropAssetPipelineEditorApp21
from swirengine.editor_extension_frontend22 import TkEditorExtensionHostApp22
from swirengine.editor_integrated_session21 import EditorIntegratedProjectSession21
from swirengine.editor_preview import EditorViewportImage
from swirengine.editor_ui_designer22 import (
    MAX_UI_DESIGNER_PREVIEW_DIMENSION,
    MAX_UI_DESIGNER_PREVIEW_STEP,
    EditorUIDesignerPanelController22,
    UIDesignerPreview22,
)
from swirengine.editor_ui_designer_frontend22 import TkUIDesignerEditorApp22
from swirengine.project_scaffold21 import new_project21
from swirengine.ui_designer22 import (
    EditorUIDesignerError22,
    EditorUIDesignerTooling22,
    UIAnimationKeyframeSpec22,
    UIAnimationSpec22,
    UIAnimationTrackSpec22,
    UIStyleSpec22,
    UIWidgetSpec22,
)


class CaptureProbe(UIDesignerPreview22):
    def capture(self, width: int, height: int) -> EditorViewportImage:
        if self.closed:
            raise RuntimeError("closed preview")
        width = min(width, MAX_UI_DESIGNER_PREVIEW_DIMENSION)
        height = min(height, MAX_UI_DESIGNER_PREVIEW_DIMENSION)
        self.runtime.layout(width, height)
        self.frames += 1
        return EditorViewportImage(2, 2, b"\x44" * 12)


def _author(controller: EditorUIDesignerPanelController22) -> None:
    controller.upsert_style(
        UIStyleSpec22(
            "primary",
            button=(0.1, 0.2, 0.3, 1.0),
            button_hover=(0.2, 0.3, 0.4, 1.0),
            button_pressed=(0.05, 0.1, 0.2, 1.0),
            button_focused=(0.3, 0.5, 0.8, 1.0),
        )
    )
    controller.upsert_widget(
        UIWidgetSpec22(
            "menu",
            "panel",
            width=500,
            height=360,
            axis="horizontal",
            anchor="top_left",
            offset_x=24,
            offset_y=-24,
        )
    )
    controller.upsert_widget(
        UIWidgetSpec22(
            "play",
            "button",
            parent="menu",
            width=240,
            height=56,
            text="Play",
            style="primary",
            action="start-game",
            enabled=False,
            focusable=True,
        )
    )
    controller.upsert_animation(
        UIAnimationSpec22(
            "pulse",
            1.0,
            (
                UIAnimationTrackSpec22(
                    "play",
                    "opacity",
                    (
                        UIAnimationKeyframeSpec22(0.0, 1.0),
                        UIAnimationKeyframeSpec22(1.0, 0.25),
                    ),
                ),
            ),
        )
    )


def test_preview_lifecycle_animation_controls_and_inert_project_actions(
    tmp_path: Path,
) -> None:
    controller = EditorUIDesignerPanelController22(
        EditorUIDesignerTooling22(tmp_path), preview_factory=CaptureProbe
    )
    _author(controller)
    controller.save()
    saved = EditorUIDesignerTooling22.open(tmp_path).asset
    saved_menu = next(widget for widget in saved.widgets if widget.id == "menu")
    saved_button = next(widget for widget in saved.widgets if widget.id == "play")
    saved_style = next(style for style in saved.styles if style.name == "primary")
    assert saved_menu.anchor == "top_left" and saved_menu.axis == "horizontal"
    assert not saved_button.enabled and saved_button.focusable is True
    assert saved_style.button_hover == (0.2, 0.3, 0.4, 1.0)
    frame = controller.start("pulse")
    preview = controller.preview
    assert preview is not None and frame.preview_active and frame.preview_running
    assert preview.runtime.scene is not None
    assert controller.capture() is not None
    menu = preview.runtime.toolkit.find("menu")
    button = preview.runtime.toolkit.find("play")
    assert menu is not None and menu.anchor.value == "top_left"
    assert menu.axis.value == "horizontal"
    assert button is not None and not button.enabled and button.focusable

    controller.pause()
    paused_frames = preview.frames
    assert controller.capture() is not None
    assert preview.frames == paused_frames
    before = controller.frame().preview_time
    stepped = controller.step(1.0)
    assert not stepped.preview_running
    assert stepped.preview_time > before
    assert stepped.preview_time - before <= MAX_UI_DESIGNER_PREVIEW_STEP
    assert controller.capture() is not None
    assert preview.frames == paused_frames + 1
    controller.seek(0.75)
    assert controller.frame().preview_time == pytest.approx(0.75)
    controller.resume()
    controller.update_preview(1.0, 480, 320)
    assert controller.frame().preview_time >= 0.75

    controller.stop()
    controller.stop()
    assert preview.closed
    assert not controller.active and controller.image is None


def test_valid_edit_rebuilds_once_and_invalid_edit_preserves_live_preview(
    tmp_path: Path,
) -> None:
    tooling = EditorUIDesignerTooling22(tmp_path)
    controller = EditorUIDesignerPanelController22(tooling, preview_factory=CaptureProbe)
    _author(controller)
    controller.save()
    controller.start("pulse")
    controller.capture()
    original = controller.preview
    button = next(widget for widget in tooling.asset.widgets if widget.id == "play")

    with pytest.raises(EditorUIDesignerError22):
        controller.upsert_widget(replace(button, parent="missing"))
    assert controller.preview is original
    assert controller.active and controller.running and not tooling.dirty

    controller.upsert_widget(replace(button, text="Launch"))
    replacement = controller.preview
    assert original is not None and original.closed
    assert replacement is not None and replacement is not original
    controller.capture()
    assert controller.preview is replacement
    controller.stop()


def test_external_fingerprint_change_invalidates_preview_before_reuse(tmp_path: Path) -> None:
    tooling = EditorUIDesignerTooling22(tmp_path)
    controller = EditorUIDesignerPanelController22(tooling, preview_factory=CaptureProbe)
    _author(controller)
    controller.start("pulse")
    original = controller.preview
    button = next(widget for widget in tooling.asset.widgets if widget.id == "play")
    tooling.upsert_widget(replace(button, text="Changed outside panel"))
    controller.capture()
    assert original is not None and original.closed
    assert controller.preview is not original
    controller.stop()


def test_rejected_reload_preserves_live_asset_and_preview(tmp_path: Path) -> None:
    tooling = EditorUIDesignerTooling22(tmp_path)
    controller = EditorUIDesignerPanelController22(tooling, preview_factory=CaptureProbe)
    _author(controller)
    controller.save()
    asset = tooling.asset
    controller.start("pulse")
    preview = controller.preview
    tooling.target.write_text("{invalid", encoding="ascii")

    with pytest.raises(EditorUIDesignerError22, match="cannot load"):
        controller.reload()

    assert tooling.asset is asset and not tooling.dirty
    assert controller.preview is preview and controller.active and controller.running
    controller.stop()


def test_renderer_failure_closes_runtime_and_releases_backend(tmp_path: Path) -> None:
    class Viewport:
        def capture(self, *_args, **_kwargs):
            raise RuntimeError("renderer failed")

    class Backend:
        def __init__(self) -> None:
            self.viewport = Viewport()
            self.released = False

        def release(self) -> None:
            self.released = True

    backend = Backend()
    tooling = EditorUIDesignerTooling22(tmp_path)
    controller = EditorUIDesignerPanelController22(
        tooling,
        preview_factory=lambda active: UIDesignerPreview22(
            active, backend_factory=lambda *_args: backend
        ),
    )
    controller.upsert_widget(UIWidgetSpec22("title", "label", text="Title"))
    controller.start()
    preview = controller.preview
    with pytest.raises(RuntimeError, match="renderer failed"):
        controller.capture()
    assert preview is not None and preview.closed and backend.released
    assert not controller.active and not controller.running and controller.image is None
    assert "renderer failed" in controller.status


def test_integrated_session_saves_reopens_and_adopts_ui_designer(tmp_path: Path) -> None:
    root = new_project21("UIDesigner", "2d", parent=tmp_path)
    session = EditorIntegratedProjectSession21.open(root)
    session.ui_designer.upsert_widget(UIWidgetSpec22("title", "label", text="SWIR"))
    assert session.ui_hud is not None
    assert session.summary().dirty
    session.save()
    assert not session.summary().dirty
    assert session.ui_designer.target.is_file()

    reopened = EditorIntegratedProjectSession21.open(root)
    assert tuple(widget.id for widget in reopened.ui_designer.asset.widgets) == ("title",)
    assert not reopened.summary().dirty

    base = EditorProjectSession.open(root)
    promoted = EditorIntegratedProjectSession21.adopt(base)
    assert promoted.controller is base.controller
    assert promoted.workspace is base.workspace
    assert promoted.ui_designer.target.parent == root.resolve() / "config"


def test_integrated_shell_keeps_ui_designer_under_extension_host_first() -> None:
    assert TkIntegratedEditorApp21.__bases__[0] is TkEditorExtensionHostApp22
    assert issubclass(TkEditorExtensionHostApp22, TkUIDesignerEditorApp22)
    assert issubclass(TkIntegratedEditorApp21, TkUIDesignerEditorApp22)
    assert issubclass(TkIntegratedEditorApp21, TkNativeDropAssetPipelineEditorApp21)


def test_run_editor_session_routes_project_ui_designer(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import swirengine.editor_asset_app21 as asset_app

    root = new_project21("UIDesignerRouting", "2d", parent=tmp_path)
    session = EditorIntegratedProjectSession21.open(root)
    captured: dict[str, object] = {}

    class Workflow:
        def shutdown(self) -> None:
            captured["shutdown"] = True

    monkeypatch.setattr(
        asset_app,
        "create_format_aware_editor_asset_pipeline21",
        lambda _manager: object(),
    )
    monkeypatch.setattr(
        asset_app,
        "EditorAssetWorkflow21",
        lambda _backend, _browser: Workflow(),
    )
    monkeypatch.setattr(
        asset_app,
        "AnimationProjectResourceResolver22",
        lambda _root: object(),
    )

    def init_app(self, controller, **kwargs):
        captured["controller"] = controller
        captured.update(kwargs)

    monkeypatch.setattr(TkIntegratedEditorApp21, "__init__", init_app)
    monkeypatch.setattr(
        TkIntegratedEditorApp21,
        "run",
        lambda _self: captured.__setitem__("ran", True),
    )
    monkeypatch.setattr(session, "enable_live_viewport", lambda: None)
    monkeypatch.setattr(session, "disable_live_viewport", lambda: None)
    monkeypatch.setattr(session, "_install_file_menu", lambda _app: None)
    monkeypatch.setattr(session, "_schedule_recovery", lambda _app: None)

    run_editor_session21(session)

    assert captured["ui_designer"] is session.ui_designer
    assert captured["controller"] is session.controller
    assert captured["ran"] is True and captured["shutdown"] is True
