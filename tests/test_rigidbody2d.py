from dataclasses import dataclass

from swirengine.physics.collision2d import BoxCollider2D, CollisionWorld2D
from swirengine.physics.rigidbody2d import PhysicsWorld2D, RigidBody2D


@dataclass
class Body:
    x: float
    y: float
    width: float = 10.0
    height: float = 10.0


def test_dynamic_body_applies_gravity_and_moves():
    target = Body(0, 20)
    collisions = CollisionWorld2D()
    collider = collisions.add(BoxCollider2D(target))
    physics = PhysicsWorld2D(collisions, gravity=(0, -10))
    body = physics.add(RigidBody2D(target, collider))

    physics.step(1.0)

    assert body.velocity_y == -10
    assert target.y == 10


def test_body_resolves_floor_collision():
    target = Body(0, 15)
    floor = Body(0, 0, 100, 10)
    collisions = CollisionWorld2D()
    collider = collisions.add(BoxCollider2D(target))
    collisions.add(BoxCollider2D(floor))
    physics = PhysicsWorld2D(collisions, gravity=(0, -10))
    body = physics.add(RigidBody2D(target, collider))

    physics.step(1.0)

    assert target.y == 10
    assert body.velocity_y == 0


def test_impulse_respects_mass():
    target = Body(0, 0)
    collider = BoxCollider2D(target)
    body = RigidBody2D(target, collider, mass=2)
    body.apply_impulse(4, 6)
    assert body.velocity == (2, 3)
