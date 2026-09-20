from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import PurePosixPath

import pytest

from swirengine import Scene
from swirengine.editor import SceneInspector
from swirengine.editor_authoring import EditorAuthoringSession
from swirengine.editor_typed_inspector import EditorTypedInspector


class Mood(Enum):
    IDLE = "idle"
    ALERT = "alert"


@dataclass
class InspectableActor:
    name: str
    enabled: bool = True
    health: int = 100
    speed: float = 3.0
    title: str = "Actor"
    mood: Mood = Mood.IDLE
    texture: PurePosixPath = field(
        default_factory=lambda: PurePosixPath("textures/default.png")
    )
    position: tuple[float, float, float] = (0.0, 0.0, 0.0)


def _typed_pair() -> tuple[InspectableActor, InspectableActor, EditorAuthoringSession, EditorTypedInspector]:
    scene = Scene()
    first = scene.add(InspectableActor("One", health=100))
    second = scene.add(InspectableActor("Two", health=75))
    authoring = EditorAuthoringSession(SceneInspector(scene))
    authoring.select(first)
    authoring.select(second, mode="add")
    return first, second, authoring, EditorTypedInspector(authoring)


def test_schema_reports_control_kinds_and_mixed_values() -> None:
    _first, _second, _authoring, typed = _typed_pair()
    fields = {field.name: field for field in typed.fields()}

    assert fields["enabled"].kind == "boolean"
    assert fields["health"].kind == "number"
    assert fields["health"].mixed
    assert fields["speed"].kind == "number"
    assert fields["title"].kind == "text"
    assert fields["mood"].kind == "choice"
    assert fields["mood"].choices == ("IDLE", "ALERT")
    assert fields["texture"].kind == "asset_path"
    assert fields["position"].kind == "vector"


def test_typed_set_coerces_and_groups_multi_selection_undo_redo() -> None:
    first, second, authoring, typed = _typed_pair()

    result = typed.set("health", "42")
    assert first.health == 42
    assert second.health == 42
    assert result.transaction.edit_count == 2

    authoring.undo()
    assert first.health == 100
    assert second.health == 75

    authoring.redo()
    assert first.health == 42
    assert second.health == 42


def test_typed_boolean_enum_path_and_vector_coercion() -> None:
    first, second, _authoring, typed = _typed_pair()

    typed.set("enabled", "off")
    typed.set("mood", "ALERT")
    typed.set("texture", "textures/hero.png")
    typed.set("position", [1, 2.5, 3])

    for actor in (first, second):
        assert actor.enabled is False
        assert actor.mood is Mood.ALERT
        assert actor.texture == PurePosixPath("textures/hero.png")
        assert actor.position == (1.0, 2.5, 3.0)


def test_incompatible_input_is_rejected_before_any_mutation() -> None:
    first, second, _authoring, typed = _typed_pair()

    with pytest.raises(TypeError):
        typed.set("health", True)
    assert first.health == 100
    assert second.health == 75

    with pytest.raises(TypeError):
        typed.set("position", [1, 2])
    assert first.position == (0.0, 0.0, 0.0)
    assert second.position == (0.0, 0.0, 0.0)


def test_empty_selection_exposes_no_fields() -> None:
    scene = Scene()
    authoring = EditorAuthoringSession(SceneInspector(scene))
    typed = EditorTypedInspector(authoring)

    assert typed.fields() == ()
    with pytest.raises(AttributeError):
        typed.field("health")
