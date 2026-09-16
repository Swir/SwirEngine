from __future__ import annotations

from swirengine.graphics.instancing import Frustum3D, FrustumPlane
from swirengine.graphics.primitives import Cube3D
from swirengine.math.types import Vec3
from swirengine.scene_visibility import (
    SceneVisibilityIndex3D,
    VisibilityAABB3D,
    visibility_bounds_for,
)


def _box_frustum(extent: float = 5.0) -> Frustum3D:
    value = float(extent)
    return Frustum3D(
        (
            FrustumPlane(1.0, 0.0, 0.0, value),
            FrustumPlane(-1.0, 0.0, 0.0, value),
            FrustumPlane(0.0, 1.0, 0.0, value),
            FrustumPlane(0.0, -1.0, 0.0, value),
            FrustumPlane(0.0, 0.0, 1.0, value),
            FrustumPlane(0.0, 0.0, -1.0, value),
        )
    )


def test_visibility_aabb_union_and_frustum_intersection() -> None:
    first = VisibilityAABB3D.from_center_extent(Vec3(), Vec3(1.0, 2.0, 3.0))
    second = VisibilityAABB3D.from_center_extent(Vec3(4.0, 0.0, 0.0), Vec3(1.0, 1.0, 1.0))
    merged = first.union(second)

    assert merged.minimum == Vec3(-1.0, -2.0, -3.0)
    assert merged.maximum == Vec3(5.0, 2.0, 3.0)
    assert first.intersects_frustum(_box_frustum(5.0))
    assert not VisibilityAABB3D.from_center_extent(
        Vec3(20.0, 0.0, 0.0), Vec3(1.0, 1.0, 1.0)
    ).intersects_frustum(_box_frustum(5.0))


def test_builtin_cube_bounds_stay_conservative_for_rotation() -> None:
    cube = Cube3D(position=Vec3(3.0, 4.0, 5.0), size=2.0, rotation=Vec3(30.0, 45.0, 60.0))
    bounds = visibility_bounds_for(cube)

    radius = 3.0**0.5
    assert bounds.minimum.x <= 3.0 - radius
    assert bounds.maximum.x >= 3.0 + radius
    assert bounds.minimum.y <= 4.0 - radius
    assert bounds.maximum.z >= 5.0 + radius


def test_static_bvh_prunes_most_object_tests_in_sparse_scene() -> None:
    index = SceneVisibilityIndex3D(leaf_size=4)
    cubes: list[Cube3D] = []
    for x in range(-16, 16):
        for z in range(-16, 16):
            cube = Cube3D(position=Vec3(float(x * 20), 0.0, float(z * 20)))
            cubes.append(cube)
            index.add(cube)

    result = index.query(_box_frustum(6.0), refresh_dynamic=False)

    assert result.visible == (cubes[16 * 32 + 16],)
    assert result.diagnostics.source_entries == 1024
    assert result.diagnostics.static_entries == 1024
    assert result.diagnostics.dynamic_entries == 0
    assert result.diagnostics.bvh_nodes > 1
    assert result.diagnostics.leaf_tests < 64
    assert result.diagnostics.object_test_reduction > 0.93
    assert index.rebuilds == 1


def test_dynamic_refit_tracks_motion_without_static_rebuild() -> None:
    index = SceneVisibilityIndex3D(leaf_size=2)
    static = Cube3D(position=Vec3(0.0, 0.0, 0.0))
    moving = Cube3D(position=Vec3(50.0, 0.0, 0.0))
    index.add(static)
    index.add(moving, dynamic=True)

    first = index.query(_box_frustum(5.0))
    rebuilds = index.rebuilds
    assert first.visible == (static,)

    moving.position = Vec3(2.0, 0.0, 0.0)
    second = index.query(_box_frustum(5.0))

    assert second.visible == (static, moving)
    assert index.rebuilds == rebuilds
    assert index.refits >= 2
    assert second.diagnostics.dynamic_entries == 1


def test_static_refit_marks_bvh_dirty_and_rebuilds_on_next_query() -> None:
    index = SceneVisibilityIndex3D(leaf_size=1)
    cube = Cube3D(position=Vec3(30.0, 0.0, 0.0))
    index.add(cube)
    first = index.query(_box_frustum(5.0), refresh_dynamic=False)
    assert first.visible == ()
    rebuilds = index.rebuilds

    cube.position = Vec3()
    index.refit(cube)
    second = index.query(_box_frustum(5.0), refresh_dynamic=False)

    assert second.visible == (cube,)
    assert index.rebuilds == rebuilds + 1


def test_occlusion_stage_runs_only_for_frustum_candidates() -> None:
    index = SceneVisibilityIndex3D(leaf_size=2)
    near = Cube3D(position=Vec3(0.0, 0.0, 0.0), name="near")
    hidden = Cube3D(position=Vec3(2.0, 0.0, 0.0), name="hidden")
    outside = Cube3D(position=Vec3(100.0, 0.0, 0.0), name="outside")
    index.add_many((near, hidden, outside))
    tested: list[str] = []

    def occlusion(item: object, _bounds: VisibilityAABB3D) -> bool:
        tested.append(str(getattr(item, "name", "")))
        return item is not hidden

    result = index.query(_box_frustum(5.0), occlusion=occlusion, refresh_dynamic=False)

    assert result.visible == (near,)
    assert set(tested) == {"near", "hidden"}
    assert result.diagnostics.occlusion_tests == 2
    assert result.diagnostics.occlusion_rejected == 1


def test_index_honors_custom_visibility_bounds() -> None:
    class Custom:
        enabled = True
        visible = True
        visibility_bounds = VisibilityAABB3D.from_center_extent(Vec3(), Vec3(0.5, 0.5, 0.5))

    item = Custom()
    index = SceneVisibilityIndex3D()
    index.add(item)

    result = index.query(_box_frustum(1.0), refresh_dynamic=False)
    assert result.visible == (item,)
