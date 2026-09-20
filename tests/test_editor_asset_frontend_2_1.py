from __future__ import annotations

from pathlib import Path

import pytest

from swirengine.assets import AssetManager
from swirengine.editor_asset_frontend21 import (
    EditorAssetWorkflow21,
    create_editor_asset_pipeline21,
)
from swirengine.editor_assets import EditorAssetBrowser


def _workflow(tmp_path: Path) -> EditorAssetWorkflow21:
    manager = AssetManager(tmp_path / "project" / "assets")
    browser = EditorAssetBrowser(manager)
    backend = create_editor_asset_pipeline21(manager, max_workers=1)
    return EditorAssetWorkflow21(backend, browser)


def test_default_editor_pipeline_uses_runtime_asset_scheduler(tmp_path: Path) -> None:
    workflow = _workflow(tmp_path)
    try:
        backend = workflow.backend
        assert backend.processor_for("textures/player.png") == "editor-source-metadata"
        assert backend.processor_for("audio/theme.wav") == "editor-source-metadata"
        assert backend.processor_for("models/arena.glb") == "editor-source-metadata"
        assert backend.processor_for("scripts/player.py") == "editor-source-metadata"
        assert backend.processor_for("shaders/world.frag") == "editor-source-metadata"
        assert backend.processor_for("unknown/archive.bin") is None
        assert backend.pipeline.processor_names() == ("editor-source-metadata",)
        assert backend.pipeline.max_workers == 1
    finally:
        workflow.shutdown()


def test_asset_workflow_import_preview_background_and_reimport(tmp_path: Path) -> None:
    source = tmp_path / "source" / "dialogue.txt"
    source.parent.mkdir()
    source.write_text("first version\n", encoding="utf-8")
    workflow = _workflow(tmp_path)
    try:
        tickets = workflow.import_paths([source])
        assert len(tickets) == 1
        ticket = tickets[0]
        assert ticket.relative_path == "dialogue.txt"
        assert ticket.copied is True
        assert ticket.queued is True
        assert workflow.selected_path == "dialogue.txt"

        result = workflow.backend.wait(ticket, timeout=5.0)
        assert result.successful is True
        assert result.value["size_bytes"] == source.stat().st_size
        assert len(result.value["sha256"]) == 64

        frame = workflow.refresh()
        assert frame.selected_path == "dialogue.txt"
        assert frame.preview is not None
        assert frame.preview.text == source.read_bytes().decode("utf-8")
        assert frame.dependencies is not None
        assert frame.dependencies.dependencies == ()
        assert frame.dependencies.dependents == ()
        assert frame.issues == ()
        assert frame.healthy is True
        assert frame.pipeline.diagnostics.completed >= 1

        source.write_text("second version\n", encoding="utf-8")
        reimport = workflow.reimport_selected()
        assert reimport.relative_path == "dialogue.txt"
        assert reimport.copied is True
        assert reimport.queued is True
        second = workflow.backend.wait(reimport, timeout=5.0)
        assert second.successful is True
        assert second.value["size_bytes"] == source.stat().st_size
        assert workflow.frame().preview is not None
        assert workflow.frame().preview.text == source.read_bytes().decode("utf-8")
    finally:
        workflow.shutdown()


def test_asset_workflow_directory_import_preserves_drop_structure(tmp_path: Path) -> None:
    dropped = tmp_path / "external" / "characters"
    (dropped / "hero").mkdir(parents=True)
    (dropped / "hero" / "stats.json").write_text('{"hp": 100}\n', encoding="utf-8")
    (dropped / "readme.txt").write_text("characters\n", encoding="utf-8")
    workflow = _workflow(tmp_path)
    try:
        tickets = workflow.import_paths([dropped], destination_folder="content", submit=False)
        assert tuple(ticket.relative_path for ticket in tickets) == (
            "content/characters/hero/stats.json",
            "content/characters/readme.txt",
        )
        frame = workflow.browser.frame()
        assert tuple(entry.relative_path for entry in frame.entries) == (
            "content/characters/hero/stats.json",
            "content/characters/readme.txt",
        )
        assert workflow.selected_path == "content/characters/readme.txt"
    finally:
        workflow.shutdown()


def test_asset_workflow_requires_one_shared_asset_manager(tmp_path: Path) -> None:
    first = AssetManager(tmp_path / "first")
    second = AssetManager(tmp_path / "second")
    backend = create_editor_asset_pipeline21(first, max_workers=1)
    try:
        with pytest.raises(ValueError, match="share one AssetManager"):
            EditorAssetWorkflow21(backend, EditorAssetBrowser(second))
    finally:
        backend.close()
