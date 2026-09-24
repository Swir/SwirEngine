from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from swirengine.terrain import TerrainConfig, TerrainMaterialLayer
from swirengine.terrain_authoring22 import (
    DirtyTerrainChunk,
    FoliagePlacement,
    TerrainAuthoringAsset,
    TerrainAuthoringSession,
    TerrainEditorSession,
    TerrainProjectStore,
    WorldStreamingAuthoring,
)


def test_sculpt_tracks_dirty_chunks_and_undo_redo() -> None:
    config = TerrainConfig(chunk_cells=4)
    asset = TerrainAuthoringAsset.flat(10, 10, config=config)
    session = TerrainAuthoringSession(asset)

    stroke = session.sculpt(x=4.0, z=4.0, radius=2.0, strength=2.0, mode="raise")

    assert stroke.samples
    assert asset.heights[4, 4] == pytest.approx(2.0)
    assert DirtyTerrainChunk(1, 1) in asset.dirty_chunks()
    assert session.undo()
    assert asset.heights[4, 4] == pytest.approx(0.0)
    assert session.redo()
    assert asset.heights[4, 4] == pytest.approx(2.0)


def test_paint_normalizes_runtime_material_weights() -> None:
    layers = (
        TerrainMaterialLayer("grass"),
        TerrainMaterialLayer("rock", roughness=0.8),
    )
    splat = np.zeros((5, 5, 2), dtype="f4")
    splat[:, :, 0] = 1.0
    asset = TerrainAuthoringAsset(np.zeros((5, 5), dtype="f4"), layers=layers, splat=splat)

    changed = asset.paint(1, x=2.0, z=2.0, radius=1.5, strength=1.0)
    runtime = asset.to_runtime()

    assert changed > 0
    assert asset.splat is not None
    assert np.allclose(asset.splat.sum(axis=2), 1.0)
    assert runtime.materials is not None
    assert runtime.sample_material_weights(2.0, 2.0)[1] > 0.99


def test_foliage_is_bounded_project_relative_and_deterministic() -> None:
    asset = TerrainAuthoringAsset.flat(5, 5)
    asset.add_foliage(FoliagePlacement("assets/trees/pine.glb", 2.0, 1.0, yaw=90.0))
    asset.add_foliage(FoliagePlacement("assets/trees/birch.glb", 1.0, 1.0))

    first = asset.canonical_json()
    second = asset.canonical_json()

    assert first == second
    payload = json.loads(first)
    assert [item["asset"] for item in payload["foliage"]] == [
        "assets/trees/birch.glb",
        "assets/trees/pine.glb",
    ]
    with pytest.raises(ValueError):
        FoliagePlacement("../outside.glb", 0.0, 0.0)
    with pytest.raises(ValueError):
        asset.add_foliage(FoliagePlacement("assets/tree.glb", 99.0, 0.0))


def test_authored_lod_and_streaming_round_trip_to_shipping_runtime() -> None:
    config = TerrainConfig(
        cell_size=2.0,
        chunk_cells=4,
        lod_steps=(1, 2, 4),
        lod_distances=(20.0, 40.0),
    )
    streaming = WorldStreamingAuthoring(
        active_radius_chunks=2,
        preload_radius_chunks=3,
        retention_radius_chunks=5,
        max_activations_per_update=7,
    )
    asset = TerrainAuthoringAsset.flat(9, 9, config=config)
    asset.streaming = streaming

    runtime = asset.to_runtime()
    settings = asset.runtime_streaming_settings()

    assert runtime.config.lod_steps == (1, 2, 4)
    assert runtime.chunk_world_size == pytest.approx(8.0)
    assert settings.chunk_size == pytest.approx(8.0)
    assert settings.active_radius_chunks == 2
    assert settings.preload_radius_chunks == 3
    assert settings.retention_radius_chunks == 5
    assert settings.max_activations_per_update == 7


