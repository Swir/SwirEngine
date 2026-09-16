from __future__ import annotations

from dataclasses import dataclass

import pytest

from swirengine import Cube3D, Scene, Vec3
from swirengine.editor import SceneInspector
from swirengine.editor_authoring import EditorAuthoringSession, EditorAuthoringTransaction


@dataclass
class Actor:
    name: str
    health: int = 100
    enabled: bool = True


def test_multi_selection_modes_keep_primary_selection_compatible() -> None:
    scene = Scene()
    first = scene.add(Actor("First"))
    second = scene.add(Actor("Second"))
    third = scene.add(Actor("Third"))
    inspector = SceneInspector(scene)
    authoring = EditorAuthoringSession(inspector)

    snapshot = authoring.select(first)
    assert snapshot.keys == (inspector.key_for(first),)
    assert inspector.selected_target is first

    snapshot = authoring.select(second, mode="add")
    assert snapshot.keys == (inspector.key_for(first), inspector.key_for(second))
    assert snapshot.primary_key == inspector.key_for(second)
    assert inspector.selected_target is second

    snapshot = authoring.select(third, mode="add")
    assert snapshot.count == 3
    assert inspector.selected_target is third

    snapshot = authoring.select(second, mode="toggle")
    assert snapshot.keys == (inspector.key_for(first), inspector.key_for(third))
    assert inspector.selected_target is third

    snapshot = authoring.select(third, mode="toggle")
    assert snapshot.keys == (inspector.key_for(first),)
    assert inspector.selected_target is first


def test_hierarchy_range_selection_is_inclusive_and_target_is_primary() -> None:
    scene = Scene()
    root = scene.add(Actor("Root"))
    first = scene.add(Actor("First"))
    second = scene.add(Actor("Second"))
    third = scene.add(Actor("Third"))
    inspector = SceneInspector(scene)
    inspector.set_parent(first, root)
    inspector.set_parent(second, root)
    inspector.set_parent(third, root)
    inspector.clear_history()
    authoring = EditorAuthoringSession(inspector)

    snapshot = authoring.select_range(first, third)

    assert snapshot.keys == (
        inspector.key_for(first),
        inspector.key_for(second),
        inspector.key_for(third),
    )
    assert snapshot.primary_key == inspector.key_for(third)
    assert inspector.selected_target is third

    reverse = authoring.select_range(third, first)
    assert set(reverse.keys) == {
        inspector.key_for(first),
        inspector.key_for(second),
        inspector.key_for(third),
    }
    assert reverse.primary_key == inspector.key_for(first)
    assert inspector.selected_target is first


def test_stale_multi_selection_is_pruned_and_primary_is_resynchronized() -> None:
    scene = Scene()
    first = scene.add(Actor("First"))
    second = scene.add(Actor("Second"))
    inspector = SceneInspector(scene)
    authoring = EditorAuthoringSession(inspector)
    authoring.select(first)
    authoring.select(second, mode="add")

    scene.remove(second)
    snapshot = authoring.selection_snapshot

    assert snapshot.keys == (inspector.key_for(first),)
    assert inspector.selected_target is first


def test_batch_property_edit_undoes_and_redoes_as_one_authoring_transaction() -> None:
    scene = Scene()
    first = scene.add(Actor("First", health=100))
    second = scene.add(Actor("Second", health=80))
    inspector = SceneInspector(scene)
    authoring = EditorAuthoringSession(inspector)
    authoring.select(first)
    authoring.select(second, mode="add")

    result = authoring.set_property("health", 25)

    assert result.target_keys == (inspector.key_for(first), inspector.key_for(second))
    assert result.transaction.edit_count == 2
    assert (first.health, second.health) == (25, 25)
    assert len(inspector.undo_history) == 2

    undone = authoring.undo()
    assert isinstance(undone, EditorAuthoringTransaction)
    assert (first.health, second.health) == (100, 80)
    assert not inspector.can_undo
    assert inspector.can_redo

    redone = authoring.redo()
    assert isinstance(redone, EditorAuthoringTransaction)
    assert (first.health, second.health) == (25, 25)
    assert inspector.can_undo
    assert not inspector.can_redo


