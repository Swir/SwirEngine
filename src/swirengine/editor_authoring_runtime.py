from __future__ import annotations

from dataclasses import dataclass
from pathlib import PurePath

from .editor import HistoryEdit
from .editor_authoring import (
    EditorAssetPropertyDropResult,
    EditorAuthoringSession,
    EditorAuthoringTransaction,
    EditorBatchPropertyResult,
    EditorMultiGizmoResult,
    EditorSelectionSnapshot,
    SelectionMode,
)
from .editor_authoring_state import (
    EditorAuthoringState,
    capture_editor_authoring,
    restore_editor_authoring,
)
from .editor_runtime import EditorRuntimeMode, EditorRuntimeSession


class EditorAuthoringIsolationError(RuntimeError):
    """Raised when the edit scene/history changes unexpectedly during Play mode."""


@dataclass(frozen=True, slots=True)
class EditorAuthoringRuntimeFrame:
    mode: EditorRuntimeMode
    authoring_locked: bool
    selection: EditorSelectionSnapshot
    runtime_scene_isolated: bool


@dataclass(frozen=True, slots=True)
class _EditBaseline:
    state: EditorAuthoringState
    scene_payload: str
    undo_history: tuple[object, ...]
    redo_history: tuple[object, ...]


class EditorAuthoringPlayController:
    """Coordinate authoring with isolated Play/Edit round-trips.

    The controller captures portable selection state plus edit-scene/history fingerprints before
    the first Play transition. Creator mutations routed through this controller are locked until
    Play ends. On stop, external edit-scene/history mutations are detected before the runtime scene
    is discarded; the caller can explicitly force stop when it intentionally changed edit data.
    """

    def __init__(
        self,
        authoring: EditorAuthoringSession,
        runtime: EditorRuntimeSession,
    ) -> None:
        if not isinstance(authoring, EditorAuthoringSession):
            raise TypeError("authoring must be an EditorAuthoringSession")
        if not isinstance(runtime, EditorRuntimeSession):
            raise TypeError("runtime must be an EditorRuntimeSession")
        if authoring.inspector.scene is not runtime.edit_scene:
            raise ValueError("authoring and runtime must reference the same edit scene")
        self.authoring = authoring
        self.runtime = runtime
        self._baseline: _EditBaseline | None = None

    @property
    def mode(self) -> EditorRuntimeMode:
        return self.runtime.mode

    @property
    def authoring_locked(self) -> bool:
        return self.runtime.mode is not EditorRuntimeMode.EDIT

    def frame(self) -> EditorAuthoringRuntimeFrame:
        runtime_frame = self.runtime.frame()
        return EditorAuthoringRuntimeFrame(
            runtime_frame.mode,
            self.authoring_locked,
            self.authoring.selection_snapshot,
            runtime_frame.play_scene_isolated,
        )

    def play(self):
        if self.runtime.mode is EditorRuntimeMode.EDIT:
            self._baseline = self._capture_baseline()
        try:
            return self.runtime.play()
        except Exception:
            if self.runtime.mode is EditorRuntimeMode.EDIT:
                self._baseline = None
            raise

    def pause(self) -> bool:
        return self.runtime.pause()

    def update(self, dt: float) -> bool:
        return self.runtime.update(dt)

    def step(self, dt: float | None = None) -> bool:
        return self.runtime.step(dt)

    def stop(self, *, force: bool = False) -> bool:
        if self.runtime.mode is EditorRuntimeMode.EDIT:
            return False
        baseline = self._baseline
        if baseline is None:
            raise EditorAuthoringIsolationError("missing Play/Edit authoring baseline")

        violation = self._isolation_violation(baseline)
        if violation is not None and not force:
            raise EditorAuthoringIsolationError(violation)

        stopped = self.runtime.stop()
        if stopped:
            self._restore_selection(baseline.state, best_effort=force)
            self._baseline = None
        return stopped

    def select(
        self,
        target_or_key: object | str,
        *,
        mode: SelectionMode = "replace",
    ) -> EditorSelectionSnapshot:
        self._require_edit_mode()
        return self.authoring.select(target_or_key, mode=mode)

    def select_range(
        self,
        anchor: object | str,
        target: object | str,
        *,
        additive: bool = False,
    ) -> EditorSelectionSnapshot:
        self._require_edit_mode()
        return self.authoring.select_range(anchor, target, additive=additive)

    def clear_selection(self) -> EditorSelectionSnapshot:
        self._require_edit_mode()
        return self.authoring.clear_selection()

    def set_property(self, name: str, value: object) -> EditorBatchPropertyResult:
        self._require_edit_mode()
        return self.authoring.set_property(name, value)

    def set_asset_path(
        self, name: str, relative_path: str | PurePath
    ) -> EditorAssetPropertyDropResult:
        self._require_edit_mode()
        return self.authoring.set_asset_path(name, relative_path)

    def apply_gizmo(
        self,
        mode: str,
        axis: str,
        delta: float,
        *,
        snap: float | None = None,
    ) -> EditorMultiGizmoResult:
        self._require_edit_mode()
        return self.authoring.apply_gizmo(mode, axis, delta, snap=snap)

    def undo(self) -> HistoryEdit | EditorAuthoringTransaction | None:
        self._require_edit_mode()
        return self.authoring.undo()

    def redo(self) -> HistoryEdit | EditorAuthoringTransaction | None:
        self._require_edit_mode()
        return self.authoring.redo()

    def assert_isolated(self) -> None:
        baseline = self._baseline
        if baseline is None:
            if self.runtime.mode is EditorRuntimeMode.EDIT:
                return
            raise EditorAuthoringIsolationError("missing Play/Edit authoring baseline")
        violation = self._isolation_violation(baseline)
        if violation is not None:
            raise EditorAuthoringIsolationError(violation)

    def _capture_baseline(self) -> _EditBaseline:
        inspector = self.authoring.inspector
        state = capture_editor_authoring(inspector, self.authoring.selection)
        scene_payload = self.runtime.serializer.dumps_scene(self.runtime.edit_scene, indent=None)
        return _EditBaseline(
            state,
            scene_payload,
            inspector.undo_history,
            inspector.redo_history,
        )

    def _isolation_violation(self, baseline: _EditBaseline) -> str | None:
        current_scene = self.runtime.serializer.dumps_scene(self.runtime.edit_scene, indent=None)
        if current_scene != baseline.scene_payload:
            return "edit scene changed while Play mode was active"
        inspector = self.authoring.inspector
        history_changed = (
            inspector.undo_history != baseline.undo_history
            or inspector.redo_history != baseline.redo_history
        )
        if history_changed:
            return "editor history changed while Play mode was active"
        return None

    def _restore_selection(self, state: EditorAuthoringState, *, best_effort: bool) -> None:
        try:
            restore_editor_authoring(
                self.authoring.inspector,
                self.authoring.selection,
                state,
            )
        except (KeyError, LookupError, ValueError):
            if not best_effort:
                raise
            self.authoring.clear_selection()

    def _require_edit_mode(self) -> None:
        if self.authoring_locked:
            raise RuntimeError("authoring mutations are locked while Play mode is active")
