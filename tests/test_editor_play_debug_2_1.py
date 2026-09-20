from __future__ import annotations

from dataclasses import dataclass

import pytest

from swirengine import Scene
from swirengine.editor_preview import DEFAULT_EDITOR_FIXED_STEP, EditorPreviewSession
from swirengine.editor_runtime import EditorRuntimeMode, EditorRuntimeSession
from swirengine.editor_workspace import EditorWorkspace
from swirengine.profiler import Profiler
from swirengine.serialization import SceneCodecRegistry, SceneSerializer


@dataclass
class MovingActor:
    name: str
    x: float = 0.0
    enabled: bool = True

    def update(self, dt: float) -> None:
        self.x += dt * 10.0


@dataclass
class CrashingActor:
    name: str
    enabled: bool = True

    def update(self, dt: float) -> None:
        del dt
        raise RuntimeError("game update exploded")


def _serializer(*types: type[object]) -> SceneSerializer:
    registry = SceneCodecRegistry.default()
    for actor_type in types:
        registry.register(actor_type)
    return SceneSerializer(registry)


def test_production_preview_step_has_deterministic_60hz_default() -> None:
    preview = EditorPreviewSession(EditorWorkspace(Scene()))

    assert preview.runtime.fixed_step == pytest.approx(DEFAULT_EDITOR_FIXED_STEP)
    assert preview.step()
    assert preview.runtime.mode is EditorRuntimeMode.PAUSED
    assert preview.runtime.frame_count == 1
    assert preview.runtime.elapsed == pytest.approx(DEFAULT_EDITOR_FIXED_STEP)


def test_preview_feeds_successful_runtime_ticks_into_profiler() -> None:
    profiler = Profiler()
    preview = EditorPreviewSession(EditorWorkspace(Scene()), profiler=profiler)

    assert preview.play_pause() is EditorRuntimeMode.PLAYING
    assert preview.update(DEFAULT_EDITOR_FIXED_STEP)
    assert len(profiler.samples) == 1
    assert profiler.latest.frame_ms == pytest.approx(DEFAULT_EDITOR_FIXED_STEP * 1000.0)
    assert profiler.latest.fps == pytest.approx(60.0)
    assert profiler.latest.update_ms >= 0.0

    assert preview.play_pause() is EditorRuntimeMode.PAUSED
    assert not preview.update(DEFAULT_EDITOR_FIXED_STEP)
    assert len(profiler.samples) == 1

    assert preview.step()
    assert len(profiler.samples) == 2
    assert profiler.latest.frame_ms == pytest.approx(DEFAULT_EDITOR_FIXED_STEP * 1000.0)
    assert profiler.latest.fps == pytest.approx(60.0)


def test_failed_runtime_update_recovers_to_edit_without_leaking_runtime_state() -> None:
    scene = Scene()
    edit_actor = scene.add(CrashingActor("Broken"))
    runtime = EditorRuntimeSession(
        scene,
        serializer=_serializer(CrashingActor),
        fixed_step=DEFAULT_EDITOR_FIXED_STEP,
    )
    errors: list[tuple[str, str]] = []
    profiler = Profiler()
    preview = EditorPreviewSession(
        EditorWorkspace(scene),
        runtime=runtime,
        error_sink=lambda operation, exc: errors.append((operation, str(exc))),
        profiler=profiler,
    )

    assert preview.play_pause() is EditorRuntimeMode.PLAYING
    assert not preview.update(DEFAULT_EDITOR_FIXED_STEP)

    assert runtime.mode is EditorRuntimeMode.EDIT
    assert runtime.active_scene is scene
    assert scene.find("Broken") is edit_actor
    assert preview.last_error == "Runtime update failed: RuntimeError: game update exploded"
    assert preview.frame().runtime_error == preview.last_error
    assert errors == [("update", "game update exploded")]
    assert profiler.samples == ()


def test_failed_single_step_recovers_to_edit_and_next_play_clears_error() -> None:
    scene = Scene()
    scene.add(CrashingActor("Broken"))
    runtime = EditorRuntimeSession(
        scene,
        serializer=_serializer(CrashingActor),
        fixed_step=DEFAULT_EDITOR_FIXED_STEP,
    )
    preview = EditorPreviewSession(EditorWorkspace(scene), runtime=runtime)

    assert not preview.step()
    assert runtime.mode is EditorRuntimeMode.EDIT
    assert preview.last_error is not None

    assert preview.play_pause() is EditorRuntimeMode.PLAYING
    assert preview.last_error is None


def test_runtime_scene_remains_isolated_while_step_uses_default_delta() -> None:
    scene = Scene()
    actor = scene.add(MovingActor("Player", x=2.0))
    runtime = EditorRuntimeSession(
        scene,
        serializer=_serializer(MovingActor),
        fixed_step=DEFAULT_EDITOR_FIXED_STEP,
    )
    preview = EditorPreviewSession(EditorWorkspace(scene), runtime=runtime)

    assert preview.step()

    assert actor.x == pytest.approx(2.0)
    assert runtime.runtime_scene is not None
    assert runtime.runtime_scene.find("Player").x == pytest.approx(
        2.0 + DEFAULT_EDITOR_FIXED_STEP * 10.0
    )
    assert runtime.mode is EditorRuntimeMode.PAUSED
