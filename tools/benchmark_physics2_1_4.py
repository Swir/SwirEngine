from __future__ import annotations

import argparse
import time
from dataclasses import dataclass, field

from swirengine.math.types import Vec3
from swirengine.physics import BoxCollider3D
from swirengine.physics.dynamics3d import PhysicsBody3D, PhysicsScene3D


@dataclass
class Target3D:
    position: Vec3 = field(default_factory=Vec3)


def body(x: float, *, body_type: str = "static", size: float = 1.0) -> PhysicsBody3D:
    target = Target3D(Vec3(float(x), 0.0, 0.0))
    collider = BoxCollider3D(target, width=size, height=size, depth=size)
    return PhysicsBody3D(target, collider, body_type=body_type)  # type: ignore[arg-type]


def main() -> None:
    parser = argparse.ArgumentParser(description="SwirEngine 1.4 Physics 2.0 regression gate")
    parser.add_argument("--static-bodies", type=int, default=2000)
    parser.add_argument("--frames", type=int, default=120)
    args = parser.parse_args()
    if args.static_bodies < 100 or args.frames < 2:
        raise SystemExit("benchmark requires at least 100 static bodies and 2 frames")

    scene = PhysicsScene3D(gravity=Vec3(), cell_size=2.0, fixed_dt=1.0 / 120.0)
    for index in range(args.static_bodies):
        scene.add(body(index * 8.0))
    mover = body(0.2, body_type="dynamic")
    scene.add(mover)

    naive_pairs = len(scene.bodies) * (len(scene.bodies) - 1) // 2
    started = time.perf_counter()
    for _ in range(args.frames):
        scene.step(scene.fixed_dt)
    elapsed = time.perf_counter() - started
    diagnostics = scene.diagnostics

    if diagnostics.candidate_pairs >= naive_pairs // 100:
        raise SystemExit(
            "broadphase gate failed: "
            f"candidate_pairs={diagnostics.candidate_pairs}, naive_pairs={naive_pairs}"
        )
    if diagnostics.narrow_phase_tests > diagnostics.candidate_pairs:
        raise SystemExit("narrow-phase gate failed: tests exceeded broad-phase candidates")

    ccd = PhysicsScene3D(gravity=Vec3(), fixed_dt=1.0 / 60.0)
    bullet = body(0.0, body_type="dynamic", size=0.5)
    bullet.continuous = True
    wall = body(5.0, size=0.2)
    ccd.add(bullet)
    ccd.add(wall)
    bullet.set_velocity(1000.0, 0.0, 0.0)
    ccd.step(ccd.fixed_dt)
    if bullet.position.x >= 5.0 or ccd.diagnostics.sweep_hits != 1:
        raise SystemExit(
            "CCD gate failed: "
            f"x={bullet.position.x}, sweep_hits={ccd.diagnostics.sweep_hits}"
        )

    print(
        "physics2_gate",
        f"bodies={len(scene.bodies)}",
        f"naive_pairs={naive_pairs}",
        f"candidate_pairs={diagnostics.candidate_pairs}",
        f"narrow_tests={diagnostics.narrow_phase_tests}",
        f"frames={args.frames}",
        f"elapsed_ms={elapsed * 1000.0:.3f}",
        f"ccd_x={bullet.position.x:.5f}",
        f"ccd_sweep_hits={ccd.diagnostics.sweep_hits}",
    )
    print("Host timings are diagnostics only; this gate makes no FPS claim.")


if __name__ == "__main__":
    main()
