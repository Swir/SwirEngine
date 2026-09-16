from __future__ import annotations

from dataclasses import dataclass

import pytest

from swirengine import Scene
from swirengine.editor import SceneInspector
from swirengine.editor_authoring import EditorAuthoringSession
from swirengine.editor_authoring_runtime import (
    EditorAuthoringIsolationError,
    EditorAuthoringPlayController,
)
from swirengine.editor_runtime import EditorRuntimeMode, EditorRuntimeSession
from swirengine.serialization import SceneCodecRegistry, SceneSerializer


@dataclass
class MovingActor:
    name: str
    x: float = 0.0
    enabled: bool = True

    def update(self, dt: float) -> None:
        self.x += float(dt) * 10.0


def _serializer() -> SceneSerializer:
    registry = SceneCodecRegistry.default()
    registry.register(MovingActor)
    return SceneSerializer(registry)


def test_play_round_trip_restores_portable_authoring_selection() -> None:
    scene = Scene()
    first = scene.add(MovingActor("First", x=1.0))
    second = scene.add(MovingActor("Second", x=2.0))
    authoring = EditorAuthoringSession(SceneInspector(scene))
    authoring.select(first)
    authoring.select(second, mode="add")
    controller = EditorAuthoringPlayController(
        authoring,
        EditorRuntimeSession(scene, serializer=_serializer()),
    )

    runtime = controller.play()
    authoring.clear_selection()
    assert controller.frame().authoring_locked
    assert controller.update(0.5)
    assert runtime.find("First").x == pytest.approx(6.0)
    assert first.x == pytest.approx(1.0)

    assert controller.stop()
    assert controller.mode is EditorRuntimeMode.EDIT
    assert authoring.selected_targets == (first, second)
    assert authoring.selection_snapshot.primary_key == authoring.inspector.key_for(second)


def test_guarded_authoring_mutations_are_locked_during_play() -> None:
    scene = Scene()
    actor = scene.add(MovingActor("Player", x=3.0))
    authoring = EditorAuthoringSession(SceneInspector(scene))
    authoring.select(actor)
    controller = EditorAuthoringPlayController(
        authoring,
        EditorRuntimeSession(scene, serializer=_serializer()),
    )
    controller.play()

    with pytest.raises(RuntimeError, match="locked"):
        controller.set_property("x", 99.0)
    with pytest.raises(RuntimeError, match="locked"):
        controller.undo()

    assert actor.x == pytest.approx(3.0)
    assert not authoring.inspector.can_undo
    assert controller.stop()


def test_external_edit_scene_mutation_is_detected_before_runtime_is_discarded() -> None:
    scene = Scene()
    actor = scene.add(MovingActor("Player", x=3.0))
    inspector = SceneInspector(scene)
    authoring = EditorAuthoringSession(inspector)
    authoring.select(actor)
    runtime = EditorRuntimeSession(scene, serializer=_serializer())
    controller = EditorAuthoringPlayController(authoring, runtime)
    controller.play()

    inspector.set_property("x", 12.0, target=actor)

    with pytest.raises(EditorAuthoringIsolationError, match="edit scene changed"):
        controller.stop()

    assert runtime.mode is EditorRuntimeMode.PLAYING
    assert runtime.runtime_scene is not None

    assert controller.stop(force=True)
    assert runtime.mode is EditorRuntimeMode.EDIT
    assert actor.x == pytest.approx(12.0)


def test_pause_resume_keeps_one_isolation_baseline_until_stop() -> None:
    scene = Scene()
    actor = scene.add(MovingActor("Player"))
    authoring = EditorAuthoringSession(SceneInspector(scene))
    authoring.select(actor)
    controller = EditorAuthoringPlayController(
        authoring,
        EditorRuntimeSession(scene, serializer=_serializer(), fixed_step=0.25),
    )

    runtime = controller.play()
    assert controller.pause()
    assert controller.step()
    assert controller.play() is runtime
    controller.assert_isolated()
    assert controller.stop()
    assert actor.x == pytest.approx(0.0)


def test_controller_requires_authoring_and_runtime_to_share_edit_scene() -> None:
    scene = Scene()
    other = Scene()
    authoring = EditorAuthoringSession(SceneInspector(scene))

    with pytest.raises(ValueError, match="same edit scene"):
        EditorAuthoringPlayController(
            authoring,
            EditorRuntimeSession(other, serializer=_serializer()),
        )
