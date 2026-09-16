from __future__ import annotations

from dataclasses import replace

from .core.scene import Scene
from .editor import HistoryEdit
from .editor_assets import EditorAssetDragPayload
from .editor_authoring import (
    EditorAssetPropertyDropResult,
    EditorAuthoringSession,
    EditorAuthoringTransaction,
    EditorBatchPropertyResult,
    EditorMultiGizmoResult,
    EditorSelectionSnapshot,
    SelectionMode,
)
from .editor_frontend import EditorFrontendController, EditorFrontendFrame, parse_editor_value
from .editor_workspace import EditorProjectState, EditorWorkspace


class EditorAuthoringWorkspace(EditorWorkspace):
    """Additive SwirEngine 1.4 workspace with multi-selection authoring.

    The stable ``EditorWorkspace`` remains untouched. This subclass mirrors its primary selection
    into the legacy ``SceneInspector`` while exposing the complete 1.4 selection and grouped edit
    operations through ``authoring``.
    """

    def __init__(self, *args: object, **kwargs: object) -> None:
        super().__init__(*args, **kwargs)
        self.authoring = EditorAuthoringSession(self.inspector)

    @property
    def selection(self) -> EditorSelectionSnapshot:
        return self.authoring.selection_snapshot

    def select(
        self,
        target_or_key: object | str | None,
        *,
        mode: SelectionMode = "replace",
    ) -> object | None:
        if target_or_key is None:
            self.authoring.clear_selection()
            return None
        self.authoring.select(target_or_key, mode=mode)
        return self.authoring.selection.primary_target

    def select_range(
        self,
        anchor: object | str,
        target: object | str,
        *,
        additive: bool = False,
    ) -> EditorSelectionSnapshot:
        return self.authoring.select_range(anchor, target, additive=additive)

    def set_selected_property(self, name: str, value: object) -> EditorBatchPropertyResult:
        return self.authoring.set_property(name, value)

    def drop_asset_on_selected_property(
        self,
        payload: EditorAssetDragPayload,
        name: str,
    ) -> EditorAssetPropertyDropResult:
        """Apply an asset-browser drag payload to one inspector property on the selection."""

        if not isinstance(payload, EditorAssetDragPayload):
            raise TypeError("payload must be an EditorAssetDragPayload")
        return self.authoring.set_asset_path(name, payload.relative_path)

    def apply_selected_gizmo(
        self,
        mode: str,
        axis: str,
        delta: float,
        *,
        snap: float | None = None,
    ) -> EditorMultiGizmoResult:
        if snap is None and self.viewport.snap_enabled:
            snap = {
                "translate": self.viewport.translation_snap,
                "rotate": self.viewport.rotation_snap,
                "scale": self.viewport.scale_snap,
            }.get(mode)
        return self.authoring.apply_gizmo(mode, axis, delta, snap=snap)

    def undo(self) -> HistoryEdit | EditorAuthoringTransaction | None:
        return self.authoring.undo()

    def redo(self) -> HistoryEdit | EditorAuthoringTransaction | None:
        return self.authoring.redo()

    def switch_scene(self, scene_id: str, scene: Scene, *, restore: bool = True) -> None:
        super().switch_scene(scene_id, scene, restore=restore)
        self.authoring = EditorAuthoringSession(self.inspector)

    def restore_project(
        self,
        state: EditorProjectState,
        scene: Scene,
        *,
        scene_id: str | None = None,
    ) -> None:
        super().restore_project(state, scene, scene_id=scene_id)
        self.authoring = EditorAuthoringSession(self.inspector)


class EditorAuthoringFrontendController(EditorFrontendController):
    """1.4 front-end adapter exposing multi-selection without changing the 1.3 controller."""

    workspace: EditorAuthoringWorkspace

    def __init__(self, workspace: EditorAuthoringWorkspace, **kwargs: object) -> None:
        if not isinstance(workspace, EditorAuthoringWorkspace):
            raise TypeError("workspace must be an EditorAuthoringWorkspace")
        super().__init__(workspace, **kwargs)

    def frame(self) -> EditorFrontendFrame:
        frame = super().frame()
        selected = set(self.workspace.selection.keys)
        hierarchy = tuple(
            replace(row, selected=row.key in selected)
            for row in frame.hierarchy
        )
        return replace(frame, hierarchy=hierarchy)

    def select(
        self,
        key: str | None,
        *,
        mode: SelectionMode = "replace",
    ) -> object | None:
        selected = self.workspace.select(key, mode=mode)
        count = self.workspace.selection.count
        if key is None:
            self._status = "Selection cleared"
        elif count == 1:
            self._status = f"Selected {key}"
        else:
            self._status = f"Selected {count} items"
        return selected

    def select_range(
        self,
        anchor_key: str,
        target_key: str,
        *,
        additive: bool = False,
    ) -> EditorSelectionSnapshot:
        snapshot = self.workspace.select_range(anchor_key, target_key, additive=additive)
        self._status = f"Selected {snapshot.count} items"
        return snapshot

    def edit_property(self, name: str, text: str) -> object:
        snapshot = self.workspace.inspector.inspect()
        if snapshot is None:
            raise RuntimeError("no scene object is selected")
        field = next((item for item in snapshot.fields if item.name == name), None)
        if field is None:
            raise KeyError(f"unknown inspector field {name!r}")
        if not field.editable:
            raise ValueError(f"inspector field {name!r} is read-only")
        value = parse_editor_value(text, field.value)
        result = self.workspace.set_selected_property(name, value)
        self._status = (
            f"Changed {name}"
            if len(result.target_keys) == 1
            else f"Changed {name} on {len(result.target_keys)} items"
        )
        return result.value

    def drop_asset_on_property(
        self,
        name: str,
        payload: EditorAssetDragPayload,
    ) -> EditorAssetPropertyDropResult:
        """Complete an asset-browser drag gesture on an editable inspector property."""

        result = self.workspace.drop_asset_on_selected_property(payload, name)
        target_count = len(result.target_keys)
        self._status = (
            f"Dropped {payload.name} on {name}"
            if target_count == 1
            else f"Dropped {payload.name} on {name} for {target_count} items"
        )
        return result

    def apply_gizmo(self, mode: str, axis: str, delta: float) -> EditorMultiGizmoResult:
        result = self.workspace.apply_selected_gizmo(mode, axis, delta)
        target_count = len(result.results)
        self._status = (
            f"{mode.title()} {axis}: {target_count} item"
            + ("" if target_count == 1 else "s")
        )
        return result
