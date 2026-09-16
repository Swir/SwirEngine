from __future__ import annotations

import numpy as np

from swirengine.core.scene import Scene
from swirengine.large_world import LargeWorldStreamer
from swirengine.terrain import HeightmapTerrain, TerrainCollider3D, TerrainConfig


def main() -> None:
    size = 129
    z, x = np.mgrid[0:size, 0:size]
    heightmap = (
        np.sin(x * 0.08) * 3.0
        + np.cos(z * 0.06) * 2.0
        + np.sin((x + z) * 0.025) * 4.0
    ).astype("f4")
    terrain = HeightmapTerrain(
        heightmap,
        config=TerrainConfig(
            cell_size=2.0,
            height_scale=1.0,
            chunk_cells=16,
            lod_steps=(1, 2, 4, 8),
            lod_distances=(60.0, 120.0, 220.0),
        ),
    )

    focus_x = terrain.world_width * 0.5
    focus_z = terrain.world_depth * 0.5
    selections = terrain.select_chunks(focus_x, focus_z, radius_chunks=2)
    print("selected terrain chunks:")
    for selection in selections:
        chunk = terrain.chunk_mesh(selection.key, selection.lod)
        print(
            f"  key={selection.key} lod={selection.lod} "
            f"distance={selection.distance:.1f} triangles={chunk.triangle_count}"
        )

    collider = TerrainCollider3D(terrain)
    hit = collider.raycast_down(focus_x, 100.0, focus_z, 200.0)
    if hit is not None:
        print(
            f"ground_y={hit.point.y:.2f} distance={hit.distance:.2f} "
            f"normal=({hit.normal.x:.2f}, {hit.normal.y:.2f}, {hit.normal.z:.2f})"
        )

    scene = Scene()
    streamer = LargeWorldStreamer(
        scene,
        terrain.large_world_provider(lod=1),
        settings=terrain.large_world_settings(
            active_radius_chunks=1,
            preload_radius_chunks=1,
            retention_radius_chunks=2,
            max_activations_per_update=9,
        ),
    )
    result = streamer.update((focus_x, focus_z))
    print(
        f"large_world active={result.diagnostics.active_chunks} "
        f"tracked={result.diagnostics.tracked_chunks} scene_objects={len(scene.objects)}"
    )
    print(f"terrain diagnostics={terrain.diagnostics}")


if __name__ == "__main__":
    main()
