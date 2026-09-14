from __future__ import annotations

import time

import numpy as np

from swirengine.graphics.camera3d import Camera3D
from swirengine.graphics.instancing import InstancedCube3D
from swirengine.math.types import Vec3, perspective


def build_batch(count: int = 10_000) -> InstancedCube3D:
    batch = InstancedCube3D()
    side = 100
    for index in range(count):
        x = index % side
        z = index // side
        batch.add_cube(
            position=Vec3((x - side / 2) * 1.2, 0.0, -4.0 - z * 1.2),
            size=0.65,
        )
    return batch


def main() -> None:
    batch = build_batch()
    camera = Camera3D(
        position=Vec3(0.0, 8.0, 18.0),
        target=Vec3(0.0, 0.0, -35.0),
        far=180.0,
    )
    view_projection = (
        perspective(camera.fov, 16.0 / 9.0, camera.near, camera.far) @ camera.view_matrix()
    )
    staging = np.empty((batch.instance_count, 20), dtype="f4")

    prepared = batch.prepare(view_projection, staging=staging)
    rounds = 100
    start = time.perf_counter()
    for _ in range(rounds):
        prepared = batch.prepare(view_projection, staging=staging)
    elapsed = time.perf_counter() - start

    diagnostics = prepared.diagnostics
    print(f"source instances : {diagnostics.source_instances:,}")
    print(f"visible instances: {diagnostics.visible_instances:,}")
    print(f"culled instances : {diagnostics.culled_instances:,}")
    print(
        "draw-call model  : "
        f"{diagnostics.draw_calls_before:,} -> {diagnostics.draw_calls_after:,}"
    )
    print(f"CPU cull+pack     : {elapsed / rounds * 1000.0:.3f} ms/round")
    print("Timing is host-dependent diagnostic data, not an FPS claim.")

    assert diagnostics.source_instances == 10_000
    assert diagnostics.draw_calls_after <= 1
    assert diagnostics.draw_calls_before == diagnostics.active_instances
    assert np.shares_memory(prepared.data, staging)


if __name__ == "__main__":
    main()
