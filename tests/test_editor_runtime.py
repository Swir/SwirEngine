from dataclasses import dataclass

import pytest

from swirengine import Scene
from swirengine.editor_runtime import EditorRuntimeMode, EditorRuntimeSession
from swirengine.serialization import SceneCodecRegistry, SceneSerializer


@dataclass
class MovingActor:
    name: str
    x: float = 0.0
    enabled: bool = True

    def update(self, dt: float) -> None:
        self.x += dt * 10.0


def runtime_serializer() -> SceneSerializer:
    registry = SceneCodecRegistry.default()
    registry.register(MovingActor)
    return SceneSerializer(registry)


def test_play_mode_clones_scene_and_discards_runtime_mutations_on_stop():
    scene = Scene()
    actor = scene.add(MovingActor("Player", x=2.0))
    session = EditorRuntimeSession(scene, serializer=runtime_serializer())

    runtime = session.play()
    runtime_actor = runtime.find("Player")

    assert runtime is not scene
    assert runtime_actor is not actor
    assert session.mode is EditorRuntimeMode.PLAYING
    assert session.frame().play_scene_isolated

    assert session.update(0.5)
    assert runtime_actor.x == pytest.approx(7.0)
    assert actor.x == pytest.approx(2.0)

    assert session.stop()
    assert session.active_scene is scene
    assert session.mode is EditorRuntimeMode.EDIT
    assert actor.x == pytest.approx(2.0)
    assert session.elapsed == 0.0
    assert session.frame_count == 0


def test_pause_resume_and_single_step_preserve_runtime_scene():
    scene = Scene()
    scene.add(MovingActor("Player"))
    session = EditorRuntimeSession(scene, serializer=runtime_serializer(), fixed_step=0.25)

    runtime = session.play()
    assert session.update(99.0)
    assert runtime.find("Player").x == pytest.approx(2.5)
    assert session.pause()
    assert not session.update(1.0)

    assert session.step()
    assert runtime.find("Player").x == pytest.approx(5.0)
    assert session.mode is EditorRuntimeMode.PAUSED
    assert session.frame_count == 2
    assert session.elapsed == pytest.approx(0.5)

    assert session.play() is runtime
    assert session.mode is EditorRuntimeMode.PLAYING


def test_runtime_callbacks_are_ordered_and_unsubscribable():
    scene = Scene()
    scene.add(MovingActor("Player"))
    session = EditorRuntimeSession(scene, serializer=runtime_serializer())
    events: list[tuple[str, Scene]] = []

    remove_start = session.on_started(lambda runtime: events.append(("start", runtime)))
    session.on_stopped(lambda runtime: events.append(("stop", runtime)))

    first_runtime = session.play()
    session.stop()
    remove_start()
    second_runtime = session.play()
    session.stop()

    assert events == [("start", first_runtime), ("stop", first_runtime), ("stop", second_runtime)]


def test_runtime_session_validates_steps_and_scene_replacement():
    scene = Scene()
    session = EditorRuntimeSession(scene, serializer=runtime_serializer())

    with pytest.raises(ValueError, match="fixed_step"):
        EditorRuntimeSession(scene, fixed_step=0.0)
    with pytest.raises(ValueError, match="dt is required"):
        session.play()
        session.pause()
        session.step()
    with pytest.raises(ValueError, match="dt cannot be negative"):
        session.step(-0.1)
    with pytest.raises(RuntimeError, match="Play mode"):
        session.replace_edit_scene(Scene())

    session.stop()
    replacement = Scene()
    session.replace_edit_scene(replacement)
    assert session.edit_scene is replacement
    assert session.active_scene is replacement
