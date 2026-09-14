import numpy as np
import pytest

from swirengine.graphics.camera3d import Camera3D
from swirengine.graphics.instancing import (
    Frustum3D,
    Instance3D,
    InstancedCube3D,
    InstancedMesh3D,
)
from swirengine.graphics.mesh import cube_mesh
from swirengine.math.types import Color, Transform, Vec3, perspective


def test_identity_frustum_accepts_origin_and_rejects_far_sphere():
    frustum = Frustum3D.from_view_projection(np.eye(4, dtype="f4"))

    assert frustum.sphere_visible(Vec3(0.0, 0.0, 0.0), 0.1)
    assert frustum.sphere_visible(Vec3(1.05, 0.0, 0.0), 0.1)
    assert not frustum.sphere_visible(Vec3(1.2, 0.0, 0.0), 0.1)


def test_camera_frustum_culls_behind_camera():
    camera = Camera3D(
        position=Vec3(0.0, 0.0, 0.0),
        target=Vec3(0.0, 0.0, -1.0),
        near=0.1,
        far=100.0,
    )
    projection = perspective(camera.fov, 16.0 / 9.0, camera.near, camera.far)
    frustum = Frustum3D.from_view_projection(projection @ camera.view_matrix())

    assert frustum.sphere_visible(Vec3(0.0, 0.0, -5.0), 0.5)
    assert not frustum.sphere_visible(Vec3(0.0, 0.0, 5.0), 0.5)


def test_instanced_cube_ergonomics_are_additive_and_mutable():
    batch = InstancedCube3D(color=Color(0.2, 0.7, 1.0, 1.0), name="forest")

    first = batch.add_cube(position=Vec3(1.0, 2.0, -3.0), size=2.0)
    second = batch.add_instance(position=Vec3(-1.0, 0.0, -4.0))

    assert batch.instance_count == 2
    assert first.scale == Vec3(2.0, 2.0, 2.0)
    assert batch.remove_instance(first)
    assert not batch.remove_instance(first)
    assert batch.instances == [second]

    batch.clear_instances()
    assert batch.instance_count == 0


def test_prepare_packs_model_matrix_without_per_instance_transform_matrix():
    batch = InstancedMesh3D(cube_mesh(), cull=False)
    instance = batch.add_instance(
        position=Vec3(1.0, 2.0, 3.0),
        rotation=Vec3(10.0, 20.0, 30.0),
        scale=Vec3(2.0, 3.0, 4.0),
        color=Color(0.1, 0.2, 0.3, 0.4),
    )
    staging = np.empty((8, 20), dtype="f4")

    prepared = batch.prepare(np.eye(4, dtype="f4"), staging=staging)

    expected = Transform(
        position=instance.position,
        rotation=instance.rotation,
        scale=instance.scale,
    ).matrix()
    packed_model = prepared.data[0, :16].reshape(4, 4).T
    assert np.allclose(packed_model, expected, atol=1e-6)
    assert prepared.data.base is staging or np.shares_memory(prepared.data, staging)
    assert prepared.data[0, 16:20] == pytest.approx((0.1, 0.2, 0.3, 0.4))


def test_prepare_reuses_staging_and_reports_instancing_draw_call_reduction():
    batch = InstancedCube3D(cull=False)
    for index in range(1000):
        batch.add_cube(position=Vec3(float(index), 0.0, -10.0))

    staging = np.empty((1000, 20), dtype="f4")
    prepared = batch.prepare(np.eye(4, dtype="f4"), staging=staging)
    metrics = prepared.diagnostics

    assert metrics.source_instances == 1000
    assert metrics.active_instances == 1000
    assert metrics.visible_instances == 1000
    assert metrics.culled_instances == 0
    assert metrics.draw_calls_before == 1000
    assert metrics.draw_calls_after == 1
    assert metrics.draw_call_reduction == pytest.approx(0.999)
    assert np.shares_memory(prepared.data, staging)


def test_frustum_culling_filters_large_offscreen_instance_set():
    batch = InstancedCube3D()
    for index in range(100):
        batch.add_cube(position=Vec3((index % 10 - 5) * 0.08, 0.0, 0.0), size=0.05)
    for index in range(900):
        batch.add_cube(position=Vec3(10.0 + index, 0.0, 0.0), size=0.05)

    prepared = batch.prepare(np.eye(4, dtype="f4"))
    metrics = prepared.diagnostics

    assert metrics.source_instances == 1000
    assert metrics.active_instances == 1000
    assert metrics.visible_instances == 100
    assert metrics.culled_instances == 900
    assert metrics.draw_calls_before == 1000
    assert metrics.draw_calls_after == 1


def test_scale_expands_conservative_culling_radius():
    batch = InstancedCube3D()
    batch.add_instance(position=Vec3(2.0, 0.0, 0.0), scale=Vec3(2.0, 2.0, 2.0))

    prepared = batch.prepare(np.eye(4, dtype="f4"))

    assert prepared.diagnostics.visible_instances == 1


def test_hidden_instances_do_not_reach_culling_or_gpu_packing():
    batch = InstancedCube3D(cull=False)
    batch.extend(
        (
            Instance3D(position=Vec3(0.0, 0.0, -2.0)),
            Instance3D(position=Vec3(1.0, 0.0, -2.0), visible=False),
            Instance3D(position=Vec3(2.0, 0.0, -2.0), enabled=False),
        )
    )

    prepared = batch.prepare(np.eye(4, dtype="f4"))

    assert prepared.diagnostics.source_instances == 3
    assert prepared.diagnostics.active_instances == 1
    assert prepared.diagnostics.visible_instances == 1
