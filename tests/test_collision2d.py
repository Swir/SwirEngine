import pytest

from swirengine import AABB, BoxCollider2D, CollisionWorld2D, Rectangle2D, Sprite2D
from swirengine.physics import CollisionDiagnostics, RaycastHit2D


def test_aabb_intersection_and_point_containment():
    first = AABB(0, 0, 10, 10)
    second = AABB(9, 0, 10, 10)
    far = AABB(30, 0, 10, 10)

    assert first.intersects(second)
    assert not first.intersects(far)
    assert first.contains(0, 0)
    assert first.contains(5, 5)
    assert not first.contains(6, 0)


def test_aabb_rejects_negative_size():
    with pytest.raises(ValueError):
        AABB(0, 0, -1, 10)


def test_box_collider_tracks_target_position():
    actor = Rectangle2D(5, 7, 20, 30)
    collider = BoxCollider2D(actor, offset_x=2, offset_y=-3)

    assert collider.bounds == AABB(7, 4, 20, 30)
    actor.x = 10
    assert collider.bounds.x == 12


def test_sprite_collider_requires_known_size():
    sprite = Sprite2D("hero.png")
    collider = BoxCollider2D(sprite)
    with pytest.raises(ValueError):
        _ = collider.bounds


def test_collision_world_query_and_layer_mask():
    world = CollisionWorld2D()
    player = world.add(BoxCollider2D(Rectangle2D(0, 0, 10, 10), tag="player"))
    enemy = world.add(BoxCollider2D(Rectangle2D(5, 0, 10, 10), tag="enemy"))
    wall = world.add(BoxCollider2D(Rectangle2D(50, 0, 10, 10), tag="wall"))

    assert world.query(player) == (enemy,)
    assert world.query(player, tag="enemy") == (enemy,)
    assert world.query(player, tag="wall") == ()
    assert world.pairs() == ((player, enemy),)
    assert wall not in world.query(player)

    enemy.layer = 2
    player.mask = 1
    assert world.query(player) == ()


def test_spatial_index_tracks_moving_targets_without_manual_sync():
    world = CollisionWorld2D(cell_size=32)
    player_shape = Rectangle2D(0, 0, 10, 10)
    enemy_shape = Rectangle2D(200, 0, 10, 10)
    player = world.add(BoxCollider2D(player_shape))
    enemy = world.add(BoxCollider2D(enemy_shape))

    assert world.query(player) == ()
    enemy_shape.x = 4
    assert world.query(player) == (enemy,)


def test_overlap_point_and_raycast_queries_are_deterministic():
    world = CollisionWorld2D(cell_size=16)
    near = world.add(BoxCollider2D(Rectangle2D(20, 0, 10, 10), tag="enemy", layer=2))
    far = world.add(BoxCollider2D(Rectangle2D(50, 0, 10, 10), tag="enemy", layer=2))
    world.add(BoxCollider2D(Rectangle2D(20, 40, 10, 10), tag="wall", layer=4))

    assert world.overlap_aabb(AABB(20, 0, 14, 14), layer_mask=2) == (near,)
    assert world.query_point(20, 0, tag="enemy") == (near,)

    hits = world.raycast(0, 0, 1, 0, max_distance=100, layer_mask=2)
    assert tuple(hit.collider for hit in hits) == (near, far)
    assert all(isinstance(hit, RaycastHit2D) for hit in hits)
    assert hits[0].distance == pytest.approx(15.0)
    assert hits[0].normal_x == -1.0
    assert hits[0].normal_y == 0.0


def test_raycast_rejects_invalid_direction_and_distance():
    world = CollisionWorld2D()
    with pytest.raises(ValueError, match="non-zero"):
        world.raycast(0, 0, 0, 0)
    with pytest.raises(ValueError, match="non-negative"):
        world.raycast(0, 0, 1, 0, max_distance=-1)


def test_broad_phase_reduces_sparse_pair_candidates_by_two_orders_of_magnitude():
    world = CollisionWorld2D(cell_size=32)
    count = 1000
    for index in range(count):
        world.add(BoxCollider2D(Rectangle2D(index * 64, 0, 8, 8)))

    assert world.pairs() == ()
    diagnostics = world.diagnostics
    brute_force_pairs = count * (count - 1) // 2

    assert isinstance(diagnostics, CollisionDiagnostics)
    assert diagnostics.collider_count == count
    assert diagnostics.candidate_count < brute_force_pairs // 100
    assert diagnostics.narrow_phase_tests == 0
    assert diagnostics.hits == 0
