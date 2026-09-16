from __future__ import annotations

import swirengine as swir
from swirengine.core.scene import Scene
from swirengine.graphics.camera3d import Camera3D
from swirengine.graphics.primitives import Cube3D
from swirengine.math.types import Vec3
from swirengine.scene_acceleration import (
    SceneAccelerationRuntime3D,
    disable_scene_acceleration,
    enable_scene_acceleration,
)


class _FallbackRenderObject:
    enabled = True
    visible = True


def test_scene_acceleration_filters_indexed_objects_and_keeps_fallbacks() -> None:
    scene = Scene()
    visible = scene.add(Cube3D(position=Vec3(0.0, 0.0, -5.0)))
    hidden = scene.add(Cube3D(position=Vec3(100.0, 0.0, -5.0)))
    fallback = scene.add(_FallbackRenderObject())
    runtime = SceneAccelerationRuntime3D(leaf_size=1)

    frame = runtime.frame(scene, Camera3D(), width=1280, height=720)

    assert visible in frame.view.objects
    assert hidden not in frame.view.objects
    assert fallback in frame.view.objects
    assert frame.diagnostics.indexed_entries == 2
    assert frame.diagnostics.fallback_entries == 1
    assert frame.diagnostics.query.visible_entries == 1


def test_scene_snapshot_is_not_rescanned_until_membership_changes() -> None:
    scene = Scene()
    scene.add(Cube3D(position=Vec3(0.0, 0.0, -5.0)))
    runtime = SceneAccelerationRuntime3D()
    camera = Camera3D()

    first = runtime.frame(scene, camera, width=800, height=600)
    second = runtime.frame(scene, camera, width=800, height=600)
    assert first.diagnostics.snapshot_rebuilds == 1
    assert second.diagnostics.snapshot_rebuilds == 1

    scene.add(Cube3D(position=Vec3(2.0, 0.0, -6.0)))
    third = runtime.frame(scene, camera, width=800, height=600)
    assert third.diagnostics.snapshot_rebuilds == 2
    assert third.diagnostics.indexed_entries == 2


def test_dynamic_cube_refits_without_rebuilding_static_bvh() -> None:
    scene = Scene()
    scene.add(Cube3D(position=Vec3(0.0, 0.0, -5.0)))
    moving = scene.add(
        Cube3D(position=Vec3(100.0, 0.0, -5.0), visibility_dynamic=True)
    )
    runtime = SceneAccelerationRuntime3D(leaf_size=1)
    camera = Camera3D()

    first = runtime.frame(scene, camera, width=1280, height=720)
    rebuilds = runtime.index.rebuilds
    assert moving not in first.view.objects

    moving.position = Vec3(1.0, 0.0, -5.0)
    second = runtime.frame(scene, camera, width=1280, height=720)

    assert moving in second.view.objects
    assert runtime.index.rebuilds == rebuilds
    assert runtime.index.refits >= 2


def test_acceleration_view_preserves_scene_registration_order_for_candidates() -> None:
    scene = Scene()
    first = scene.add(Cube3D(position=Vec3(-1.0, 0.0, -5.0)))
    fallback = scene.add(_FallbackRenderObject())
    second = scene.add(Cube3D(position=Vec3(1.0, 0.0, -5.0)))
    runtime = SceneAccelerationRuntime3D(leaf_size=1)

    frame = runtime.frame(scene, Camera3D(), width=800, height=600)
    assert frame.view.objects == (first, fallback, second)


def test_enable_and_disable_scene_acceleration_attach_runtime() -> None:
    scene = Scene()
    runtime = enable_scene_acceleration(scene, leaf_size=3)

    assert scene.scene_acceleration is runtime
    assert runtime.index.leaf_size == 3
    assert disable_scene_acceleration(scene) is True
    assert not hasattr(scene, "scene_acceleration")
    assert disable_scene_acceleration(scene) is False


def test_scene_acceleration_public_api_is_top_level() -> None:
    assert swir.SceneAccelerationRuntime3D is SceneAccelerationRuntime3D
    assert swir.SceneVisibilityIndex3D.__name__ == "SceneVisibilityIndex3D"
    assert swir.SceneAcceleratedRenderer2.__name__ == "SceneAcceleratedRenderer2"
    assert swir.HiZDepthPyramid3D.__name__ == "HiZDepthPyramid3D"
    assert swir.HiZPyramidPass3D.__name__ == "HiZPyramidPass3D"
    assert swir.enable_scene_acceleration is enable_scene_acceleration
    assert swir.disable_scene_acceleration is disable_scene_acceleration
