from __future__ import annotations

import argparse
import time
from dataclasses import dataclass, field

from swirengine.character import CharacterConfig3D, CharacterController3D
from swirengine.math.types import Vec3
from swirengine.physics import BoxCollider3D
from swirengine.physics.dynamics3d import PhysicsBody3D, PhysicsScene3D


@dataclass
class Target3D:
    position: Vec3 = field(default_factory=Vec3)


def static_box(
    scene: PhysicsScene3D,
    x: float,
    y: float,
    z: float,
    width: float,
    height: float,
    depth: float,
) -> None:
    target = Target3D(Vec3(x, y, z))
    collider = BoxCollider3D(target, width=width, height=height, depth=depth)
    scene.add(PhysicsBody3D(target, collider, body_type="static"))


def main() -> None:
    parser = argparse.ArgumentParser(description="SwirEngine 1.4 character-controller gate")
    parser.add_argument("--frames", type=int, default=600)
    args = parser.parse_args()
    if args.frames < 120:
        raise SystemExit("benchmark requires at least 120 frames")

    scene = PhysicsScene3D(gravity=Vec3(), cell_size=2.0)
    static_box(scene, 0.0, -0.5, 0.0, 80.0, 1.0, 12.0)
    for index in range(20):
        static_box(scene, 4.0 + index * 3.0, 0.15, 0.0, 0.8, 0.3, 3.0)

    target = Target3D(Vec3(0.0, 0.9, 0.0))
    controller = CharacterController3D(
        target,
        scene,
        config=CharacterConfig3D(
            walk_speed=5.0,
            ground_acceleration=100.0,
            step_height=0.4,
        ),
    )

    total_sweeps = 0
    total_hits = 0
    total_steps = 0
    started = time.perf_counter()
    for _ in range(args.frames):
        controller.update_world(Vec3(1.0, 0.0, 0.0), 1.0 / 120.0)
        diagnostics = controller.diagnostics
        total_sweeps += diagnostics.sweeps
        total_hits += diagnostics.hits
        total_steps += diagnostics.step_successes
    elapsed = time.perf_counter() - started

    if not controller.grounded:
        raise SystemExit("grounding gate failed: controller is not grounded")
    if target.position.x <= 10.0:
        raise SystemExit(f"movement gate failed: x={target.position.x:.4f}")
    if total_steps < 1:
        raise SystemExit("step gate failed: no low obstacle was climbed")
    if total_sweeps > args.frames * 12:
        raise SystemExit(
            f"sweep-budget gate failed: sweeps={total_sweeps}, frames={args.frames}"
        )

    print(
        "character_controller_gate",
        f"frames={args.frames}",
        f"x={target.position.x:.4f}",
        f"grounded={controller.grounded}",
        f"sweeps={total_sweeps}",
        f"hits={total_hits}",
        f"steps={total_steps}",
        f"elapsed_ms={elapsed * 1000.0:.3f}",
    )
    print("Host timings are diagnostics only; this gate makes no FPS claim.")


if __name__ == "__main__":
    main()
