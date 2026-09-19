from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path, PurePosixPath, PureWindowsPath

from .core.scene import Scene
from .ecs import Entity
from .editor_workspace import EditorProjectState, EditorWorkspace
from .serialization import SceneSerializationError, SceneSerializer

RECOVERY_FORMAT = "swirengine.editor_recovery"
RECOVERY_VERSION = 1
DEFAULT_RECOVERY_FILE = ".swir/recovery.json"


class UnsavedSceneChangesError(RuntimeError):
    """Raised when a destructive scene action would discard unsaved editor work."""


def _project_relative_path(value: str | Path, *, label: str) -> str:
    raw = str(value).strip()
    normalized = raw.replace("\\", "/")
    if not normalized or normalized == ".":
        raise ValueError(f"{label} cannot be empty")
    posix = PurePosixPath(normalized)
    windows = PureWindowsPath(raw)
    if (
        posix.is_absolute()
        or windows.is_absolute()
        or bool(windows.drive)
        or bool(windows.root)
        or ".." in posix.parts
    ):
        raise ValueError(f"{label} must stay project-relative")
    return posix.as_posix()


def _copy_name(value: object) -> str:
    name = str(value or "").strip()
    return f"{name} Copy" if name else "Copy"


@dataclass(frozen=True, slots=True)
class EditorSceneTab:
    path: str
    active: bool
    dirty: bool
    object_count: int
    entity_count: int


