from __future__ import annotations

import json
from pathlib import Path

from swirengine.assets import AssetManager
from swirengine.editor_asset_formats21 import (
    create_format_aware_editor_asset_pipeline21,
    inspect_gltf21,
)


def test_format_aware_pipeline_tracks_gltf_dependencies_and_structured_preview(
    tmp_path: Path,
) -> None:
    source_dir = tmp_path / "drop" / "arena"
    texture_dir = source_dir / "textures"
    texture_dir.mkdir(parents=True)
    (source_dir / "mesh.bin").write_bytes(b"mesh-payload")
    (texture_dir / "albedo.png").write_bytes(b"not-a-decoded-preview")
    document = {
        "asset": {"version": "2.0"},
        "scenes": [{"nodes": [0]}],
        "nodes": [{"mesh": 0}],
        "meshes": [{"primitives": []}],
        "materials": [{}],
        "animations": [{}],
        "buffers": [{"uri": "mesh.bin", "byteLength": 12}],
        "images": [{"uri": "textures/albedo.png"}],
    }
    (source_dir / "arena.gltf").write_text(json.dumps(document), encoding="utf-8")

    manager = AssetManager(tmp_path / "project" / "assets")
    backend = create_format_aware_editor_asset_pipeline21(manager, max_workers=1)
    try:
        tickets = backend.import_paths((source_dir,), submit=True)
        gltf_ticket = next(ticket for ticket in tickets if ticket.relative_path.endswith("arena.gltf"))
        result = backend.wait(gltf_ticket, timeout=5.0)

        assert result.successful
        assert result.value["scenes"] == 1
        assert result.value["nodes"] == 1
        assert result.value["meshes"] == 1
        assert result.value["materials"] == 1
        assert result.value["animations"] == 1
        assert result.value["external_dependencies"] == 2
        assert result.value["missing_dependencies"] == 0
        assert backend.processor_for(gltf_ticket.relative_path) == "editor-gltf-metadata"

        preview = backend.preview(gltf_ticket.relative_path)
        assert preview.summary.startswith("glTF 2.0")
        assert "Scenes: 1" in (preview.text or "")
        assert "Meshes: 1" in (preview.text or "")
        assert "External dependencies: 2" in (preview.text or "")

        dependencies = backend.dependencies(gltf_ticket.relative_path)
        assert dependencies.dependencies == (
            "arena/mesh.bin",
            "arena/textures/albedo.png",
        )

        manager.require("arena/textures/albedo.png").unlink()
        issues = backend.validate_asset(gltf_ticket.relative_path)
        missing = [issue for issue in issues if issue.code == "dependency_missing"]
        assert len(missing) == 1
        assert "arena/textures/albedo.png" in missing[0].message
        assert missing[0].blocking
    finally:
        backend.close()


def test_gltf_inspection_ignores_embedded_data_uris_and_reports_missing_files(
    tmp_path: Path,
) -> None:
    source = tmp_path / "model.gltf"
    source.write_text(
        json.dumps(
            {
                "asset": {"version": "2.0"},
                "buffers": [
                    {"uri": "missing.bin", "byteLength": 4},
                    {"uri": "data:application/octet-stream;base64,AAAA", "byteLength": 3},
                ],
                "images": [{"uri": "data:image/png;base64,AAAA"}],
            }
        ),
        encoding="utf-8",
    )

    inspection = inspect_gltf21(source)

    assert inspection.external_dependencies == ((tmp_path / "missing.bin").resolve(),)
    assert inspection.missing_dependencies == ((tmp_path / "missing.bin").resolve(),)
    assert inspection.buffers == 2
    assert inspection.images == 1


def test_format_aware_pipeline_surfaces_invalid_gltf_as_actionable_error(tmp_path: Path) -> None:
    root = tmp_path / "project" / "assets"
    root.mkdir(parents=True)
    (root / "broken.gltf").write_text("{not-json", encoding="utf-8")
    manager = AssetManager(root)
    backend = create_format_aware_editor_asset_pipeline21(manager, max_workers=1)
    try:
        issues = backend.validate_asset("broken.gltf")

        invalid = next(issue for issue in issues if issue.code == "gltf_invalid")
        assert invalid.blocking
        assert invalid.action is not None
        assert "reimport" in invalid.action.lower()
    finally:
        backend.close()
