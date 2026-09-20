from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from .editor_authoring import (
    EditorAssetPropertyDropResult,
    EditorAuthoringTransaction,
    EditorBatchPropertyResult,
    EditorSelectionSnapshot,
    SelectionMode,
)
from .editor_component_authoring import EditorComponentAuthoringSession, EditorComponentResult
from .editor_prefab_authoring import (
    EditorPrefabAsset,
    EditorPrefabAuthoring,
    EditorPrefabBinding,
    EditorPrefabInstantiation,
)
from .editor_typed_inspector import EditorTypedInspector, InspectorEditorSpec
from .editor_workspace import EditorWorkspace
from .serialization import SceneSerializer


@dataclass(frozen=True, slots=True)
class EditorProjectAuthoringFrame:
    """Small immutable creator snapshot for project/editor front-ends."""

    scene_id: str
    selection: EditorSelectionSnapshot
    fields: tuple[InspectorEditorSpec, ...]
    prefab_assets: tuple[EditorPrefabAsset, ...]
    prefab_bindings: tuple[EditorPrefabBinding, ...]


class EditorProjectAuthoring21:
    """Project-aware bridge for the SwirEditor 2.1 authoring systems.

    ``EditorWorkspace.switch_scene`` intentionally replaces its ``SceneInspector``. The typed
    Inspector, component authoring and prefab layers are all bound to one inspector, so an editor
    shell must rebind them whenever the workspace changes scene. This class owns that lifecycle and
    gives desktop/web front-ends one stable object to call.

    Persisted prefab assets are remembered as project-relative asset paths and reloaded after a
    scene rebind. Live prefab instance bindings are scene-local by design and are discarded when the
    inspector changes; carrying bindings into another scene would make them reference stale object
    keys. In-memory prefabs without a persistence path are likewise scene-local.
    """

    def __init__(
        self,
        workspace: EditorWorkspace,
        *,
        serializer: SceneSerializer | None = None,
        asset_root: str | Path = "assets",
    ) -> None:
        if not isinstance(workspace, EditorWorkspace):
            raise TypeError("workspace must be an EditorWorkspace")
        if serializer is not None and not isinstance(serializer, SceneSerializer):
            raise TypeError("serializer must be a SceneSerializer")
        self.workspace = workspace
        self.serializer = serializer or SceneSerializer()
        self.asset_root = Path(asset_root)
        self._bound_inspector: object | None = None
        self._components: EditorComponentAuthoringSession | None = None
        self._typed: EditorTypedInspector | None = None
        self._prefabs: EditorPrefabAuthoring | None = None
        self._persisted_prefabs: dict[str, str] = {}
        self._bind_current_inspector()

    @property
    def components(self) -> EditorComponentAuthoringSession:
        self._ensure_bound()
        assert self._components is not None
        return self._components

    @property
    def typed(self) -> EditorTypedInspector:
        self._ensure_bound()
        assert self._typed is not None
        return self._typed

    @property
    def prefabs(self) -> EditorPrefabAuthoring:
        self._ensure_bound()
        assert self._prefabs is not None
        return self._prefabs

    def frame(self) -> EditorProjectAuthoringFrame:
        components = self.components
        typed = self.typed
        prefabs = self.prefabs
        return EditorProjectAuthoringFrame(
            self.workspace.scene_id,
            components.selection_snapshot,
            typed.fields(),
            prefabs.assets,
            prefabs.bindings,
        )

    def select(
        self,
        target_or_key: object | str,
        *,
        mode: SelectionMode = "replace",
    ) -> EditorSelectionSnapshot:
        return self.components.select(target_or_key, mode=mode)

    def select_many(
        self,
        targets_or_keys: Iterable[object | str],
        *,
        replace: bool = True,
    ) -> EditorSelectionSnapshot:
        components = self.components
        if replace:
            components.clear_selection()
        snapshot = components.selection_snapshot
        for target in targets_or_keys:
            snapshot = components.select(target, mode="add")
        return snapshot

    def clear_selection(self) -> EditorSelectionSnapshot:
        return self.components.clear_selection()

    def set_typed_property(
        self,
        name: str,
        value: object,
    ) -> EditorBatchPropertyResult | EditorAssetPropertyDropResult:
        return self.typed.set(name, value)

    def add_component(self, component: object) -> EditorComponentResult:
        return self.components.add_component(component)

    def remove_component(self, component_type: type[object]) -> EditorComponentResult:
        return self.components.remove_component(component_type)

    def create_prefab(
        self,
        asset_id: str,
        *,
        name: str | None = None,
        relative_path: str | Path | None = None,
        replace_existing: bool = False,
    ) -> EditorPrefabAsset:
        asset = self.prefabs.create_from_selection(
            asset_id,
            name=name,
            relative_path=relative_path,
            replace_existing=replace_existing,
        )
        if asset.relative_path is not None:
            self._persisted_prefabs[asset.asset_id] = asset.relative_path
        return asset

    def load_prefab(
        self,
        asset_id: str,
        relative_path: str | Path,
        *,
        replace_existing: bool = False,
    ) -> EditorPrefabAsset:
        asset = self.prefabs.load_asset(
            asset_id,
            relative_path,
            replace_existing=replace_existing,
        )
        assert asset.relative_path is not None
        self._persisted_prefabs[asset.asset_id] = asset.relative_path
        return asset

    def instantiate_prefab(
        self,
        asset_id: str,
        *,
        select_instance: bool = True,
    ) -> EditorPrefabInstantiation:
        return self.prefabs.instantiate(asset_id, select_instance=select_instance)

    def apply_prefab(self, binding_id: str) -> EditorPrefabAsset:
        asset = self.prefabs.apply(binding_id)
        if asset.relative_path is not None:
            self._persisted_prefabs[asset.asset_id] = asset.relative_path
        return asset

    def revert_prefab(self, binding_id: str) -> EditorAuthoringTransaction:
        return self.prefabs.revert(binding_id)

    def undo(self) -> object | None:
        return self.components.undo()

    def redo(self) -> object | None:
        return self.components.redo()

    def _ensure_bound(self) -> None:
        if self._bound_inspector is not self.workspace.inspector:
            self._bind_current_inspector()

    def _bind_current_inspector(self) -> None:
        components = EditorComponentAuthoringSession(self.workspace.inspector)
        prefabs = EditorPrefabAuthoring(
            components,
            serializer=self.serializer,
            asset_root=self.asset_root,
        )
        for asset_id, relative_path in sorted(self._persisted_prefabs.items()):
            prefabs.load_asset(asset_id, relative_path)
        self._bound_inspector = self.workspace.inspector
        self._components = components
        self._typed = EditorTypedInspector(components)
        self._prefabs = prefabs
