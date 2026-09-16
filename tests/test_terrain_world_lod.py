from __future__ import annotations

import numpy as np
import pytest

from swirengine.graphics.mesh import Mesh3D
from swirengine.large_world import ChunkKey
from swirengine.math.types import Vec3
from swirengine.terrain import (
    HeightmapTerrain,
    TerrainChunkKey,
    TerrainCollider3D,
    TerrainConfig,
    TerrainMaterialLayer,
    TerrainMaterialSet,
    TerrainSplatMap,
)


def test_heightmap_sampling_and_normal_are_world_space() -> None:
    heightmap = np.array(
        [
            [0.0, 1.0, 2.0],
            [0.0, 1.0, 2.0],
            [0.0, 1.0, 2.0],
        ],
        dtype="f4",
    )
    terrain = HeightmapTerrain(
        heightmap,
        config=TerrainConfig(cell_size=2.0, height_scale=3.0, chunk_cells=2),
        origin=Vec3(10.0, 5.0, 20.0),
    )

    assert terrain.sample_height(12.0, 22.0) == pytest.approx(8.0)
    assert terrain.sample_height(11.0, 22.0) == pytest.approx(6.5)
    normal = terrain.sample_normal(12.0, 22.0)
    assert normal.y > 0.0
    assert normal.x < 0.0
    assert terrain.contains(10.0, 20.0)
    assert terrain.contains(14.0, 24.0)
    assert not terrain.contains(14.1, 24.0)
    with pytest.raises(ValueError):
        terrain.sample_height(100.0, 100.0)


def test_chunk_mesh_lods_reduce_geometry_and_cache_reuses_meshes() -> None:
    heightmap = np.zeros((9, 9), dtype="f4")
    terrain = HeightmapTerrain(
        heightmap,
        config=TerrainConfig(
            chunk_cells=8,
            lod_steps=(1, 2, 4),
            lod_distances=(10.0, 20.0),
            mesh_cache_size=4,
        ),
    )
    key = TerrainChunkKey(0, 0)

    lod0 = terrain.chunk_mesh(key, 0)
    lod1 = terrain.chunk_mesh(key, 1)
    lod2 = terrain.chunk_mesh(key, 2)
    assert lod0.triangle_count == 128
    assert lod1.triangle_count == 32
    assert lod2.triangle_count == 8
    assert terrain.chunk_mesh(key, 0) is lod0

    diagnostics = terrain.diagnostics
    assert diagnostics.mesh_builds == 3
    assert diagnostics.cache_misses == 3
    assert diagnostics.cache_hits == 1
    assert diagnostics.cached_meshes == 3


def test_edge_chunks_keep_final_heightmap_sample_at_coarse_lod() -> None:
    terrain = HeightmapTerrain(
        np.zeros((8, 11), dtype="f4"),
        config=TerrainConfig(
            chunk_cells=6,
            lod_steps=(1, 4),
            lod_distances=(12.0,),
        ),
    )
    edge = terrain.chunk_mesh(TerrainChunkKey(1, 1), 1)

    assert edge.world_width == pytest.approx(4.0)
    assert edge.world_depth == pytest.approx(1.0)
    assert edge.triangle_count == 2
    assert np.max(edge.mesh.vertices[:, 0]) == pytest.approx(4.0)
    assert np.max(edge.mesh.vertices[:, 2]) == pytest.approx(1.0)


def test_lod_selection_scans_only_local_window_and_reuses_cached_meshes() -> None:
    terrain = HeightmapTerrain(
        np.zeros((257, 257), dtype="f4"),
        config=TerrainConfig(
            chunk_cells=32,
            lod_steps=(1, 2, 4),
            lod_distances=(40.0, 90.0),
            mesh_cache_size=64,
        ),
    )

    first = terrain.select_chunks(128.0, 128.0, radius_chunks=1)
    first_builds = terrain.diagnostics.mesh_builds
    second = terrain.select_chunks(128.0, 128.0, radius_chunks=1)

    assert len(first) == 9
    assert [(item.key, item.lod) for item in first] == [
        (item.key, item.lod) for item in second
    ]
    assert terrain.diagnostics.mesh_builds == first_builds
    assert terrain.diagnostics.cache_hits >= 9
    assert terrain.diagnostics.selected_chunks == 9


def test_material_splat_weights_are_normalized_and_bilinear() -> None:
    splat = TerrainSplatMap(
        np.array(
            [
                [[2.0, 0.0], [0.0, 2.0]],
                [[2.0, 0.0], [0.0, 2.0]],
            ],
            dtype="f4",
        )
    )
    materials = TerrainMaterialSet(
        layers=(TerrainMaterialLayer("grass"), TerrainMaterialLayer("rock", uv_scale=4.0)),
        splat=splat,
    )
    terrain = HeightmapTerrain(np.zeros((2, 2), dtype="f4"), materials=materials)

    center = terrain.sample_material_weights(0.5, 0.5)
    assert center.sum() == pytest.approx(1.0)
    assert center.tolist() == pytest.approx([0.5, 0.5])


def test_zero_splat_pixel_falls_back_to_first_layer() -> None:
    splat = TerrainSplatMap(np.zeros((2, 2, 3), dtype="f4"))
    assert splat.sample_uv(0.5, 0.5).tolist() == pytest.approx([1.0, 0.0, 0.0])


def test_terrain_collider_supports_ground_queries_and_downward_raycast() -> None:
    terrain = HeightmapTerrain(np.full((3, 3), 2.0, dtype="f4"))
    collider = TerrainCollider3D(terrain)

    assert collider.height_at(1.0, 1.0) == pytest.approx(2.0)
    hit = collider.raycast_down(1.0, 10.0, 1.0, 20.0)
    assert hit is not None
    assert hit.distance == pytest.approx(8.0)
    assert hit.point.y == pytest.approx(2.0)
    assert hit.normal.y == pytest.approx(1.0)
    assert collider.raycast_down(1.0, 10.0, 1.0, 2.0) is None
    assert collider.snap_to_ground(Vec3(1.0, 99.0, 1.0), offset=0.25).y == pytest.approx(2.25)
    assert collider.height_at(50.0, 50.0) is None


def test_large_world_provider_maps_2d_streaming_keys_to_xz_terrain_chunks() -> None:
    terrain = HeightmapTerrain(
        np.zeros((9, 9), dtype="f4"),
        config=TerrainConfig(chunk_cells=4, lod_steps=(1,), lod_distances=()),
    )
    provider = terrain.large_world_provider()

    definition = provider(ChunkKey(1, 0, 0))
    assert definition is not None
    content = definition.factory(None)  # type: ignore[arg-type]
    assert len(content.objects) == 1
    assert isinstance(content.objects[0], Mesh3D)
    assert content.objects[0].position.x == pytest.approx(4.0)
    assert content.objects[0].position.z == pytest.approx(0.0)
    assert provider(ChunkKey(99, 99, 0)) is None
    assert provider(ChunkKey(0, 0, 1)) is None

    settings = terrain.large_world_settings(active_radius_chunks=1)
    assert settings.dimensions == 2
    assert settings.chunk_size == pytest.approx(4.0)