def test_batch_property_transaction_tracks_only_real_history_edits() -> None:
    scene = Scene()
    unchanged = scene.add(Actor("Unchanged", health=25))
    changed = scene.add(Actor("Changed", health=80))
    inspector = SceneInspector(scene)
    authoring = EditorAuthoringSession(inspector)
    authoring.select(unchanged)
    authoring.select(changed, mode="add")

    result = authoring.set_property("health", 25)

    assert result.target_keys == (inspector.key_for(unchanged), inspector.key_for(changed))
    assert result.transaction.edit_count == 1
    assert len(inspector.undo_history) == 1
    assert (unchanged.health, changed.health) == (25, 25)

    undone = authoring.undo()
    assert isinstance(undone, EditorAuthoringTransaction)
    assert (unchanged.health, changed.health) == (25, 80)
    redone = authoring.redo()
    assert isinstance(redone, EditorAuthoringTransaction)
    assert (unchanged.health, changed.health) == (25, 25)


def test_all_noop_batch_does_not_create_authoring_or_inspector_history() -> None:
    scene = Scene()
    first = scene.add(Actor("First", health=25))
    second = scene.add(Actor("Second", health=25))
    inspector = SceneInspector(scene)
    authoring = EditorAuthoringSession(inspector)
    authoring.select(first)
    authoring.select(second, mode="add")

    result = authoring.set_property("health", 25)

    assert result.transaction.edit_count == 0
    assert not inspector.can_undo
    assert authoring.undo() is None


def test_multi_gizmo_preflights_selection_and_groups_history() -> None:
    scene = Scene()
    first = scene.add(Cube3D(position=Vec3(0.0, 0.0, -5.0)))
    second = scene.add(Cube3D(position=Vec3(5.0, 0.0, -5.0)))
    inspector = SceneInspector(scene)
    authoring = EditorAuthoringSession(inspector)
    authoring.select(first)
    authoring.select(second, mode="add")

    result = authoring.apply_gizmo("translate", "x", 2.0, snap=1.0)

    assert result.transaction.edit_count == 2
    assert first.position.x == pytest.approx(2.0)
    assert second.position.x == pytest.approx(7.0)

    authoring.undo()
    assert first.position.x == pytest.approx(0.0)
    assert second.position.x == pytest.approx(5.0)
    authoring.redo()
    assert first.position.x == pytest.approx(2.0)
    assert second.position.x == pytest.approx(7.0)


def test_multi_gizmo_mixed_unsupported_selection_fails_before_mutation() -> None:
    scene = Scene()
    cube = scene.add(Cube3D(position=Vec3(1.0, 0.0, -5.0)))
    actor = scene.add(Actor("NoTransform"))
    inspector = SceneInspector(scene)
    authoring = EditorAuthoringSession(inspector)
    authoring.select(cube)
    authoring.select(actor, mode="add")

    with pytest.raises(TypeError, match="translatable"):
        authoring.apply_gizmo("translate", "x", 3.0)

    assert cube.position.x == pytest.approx(1.0)
    assert not inspector.can_undo


def test_interleaved_legacy_edit_falls_back_to_single_inspector_undo() -> None:
    scene = Scene()
    first = scene.add(Actor("First", health=100))
    second = scene.add(Actor("Second", health=80))
    inspector = SceneInspector(scene)
    authoring = EditorAuthoringSession(inspector)
    authoring.select(first)
    authoring.select(second, mode="add")
    authoring.set_property("health", 25)

    inspector.set_property("name", "Legacy", target=first)
    undone = authoring.undo()

    assert not isinstance(undone, EditorAuthoringTransaction)
    assert first.name == "First"
    assert (first.health, second.health) == (25, 25)
