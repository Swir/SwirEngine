import pytest

from swirengine import (
    AABB3D,
    BoxCollider3D,
    CollisionDiagnostics3D,
    CollisionWorld3D,
    Cube3D,
    RaycastHit3D,
    SphereBounds3D,
    SphereCollider3D,
    Vec3,
)


def test_aabb3d_intersection_and_point_containment():
    first = AABB3D(0, 0, 0, 10, 10, 10)
    touching = AABB3D(10, 0, 0, 10, 10, 10)
    far = AABB3D(30, 0, 0, 10, 10, 10)

    assert first.intersects(touching)
    assert not first.intersects(far)
    assert first.contains(0, 0, 0)
    assert first.contains(5, 5, 5)
    assert not first.contains(6, 0, 0)


def test_3d_bounds_reject_negative_dimensions():
    with pytest.raises(ValueError):
        AABB3D(0, 0, 0, -1, 1, 1)
    with pytest.raises(ValueError):
        SphereBounds3D(0, 0, 0, -1)


def test_box_collider_tracks_cube_position_and_size():
    cube = Cube3D(position=Vec3(2, 3, 4), size=6)
    collider = BoxCollider3D(cube, offset=Vec3(1, -1, 2))

    assert collider.bounds == AABB3D(3, 2, 6, 6, 6, 6)
    cube.position.x = 10
    assert collider.bounds.x == 11


def test_sphere_collider_tracks_live_target_and_requires_radius():
    cube = Cube3D(position=Vec3(1, 2, 3))
    collider = SphereCollider3D(cube, radius=2.5, offset=Vec3(0, 1, 0))

    assert collider.bounds == SphereBounds3D(1, 3, 3, 2.5)
    cube.position.z = 8
    assert collider.bounds.z == 8

    unknown = SphereCollider3D(Cube3D())
    with pytest.raises(ValueError, match="radius"):
        _ = unknown.bounds


def test_box_sphere_and_sphere_sphere_narrow_phase():
    world = CollisionWorld3D(cell_size=4)
    box = world.add(BoxCollider3D(Cube3D(position=Vec3(0, 0, 0), size=2), tag="box"))
    sphere = world.add(
        SphereCollider3D(Cube3D(position=Vec3(1.5, 0, 0)), radius=1.0, tag="sphere")
    )
    far_sphere = world.add(
        SphereCollider3D(Cube3D(position=Vec3(10, 0, 0)), radius=1.0, tag="far")
    )

    assert world.query(box) == (sphere,)
    assert world.query(sphere) == (box,)
    assert world.pairs() == ((box, sphere),)
    assert far_sphere not in world.query(box)


def test_overlap_queries_layer_mask_and_point_are_deterministic():
    world = CollisionWorld3D(cell_size=2)
    box = world.add(
        BoxCollider3D(Cube3D(position=Vec3(2, 0, 0), size=2), tag="enemy", layer=2)
    )
    sphere = world.add(
        SphereCollider3D(
            Cube3D(position=Vec3(5, 0, 0)),
            radius=1,
            tag="enemy",
            layer=2,
        )
    )
    world.add(BoxCollider3D(Cube3D(position=Vec3(2, 6, 0), size=2), tag="wall", layer=4))

    assert world.overlap_box(AABB3D(2, 0, 0, 3, 3, 3), layer_mask=2) == (box,)
    assert world.overlap_sphere(Vec3(4, 0, 0), 2.1, layer_mask=2) == (box, sphere)
    assert world.query_point(Vec3(2, 0, 0), tag="enemy") == (box,)


def test_layer_and_mask_filter_pair_queries():
    world = CollisionWorld3D()
    player = world.add(BoxCollider3D(Cube3D(size=2), layer=1, mask=2))
    enemy = world.add(BoxCollider3D(Cube3D(position=Vec3(0.5, 0, 0), size=2), layer=2))

    assert world.query(player) == (enemy,)
    enemy.mask = 4
    assert world.query(player) == ()


def test_raycast_hits_boxes_and_spheres_in_distance_order():
    world = CollisionWorld3D(cell_size=2)
    near = world.add(
        SphereCollider3D(Cube3D(position=Vec3(4, 0, 0)), radius=1, tag="enemy", layer=2)
    )
    far = world.add(
        BoxCollider3D(Cube3D(position=Vec3(8, 0, 0), size=2), tag="enemy", layer=2)
    )
    world.add(BoxCollider3D(Cube3D(position=Vec3(4, 5, 0), size=2), tag="wall", layer=4))

    hits = world.raycast(Vec3(), Vec3(10, 0, 0), max_distance=20, layer_mask=2)

    assert tuple(hit.collider for hit in hits) == (near, far)
    assert all(isinstance(hit, RaycastHit3D) for hit in hits)
    assert hits[0].distance == pytest.approx(3.0)
    assert hits[0].point.x == pytest.approx(3.0)
    assert hits[0].normal.x == pytest.approx(-1.0)
    assert hits[1].distance == pytest.approx(7.0)
    assert hits[1].normal.x == -1.0


def test_raycast_rejects_invalid_direction_and_distance():
    world = CollisionWorld3D()
    with pytest.raises(ValueError, match="non-zero"):
        world.raycast(Vec3(), Vec3())
    with pytest.raises(ValueError, match="non-negative"):
        world.raycast(Vec3(), Vec3(1, 0, 0), max_distance=-1)


def test_spatial_index_tracks_moving_targets_without_manual_sync():
    world = CollisionWorld3D(cell_size=4)
    player_shape = Cube3D(position=Vec3(), size=1)
    enemy_shape = Cube3D(position=Vec3(30, 0, 0), size=1)
    player = world.add(BoxCollider3D(player_shape))
    enemy = world.add(BoxCollider3D(enemy_shape))

    assert world.query(player) == ()
    enemy_shape.position.x = 0.5
    assert world.query(player) == (enemy,)


def test_broad_phase_reduces_sparse_pair_candidates_by_two_orders_of_magnitude():
    world = CollisionWorld3D(cell_size=4)
    count = 1000
    for index in range(count):
        world.add(BoxCollider3D(Cube3D(position=Vec3(index * 8, 0, 0), size=1)))

    assert world.pairs() == ()
    diagnostics = world.diagnostics
    brute_force_pairs = count * (count - 1) // 2

    assert isinstance(diagnostics, CollisionDiagnostics3D)
    assert diagnostics.collider_count == count
    assert diagnostics.candidate_count < brute_force_pairs // 100
    assert diagnostics.narrow_phase_tests == 0
    assert diagnostics.hits == 0


def test_finite_raycast_uses_spatial_candidates_instead_of_full_registry_scan():
    world = CollisionWorld3D(cell_size=4)
    for index in range(1000):
        world.add(BoxCollider3D(Cube3D(position=Vec3(index * 8, 0, 0), size=1)))

    hits = world.raycast(Vec3(-2, 0, 0), Vec3(1, 0, 0), max_distance=20)

    assert hits
    assert world.diagnostics.candidate_count < 10
    assert world.diagnostics.narrow_phase_tests < 10
