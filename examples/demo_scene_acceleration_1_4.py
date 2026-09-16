from __future__ import annotations

import numpy as np

from swirengine.core.scene import Scene
from swirengine.graphics.camera3d import Camera3D
from swirengine.graphics.hiz import HiZDepthPyramid3D
from swirengine.graphics.primitives import Cube3D
from swirengine.math.types import Vec3
from swirengine.scene_acceleration import enable_scene_acceleration


def main() -> int:
    scene = Scene()
    side = 64
    half = side // 2
    for x in range(-half, side - half):
        for z in range(-half, side - half):
            scene.add(
                Cube3D(
                    position=Vec3(float(x * 12), 0.0, -40.0 + float(z * 12)),
                    size=1.0,
                )
            )

    mover = scene.add(
        Cube3D(position=Vec3(100.0, 0.0, -8.0), visibility_dynamic=True, name="mover")
    )
    runtime = enable_scene_acceleration(scene, leaf_size=8)
    camera = Camera3D(position=Vec3(0.0, 4.0, 8.0), target=Vec3(0.0, 0.0, -40.0))

    first = runtime.frame(scene, camera, width=1280, height=720)
    rebuilds = runtime.snapshot_rebuilds
    mover.position = Vec3(0.0, 0.0, -8.0)
    second = runtime.frame(scene, camera, width=1280, height=720)

    if runtime.snapshot_rebuilds != rebuilds:
        raise SystemExit("dynamic refit unexpectedly rebuilt the scene membership snapshot")
    if mover not in second.view.objects:
        raise SystemExit("dynamic mover was not visible after refit")
    if second.diagnostics.query.leaf_tests >= second.diagnostics.query.source_entries:
        raise SystemExit("BVH failed to reduce per-object frustum tests")

    depth = np.full((16, 16), 0.25, dtype="f4")
    depth[7, 7] = 1.0
    hiz = HiZDepthPyramid3D(depth)
    hole = hiz.query_occluded((0.25, 0.25, 0.75, 0.75), 0.8)
    if hole.occluded:
        raise SystemExit("conservative Hi-Z incorrectly culled through a depth hole")

    print(
        "scene_acceleration_1_4 "
        f"indexed={second.diagnostics.indexed_entries} "
        f"visible={second.diagnostics.query.visible_entries} "
        f"leaf_tests={second.diagnostics.query.leaf_tests} "
        f"reduction={second.diagnostics.query.object_test_reduction:.4f} "
        f"snapshot_rebuilds={second.diagnostics.snapshot_rebuilds} "
        f"dynamic_refits={runtime.index.refits}"
    )
    print("Hi-Z hole-safety contract passed; timing/FPS claims are intentionally excluded.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
