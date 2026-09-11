import pytest

from swirengine import AABB, BoxCollider2D, CollisionWorld2D, Rectangle2D, Sprite2D


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
