from __future__ import annotations

from dataclasses import dataclass, field

from swirengine.character import CharacterConfig3D, CharacterController3D, CharacterInput3D
from swirengine.math.types import Vec3
from swirengine.physics import BoxCollider3D
from swirengine.physics.dynamics3d import PhysicsBody3D, PhysicsScene3D


@dataclass
class Target3D:
    position: Vec3 = field(default_factory=Vec3)


def add_static_box(
    scene: PhysicsScene3D,
    position: Vec3,
    *,
    width: float,
    height: float,
    depth: float,
) -> None:
    target = Target3D(position)
    collider = BoxCollider3D(target, width=width, height=height, depth=depth)
    scene.add(PhysicsBody3D(target, collider, body_type="static"))


def main() -> None:
    scene = PhysicsScene3D(gravity=Vec3())
    add_static_box(
        scene,
        Vec3(0.0, -0.5, 0.0),
        width=24.0,
        height=1.0,
        depth=8.0,
    )
    add_static_box(
        scene,
        Vec3(2.0, 0.15, 0.0),
        width=0.8,
        height=0.3,
        depth=3.0,
    )
    add_static_box(
        scene,
        Vec3(5.0, 1.0, 0.0),
        width=0.3,
        height=2.0,
        depth=3.0,
    )

    player = Target3D(Vec3(0.0, 0.9, 0.0))
    controller = CharacterController3D(
        player,
        scene,
        config=CharacterConfig3D(
            walk_speed=4.0,
            ground_acceleration=100.0,
            step_height=0.4,
        ),
    )

    for frame in range(180):
        command = CharacterInput3D(move_x=1.0, jump=frame == 100)
        state = controller.update(command, 1.0 / 60.0)
        if frame in (0, 60, 100, 179):
            print(
                "character_frame",
                frame,
                f"position=({state.position.x:.3f},{state.position.y:.3f},{state.position.z:.3f})",
                f"velocity=({state.velocity.x:.3f},{state.velocity.y:.3f},{state.velocity.z:.3f})",
                f"grounded={state.grounded}",
                f"sweeps={controller.diagnostics.sweeps}",
            )

    if player.position.x <= 1.0:
        raise SystemExit("character demo failed to move through the course")
    print("Character Controllers 1.4 demo completed successfully.")


if __name__ == "__main__":
    main()
