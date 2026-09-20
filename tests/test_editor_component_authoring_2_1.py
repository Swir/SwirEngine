from __future__ import annotations

from dataclasses import dataclass

import pytest

from swirengine import Scene
from swirengine.editor import SceneInspector
from swirengine.editor_component_authoring import EditorComponentAuthoringSession
from swirengine.editor_typed_inspector import EditorTypedInspector


@dataclass
class Health:
    value: int = 100


@dataclass
class Speed:
    value: float = 3.0


def _entity_pair() -> tuple[object, object, EditorComponentAuthoringSession]:
    scene = Scene()
    first = scene.create_entity(name="One")
    second = scene.create_entity(name="Two")
    session = EditorComponentAuthoringSession(SceneInspector(scene))
    session.select(first)
    session.select(second, mode="add")
    return first, second, session


def test_add_component_is_one_multi_selection_undo_redo_action() -> None:
    first, second, session = _entity_pair()

    result = session.add_component(Health(75))
    assert result.target_keys == (f"entity:{first.id}", f"entity:{second.id}")
    assert first.require(Health).value == 75
    assert second.require(Health).value == 75
    assert len(session.creator_undo_history) == 1

    session.undo()
    assert first.get(Health) is None
    assert second.get(Health) is None

    session.redo()
    assert first.require(Health).value == 75
    assert second.require(Health).value == 75


def test_remove_component_restores_lossless_snapshots() -> None:
    first, second, session = _entity_pair()
    first.add(Health(10))
    second.add(Health(20))

    session.remove_component(Health)
    assert first.get(Health) is None
    assert second.get(Health) is None

    session.undo()
    assert first.require(Health).value == 10
    assert second.require(Health).value == 20

    session.redo()
    assert first.get(Health) is None
    assert second.get(Health) is None


def test_component_preflight_prevents_partial_multi_selection_mutation() -> None:
    first, second, session = _entity_pair()
    second.add(Health(5))

    with pytest.raises(ValueError):
        session.add_component(Health(50))
    assert first.get(Health) is None
    assert second.require(Health).value == 5

    first.add(Speed(1.0))
    with pytest.raises(KeyError):
        session.remove_component(Speed)
    assert first.require(Speed).value == 1.0
    assert second.get(Speed) is None


def test_component_authoring_rejects_mixed_object_entity_selection() -> None:
    scene = Scene()
    entity = scene.create_entity(name="Entity")
    object_target = scene.add(Health(10))
    session = EditorComponentAuthoringSession(SceneInspector(scene))
    session.select(entity)
    session.select(object_target, mode="add")

    with pytest.raises(TypeError):
        session.add_component(Speed())
    assert entity.get(Speed) is None


def test_property_and_component_edits_share_chronological_creator_undo() -> None:
    first, second, session = _entity_pair()
    typed = EditorTypedInspector(session)

    typed.set("name", "Shared")
    session.add_component(Health(40))
    assert first.name == "Shared"
    assert second.name == "Shared"
    assert first.has(Health) and second.has(Health)

    session.undo()
    assert not first.has(Health) and not second.has(Health)
    assert first.name == "Shared" and second.name == "Shared"

    session.undo()
    assert first.name == "One"
    assert second.name == "Two"

    session.redo()
    session.redo()
    assert first.name == "Shared" and second.name == "Shared"
    assert first.require(Health).value == 40
    assert second.require(Health).value == 40


def test_component_undo_fails_without_corrupting_history_when_target_disappears() -> None:
    first, second, session = _entity_pair()
    session.add_component(Health())
    second.destroy()

    with pytest.raises(LookupError):
        session.undo()
    assert len(session.creator_undo_history) == 1
    assert first.has(Health)
