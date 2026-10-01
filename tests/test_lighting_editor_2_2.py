from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from swirengine.core.scene import Scene
from swirengine.editor_lighting22 import (
    MAX_LIGHTING_PREVIEW_OBJECTS,
    EditorLightingPanelController22,
    LightingScenePreview22,
    LightingSceneSource22,
)
from swirengine.editor_preview import EditorViewportImage
from swirengine.graphics.camera import Camera2D
from swirengine.graphics.camera3d import Camera3D
from swirengine.graphics.primitives import Cube3D, Rectangle2D
from swirengine.lighting_authoring22 import (
    EditorLightingError22,
    EditorLightingTooling22,
    LightSpec22,
)
from swirengine.serialization import SceneSerializer


class CaptureProbe(LightingScenePreview22):
    """CPU lifecycle probe only. Real renderer behavior has a required EGL test."""

    def capture(self, width, height, camera):
        if self._closed:
            raise RuntimeError("closed probe")
        self.frames += 1
        return EditorViewportImage(2, 2, b"\x11" * 12)


@pytest.fixture(params=("2d", "3d"))
def setup_controller(tmp_path: Path, request):
    mode = request.param
    scene = Scene()
    scene.add(Cube3D() if mode == "3d" else Rectangle2D(8, 8, 32, 32))
    source = LightingSceneSource22("scenes/main.swirscene", mode, scene,
                                  Camera3D() if mode == "3d" else Camera2D(), SceneSerializer())
    active = [source]
    tool = EditorLightingTooling22(tmp_path)
    controller = EditorLightingPanelController22(tool, lambda: active[0], preview_factory=CaptureProbe)
    return controller, active


def test_panel_authoring_save_reopen_and_preview_snapshot_isolation(setup_controller) -> None:
    controller, active = setup_controller
    source = active[0]
    before = source.serializer.dumps_scene(source.scene)
    assert not controller.tooling.dirty
    controller.update_section("postfx", exposure=1.8, contrast=1.2)
    if source.mode == "3d":
        controller.set_light(LightSpec22("key", intensity=2.0))
        controller.update_section("environment", enabled=True)
        controller.update_section("renderer", shadow_cascades=2)
    assert controller.tooling.dirty
    controller.save()
    canonical = controller.tooling.target.read_bytes()
    assert EditorLightingTooling22(controller.tooling.project_root).profiles() == controller.tooling.profiles()
    controller.start()
    assert controller.running
    assert controller._preview.game.scene is not source.scene
    original_object = source.scene.objects[0]
    cloned_object = controller._preview.game.scene.objects[0]
    assert cloned_object is not original_object
    assert controller.capture() is not None
    preview = controller._preview
    for _ in range(3):
        controller.capture()
        assert controller._preview is preview
    controller.pause()
    frames = preview.frames
    assert controller.capture() is not None
    assert preview.frames == frames
    assert controller.capture(step=True) is not None
    assert preview.frames == frames + 1 and not controller.running
    controller.stop()
    controller.stop()
    assert preview._closed
    assert not controller.active and controller.image is None
    assert source.serializer.dumps_scene(source.scene) == before
    assert controller.tooling.target.read_bytes() == canonical
    assert not controller.tooling.dirty


def test_profile_apply_rebuilds_once_and_scene_switch_fails_closed(setup_controller) -> None:
    controller, active = setup_controller
    controller.start()
    controller.capture()
    old = controller._preview
    controller.update_section("postfx", exposure=2.0)
    assert controller.capture() is not None
    new = controller._preview
    assert old._closed and old is not new
    assert new.game.postprocess.exposure == 2.0
    controller.capture()
    assert controller._preview is new
    active[0] = replace(active[0], key="scenes/other.swirscene", scene=Scene())
    assert controller.capture() is None
    assert not controller.active and not controller.running
    assert new._closed
    assert "scene changed" in controller.status
    controller.start()
    assert controller.spec().scene == "scenes/other.swirscene"
    assert controller.spec().postfx.exposure == 1.0
    controller.stop()


