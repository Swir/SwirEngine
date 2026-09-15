import pytest

from swirengine import BoxCollider3D, CollisionWorld3D, Cube3D, PhysicsWorld3D, RigidBody3D, Vec3


def test_rigidbody3d_force_and_impulse_are_mass_aware():
    cube = Cube3D()
    collider = BoxCollider3D(cube)
    body = RigidBody3D(cube, collider, mass=2.0)

    body.apply_impulse(4, 2, -2)
    assert body.velocity == Vec3(2, 1, -1)

    body.apply_force(2, 0, 0)
    body.step(0.5, CollisionWorld3D(), Vec3())
    assert body.velocity.x == pytest.approx(2.5)
    assert cube.position.x == pytest.approx(1.25)


def test_kinematic_box_body_resolves_against_static_box():
    collisions = CollisionWorld3D(cell_size=2)
    player = Cube3D(position=Vec3(0, 0, 0), size=1)
    floor = Cube3D(position=Vec3(0, -1.5, 0), size=2)
    player_collider = collisions.add(BoxCollider3D(player, tag="player"))
    collisions.add(BoxCollider3D(floor, tag="floor"))
    body = RigidBody3D(player, player_collider, body_type="kinematic").set_velocity(0, -1, 0)

    body.step(0.1, collisions, Vec3())

    assert player.position.y == pytest.approx(0.0)
    assert body.velocity.y == pytest.approx(0.0)


def test_restitution_bounces_velocity_on_contact():
    collisions = CollisionWorld3D(cell_size=2)
    player = Cube3D(position=Vec3(0, 0, 0), size=1)
    wall = Cube3D(position=Vec3(1.5, 0, 0), size=2)
    player_collider = collisions.add(BoxCollider3D(player))
    collisions.add(BoxCollider3D(wall))
    body = RigidBody3D(
        player,
        player_collider,
        body_type="kinematic",
        restitution=0.5,
    ).set_velocity(2, 0, 0)

    body.step(0.1, collisions, Vec3())

    assert player.position.x == pytest.approx(0.0)
    assert body.velocity.x == pytest.approx(-1.0)


def test_physics_world_uses_deterministic_fixed_substeps():
    collisions = CollisionWorld3D(cell_size=2)
    cube = Cube3D()
    body = RigidBody3D(cube, BoxCollider3D(cube), body_type="kinematic").set_velocity(2, 0, 0)
    physics = PhysicsWorld3D(
        collisions,
        gravity=Vec3(),
        fixed_dt=0.1,
        max_substeps=8,
    )
    physics.add(body)

    steps = physics.step(0.25)

    assert steps == 2
    assert cube.position.x == pytest.approx(0.4)
    assert physics.interpolation_alpha == pytest.approx(0.5)
    assert body.collider in physics.collisions.colliders


def test_physics_world_caps_substeps_and_reports_dropped_time():
    cube = Cube3D()
    body = RigidBody3D(cube, BoxCollider3D(cube), body_type="kinematic").set_velocity(1, 0, 0)
    physics = PhysicsWorld3D(gravity=Vec3(), fixed_dt=0.1, max_substeps=2)
    physics.add(body)

    steps = physics.step(1.0)

    assert steps == 2
    assert cube.position.x == pytest.approx(0.2)
    assert physics.dropped_time == pytest.approx(0.8)
    assert physics.interpolation_alpha == pytest.approx(0.0)


def test_static_body_does_not_move_or_accumulate_forces():
    cube = Cube3D()
    body = RigidBody3D(cube, BoxCollider3D(cube), body_type="static")
    body.apply_force(100, 100, 100)
    body.step(1.0, CollisionWorld3D(), Vec3(0, -9.81, 0))

    assert cube.position == Vec3()
    assert body.velocity == Vec3()


def test_body_requires_matching_collider_target():
    with pytest.raises(ValueError, match="same object"):
        RigidBody3D(Cube3D(), BoxCollider3D(Cube3D()))
