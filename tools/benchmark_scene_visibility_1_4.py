from __future__ import annotations

import argparse
import time
from dataclasses import dataclass

from swirengine.graphics.instancing import Frustum3D, FrustumPlane
from swirengine.math.types import Vec3
from swirengine.scene_visibility import SceneVisibilityIndex3D, VisibilityAABB3D


@dataclass(slots=True)
class _Object:
    visibility_bounds: VisibilityAABB3D
    enabled: bool = True
    visible: bool = True


def _box_frustum(extent: float) -> Frustum3D:
    return Frustum3D(
        (
            FrustumPlane(1.0, 0.0, 0.0, extent),
            FrustumPlane(-1.0, 0.0, 0.0, extent),
            FrustumPlane(0.0, 1.0, 0.0, extent),
            FrustumPlane(0.0, -1.0, 0.0, extent),
            FrustumPlane(0.0, 0.0, 1.0, extent),
            FrustumPlane(0.0, 0.0, -1.0, extent),
        )
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="SwirEngine 1.4 scene-visibility workload gate")
    parser.add_argument("--side", type=int, default=128)
    parser.add_argument("--queries", type=int, default=250)
    parser.add_argument("--leaf-size", type=int, default=8)
    parser.add_argument("--max-leaf-tests", type=int, default=256)
    args = parser.parse_args()

    side = max(8, int(args.side))
    queries = max(1, int(args.queries))
    index = SceneVisibilityIndex3D(leaf_size=max(1, int(args.leaf_size)))

    spacing = 20.0
    half = side // 2
    for x in range(-half, side - half):
        for z in range(-half, side - half):
            center = Vec3(float(x) * spacing, 0.0, float(z) * spacing)
            bounds = VisibilityAABB3D.from_center_extent(center, Vec3(0.5, 0.5, 0.5))
            index.add(_Object(bounds), bounds=bounds)

    object_count = index.entry_count
    if object_count != side * side:
        raise SystemExit(f"unexpected object count: {object_count}")

    frustum = _box_frustum(25.0)
    started = time.perf_counter()
    first = index.query(frustum, refresh_dynamic=False)
    for _ in range(queries - 1):
        current = index.query(frustum, refresh_dynamic=False)
        if current.diagnostics.leaf_tests != first.diagnostics.leaf_tests:
            raise SystemExit("visibility workload is not deterministic")
    elapsed = time.perf_counter() - started

    diagnostics = first.diagnostics
    if diagnostics.leaf_tests > int(args.max_leaf_tests):
        raise SystemExit(
            f"leaf-test budget exceeded: {diagnostics.leaf_tests} > {args.max_leaf_tests}"
        )
    if diagnostics.object_test_reduction < 0.98:
        raise SystemExit(
            f"object-test reduction too small: {diagnostics.object_test_reduction:.4f}"
        )
    if diagnostics.visible_entries <= 0:
        raise SystemExit("benchmark frustum unexpectedly contains no objects")

    average_ms = elapsed * 1000.0 / queries
    print(
        "scene_visibility_1_4 "
        f"objects={object_count} visible={diagnostics.visible_entries} "
        f"nodes={diagnostics.bvh_nodes} node_tests={diagnostics.node_tests} "
        f"leaf_tests={diagnostics.leaf_tests} "
        f"reduction={diagnostics.object_test_reduction:.4f} "
        f"queries={queries} avg_ms={average_ms:.4f}"
    )
    print("Host timing is diagnostic-only; the gate is based on deterministic work counts.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