def test_swirterrain_round_trip_preserves_canonical_asset() -> None:
    layers = (TerrainMaterialLayer("grass"), TerrainMaterialLayer("rock"))
    splat = np.zeros((4, 4, 2), dtype="f4")
    splat[:, :, 0] = 1.0
    asset = TerrainAuthoringAsset(
        np.arange(16, dtype="f4").reshape(4, 4),
        config=TerrainConfig(cell_size=2.0, chunk_cells=2),
        layers=layers,
        splat=splat,
        foliage=[FoliagePlacement("assets/trees/pine.glb", 2.0, 4.0, yaw=45.0)],
        streaming=WorldStreamingAuthoring(1, 3, 4, 2),
    )
    asset.paint(1, x=2.0, z=2.0, radius=2.0, strength=0.5)

    payload = asset.to_swirterrain_bytes()
    restored = TerrainAuthoringAsset.from_swirterrain_bytes(payload)

    assert restored.to_swirterrain_bytes() == payload
    assert np.array_equal(restored.heights, asset.heights)
    assert restored.config == asset.config
    assert restored.streaming == asset.streaming
    assert restored.foliage == asset.foliage


def test_swirterrain_parser_rejects_invalid_format_version_and_shape() -> None:
    payload = json.loads(TerrainAuthoringAsset.flat(4, 4).canonical_json())
    payload["format"] = "unknown"
    with pytest.raises(ValueError, match="format"):
        TerrainAuthoringAsset.from_swirterrain_bytes(json.dumps(payload))

    payload["format"] = TerrainAuthoringAsset.FORMAT
    payload["version"] = 999
    with pytest.raises(ValueError, match="version"):
        TerrainAuthoringAsset.from_swirterrain_bytes(json.dumps(payload))

    payload["version"] = TerrainAuthoringAsset.VERSION
    payload["heights"] = [[0.0]]
    with pytest.raises(ValueError, match="at least 2x2"):
        TerrainAuthoringAsset.from_swirterrain_bytes(json.dumps(payload))

    with pytest.raises(ValueError, match="invalid"):
        TerrainAuthoringAsset.from_swirterrain_bytes(b"not-json")


def test_project_store_is_scoped_to_assets_terrain(tmp_path: Path) -> None:
    store = TerrainProjectStore(tmp_path)
    asset = TerrainAuthoringAsset.flat(4, 4, value=1.5)

    target = store.save("world/main.swirterrain", asset)

    assert target == tmp_path / "assets" / "terrain" / "world" / "main.swirterrain"
    assert store.load("assets/terrain/world/main.swirterrain").to_swirterrain_bytes() == (
        asset.to_swirterrain_bytes()
    )
    with pytest.raises(ValueError):
        store.resolve("../outside.swirterrain")
    with pytest.raises(ValueError):
        store.resolve("/outside.swirterrain")
    with pytest.raises(ValueError):
        store.resolve("world/main.json")


def test_editor_session_save_reopen_dirty_undo_and_runtime_preview(tmp_path: Path) -> None:
    store = TerrainProjectStore(tmp_path)
    session = TerrainEditorSession.create(
        store,
        "levels/demo.swirterrain",
        TerrainAuthoringAsset.flat(6, 6),
    )

    assert session.dirty
    session.sculpt(x=2.0, z=2.0, radius=1.5, strength=2.0)
    assert session.runtime_preview().sample_height(2.0, 2.0) == pytest.approx(2.0)
    saved_path = session.save()
    assert saved_path.is_file()
    assert not session.dirty

    assert session.undo()
    assert session.dirty
    assert session.redo()
    assert not session.dirty

    reopened = TerrainEditorSession.open(store, "levels/demo.swirterrain")
    assert not reopened.dirty
    assert reopened.asset.to_swirterrain_bytes() == session.asset.to_swirterrain_bytes()
    reopened.sculpt(x=3.0, z=3.0, radius=1.0, strength=1.0)
    assert reopened.dirty
    reopened.reload()
    assert not reopened.dirty
    assert reopened.asset.to_swirterrain_bytes() == session.asset.to_swirterrain_bytes()


def test_invalid_authoring_inputs_fail_closed() -> None:
    with pytest.raises(ValueError):
        TerrainAuthoringAsset(np.zeros((1, 3), dtype="f4"))
    with pytest.raises(ValueError):
        WorldStreamingAuthoring(active_radius_chunks=3, preload_radius_chunks=2)

    asset = TerrainAuthoringAsset.flat(4, 4)
    with pytest.raises(ValueError):
        asset.sculpt(x=1.0, z=1.0, radius=0.0, strength=1.0)
    with pytest.raises(ValueError):
        asset.sculpt(x=1.0, z=1.0, radius=1.0, strength=1.0, mode="flatten")
