from __future__ import annotations

from pathlib import Path

import pytest

from swirengine import Color, Rectangle2D
from swirengine.editor_app21 import EditorProjectSession
from swirengine.editor_scene21 import UnsavedSceneChangesError
from swirengine.project_scaffold21 import new_project21


def _rect(name: str) -> Rectangle2D:
    return Rectangle2D(10, 20, 48, 32, Color(0.1, 0.7, 1.0, 1.0), name=name)


def test_scene_authoring_manages_multiple_open_scenes_and_dirty_tabs(tmp_path: Path) -> None:
    root = new_project21("SceneTabs", "2d", parent=tmp_path)
    session = EditorProjectSession.open(root)

    assert session.scenes.dirty
    session.scenes.add_object(_rect("MainPlayer"))
    session.save()
    assert not session.scenes.dirty

    arena = session.scenes.new_scene("scenes/arena.swirscene")
    arena.add(_rect("ArenaPlayer"))
    assert session.scenes.active_path == "scenes/arena.swirscene"
    assert session.scenes.dirty
    session.save()

    tabs = {tab.path: tab for tab in session.scenes.tabs()}
    assert set(tabs) == {"scenes/main.swirscene", "scenes/arena.swirscene"}
    assert tabs["scenes/arena.swirscene"].active
    assert tabs["scenes/arena.swirscene"].object_count == 1
    assert not any(tab.dirty for tab in tabs.values())

    main = session.scenes.open_scene("scenes/main.swirscene")
    assert len(main.objects) == 1
    assert main.objects[0].name == "MainPlayer"
    session.save()
    assert not session.scenes.dirty


def test_scene_authoring_duplicates_reparents_and_removes_objects_and_entities(
    tmp_path: Path,
) -> None:
    root = new_project21("AuthoringOps", "2d", parent=tmp_path)
    session = EditorProjectSession.open(root)
    parent = session.scenes.add_object(_rect("Parent"))
    child = session.scenes.add_object(_rect("Child"), parent=parent)

    duplicate = session.scenes.duplicate(child)
    assert duplicate is not child
    assert duplicate.name == "Child Copy"
    assert session.workspace.inspector.parent(duplicate) is parent
    assert session.workspace.inspector.selected_target is duplicate

    entity = session.scenes.create_entity(name="Enemy", tags=("enemy",), parent=parent)
    entity_copy = session.scenes.duplicate(entity)
    assert entity_copy.name == "Enemy Copy"
    assert entity_copy.tags == entity.tags
    assert session.workspace.inspector.parent(entity_copy) is parent

    session.scenes.reparent(duplicate, None)
    assert session.workspace.inspector.parent(duplicate) is None
    assert session.scenes.remove(entity_copy)
    assert entity_copy not in session.workspace.scene.entities
    assert session.scenes.remove(duplicate)
    assert duplicate not in session.workspace.scene.objects


def test_closing_dirty_scene_requires_explicit_discard(tmp_path: Path) -> None:
    root = new_project21("CloseProtection", "2d", parent=tmp_path)
    session = EditorProjectSession.open(root)
    session.save()
    session.scenes.new_scene("scenes/unsaved.swirscene")
    session.scenes.add_object(_rect("Unsaved"))

    with pytest.raises(UnsavedSceneChangesError, match="unsaved changes"):
        session.scenes.close_scene("scenes/unsaved.swirscene")

    session.scenes.close_scene("scenes/unsaved.swirscene", discard_unsaved=True)
    assert session.scenes.scene_paths == ("scenes/main.swirscene",)
    assert session.scenes.active_path == "scenes/main.swirscene"


def test_recovery_snapshot_restores_unsaved_scene_and_is_cleared_after_save(tmp_path: Path) -> None:
    root = new_project21("Recovery", "2d", parent=tmp_path)
    session = EditorProjectSession.open(root)
    session.save()
    session.scenes.add_object(_rect("RecoveredPlayer"))
    recovery_path = session.scenes.write_recovery()

    assert recovery_path.is_file()
    recovered = EditorProjectSession.open(root, restore_recovery=True)
    assert len(recovered.workspace.scene.objects) == 1
    assert recovered.workspace.scene.objects[0].name == "RecoveredPlayer"
    assert recovered.scenes.dirty
    assert recovered.scenes.recovery_available

    recovered.save()
    assert not recovered.scenes.recovery_available
    assert not recovered.scenes.dirty

    reopened = EditorProjectSession.open(root)
    assert len(reopened.workspace.scene.objects) == 1
    assert reopened.workspace.scene.objects[0].name == "RecoveredPlayer"
