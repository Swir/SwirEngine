from __future__ import annotations

from dataclasses import dataclass, field

import pytest

from swirengine.math.types import Vec3
from swirengine.physics.collision3d import AABB3D, BoxCollider3D, SphereBounds3D, SphereCollider3D
from swirengine.physics.dynamics3d import (
    DistanceJoint3D,
    PhysicsBackend3D,
    PhysicsBody3D,
    PhysicsMaterial3D,
    PhysicsScene3D,
)


@dataclass
class Target3D:
    position: Vec3 = field(default_factory=Vec3)


def box_body(
    x: float,
    y: float,
    z: float,
    *,
    size: float = 1.0,
    body_type: str = "dynamic",
    friction: float = 0.5,
    restitution: float = 0.0,
    continuous: bool = False,
) -> PhysicsBody3D:
    target = Target3D(Vec3(x, y, z))
    collider = BoxCollider3D(target, width=size, height=size, depth=size)
    return PhysicsBody3D(
        target,
        collider,
        body_type=body_type,  # type: ignore[arg-type]
        material=PhysicsMaterial3D(friction=friction, restitution=restitution),
        continuous=continuous,
    )


def sphere_body(
    x: float,
    y: float,
    z: float,
    *,
    radius: float = 0.5,
    body_type: str = "dynamic",
    restitution: float = 0.0,
) -> PhysicsBody3D:
    target = Target3D(Vec3(x, y, z))
    collider = SphereCollider3D(target, radius=radius)
    return PhysicsBody3D(
        target,
        collider,
        body_type=body_type,  # type: ignore[arg-type]
        material=PhysicsMaterial3D(restitution=restitution),
    )


def test_material_and_body_validation() -> None:
    with pytest.raises(ValueError):
        PhysicsMaterial3D(friction=-0.1)
    with pytest.raises(ValueError):
        PhysicsMaterial3D(restitution=1.1)

    body = box_body(0.0, 0.0, 0.0)
    assert body.inverse_mass == pytest.approx(1.0)
    body.apply_impulse(2.0, 0.0, 0.0)
    assert body.velocity.x == pytest.approx(2.0)


def test_fixed_step_gravity_is_deterministic() -> None:
    scene = PhysicsScene3D(gravity=Vec3(0.0, -10.0, 0.0), fixed_dt=0.1)
    body = scene.add(box_body(0.0, 10.0, 0.0))

    assert scene.step(0.35) == 3
    assert body.velocity.y == pytest.approx(-3.0)
    assert body.position.y == pytest.approx(9.4)
    assert scene.interpolation_alpha == pytest.approx(0.5)


def test_box_contact_separates_penetration() -> None:
    scene = PhysicsScene3D(gravity=Vec3(), fixed_dt=1.0 / 60.0, solver_iterations=4)
    dynamic = scene.add(box_body(0.0, 0.0, 0.0))
    scene.add(box_body(0.75, 0.0, 0.0, body_type="static"))

    scene.step(scene.fixed_dt)

    assert dynamic.position.x < 0.0
    assert scene.diagnostics.contacts == 1
    assert scene.diagnostics.narrow_phase_tests == 1


def test_restitution_reverses_normal_velocity() -> None:
    scene = PhysicsScene3D(gravity=Vec3(), fixed_dt=0.05)
    dynamic = scene.add(box_body(0.0, 0.0, 0.0, restitution=1.0))
    scene.add(box_body(1.1, 0.0, 0.0, body_type="static", restitution=1.0))
    dynamic.set_velocity(4.0, 0.0, 0.0)

    scene.step(0.05)

    assert dynamic.velocity.x < -3.9
    assert scene.diagnostics.normal_impulses >= 1


def _sliding_speed(friction: float) -> float:
    scene = PhysicsScene3D(gravity=Vec3(0.0, -10.0, 0.0), fixed_dt=1.0 / 120.0)
    floor_body = box_body(0.0, -0.5, 0.0, size=20.0, body_type="static", friction=friction)
    slider = box_body(0.0, 0.52, 0.0, friction=friction)
    slider.set_velocity(5.0, 0.0, 0.0)
    scene.add(floor_body)
    scene.add(slider)
    for _ in range(60):
        scene.step(scene.fixed_dt)
    return abs(slider.velocity.x)


def test_contact_friction_reduces_tangential_velocity() -> None:
    no_friction = _sliding_speed(0.0)
    high_friction = _sliding_speed(1.0)

    assert no_friction > 4.9
    assert high_friction < no_friction - 1.0


