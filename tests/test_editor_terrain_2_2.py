from __future__ import annotations

from pathlib import Path

import pytest

from swirengine.editor_integrated_session21 import EditorIntegratedProjectSession21
from swirengine.editor_terrain22 import (
    EditorTerrainError22,
    EditorTerrainPanelController22,
    EditorTerrainTooling22,
)
from swirengine.project_scaffold21 import new_project21


def test_terrain_controller_runs_full_creator_workflow(tmp_path: Path) -> None:
    tooling = EditorTerrainTooling22(tmp_path)
    controller = EditorTerrainPanelController22(tooling)

    document = controller.create("world/demo.swirterrain", width=9, height=9)
    assert tooling.dirty
    assert len(document.asset.layers) == 2
    assert controller.sculpt(x=4.0, z=4.0, radius=2.0, strength=2.0) > 0
    assert controller.paint(1, x=4.0, z=4.0, radius=2.0, strength=1.0) > 0
    controller.add_foliage("assets/trees/pine.glb", x=4.0, z=4.0)

    preview = controller.runtime_preview()
    assert preview.world_width == pytest.approx(8.0)
    assert preview.world_depth == pytest.approx(8.0)
    assert preview.chunks_x == 1
    assert preview.chunks_z == 1
    assert preview.lod_count == 4

    saved = controller.save()
    assert len(saved) == 1
    assert not tooling.dirty
    canonical = document.asset.to_swirterrain_bytes()

    reopened = EditorTerrainTooling22(tmp_path)
    restored = reopened.open("world/demo.swirterrain")
    assert restored.asset.to_swirterrain_bytes() == canonical
    assert not reopened.dirty
    assert reopened.snapshot().selected == "world/demo.swirterrain"


def test_terrain_tooling_rejects_escape_and_duplicate_assets(tmp_path: Path) -> None:
    tooling = EditorTerrainTooling22(tmp_path)
    tooling.create("world/demo.swirterrain", width=5, height=5)

    with pytest.raises(ValueError):
        tooling.create("../escape.swirterrain", width=5, height=5)
    tooling.save()
    with pytest.raises(EditorTerrainError22, match="already exists"):
        tooling.create("world/demo.swirterrain", width=5, height=5)


def test_integrated_project_session_tracks_and_saves_terrain_documents(tmp_path: Path) -> None:
    root = new_project21("TerrainIntegrated", "3d", parent=tmp_path)
    session = EditorIntegratedProjectSession21.open(root)

    session.terrains.create("world/main.swirterrain", width=9, height=9)
    assert session.terrains.dirty
    assert session.summary().dirty

    session.save()

    assert not session.terrains.dirty
    assert (root / "assets" / "terrain" / "world" / "main.swirterrain").is_file()
    reopened = EditorIntegratedProjectSession21.open(root)
    restored = reopened.terrains.open("world/main.swirterrain")
    assert restored.asset.heights.shape == (9, 9)
    assert not reopened.terrains.dirty
