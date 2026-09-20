from __future__ import annotations

from pathlib import Path

import pytest

from swirengine import AssetManager
from swirengine.asset_pipeline import AssetImportState, AssetPipeline
from swirengine.editor_asset_pipeline21 import (
    EditorAssetIssueSeverity,
    EditorAssetPipeline21,
)


def _workspace(tmp_path: Path) -> tuple[AssetManager, AssetPipeline, EditorAssetPipeline21]:
    manager = AssetManager(tmp_path / "project" / "assets")
    pipeline = AssetPipeline(manager, max_workers=1)
    pipeline.register_processor(
        "text",
        suffixes=(".txt",),
        loader=lambda path: path.read_text(encoding="utf-8").upper(),
    )
    return manager, pipeline, EditorAssetPipeline21(manager, pipeline)


def test_editor_asset_pipeline_imports_previews_and_reimports_from_origin(tmp_path: Path) -> None:
    manager, _pipeline, editor = _workspace(tmp_path)
    source = tmp_path / "incoming" / "dialogue.txt"
    source.parent.mkdir()
    source.write_text("hello creator", encoding="utf-8")

    ticket = editor.import_file(source, destination="text/dialogue.txt")

    assert ticket.relative_path == "text/dialogue.txt"
    assert ticket.copied
    assert ticket.queued
    assert manager.require("text/dialogue.txt").read_text(encoding="utf-8") == "hello creator"
    result = editor.wait(ticket, timeout=2.0)
    assert result.state is AssetImportState.COMPLETED
    assert result.value == "HELLO CREATOR"

    preview = editor.preview("text/dialogue.txt")
    assert preview.text == "hello creator"
    assert preview.kind == "other"
    assert editor.origin("text/dialogue.txt") == source.resolve()

    source.write_text("changed", encoding="utf-8")
    reimport = editor.reimport("text/dialogue.txt")
    reimport_result = editor.wait(reimport, timeout=2.0)

    assert reimport.copied
    assert reimport_result.state is AssetImportState.COMPLETED
    assert reimport_result.value == "CHANGED"
    assert manager.require("text/dialogue.txt").read_text(encoding="utf-8") == "changed"
    editor.close()


def test_editor_asset_pipeline_drop_batch_preserves_directory_structure(tmp_path: Path) -> None:
    _manager, _pipeline, editor = _workspace(tmp_path)
    drop = tmp_path / "drop"
    (drop / "nested").mkdir(parents=True)
    (drop / "one.txt").write_text("one", encoding="utf-8")
    (drop / "nested" / "two.txt").write_text("two", encoding="utf-8")
    (drop / "nested" / "raw.bin").write_bytes(b"binary")

    tickets = editor.import_paths((drop,), destination_folder="imports", submit=True)

    assert [ticket.relative_path for ticket in tickets] == [
        "imports/drop/nested/raw.bin",
        "imports/drop/nested/two.txt",
        "imports/drop/one.txt",
    ]
    unsupported = tickets[0]
    assert not unsupported.queued
    issue = next(item for item in unsupported.issues if item.code == "processor_missing")
    assert issue.severity is EditorAssetIssueSeverity.WARNING
    assert "register" in (issue.action or "").lower()

    queued = [ticket for ticket in tickets if ticket.queued]
    assert len(queued) == 2
    assert {editor.wait(ticket, timeout=2.0).value for ticket in queued} == {"ONE", "TWO"}
    editor.close()


def test_editor_asset_pipeline_exposes_runtime_dependency_graph(tmp_path: Path) -> None:
    root = tmp_path / "project" / "assets"
    root.mkdir(parents=True)
    (root / "material.dep").write_text("texture.txt", encoding="utf-8")
    (root / "texture.txt").write_text("pixels", encoding="utf-8")
    manager = AssetManager(root)
    pipeline = AssetPipeline(manager, max_workers=1)
    pipeline.register_processor(
        "dependency",
        suffixes=(".dep",),
        loader=lambda path: path.read_text(encoding="utf-8"),
        dependencies=lambda path: (path.read_text(encoding="utf-8").strip(),),
    )
    editor = EditorAssetPipeline21(manager, pipeline)

    ticket = editor.reimport("material.dep")
    result = editor.wait(ticket, timeout=2.0)

    assert result.successful
    view = editor.dependencies("material.dep")
    assert view.dependencies == ("texture.txt",)
    assert view.dependents == ()

    reverse = pipeline.dependencies.direct_dependents(root / "texture.txt")
    assert reverse == ((root / "material.dep").resolve(),)

    (root / "texture.txt").unlink()
    issues = editor.validate_asset("material.dep")
    missing = next(issue for issue in issues if issue.code == "dependency_missing")
    assert missing.severity is EditorAssetIssueSeverity.ERROR
    assert "texture.txt" in missing.message
    editor.close()


@pytest.mark.parametrize(
    "destination",
    (
        "../escape.txt",
        "/tmp/escape.txt",
        r"C:\temp\escape.txt",
        r"\\server\share\escape.txt",
    ),
)
def test_editor_asset_pipeline_rejects_unsafe_destinations(
    tmp_path: Path,
    destination: str,
) -> None:
    _manager, _pipeline, editor = _workspace(tmp_path)
    source = tmp_path / "source.txt"
    source.write_text("safe", encoding="utf-8")

    issues = editor.validate_import(source, destination=destination)

    assert any(issue.code == "destination_unsafe" and issue.blocking for issue in issues)
    with pytest.raises(ValueError, match="project-relative"):
        editor.import_file(source, destination=destination)
    editor.close()


def test_editor_asset_pipeline_requires_explicit_overwrite_and_reports_failures(
    tmp_path: Path,
) -> None:
    manager = AssetManager(tmp_path / "project" / "assets")
    pipeline = AssetPipeline(manager, max_workers=1)
    pipeline.register_processor(
        "broken",
        suffixes=(".bad",),
        loader=lambda _path: (_ for _ in ()).throw(RuntimeError("broken importer")),
    )
    editor = EditorAssetPipeline21(manager, pipeline)
    first = tmp_path / "first.bad"
    second = tmp_path / "second.bad"
    first.write_bytes(b"first")
    second.write_bytes(b"second")

    initial = editor.import_file(first, destination="same.bad")
    failure = editor.wait(initial, timeout=2.0)
    assert failure.state is AssetImportState.FAILED
    assert failure.error == "broken importer"

    issues = editor.validate_import(second, destination="same.bad")
    assert any(issue.code == "destination_exists" and issue.blocking for issue in issues)
    with pytest.raises(ValueError, match="already exists"):
        editor.import_file(second, destination="same.bad")

    overwritten = editor.import_file(second, destination="same.bad", overwrite=True)
    overwritten_failure = editor.wait(overwritten, timeout=2.0)
    assert overwritten_failure.state is AssetImportState.FAILED
    assert manager.require("same.bad").read_bytes() == b"second"
    assert editor.frame().diagnostics.failed == 2
    assert len(editor.frame().recent_results) == 2
    editor.close()
