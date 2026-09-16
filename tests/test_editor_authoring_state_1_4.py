from __future__ import annotations

from dataclasses import dataclass

import pytest

from swirengine import Scene
from swirengine.editor import SceneInspector
from swirengine.editor_authoring import EditorSelectionModel
from swirengine.editor_authoring_state import (
    EDITOR_AUTHORING_FORMAT,
    EditorAuthoringState,
    capture_editor_authoring,
    restore_editor_authoring,
)
from swirengine.editor_state import capture_editor_hierarchy


@dataclass
class Actor:
    name: str
    enabled: bool = True


def test_authoring_state_json_round_trip_preserves_primary_and_anchor() -> None:
    scene = Scene()
    first = scene.add(Actor("First"))
    second = scene.add(Actor("Second"))
    entity = scene.create_entity(name="Entity")
    inspector = SceneInspector(scene)
    selection = EditorSelectionModel(inspector)
    selection.select(first)
    selection.select(entity, mode="add")
    selection.select(second, mode="add")

    state = capture_editor_authoring(
        inspector,
        selection,
        anchor_key=inspector.key_for(first),
    )
    payload = state.to_dict()
    restored = EditorAuthoringState.loads(state.dumps())

    assert payload["format"] == EDITOR_AUTHORING_FORMAT
    assert [item.kind for item in state.selected] == ["object", "entity", "object"]
    assert state.primary == state.selected[-1]
    assert state.anchor == state.selected[0]
    assert restored == state


def test_authoring_restore_rebuilds_ordered_multi_selection_on_new_inspector() -> None:
    scene = Scene()
    first = scene.add(Actor("First"))
    second = scene.add(Actor("Second"))
    entity = scene.create_entity(name="Entity")
    original = SceneInspector(scene)
    selection = EditorSelectionModel(original)
    selection.select(first)
    selection.select(entity, mode="add")
    selection.select(second, mode="add")
    state = capture_editor_authoring(original, selection)

    inspector = SceneInspector(scene)
    restored_selection = EditorSelectionModel(inspector)
    targets = restore_editor_authoring(inspector, restored_selection, state)

    assert targets == (first, entity, second)
    assert restored_selection.primary_target is second
    assert inspector.selected_target is second


def test_authoring_restore_resolves_every_target_before_mutating_selection() -> None:
    scene = Scene()
    actor = scene.add(Actor("Only"))
    inspector = SceneInspector(scene)
    selection = EditorSelectionModel(inspector)
    selection.select(actor)

    valid = capture_editor_authoring(inspector, selection)
    broken = EditorAuthoringState(
        (*valid.selected, type(valid.selected[0])("object", 99)),
        valid.primary,
    )

    with pytest.raises(LookupError, match="object index 99"):
        restore_editor_authoring(inspector, selection, broken)

    assert selection.selected_targets == (actor,)
    assert inspector.selected_target is actor


def test_authoring_sidecar_does_not_change_stable_hierarchy_document() -> None:
    scene = Scene()
    first = scene.add(Actor("First"))
    second = scene.add(Actor("Second"))
    inspector = SceneInspector(scene)
    selection = EditorSelectionModel(inspector)
    selection.select(first)
    selection.select(second, mode="add")

    hierarchy = capture_editor_hierarchy(inspector).to_dict()
    authoring = capture_editor_authoring(inspector, selection).to_dict()

    assert hierarchy["format"] == "swirengine.editor_hierarchy"
    assert hierarchy["version"] == 1
    assert "selected" not in hierarchy
    assert authoring["format"] == "swirengine.editor_authoring"
    assert len(authoring["selected"]) == 2


def test_authoring_state_rejects_primary_or_anchor_outside_selection() -> None:
    from swirengine.editor_state import EditorTargetRef

    first = EditorTargetRef("object", 0)
    second = EditorTargetRef("object", 1)

    with pytest.raises(ValueError, match="primary"):
        EditorAuthoringState((first,), second)
    with pytest.raises(ValueError, match="anchor"):
        EditorAuthoringState((first,), first, second)