def test_invalid_edits_preserve_saved_profile_and_active_preview(setup_controller) -> None:
    controller, _ = setup_controller
    controller.start()
    controller.save()
    controller.capture()
    spec = controller.spec()
    preview = controller._preview
    image = controller.image
    with pytest.raises(EditorLightingError22):
        controller.update_section("postfx", exposure=float("nan"))
    assert controller.spec() == spec
    assert controller._preview is preview and controller.image is image
    assert controller.running and not controller.tooling.dirty
    controller.stop()


def test_capture_failure_clears_image_and_releases_preview(setup_controller) -> None:
    controller, _ = setup_controller
    controller.start()
    controller.capture()
    preview = controller._preview
    def fail(*args, **kwargs):
        raise RuntimeError("real renderer error")
    preview.capture = fail
    with pytest.raises(RuntimeError, match="real renderer error"):
        controller.capture()
    assert not controller.active and not controller.running and controller.image is None
    assert preview._closed and "real renderer error" in controller.status


def test_live_missing_or_replaced_texture_invalidates_preview(tmp_path: Path) -> None:
    scene = Scene()
    scene.add(Cube3D())
    source = LightingSceneSource22("scene", "3d", scene, Camera3D(), SceneSerializer())
    controller = EditorLightingPanelController22(EditorLightingTooling22(tmp_path), lambda: source,
                                                 preview_factory=CaptureProbe)
    assets = tmp_path / "assets"
    assets.mkdir()
    texture = assets / "sky.png"
    texture.write_bytes(b"path validation fixture; not GPU decoding")
    controller.update_section("environment", enabled=True, skybox_texture="sky.png")
    controller.start()
    controller.capture()
    old = controller._preview
    texture.write_bytes(b"changed asset fingerprint")
    controller.capture()
    assert old._closed and old is not controller._preview
    preview = controller._preview
    controller.pause()
    texture.unlink()
    with pytest.raises(EditorLightingError22, match="missing skybox"):
        controller.capture()
    assert preview._closed and not controller.active and controller.image is None


def test_pause_rebuild_and_same_path_reload_are_isolated(setup_controller) -> None:
    controller, active = setup_controller
    controller.start()
    controller.capture()
    controller.pause()
    old = controller._preview
    controller.update_section("postfx", exposure=2.2)
    controller.capture(step=True)
    assert old._closed and not controller.running
    current = controller._preview
    active[0] = replace(active[0], scene=Scene())
    assert not controller.sync_scene()
    assert current._closed and not controller.active


def test_light_controls_and_snapshot_budget(setup_controller) -> None:
    controller, active = setup_controller
    if active[0].mode == "3d":
        controller.set_light(LightSpec22("fill", kind="point", intensity=0.5))
        controller.set_light(LightSpec22("fill", kind="point", intensity=1.5))
        assert len(controller.spec().lights) == 1
        assert controller.spec().lights[0].intensity == 1.5
        controller.remove_light("fill")
        assert controller.spec().lights == ()
    else:
        with pytest.raises(EditorLightingError22, match="2D"):
            controller.set_light(LightSpec22("ignored"))
    active[0].scene.add_many(*(object() for _ in range(MAX_LIGHTING_PREVIEW_OBJECTS)))
    with pytest.raises(EditorLightingError22, match="object budget"):
        controller.start()
    assert not controller.active


def test_tk_field_parsing_does_not_coerce_bad_integer_or_boolean() -> None:
    from swirengine.editor_lighting_frontend22 import _parse_field
    assert _parse_field("1, 2, 3", (0., 0., 0.)) == (1., 2., 3.)
    assert _parse_field("", None) is None
    with pytest.raises(ValueError):
        _parse_field("1.5", 1)
    with pytest.raises(ValueError):
        _parse_field("false", False)
