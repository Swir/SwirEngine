# Terrain + World LOD — SwirEngine 1.4

SwirEngine 1.4 milestone #1 adds a heightfield terrain foundation designed to reuse the engine's existing renderer, scene, collision and large-world systems rather than introducing a parallel runtime.

## Core model

`HeightmapTerrain` owns one immutable contiguous `float32` heightmap. World-space sampling uses bilinear interpolation and configurable cell/height scale. Terrain chunks are addressed with `TerrainChunkKey(x, z)` and generated lazily as ordinary `MeshData`/`Mesh3D` objects.

The public configuration is provided by `TerrainConfig`:

- `cell_size` — horizontal world-space spacing between height samples
- `height_scale` — vertical scale applied to stored heights
- `chunk_cells` — cells per terrain chunk edge
- `lod_steps` — sampling stride per LOD, for example `(1, 2, 4, 8)`
- `lod_distances` — camera-distance thresholds between LODs
- `mesh_cache_size` — bounded LRU cache capacity for generated `(chunk, lod)` meshes

Edge chunks always include the final heightmap row/column even when a coarse LOD stride does not divide the edge chunk evenly. This prevents the terrain extent from shrinking at coarse levels.

## Per-frame work

`select_chunks()` computes the focus chunk directly and iterates only the requested local square window. It never scans all terrain chunks. The resulting `TerrainSelection` values are deterministic and sorted by distance and chunk key.

`chunk_mesh()` uses a bounded LRU cache. Repeated stable-camera frames therefore reuse existing NumPy/MeshData allocations instead of regenerating geometry. `TerrainDiagnostics` exposes mesh builds, cache hits/misses, resident cached meshes, selected chunks and selected triangle count.

The deterministic gate in `tools/benchmark_terrain_world_lod.py` checks that:

1. a local radius selects no more than its bounded `(2r+1)^2` chunk window,
2. stationary frames do not rebuild terrain meshes,
3. expected cache hits occur on repeated selection,
4. coarse LOD generates fewer triangles than LOD0.

Timing values printed by that tool are diagnostics only and are not converted into FPS claims.

## Height and collision queries

`sample_height(x, z)` and `sample_normal(x, z)` provide world-space terrain queries. `TerrainCollider3D` builds on them for grounded gameplay:

- `height_at()` / `normal_at()`
- downward heightfield raycasts
- `snap_to_ground()`

This is intentionally an additive heightfield adapter beside the existing box/sphere collision world. Physics 2.0 can consume the same stable terrain query surface when contact solving and sweeps are expanded in milestone #2.

## Terrain materials and splat maps

`TerrainMaterialLayer` records creator-facing material metadata such as albedo/normal asset names, UV scale, roughness and metallic values. `TerrainSplatMap` stores normalized HxWxL blend weights and supports bilinear sampling. `TerrainMaterialSet` validates that the declared material-layer count matches the splat-map channels.

The material/splat model is renderer-independent in milestone #1 so Renderer 2.0 can bind it to the future terrain shader path without changing gameplay/world APIs.

## Large World integration

`TerrainChunkProvider` implements the existing Large World provider contract. It maps the streamer's 2D chunk address to the terrain X/Z plane and produces ordinary `Mesh3D` scene objects. `HeightmapTerrain.large_world_settings()` returns chunk sizes aligned to the terrain configuration.

Typical setup:

```python
streamer = LargeWorldStreamer(
    scene,
    terrain.large_world_provider(lod=1),
    settings=terrain.large_world_settings(
        active_radius_chunks=1,
        preload_radius_chunks=2,
        retention_radius_chunks=3,
    ),
)
streamer.update((camera_x, camera_z))
```

Residency/unloading therefore remains owned by the existing `LargeWorldStreamer`; terrain does not duplicate scene-mount or asset-residency logic.

## Example

Run:

```bash
python examples/demo_terrain_world_lod.py
```

The example creates a procedural heightmap, selects multiple distance LODs, performs a ground raycast and mounts terrain chunks through `LargeWorldStreamer` without external assets.
