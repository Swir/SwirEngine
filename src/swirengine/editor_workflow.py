from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .core.scene import Scene
from .input.actions import InputActions, InputBinding
from .prefab import Prefab, PrefabInstance, PrefabOverrides
from .serialization import SceneSerializer


@dataclass(frozen=True, slots=True)
class EditorProjectLayout:
    """Filesystem layout used by the lightweight creator workflow."""

    root: Path
    scenes_dir: Path
    prefabs_dir: Path
    settings_dir: Path
    input_profile: Path

    @classmethod
    def at(cls, root: str | Path) -> EditorProjectLayout:
        base = Path(root).expanduser().resolve()
        return cls(
            root=base,
            scenes_dir=base / "scenes",
            prefabs_dir=base / "prefabs",
            settings_dir=base / "settings",
            input_profile=base / "settings" / "input.json",
        )

    def ensure(self) -> EditorProjectLayout:
        self.scenes_dir.mkdir(parents=True, exist_ok=True)
        self.prefabs_dir.mkdir(parents=True, exist_ok=True)
        self.settings_dir.mkdir(parents=True, exist_ok=True)
        return self


@dataclass(frozen=True, slots=True)
class PlaytestSnapshot:
    """Immutable edit-state snapshot restored when a playtest ends."""

    scene_text: str
    input_profile: dict[str, Any] | None


class EditorWorkflow:
    """Project-oriented scene/prefab/input/playtest workflow for SwirEngine creators.

    The class deliberately composes the stable 1.x runtime APIs instead of introducing a
    second scene or prefab representation. Visual frontends can call these methods directly,
    while scripts and tests can use exactly the same project workflow headlessly.
    """

    SCENE_SUFFIX = ".scene.json"
    PREFAB_SUFFIX = ".prefab.json"

    def __init__(
        self,
        root: str | Path,
        scene: Scene,
        *,
        serializer: SceneSerializer | None = None,
        input_actions: InputActions | None = None,
    ) -> None:
        self.layout = EditorProjectLayout.at(root).ensure()
        self.scene = scene
        self.serializer = serializer or SceneSerializer()
        self.input_actions = input_actions
        self.current_scene: str | None = None
        self._playtest_snapshot: PlaytestSnapshot | None = None

    @staticmethod
    def _safe_name(name: str) -> str:
        value = str(name).strip()
        if not value or value in {".", ".."}:
            raise ValueError("project item name cannot be empty")
        if Path(value).name != value or "/" in value or "\\" in value:
            raise ValueError("project item name must not contain path separators")
        return value

    @classmethod
    def _with_suffix(cls, name: str, suffix: str) -> str:
        value = cls._safe_name(name)
        return value if value.endswith(suffix) else f"{value}{suffix}"

    def scene_path(self, name: str) -> Path:
        return self.layout.scenes_dir / self._with_suffix(name, self.SCENE_SUFFIX)

    def prefab_path(self, name: str) -> Path:
        return self.layout.prefabs_dir / self._with_suffix(name, self.PREFAB_SUFFIX)

    def list_scenes(self) -> tuple[str, ...]:
        suffix = self.SCENE_SUFFIX
        return tuple(
            path.name[: -len(suffix)]
            for path in sorted(self.layout.scenes_dir.glob(f"*{suffix}"))
            if path.is_file()
        )

    def list_prefabs(self) -> tuple[str, ...]:
        suffix = self.PREFAB_SUFFIX
        return tuple(
            path.name[: -len(suffix)]
            for path in sorted(self.layout.prefabs_dir.glob(f"*{suffix}"))
            if path.is_file()
        )

    def new_scene(self, name: str | None = None) -> Scene:
        self.scene.clear()
        self.current_scene = None if name is None else self._safe_name(name)
        return self.scene

    def save_scene(self, name: str | None = None) -> Path:
        selected = name or self.current_scene
        if selected is None:
            raise ValueError("save_scene requires a name for an unnamed scene")
        logical_name = self._safe_name(selected)
        target = self.scene_path(logical_name)
        self.serializer.dump_scene(self.scene, target)
        self.current_scene = logical_name.removesuffix(self.SCENE_SUFFIX)
        return target

    def load_scene(self, name: str) -> Scene:
        logical_name = self._safe_name(name).removesuffix(self.SCENE_SUFFIX)
        self.serializer.load_scene(self.scene_path(logical_name), scene=self.scene, clear=True)
        self.current_scene = logical_name
        return self.scene

    def save_prefab(
        self,
        name: str,
        *objects: object,
        predicate: Any | None = None,
    ) -> Path:
        logical_name = self._safe_name(name).removesuffix(self.PREFAB_SUFFIX)
        if objects and predicate is not None:
            raise ValueError("use explicit objects or predicate, not both")
        prefab = (
            Prefab(*objects, name=logical_name)
            if objects
            else Prefab.from_scene(self.scene, name=logical_name, predicate=predicate)
        )
        return self.serializer.dump_prefab(prefab, self.prefab_path(logical_name))

    def load_prefab(self, name: str) -> Prefab:
        logical_name = self._safe_name(name).removesuffix(self.PREFAB_SUFFIX)
        return self.serializer.load_prefab(self.prefab_path(logical_name))

    def instantiate_prefab(
        self,
        name: str,
        *,
        overrides: PrefabOverrides | None = None,
    ) -> PrefabInstance:
        return self.load_prefab(name).instantiate(self.scene, overrides=overrides)

    def bind_input(self, action: str, binding: InputBinding, *, replace: bool = False) -> None:
        if self.input_actions is None:
            raise RuntimeError("this editor workflow has no InputActions instance")
        self.input_actions.bind(action, binding, replace=replace)

    def save_input_profile(self) -> Path:
        if self.input_actions is None:
            raise RuntimeError("this editor workflow has no InputActions instance")
        return self.input_actions.save(self.layout.input_profile)

    def load_input_profile(self, *, replace: bool = True) -> None:
        if self.input_actions is None:
            raise RuntimeError("this editor workflow has no InputActions instance")
        self.input_actions.load(self.layout.input_profile, replace=replace)

    @property
    def playtesting(self) -> bool:
        return self._playtest_snapshot is not None

    def begin_playtest(self) -> PlaytestSnapshot:
        """Snapshot edit state before entering play mode.

        Runtime mutations can then happen directly on the same scene. ``end_playtest`` restores
        the exact serialized edit scene and optional input profile, preventing play-mode changes
        from leaking back into authoring state.
        """
        if self._playtest_snapshot is not None:
            raise RuntimeError("playtest is already active")
        input_profile = None
        if self.input_actions is not None:
            input_profile = self.input_actions.to_dict()
        snapshot = PlaytestSnapshot(
            scene_text=self.serializer.dumps_scene(self.scene),
            input_profile=input_profile,
        )
        self._playtest_snapshot = snapshot
        return snapshot

    def end_playtest(self, *, restore: bool = True) -> None:
        snapshot = self._playtest_snapshot
        if snapshot is None:
            raise RuntimeError("playtest is not active")
        try:
            if restore:
                self.serializer.loads_scene(snapshot.scene_text, scene=self.scene, clear=True)
                if self.input_actions is not None and snapshot.input_profile is not None:
                    self.input_actions.load_dict(snapshot.input_profile, replace=True)
        finally:
            self._playtest_snapshot = None

    def cancel_playtest(self) -> None:
        self.end_playtest(restore=True)

    def keep_playtest_changes(self) -> None:
        self.end_playtest(restore=False)
