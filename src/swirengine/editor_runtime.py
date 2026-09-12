from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum

from .core.scene import Scene
from .serialization import SceneSerializer


class EditorRuntimeMode(str, Enum):
    """Execution state for the editor's isolated game preview."""

    EDIT = "edit"
    PLAYING = "playing"
    PAUSED = "paused"


@dataclass(frozen=True, slots=True)
class EditorRuntimeFrame:
    """Immutable editor-facing snapshot of the current preview session."""

    mode: EditorRuntimeMode
    scene: Scene
    elapsed: float
    frame_count: int
    play_scene_isolated: bool

    @property
    def is_playing(self) -> bool:
        return self.mode is EditorRuntimeMode.PLAYING

    @property
    def is_paused(self) -> bool:
        return self.mode is EditorRuntimeMode.PAUSED


class EditorRuntimeSession:
    """Own an isolated Play/Edit lifecycle for a scene editor.

    Entering Play serializes the editor scene and restores it into a fresh runtime scene. Runtime
    mutations therefore never leak back into the edit scene. Stopping discards the preview scene and
    immediately exposes the original edit scene again. The same serializer/codec registry used by a
    project can be injected so custom registered scene objects and ECS components clone correctly.
    """

    def __init__(
        self,
        edit_scene: Scene,
        *,
        serializer: SceneSerializer | None = None,
        fixed_step: float | None = None,
    ) -> None:
        if not isinstance(edit_scene, Scene):
            raise TypeError("edit_scene must be a Scene")
        if fixed_step is not None and fixed_step <= 0:
            raise ValueError("fixed_step must be greater than zero")
        self._edit_scene = edit_scene
        self.serializer = serializer or SceneSerializer()
        self.fixed_step = None if fixed_step is None else float(fixed_step)
        self._runtime_scene: Scene | None = None
        self._mode = EditorRuntimeMode.EDIT
        self._elapsed = 0.0
        self._frame_count = 0
        self._started: list[Callable[[Scene], None]] = []
        self._stopped: list[Callable[[Scene], None]] = []

    @property
    def mode(self) -> EditorRuntimeMode:
        return self._mode

    @property
    def edit_scene(self) -> Scene:
        return self._edit_scene

    @property
    def runtime_scene(self) -> Scene | None:
        return self._runtime_scene

    @property
    def active_scene(self) -> Scene:
        return self._runtime_scene if self._runtime_scene is not None else self._edit_scene

    @property
    def elapsed(self) -> float:
        return self._elapsed

    @property
    def frame_count(self) -> int:
        return self._frame_count

    def frame(self) -> EditorRuntimeFrame:
        return EditorRuntimeFrame(
            self._mode,
            self.active_scene,
            self._elapsed,
            self._frame_count,
            self._runtime_scene is not None and self._runtime_scene is not self._edit_scene,
        )

    def on_started(self, callback: Callable[[Scene], None]) -> Callable[[], None]:
        if not callable(callback):
            raise TypeError("callback must be callable")
        self._started.append(callback)
        return lambda: self._remove_callback(self._started, callback)

    def on_stopped(self, callback: Callable[[Scene], None]) -> Callable[[], None]:
        if not callable(callback):
            raise TypeError("callback must be callable")
        self._stopped.append(callback)
        return lambda: self._remove_callback(self._stopped, callback)

    def replace_edit_scene(self, scene: Scene) -> None:
        """Point the session at a newly loaded editor scene while not previewing."""
        if not isinstance(scene, Scene):
            raise TypeError("scene must be a Scene")
        if self._mode is not EditorRuntimeMode.EDIT:
            raise RuntimeError("cannot replace the edit scene while Play mode is active")
        self._edit_scene = scene

    def play(self) -> Scene:
        """Start or resume Play mode and return the isolated runtime scene."""
        if self._mode is EditorRuntimeMode.PAUSED:
            self._mode = EditorRuntimeMode.PLAYING
            assert self._runtime_scene is not None
            return self._runtime_scene
        if self._mode is EditorRuntimeMode.PLAYING:
            assert self._runtime_scene is not None
            return self._runtime_scene

        snapshot = self.serializer.dumps_scene(self._edit_scene, indent=None)
        runtime_scene = self.serializer.loads_scene(snapshot)
        self._runtime_scene = runtime_scene
        self._mode = EditorRuntimeMode.PLAYING
        self._elapsed = 0.0
        self._frame_count = 0
        for callback in tuple(self._started):
            callback(runtime_scene)
        return runtime_scene

    def pause(self) -> bool:
        if self._mode is not EditorRuntimeMode.PLAYING:
            return False
        self._mode = EditorRuntimeMode.PAUSED
        return True

    def stop(self) -> bool:
        runtime_scene = self._runtime_scene
        if runtime_scene is None:
            return False
        self._runtime_scene = None
        self._mode = EditorRuntimeMode.EDIT
        self._elapsed = 0.0
        self._frame_count = 0
        for callback in tuple(self._stopped):
            callback(runtime_scene)
        return True

    def update(self, dt: float) -> bool:
        """Advance the preview when playing; returns whether a runtime tick occurred."""
        if dt < 0:
            raise ValueError("dt cannot be negative")
        if self._mode is not EditorRuntimeMode.PLAYING or self._runtime_scene is None:
            return False
        self._advance(self.fixed_step if self.fixed_step is not None else float(dt))
        return True

    def step(self, dt: float | None = None) -> bool:
        """Advance exactly one frame while paused, preserving the paused state."""
        if self._mode is not EditorRuntimeMode.PAUSED or self._runtime_scene is None:
            return False
        resolved = self.fixed_step if dt is None else float(dt)
        if resolved is None:
            raise ValueError("dt is required when fixed_step is not configured")
        if resolved < 0:
            raise ValueError("dt cannot be negative")
        self._advance(resolved)
        return True

    def _advance(self, dt: float) -> None:
        assert self._runtime_scene is not None
        self._runtime_scene.update(dt)
        self._elapsed += dt
        self._frame_count += 1

    @staticmethod
    def _remove_callback(
        callbacks: list[Callable[[Scene], None]], callback: Callable[[Scene], None]
    ) -> None:
        try:
            callbacks.remove(callback)
        except ValueError:
            pass
