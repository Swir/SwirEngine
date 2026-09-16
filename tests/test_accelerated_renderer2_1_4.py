from __future__ import annotations

from swirengine.core.scene import Scene
from swirengine.graphics.accelerated_renderer2 import SceneAcceleratedRenderer2
from swirengine.graphics.camera3d import Camera3D
from swirengine.graphics.csm_renderer import Renderer2
from swirengine.graphics.primitives import Cube3D
from swirengine.math.types import Vec3
from swirengine.scene_acceleration import enable_scene_acceleration


def test_accelerated_renderer2_passes_culled_view_to_base_renderer(monkeypatch) -> None:
    scene = Scene()
    visible = scene.add(Cube3D(position=Vec3(0.0, 0.0, -5.0)))
    scene.add(Cube3D(position=Vec3(100.0, 0.0, -5.0)))
    enable_scene_acceleration(scene, leaf_size=1)
    camera = Camera3D()
    captured: list[object] = []

    def capture(_renderer, candidate_scene, _camera) -> None:
        captured.append(candidate_scene)

    monkeypatch.setattr(Renderer2, "_render_3d", capture)
    renderer = object.__new__(SceneAcceleratedRenderer2)
    renderer.width = 1280
    renderer.height = 720
    renderer._scene_acceleration_diagnostics = None

    SceneAcceleratedRenderer2._render_3d(renderer, scene, camera)

    assert len(captured) == 1
    assert captured[0].objects == (visible,)
    assert renderer.scene_acceleration_diagnostics is not None
    assert renderer.scene_acceleration_diagnostics.query.source_entries == 2
    assert renderer.scene_acceleration_diagnostics.query.visible_entries == 1


def test_accelerated_renderer2_falls_back_when_runtime_is_not_attached(monkeypatch) -> None:
    scene = Scene()
    captured: list[object] = []

    def capture(_renderer, candidate_scene, _camera) -> None:
        captured.append(candidate_scene)

    monkeypatch.setattr(Renderer2, "_render_3d", capture)
    renderer = object.__new__(SceneAcceleratedRenderer2)
    renderer.width = 800
    renderer.height = 600
    renderer._scene_acceleration_diagnostics = None

    SceneAcceleratedRenderer2._render_3d(renderer, scene, Camera3D())

    assert captured == [scene]
    assert renderer.scene_acceleration_diagnostics is None


def test_accelerated_renderer2_rejects_invalid_scene_runtime(monkeypatch) -> None:
    scene = Scene()
    scene.scene_acceleration = object()
    monkeypatch.setattr(Renderer2, "_render_3d", lambda *_args, **_kwargs: None)
    renderer = object.__new__(SceneAcceleratedRenderer2)
    renderer.width = 800
    renderer.height = 600
    renderer._scene_acceleration_diagnostics = None

    try:
        SceneAcceleratedRenderer2._render_3d(renderer, scene, Camera3D())
    except TypeError as exc:
        assert "SceneAccelerationRuntime3D" in str(exc)
    else:
        raise AssertionError("invalid runtime should fail explicitly")
