from __future__ import annotations

import json
from pathlib import Path

import pytest

from swirengine import Color, Rectangle2D
from swirengine.editor_app21 import (
    EDITOR_STATE_FILE,
    EditorProjectError,
    EditorProjectSession,
    create_editor_project,
)
from swirengine.creator_workflow20 import CreatorProjectWorkflow
from swirengine.project19 import ProjectManifest


def test_editor_creator_uses_2x_manifest_and_path_basename(tmp_path: Path) -> None:
    root = create_editor_project(tmp_path / "VisualGame", "3d")
    manifest = ProjectManifest.load(root)

    assert manifest.name == "VisualGame"
    assert manifest.mode == "3d"
    assert manifest.engine == ">=2.0,<3.0"
    assert (root / "assets").is_dir()
    assert (root / "scenes").is_dir()
    assert (root / "config").is_dir()
    assert (root / "config" / "controls.json").is_file()
    assert (root / "config" / "settings.json").is_file()

    report = CreatorProjectWorkflow(root).inspect(
        profile_name="linux",
        platform="linux",
        environ={},
        home=tmp_path / "home",
    )
    assert report.ready


def test_editor_session_persists_scene_and_workspace_state(tmp_path: Path) -> None:
    root = create_editor_project(tmp_path / "Persistent2D", "2d")
    session = EditorProjectSession.open(root)
    actor = session.workspace.scene.add(
        Rectangle2D(10, 20, 40, 50, Color(0.1, 0.2, 0.3, 1.0), name="hero")
    )
    session.workspace.select(actor)
    session.workspace.configure_viewport(
        mode="2d",
        gizmo="scale",
        snap_enabled=True,
        translation_snap=8.0,
    )

    saved = session.save()

    assert saved.scene_path == root / "scenes" / "main.swirscene"
    assert saved.state_path == root / EDITOR_STATE_FILE
    assert saved.scene_path.is_file()
    assert saved.state_path.is_file()

    reopened = EditorProjectSession.open(root)
    assert len(reopened.workspace.scene.objects) == 1
    assert reopened.workspace.scene.objects[0].name == "hero"
    assert reopened.workspace.viewport.mode == "2d"
    assert reopened.workspace.viewport.gizmo == "scale"
    assert reopened.workspace.viewport.snap_enabled
    assert reopened.workspace.viewport.translation_snap == pytest.approx(8.0)
    assert reopened.preview.workspace is reopened.workspace


def test_editor_session_rejects_scene_escape_from_saved_state(tmp_path: Path) -> None:
    root = create_editor_project(tmp_path / "SafeEditor", "2d")
    session = EditorProjectSession.open(root)
    session.save()

    state_path = root / EDITOR_STATE_FILE
    payload = json.loads(state_path.read_text(encoding="utf-8"))
    payload["active_scene_id"] = "../escape"
    payload["scenes"][0]["scene_id"] = "../escape"
    state_path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(EditorProjectError, match="project-relative"):
        EditorProjectSession.open(root)


def test_editor_creator_rejects_unknown_mode(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="mode"):
        create_editor_project(tmp_path / "Broken", "vr")