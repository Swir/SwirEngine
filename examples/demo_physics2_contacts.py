from __future__ import annotations

from dataclasses import dataclass, field

from swirengine.math.types import Vec3
from swirengine.physics import BoxCollider3D
from swirengine.physics.dynamics3d import (
    DistanceJoint3D,
    PhysicsBody3D,
    PhysicsMaterial3D,
    PhysicsScene3D,
)


@dataclass
class Target3D:
    position: Vec3 = field(default_factory=Vec3)


def box(
    x: float,
    y: float,
    z: float,
    *,
    size: float = 1.0,
    body_type: str = "dynamic",
    friction: float = 0.6,
    restitution: float = 0.0,
) -> PhysicsBody3D:
    target = Target3D(Vec3(x, y, z))
    collider = BoxCollider3D(target, width=size, height=size, depth=size)
    return PhysicsBody3D(
        target,
        collider,
        body_type=body_type,  # type: ignore[arg-type]
        material=PhysicsMaterial3D(friction=friction, restitution=restitution),
    )


def main() -> None:
    scene = PhysicsScene3D(fixed_dt=1.0 / 120.0, solver_iterations=6, joint_iterations=3)
    floor = scene.add(box(0.0, -1.0, 0.0, size=20.0, body_type="static"))
    first = scene.add(box(-1.0, 3.0, 0.0, restitution=0.2))
    second = scene.add(box(2.0, 3.5, 0.0, restitution=0.2))
    scene.add_joint(DistanceJoint3D(first, second, rest_length=3.0, stiffness=0.65, damping=4.0))
    first.set_velocity(2.5, 0.0, 0.0)

    for _ in range(360):
        scene.step(scene.fixed_dt)

    print("floor", floor.position)
    print("body_a", first.position, first.velocity, "sleeping=", first.is_sleeping)
    print("body_b", second.position, second.velocity, "sleeping=", second.is_sleeping)
    print("distance", (second.position - first.position).length)
    print("diagnostics", scene.diagnostics)

    ccd = scene.add(box(-8.0, 2.0, 2.0, size=0.25))
    ccd.continuous = True
    ccd.set_velocity(900.0, 0.0, 0.0)
    scene.add(box(0.0, 2.0, 2.0, size=0.2, body_type="static"))
    scene.step(scene.fixed_dt)
    print("ccd", ccd.position, ccd.velocity, scene.diagnostics.sweep_hits)


if __name__ == "__main__":
    main()
