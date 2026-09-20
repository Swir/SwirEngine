from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, replace
from pathlib import Path, PurePosixPath, PureWindowsPath

from .ecs import Entity
from .editor import PropertyEdit
from .editor_authoring import EditorAuthoringTransaction
from .editor_component_authoring import EditorComponentAuthoringSession
from .prefab import Prefab, PrefabInstance, PrefabOverrides
from .serialization import SceneSerializer


@dataclass(frozen=True, slots=True)
class EditorPrefabAsset:
    """One editor-owned prefab definition and optional project-relative persistence path."""

    asset_id: str
    prefab: Prefab
    revision: int = 1
    relative_path: str | None = None


@dataclass(frozen=True, slots=True)
class EditorPrefabBinding:
    """Tracks one live scene instance back to its editor prefab asset."""

    binding_id: str
    asset_id: str
    target_keys: tuple[str, ...]
    asset_revision: int


@dataclass(frozen=True, slots=True)
class EditorPrefabInstantiation:
    instance: PrefabInstance
    binding: EditorPrefabBinding


class EditorPrefabAuthoring:
    """High-level SwirEditor prefab workflow: create, instantiate, apply and revert.

    Runtime ``Prefab`` and ``SceneSerializer`` remain authoritative for graph cloning and storage.
    This layer adds project-safe asset paths, live instance bindings, creator selection integration
    and grouped Inspector history for instance reverts.
    """

    def __init__(
        self,
        authoring: EditorComponentAuthoringSession,
        *,
        serializer: SceneSerializer | None = None,
        asset_root: str | Path = "assets",
    ) -> None:
        self.authoring = authoring
        self.serializer = serializer or SceneSerializer()
        self.asset_root = Path(asset_root)
        self._assets: dict[str, EditorPrefabAsset] = {}
        self._bindings: dict[str, EditorPrefabBinding] = {}
        self._next_binding = 1

    @property
    def assets(self) -> tuple[EditorPrefabAsset, ...]:
        return tuple(self._assets[key] for key in sorted(self._assets))

    @property
    def bindings(self) -> tuple[EditorPrefabBinding, ...]:
        return tuple(self._bindings[key] for key in sorted(self._bindings))

    def asset(self, asset_id: str) -> EditorPrefabAsset:
        try:
            return self._assets[asset_id]
        except KeyError as exc:
            raise KeyError(f"unknown editor prefab asset {asset_id!r}") from exc

    def binding(self, binding_id: str) -> EditorPrefabBinding:
        try:
            return self._bindings[binding_id]
        except KeyError as exc:
            raise KeyError(f"unknown prefab instance binding {binding_id!r}") from exc

    def create_from_selection(
        self,
        asset_id: str,
        *,
        name: str | None = None,
        relative_path: str | Path | None = None,
        replace_existing: bool = False,
    ) -> EditorPrefabAsset:
        """Capture the current object-only selection as a reusable prefab asset."""
        clean_id = asset_id.strip()
        if not clean_id:
            raise ValueError("prefab asset_id cannot be empty")
        existing = self._assets.get(clean_id)
        if existing is not None and not replace_existing:
            raise ValueError(f"prefab asset {clean_id!r} already exists")

        targets = self.authoring.selected_targets
        if not targets:
            raise RuntimeError("no editor targets selected")
        if any(isinstance(target, Entity) for target in targets):
            raise TypeError("runtime Prefab currently supports scene-object selections, not ECS entities")

        prefab = Prefab(*targets, name=name or clean_id)
        normalized_path = (
            None if relative_path is None else self._normalize_relative_path(relative_path)
        )
        if normalized_path is not None:
            self.serializer.dump_prefab(prefab, self._resolve_asset_path(normalized_path))

        revision = 1 if existing is None else existing.revision + 1
        asset = EditorPrefabAsset(clean_id, prefab, revision, normalized_path)
        self._assets[clean_id] = asset
        return asset

    def load_asset(
        self,
        asset_id: str,
        relative_path: str | Path,
        *,
        replace_existing: bool = False,
    ) -> EditorPrefabAsset:
        clean_id = asset_id.strip()
        if not clean_id:
            raise ValueError("prefab asset_id cannot be empty")
        existing = self._assets.get(clean_id)
        if existing is not None and not replace_existing:
            raise ValueError(f"prefab asset {clean_id!r} already exists")
        normalized = self._normalize_relative_path(relative_path)
        prefab = self.serializer.load_prefab(self._resolve_asset_path(normalized))
        revision = 1 if existing is None else existing.revision + 1
        asset = EditorPrefabAsset(clean_id, prefab, revision, normalized)
        self._assets[clean_id] = asset
        return asset

    def save_asset(self, asset_id: str) -> Path:
        asset = self.asset(asset_id)
        if asset.relative_path is None:
            raise ValueError(f"prefab asset {asset_id!r} has no persistence path")
        return self.serializer.dump_prefab(
            asset.prefab,
            self._resolve_asset_path(asset.relative_path),
        )

    def instantiate(
        self,
        asset_id: str,
        *,
        overrides: PrefabOverrides | None = None,
        select_instance: bool = True,
    ) -> EditorPrefabInstantiation:
        """Instantiate an asset into the active scene and track the live instance."""
        asset = self.asset(asset_id)
        instance = asset.prefab.instantiate(
            self.authoring.inspector.scene,
            overrides=overrides,
        )
        target_keys = tuple(self.authoring.inspector.key_for(target) for target in instance.objects)
        binding_id = f"{asset_id}:{self._next_binding}"
        self._next_binding += 1
        binding = EditorPrefabBinding(binding_id, asset_id, target_keys, asset.revision)
        self._bindings[binding_id] = binding

        if select_instance:
            self.authoring.clear_selection()
            for target in instance.objects:
                self.authoring.select(target, mode="add")
        return EditorPrefabInstantiation(instance, binding)

    def apply(self, binding_id: str) -> EditorPrefabAsset:
        """Apply one live instance back to its prefab definition and persisted asset, if any."""
        binding = self.binding(binding_id)
        current_asset = self.asset(binding.asset_id)
        targets = self._binding_targets(binding)
        prefab = Prefab(*targets, name=current_asset.prefab.name)
        updated = EditorPrefabAsset(
            current_asset.asset_id,
            prefab,
            current_asset.revision + 1,
            current_asset.relative_path,
        )
        if updated.relative_path is not None:
            self.serializer.dump_prefab(
                updated.prefab,
                self._resolve_asset_path(updated.relative_path),
            )
        self._assets[updated.asset_id] = updated
        self._bindings[binding_id] = replace(binding, asset_revision=updated.revision)
        return updated

    def revert(self, binding_id: str) -> EditorAuthoringTransaction:
        """Revert a live instance to the current asset as one creator undo/redo transaction."""
        binding = self.binding(binding_id)
        asset = self.asset(binding.asset_id)
        targets = self._binding_targets(binding)
        templates = asset.prefab.templates()
        if len(targets) != len(templates):
            raise RuntimeError("prefab binding size no longer matches its asset")

        planned: list[tuple[object, str, object]] = []
        for target, template in zip(targets, templates, strict=True):
            if type(target) is not type(template):
                raise TypeError("prefab instance object type no longer matches its asset")
            snapshot = self.authoring.inspector.inspect(target)
            if snapshot is None:
                raise LookupError("prefab instance target no longer exists")
            for field in snapshot.fields:
                if not field.editable or not hasattr(template, field.name):
                    continue
                desired = deepcopy(getattr(template, field.name))
                if field.value != desired:
                    planned.append((target, field.name, desired))

        edits: list[PropertyEdit] = []
        for target, name, desired in planned:
            edits.append(
                self.authoring.inspector.set_property(name, desired, target=target)
            )
        transaction = self.authoring._record(
            f"Revert prefab {asset.asset_id}",
            tuple(edits),
        )
        self._bindings[binding_id] = replace(binding, asset_revision=asset.revision)
        return transaction

    def forget_binding(self, binding_id: str) -> bool:
        return self._bindings.pop(binding_id, None) is not None

    def _binding_targets(self, binding: EditorPrefabBinding) -> tuple[object, ...]:
        targets: list[object] = []
        for key in binding.target_keys:
            target = self.authoring.inspector.resolve(key)
            if target is None:
                raise LookupError(f"prefab instance target no longer exists: {key}")
            if isinstance(target, Entity):
                raise TypeError("prefab binding unexpectedly references an ECS entity")
            targets.append(target)
        return tuple(targets)

    def _resolve_asset_path(self, relative_path: str) -> Path:
        root = self.asset_root.expanduser().resolve()
        target = (root / PurePosixPath(relative_path)).resolve()
        try:
            target.relative_to(root)
        except ValueError as exc:
            raise ValueError("prefab asset path escapes the configured asset root") from exc
        return target

    @staticmethod
    def _normalize_relative_path(relative_path: str | Path) -> str:
        raw = str(relative_path).strip()
        if not raw:
            raise ValueError("prefab asset path cannot be empty")
        posix = PurePosixPath(raw.replace("\\", "/"))
        windows = PureWindowsPath(raw)
        if (
            posix.is_absolute()
            or windows.is_absolute()
            or bool(windows.drive)
            or bool(windows.root)
            or ".." in posix.parts
        ):
            raise ValueError("prefab asset path must stay project-relative")
        return posix.as_posix()
