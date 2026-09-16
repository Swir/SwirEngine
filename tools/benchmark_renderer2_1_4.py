from __future__ import annotations

import argparse
import time
from types import SimpleNamespace

from swirengine.graphics.camera3d import Camera3D
from swirengine.graphics.lights import DirectionalLight3D
from swirengine.graphics.primitives import Cube3D
from swirengine.graphics.renderer2 import Decal3D, Renderer2Planner, Renderer2Settings
from swirengine.math.types import Vec3


def build_scene() -> SimpleNamespace:
    objects: list[object] = [DirectionalLight3D(direction=Vec3(-0.5, -1.0, -0.25))]
    for index in range(48):
        x = float((index % 8) - 4) * 2.0
        z = -4.0 - float(index // 8) * 3.0
        objects.append(Cube3D(position=Vec3(x, 0.0, z)))
    for index in range(24):
        x = float((index % 6) - 3) * 2.5
        z = -3.0 - float(index // 6) * 5.0
        objects.append(Decal3D(position=Vec3(x, 0.0, z), size=Vec3(2.0, 1.0, 2.0)))
    return SimpleNamespace(objects=objects)


def main() -> None:
    parser = argparse.ArgumentParser(description="SwirEngine 1.4 Renderer 2.0 planner benchmark")
    parser.add_argument("--frames", type=int, default=5000)
    parser.add_argument("--budget-ms", type=float, default=2.5)
    args = parser.parse_args()
    if args.frames <= 0:
        raise SystemExit("--frames must be greater than zero")
    if args.budget_ms <= 0.0:
        raise SystemExit("--budget-ms must be greater than zero")

    scene = build_scene()
    camera = Camera3D(position=Vec3(0.0, 3.0, 7.0), target=Vec3(0.0, 0.0, -8.0))
    planner = Renderer2Planner(
        Renderer2Settings(
            shadow_cascades=4,
            shadow_resolution=2048,
            ssao_samples=16,
            bloom_levels=5,
            max_decals=256,
        )
    )

    warmup = planner.plan(scene, camera, width=1920, height=1080)
    expected_signature = (
        tuple(item.name for item in warmup.passes),
        warmup.diagnostics.visible_opaque,
        warmup.diagnostics.shadow_draws,
        warmup.diagnostics.decals_submitted,
        warmup.diagnostics.estimated_draw_calls,
    )

    started = time.perf_counter()
    last = warmup
    for _ in range(args.frames):
        last = planner.plan(scene, camera, width=1920, height=1080)
    elapsed = time.perf_counter() - started
    average_ms = elapsed * 1000.0 / args.frames

    actual_signature = (
        tuple(item.name for item in last.passes),
        last.diagnostics.visible_opaque,
        last.diagnostics.shadow_draws,
        last.diagnostics.decals_submitted,
        last.diagnostics.estimated_draw_calls,
    )
    if actual_signature != expected_signature:
        raise SystemExit("Renderer 2.0 planner produced a non-deterministic frame signature")
    if average_ms > args.budget_ms:
        raise SystemExit(
            f"Renderer 2.0 planner budget exceeded: {average_ms:.4f} ms/frame "
            f"> {args.budget_ms:.4f} ms/frame"
        )

    print(
        "Renderer 2.0 planner benchmark: PASS | "
        f"frames={args.frames} | avg={average_ms:.4f} ms | "
        f"estimated_draws={last.diagnostics.estimated_draw_calls}"
    )


if __name__ == "__main__":
    main()
