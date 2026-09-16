from __future__ import annotations

import argparse
import time

import numpy as np

from swirengine.terrain import HeightmapTerrain, TerrainConfig


def main() -> None:
    parser = argparse.ArgumentParser(description="SwirEngine 1.4 terrain/LOD regression gate")
    parser.add_argument("--chunks", type=int, default=32)
    parser.add_argument("--chunk-cells", type=int, default=16)
    parser.add_argument("--radius", type=int, default=2)
    parser.add_argument("--frames", type=int, default=120)
    args = parser.parse_args()

    if args.chunks < 3 or args.chunk_cells < 4 or args.radius < 0 or args.frames < 2:
        raise SystemExit("invalid terrain benchmark arguments")

    cells = args.chunks * args.chunk_cells
    z, x = np.mgrid[0 : cells + 1, 0 : cells + 1]
    heights = (np.sin(x * 0.035) * 0.45 + np.cos(z * 0.027) * 0.35).astype("f4")
    terrain = HeightmapTerrain(
        heights,
        config=TerrainConfig(
            chunk_cells=args.chunk_cells,
            lod_steps=(1, 2, 4, 8),
            lod_distances=(24.0, 48.0, 96.0),
            mesh_cache_size=max(64, (args.radius * 2 + 1) ** 2 * 4),
        ),
    )

    focus = cells * 0.5
    expected_max = (args.radius * 2 + 1) ** 2
    start = time.perf_counter()
    first = terrain.select_chunks(focus, focus, radius_chunks=args.radius)
    first_elapsed = time.perf_counter() - start
    first_builds = terrain.diagnostics.mesh_builds

    start = time.perf_counter()
    for _ in range(args.frames - 1):
        terrain.select_chunks(focus, focus, radius_chunks=args.radius)
    steady_elapsed = time.perf_counter() - start
    diagnostics = terrain.diagnostics

    if len(first) > expected_max:
        raise SystemExit(f"local-window gate failed: selected {len(first)} > {expected_max}")
    if diagnostics.mesh_builds != first_builds:
        raise SystemExit(
            "cache gate failed: stationary frames rebuilt terrain meshes "
            f"({first_builds} -> {diagnostics.mesh_builds})"
        )
    expected_min_hits = len(first) * (args.frames - 1)
    if diagnostics.cache_hits < expected_min_hits:
        raise SystemExit(
            f"cache-hit gate failed: {diagnostics.cache_hits} < {expected_min_hits}"
        )

    near_triangles = terrain.chunk_mesh(first[0].key, 0).triangle_count
    far_lod = len(terrain.config.lod_steps) - 1
    far_triangles = terrain.chunk_mesh(first[0].key, far_lod).triangle_count
    if far_triangles >= near_triangles:
        raise SystemExit(
            f"LOD gate failed: far triangles {far_triangles} >= near triangles {near_triangles}"
        )

    print(
        "terrain_lod_gate",
        f"world_chunks={args.chunks * args.chunks}",
        f"selected={len(first)}",
        f"mesh_builds={diagnostics.mesh_builds}",
        f"cache_hits={diagnostics.cache_hits}",
        f"near_triangles={near_triangles}",
        f"far_triangles={far_triangles}",
        f"first_ms={first_elapsed * 1000.0:.3f}",
        f"steady_total_ms={steady_elapsed * 1000.0:.3f}",
    )
    print("Host timings are diagnostics only; this gate makes no FPS claim.")


if __name__ == "__main__":
    main()
