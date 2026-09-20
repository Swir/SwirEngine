from pathlib import Path

from swirengine.cli import new_project
from swirengine.editor_app21 import EditorProjectSession
from swirengine.editor_viewport_frontend21 import EditorProductionViewportController21


def test_project_session_uses_production_viewport_and_manifest_mode(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    root = new_project("ViewportSession", "2d")

    session = EditorProjectSession.open(root)

    assert isinstance(session.controller, EditorProductionViewportController21)
    assert session.workspace.viewport.mode == "2d"
    assert session.controller.viewport_controller.workspace is session.workspace


def test_saved_viewport_mode_wins_over_manifest_default(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    root = new_project("ViewportState", "2d")
    session = EditorProjectSession.open(root)
    session.workspace.configure_viewport(mode="3d")
    session.save()

    restored = EditorProjectSession.open(root)

    assert restored.workspace.viewport.mode == "3d"
    assert isinstance(restored.controller, EditorProductionViewportController21)