def test_sphere_sphere_contact_resolves_overlap() -> None:
    scene = PhysicsScene3D(gravity=Vec3(), fixed_dt=1.0 / 60.0)
    first = scene.add(sphere_body(0.0, 0.0, 0.0, radius=1.0))
    second = scene.add(sphere_body(1.5, 0.0, 0.0, radius=1.0))

    scene.step(scene.fixed_dt)

    assert first.position.x < 0.0
    assert second.position.x > 1.5
    assert scene.diagnostics.contacts == 1


def test_box_sweep_returns_earliest_time_of_impact() -> None:
    scene = PhysicsScene3D(gravity=Vec3())
    wall = scene.add(box_body(5.0, 0.0, 0.0, size=1.0, body_type="static"))
    scene.add(box_body(8.0, 0.0, 0.0, size=1.0, body_type="static"))

    hit = scene.sweep_box(AABB3D(0.0, 0.0, 0.0, 1.0, 1.0, 1.0), Vec3(10.0, 0.0, 0.0))

    assert hit is not None
    assert hit.collider is wall.collider
    assert hit.fraction == pytest.approx(0.4)
    assert hit.distance == pytest.approx(4.0)
    assert hit.normal.x == pytest.approx(-1.0)


def test_sphere_sweep_uses_conservative_expanded_bounds() -> None:
    scene = PhysicsScene3D(gravity=Vec3())
    obstacle = scene.add(box_body(5.0, 0.0, 0.0, size=2.0, body_type="static"))

    hit = scene.sweep_sphere(SphereBounds3D(0.0, 0.0, 0.0, 1.0), Vec3(10.0, 0.0, 0.0))

    assert hit is not None
    assert hit.collider is obstacle.collider
    assert hit.fraction == pytest.approx(0.3)
    assert hit.normal.x == pytest.approx(-1.0)


def test_continuous_body_does_not_tunnel_through_thin_wall() -> None:
    scene = PhysicsScene3D(gravity=Vec3(), fixed_dt=1.0 / 60.0)
    bullet = scene.add(box_body(0.0, 0.0, 0.0, size=0.5, continuous=True))
    scene.add(box_body(5.0, 0.0, 0.0, size=0.2, body_type="static"))
    bullet.set_velocity(1000.0, 0.0, 0.0)

    scene.step(scene.fixed_dt)

    assert bullet.position.x < 5.0
    assert abs(bullet.velocity.x) < 1e-6
    assert scene.diagnostics.sweep_hits == 1


def test_distance_joint_corrects_distance() -> None:
    scene = PhysicsScene3D(gravity=Vec3(), fixed_dt=1.0 / 60.0, joint_iterations=4)
    first = scene.add(box_body(0.0, 0.0, 0.0))
    second = scene.add(box_body(4.0, 0.0, 0.0))
    scene.add_joint(DistanceJoint3D(first, second, rest_length=2.0, stiffness=1.0))

    scene.step(scene.fixed_dt)

    distance = (second.position - first.position).length
    assert distance == pytest.approx(2.0, abs=1e-5)
    assert scene.diagnostics.joint_solves >= 1


def test_resting_body_can_sleep_and_external_impulse_wakes_it() -> None:
    scene = PhysicsScene3D(gravity=Vec3(0.0, -10.0, 0.0), fixed_dt=1.0 / 120.0)
    scene.add(box_body(0.0, -0.5, 0.0, size=20.0, body_type="static"))
    sleeper = box_body(0.0, 0.51, 0.0)
    sleeper.sleep_speed_threshold = 0.2
    sleeper.sleep_time_threshold = 0.2
    scene.add(sleeper)

    for _ in range(120):
        scene.step(scene.fixed_dt)

    assert sleeper.is_sleeping
    assert scene.diagnostics.sleeping_bodies == 1
    sleeper.apply_impulse(1.0, 0.0, 0.0)
    assert not sleeper.is_sleeping
    assert sleeper.velocity.x == pytest.approx(1.0)


def test_sparse_broadphase_avoids_naive_all_pairs() -> None:
    scene = PhysicsScene3D(gravity=Vec3(), cell_size=2.0)
    for index in range(400):
        scene.add(box_body(index * 10.0, 0.0, 0.0, body_type="static"))
    dynamic = scene.add(box_body(0.2, 0.0, 0.0))

    scene.step(scene.fixed_dt)

    naive_pairs = len(scene.bodies) * (len(scene.bodies) - 1) // 2
    assert scene.diagnostics.candidate_pairs < naive_pairs // 100
    assert scene.diagnostics.contacts >= 1
    assert dynamic.position.x > 0.2


def test_physics_scene_satisfies_backend_protocol() -> None:
    scene = PhysicsScene3D()
    assert isinstance(scene, PhysicsBackend3D)