class EditorSceneAuthoring:
    """Project-backed multi-scene authoring model for SwirEditor 2.1.

    Open scenes remain alive in memory while the toolkit-neutral :class:`EditorWorkspace` switches
    between them. Dirty state covers both serialized scene data and per-scene editor hierarchy /
    viewport metadata, so reparenting or viewport changes cannot silently bypass unsaved-work
    protection. Recovery snapshots are explicit, deterministic JSON documents stored under
    ``.swir`` and never execute project code.
    """

    def __init__(
        self,
        project_root: str | Path,
        serializer: SceneSerializer,
        workspace: EditorWorkspace,
        *,
        initial_scene: str | Path,
        recovery_file: str | Path = DEFAULT_RECOVERY_FILE,
    ) -> None:
        root = Path(project_root).expanduser().resolve()
        if not root.is_dir():
            raise FileNotFoundError(root)
        if not isinstance(serializer, SceneSerializer):
            raise TypeError("serializer must be a SceneSerializer")
        if not isinstance(workspace, EditorWorkspace):
            raise TypeError("workspace must be an EditorWorkspace")
        initial = _project_relative_path(initial_scene, label="initial editor scene")
        if workspace.scene_id != initial:
            raise ValueError("workspace scene_id must match initial_scene")

        self.project_root = root
        self.serializer = serializer
        self.workspace = workspace
        self.recovery_path = root / PurePosixPath(
            _project_relative_path(recovery_file, label="editor recovery path")
        )
        self._scenes: dict[str, Scene] = {initial: workspace.scene}
        self._saved_fingerprints: dict[str, str | None] = {}
        state = self.workspace.capture_project()
        self._saved_fingerprints[initial] = (
            self._fingerprint(initial, state)
            if self._path(initial).is_file()
            else None
        )
        self._saved_ui_fingerprint = self._ui_fingerprint(state)

    @property
    def active_path(self) -> str:
        return self.workspace.scene_id

    @property
    def scene_paths(self) -> tuple[str, ...]:
        return tuple(self._scenes)

    @property
    def recovery_available(self) -> bool:
        return self.recovery_path.is_file()

    @property
    def dirty(self) -> bool:
        state = self.workspace.capture_project()
        if self._ui_fingerprint(state) != self._saved_ui_fingerprint:
            return True
        return any(self._is_dirty(path, state) for path in self._scenes)

    def tabs(self) -> tuple[EditorSceneTab, ...]:
        state = self.workspace.capture_project()
        return tuple(
            EditorSceneTab(
                path=path,
                active=path == self.active_path,
                dirty=self._is_dirty(path, state),
                object_count=len(scene.objects),
                entity_count=len(scene.entities),
            )
            for path, scene in self._scenes.items()
        )

    def new_scene(self, path: str | Path) -> Scene:
        relative = _project_relative_path(path, label="new editor scene")
        if relative in self._scenes or self._path(relative).exists():
            raise FileExistsError(f"editor scene already exists: {relative}")
        scene = Scene()
        self._scenes[relative] = scene
        self._saved_fingerprints[relative] = None
        self.workspace.switch_scene(relative, scene, restore=True)
        return scene

    def open_scene(self, path: str | Path) -> Scene:
        relative = _project_relative_path(path, label="editor scene")
        scene = self._scenes.get(relative)
        if scene is None:
            source = self._path(relative)
            if not source.is_file():
                raise FileNotFoundError(f"editor scene not found: {relative}")
            try:
                scene = self.serializer.load_scene(source)
            except (OSError, UnicodeError, SceneSerializationError) as exc:
                raise ValueError(f"cannot open editor scene {relative!r}: {exc}") from exc
            self._scenes[relative] = scene
            self.workspace.switch_scene(relative, scene, restore=True)
            state = self.workspace.capture_project()
            self._saved_fingerprints[relative] = self._fingerprint(relative, state)
            return scene
        self.workspace.switch_scene(relative, scene, restore=True)
        return scene

    def close_scene(self, path: str | Path, *, discard_unsaved: bool = False) -> None:
        relative = _project_relative_path(path, label="editor scene")
        if relative not in self._scenes:
            raise KeyError(relative)
        if len(self._scenes) == 1:
            raise RuntimeError("cannot close the last open editor scene")
        state = self.workspace.capture_project()
        if self._is_dirty(relative, state) and not discard_unsaved:
            raise UnsavedSceneChangesError(f"scene has unsaved changes: {relative}")

        if relative == self.active_path:
            replacement = next(path for path in self._scenes if path != relative)
            self.workspace.switch_scene(replacement, self._scenes[replacement], restore=True)
        del self._scenes[relative]
        self._saved_fingerprints.pop(relative, None)
        if discard_unsaved:
            self.workspace.forget_scene_state(relative)

    def add_object(self, obj: object, *, parent: object | str | None = None) -> object:
        self.workspace.scene.add(obj)
        if parent is not None:
            self.workspace.inspector.set_parent(obj, parent)
        self.workspace.select(obj)
        return obj

    def create_entity(
        self,
        *,
        name: str = "",
        enabled: bool = True,
        tags: tuple[str, ...] = (),
        parent: object | str | None = None,
    ) -> Entity:
        entity = self.workspace.scene.create_entity(name=name, enabled=enabled, tags=tags)
        if parent is not None:
            self.workspace.inspector.set_parent(entity, parent)
        self.workspace.select(entity)
        return entity

    def duplicate(self, target_or_key: object | str) -> object:
        target = self._resolve(target_or_key)
        parent = self.workspace.inspector.parent(target)
        if isinstance(target, Entity):
            duplicate = self.workspace.scene.compose_entity(
                *(deepcopy(component) for component in target.components),
                name=_copy_name(target.name),
                enabled=target.enabled,
                tags=tuple(target.tags),
            )
        else:
            duplicate = deepcopy(target)
            if hasattr(duplicate, "name"):
                try:
                    setattr(duplicate, "name", _copy_name(getattr(target, "name", "")))
                except (AttributeError, TypeError):
                    pass
            self.workspace.scene.add(duplicate)
        if parent is not None:
            self.workspace.inspector.set_parent(duplicate, parent)
        self.workspace.select(duplicate)
        return duplicate

    def remove(self, target_or_key: object | str) -> bool:
        target = self._resolve(target_or_key)
        selected = self.workspace.inspector.selected_target is target
        if isinstance(target, Entity):
            removed = target.destroy()
        else:
            removed = self.workspace.scene.remove(target)
        if removed and selected:
            self.workspace.select(None)
        return removed

    def reparent(
        self,
        child: object | str,
        parent: object | str | None,
        *,
        index: int | None = None,
    ) -> object:
        self.workspace.inspector.set_parent(child, parent, index=index)
        return self._resolve(child)

    def save_scene(self, path: str | Path | None = None) -> Path:
        relative = (
            self.active_path
            if path is None
            else _project_relative_path(path, label="editor scene")
        )
        try:
            scene = self._scenes[relative]
        except KeyError as exc:
            raise KeyError(f"scene is not open: {relative}") from exc
        destination = self._path(relative)
        self.serializer.dump_scene(scene, destination)
        state = self.workspace.capture_project()
        self._saved_fingerprints[relative] = self._fingerprint(relative, state)
        return destination

    def save_all(self, state_path: str | Path) -> EditorProjectState:
        state = self.workspace.capture_project()
        for relative, scene in self._scenes.items():
            self.serializer.dump_scene(scene, self._path(relative))
        state.save(state_path)
        state = self.workspace.capture_project()
        self._saved_fingerprints = {
            path: self._fingerprint(path, state) for path in self._scenes
        }
        self._saved_ui_fingerprint = self._ui_fingerprint(state)
        self.discard_recovery()
        return state

    def write_recovery(self) -> Path:
        state = self.workspace.capture_project()
        payload = {
            "format": RECOVERY_FORMAT,
            "version": RECOVERY_VERSION,
            "active_scene": self.active_path,
            "editor_state": state.to_dict(),
            "scenes": {
                path: json.loads(self.serializer.dumps_scene(scene, indent=None))
                for path, scene in self._scenes.items()
            },
        }
        self.recovery_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.recovery_path.with_name(f".{self.recovery_path.name}.tmp")
        temporary.write_text(
            json.dumps(payload, sort_keys=True, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        temporary.replace(self.recovery_path)
        return self.recovery_path

    def restore_recovery(self) -> tuple[EditorSceneTab, ...]:
        try:
            payload = json.loads(self.recovery_path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            raise FileNotFoundError(f"editor recovery snapshot not found: {self.recovery_path}")
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise ValueError(f"cannot read editor recovery snapshot: {exc}") from exc
        if not isinstance(payload, dict) or payload.get("format") != RECOVERY_FORMAT:
            raise ValueError("invalid SwirEditor recovery document")
        if payload.get("version") != RECOVERY_VERSION:
            raise ValueError("unsupported SwirEditor recovery version")
        active = payload.get("active_scene")
        raw_scenes = payload.get("scenes")
        raw_state = payload.get("editor_state")
        if not isinstance(active, str) or not isinstance(raw_scenes, dict) or not raw_scenes:
            raise ValueError("SwirEditor recovery document is missing scene data")

        scenes: dict[str, Scene] = {}
        for raw_path, document in raw_scenes.items():
            if not isinstance(raw_path, str) or not isinstance(document, dict):
                raise ValueError("SwirEditor recovery scene entries must be objects")
            relative = _project_relative_path(raw_path, label="recovery scene")
            try:
                scenes[relative] = self.serializer.loads_scene(
                    json.dumps(document, sort_keys=True, separators=(",", ":"))
                )
            except SceneSerializationError as exc:
                raise ValueError(f"invalid recovered scene {relative!r}: {exc}") from exc
        active = _project_relative_path(active, label="active recovery scene")
        if active not in scenes:
            raise ValueError("active recovery scene is not present in recovery payload")
        try:
            state = EditorProjectState.from_dict(raw_state)
            self.workspace.restore_project(state, scenes[active], scene_id=active)
        except (TypeError, ValueError, LookupError) as exc:
            raise ValueError(f"invalid recovered editor state: {exc}") from exc
        self._scenes = scenes
        for path in scenes:
            self._saved_fingerprints.setdefault(path, None)
        return self.tabs()

    def discard_recovery(self) -> None:
        try:
            self.recovery_path.unlink()
        except FileNotFoundError:
            pass

    def _resolve(self, target_or_key: object | str) -> object:
        if isinstance(target_or_key, str):
            target = self.workspace.inspector.resolve(target_or_key)
            if target is None:
                raise KeyError(target_or_key)
            return target
        self.workspace.inspector.key_for(target_or_key)
        return target_or_key

    def _path(self, relative: str) -> Path:
        root = self.project_root
        candidate = (root / PurePosixPath(relative)).resolve(strict=False)
        try:
            candidate.relative_to(root)
        except ValueError as exc:  # defense in depth after lexical validation
            raise ValueError(f"editor scene path escapes project root: {relative}") from exc
        return candidate

    def _is_dirty(self, path: str, state: EditorProjectState) -> bool:
        baseline = self._saved_fingerprints.get(path)
        return baseline is None or self._fingerprint(path, state) != baseline

    def _fingerprint(self, path: str, state: EditorProjectState) -> str:
        scene_state = next((item for item in state.scenes if item.scene_id == path), None)
        payload = {
            "scene": json.loads(self.serializer.dumps_scene(self._scenes[path], indent=None)),
            "editor": None if scene_state is None else scene_state.to_dict(),
        }
        encoded = json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
        ).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    @staticmethod
    def _ui_fingerprint(state: EditorProjectState) -> str:
        payload = {
            "project_name": state.project_name,
            "asset_root": state.asset_root,
            "active_scene_id": state.active_scene_id,
            "panels": [panel.to_dict() for panel in state.panels],
        }
        encoded = json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
        ).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()
