import pytest

from swirengine.graphics.primitives import Cube3D
from swirengine.graphics.static_batch import build_static_cube_batches
from swirengine.math.types import Color, Vec3


def test_static_cube_batch_reduces_same_color_draw_calls():
    cubes = [Cube3D(position=Vec3(float(index), 0.0, 0.0)) for index in range(100)]

    result = build_static_cube_batches(cubes)

    assert result.metrics.source_objects == 100
    assert result.metrics.draw_calls_before == 100
    assert result.metrics.draw_calls_after == 1
    assert result.metrics.draw_call_reduction == pytest.approx(0.99)
    assert len(result.meshes) == 1
    assert result.meshes[0].mesh.vertex_count == 3600


def test_static_cube_batch_groups_by_color():
    red = Color(1.0, 0.0, 0.0, 1.0)
    blue = Color(0.0, 0.0, 1.0, 1.0)
    cubes = [
        Cube3D(position=Vec3(0.0, 0.0, 0.0), color=red),
        Cube3D(position=Vec3(1.0, 0.0, 0.0), color=blue),
        Cube3D(position=Vec3(2.0, 0.0, 0.0), color=red),
    ]

    result = build_static_cube_batches(cubes)

    assert result.metrics.source_objects == 3
    assert result.metrics.output_batches == 2
    assert result.metrics.draw_calls_after == 2
    assert sorted(mesh.mesh.vertex_count for mesh in result.meshes) == [36, 72]


def test_static_cube_batch_bakes_translation_rotation_and_scale():
    cube = Cube3D(
        position=Vec3(4.0, -2.0, 7.0),
        size=2.0,
        rotation=Vec3(0.0, 90.0, 0.0),
    )

    result = build_static_cube_batches([cube])
    mesh = result.meshes[0].mesh

    assert mesh.vertices.shape == (36, 3)
    assert mesh.normals.shape == (36, 3)
    assert mesh.uvs is not None
    assert mesh.uvs.shape == (36, 2)
    assert mesh.vertices[:, 0].min() == pytest.approx(3.0)
    assert mesh.vertices[:, 0].max() == pytest.approx(5.0)
    assert mesh.vertices[:, 1].min() == pytest.approx(-3.0)
    assert mesh.vertices[:, 1].max() == pytest.approx(-1.0)
    assert mesh.vertices[:, 2].min() == pytest.approx(6.0)
    assert mesh.vertices[:, 2].max() == pytest.approx(8.0)


def test_hidden_or_disabled_cubes_do_not_enter_batch():
    cubes = [
        Cube3D(),
        Cube3D(visible=False),
        Cube3D(enabled=False),
    ]

    result = build_static_cube_batches(cubes)

    assert result.metrics.source_objects == 1
    assert result.metrics.draw_calls_after == 1
    assert result.meshes[0].mesh.vertex_count == 36


def test_empty_batch_is_valid_and_reports_no_reduction():
    result = build_static_cube_batches([])

    assert result.meshes == ()
    assert result.metrics.source_objects == 0
    assert result.metrics.draw_calls_before == 0
    assert result.metrics.draw_calls_after == 0
    assert result.metrics.draw_call_reduction == 0.0
