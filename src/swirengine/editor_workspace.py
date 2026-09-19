from __future__ import annotations

import json
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from .core.scene import Scene
from .editor import HierarchyItem, HistoryEdit, InspectorSnapshot, SceneInspector
from .editor_state import EditorHierarchyState, capture_editor_hierarchy, restore_editor_hierarchy

EDITOR_PROJECT_FORMAT = "swirengine.editor_project"
EDITOR_PROJECT_VERSION = 1
_PANEL_REGIONS = {"left", "right", "center", "bottom", "floating"}
_VIEWPORT_MODES = {"2d", "3d"}
_GIZMO_MODES = {"translate", "rotate", "scale", "none"}


@dataclass(frozen=True, slots=True)
class EditorPanelState:
    """Serializable layout metadata for one editor panel."""

    panel_id: str
    title: str
    region: str
    visible: bool = True
    order: int = 0
    weight: float = 1.0

    def __post_init__(self) -> None:
        if not self.panel_id.strip():
            raise ValueError("panel_id cannot be empty")
        if not self.title.strip():
            raise ValueError("panel title cannot be empty")
        if self.region not in _PANEL_REGIONS:
            raise ValueError(f"unsupported editor panel region {self.region!r}")
        if not isinstance(self.order, int) or isinstance(self.order, bool) or self.order < 0:
            raise ValueError("panel order must be a non-negative integer")
        if not isinstance(self.weight, (int, float)) or isinstance(self.weight, bool):
            raise TypeError("panel weight must be numeric")
        if float(self.weight) <= 0:
            raise ValueError("panel weight must be greater than zero")

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.panel_id,
            "title": self.title,
            "region": self.region,
            "visible": self.visible,
            "order": self.order,
            "weight": float(self.weight),
        }

    @classmethod
    def from_dict(cls, payload: object) -> EditorPanelState:
        if not isinstance(payload, dict):
            raise TypeError("editor panel state must be an object")
        panel_id = payload.get("id")
        title = payload.get("title")
        region = payload.get("region")
        visible = payload.get("visible", True)
        order = payload.get("order", 0)
        weight = payload.get("weight", 1.0)
        if not isinstance(panel_id, str):
            raise TypeError("editor panel state needs a string id")
        if not isinstance(title, str):
            raise TypeError("editor panel state needs a string title")
        if not isinstance(region, str):
            raise TypeError("editor panel state needs a string region")
        if not isinstance(visible, bool):
            raise TypeError("editor panel visible flag must be boolean")
        if not isinstance(order, int) or isinstance(order, bool):
            raise TypeError("editor panel order must be an integer")
        if not isinstance(weight, (int, float)) or isinstance(weight, bool):
            raise TypeError("editor panel weight must be numeric")
        return cls(panel_id, title, region, visible, order, float(weight))


@dataclass(frozen=True, slots=True)
class EditorViewportState:
    """Portable viewport preferences shared by future desktop/web editor front-ends."""

    mode: str = "3d"
    gizmo: str = "translate"
    grid_visible: bool = True
    snap_enabled: bool = False
    translation_snap: float = 1.0
    rotation_snap: float = 15.0
    scale_snap: float = 0.1

    def __post_init__(self) -> None:
        if self.mode not in _VIEWPORT_MODES:
            raise ValueError(f"unsupported viewport mode {self.mode!r}")
        if self.gizmo not in _GIZMO_MODES:
            raise ValueError(f"unsupported gizmo mode {self.gizmo!r}")
        for name in ("translation_snap", "rotation_snap", "scale_snap"):
            value = getattr(self, name)
            if not isinstance(value, (int, float)) or isinstance(value, bool):
                raise TypeError(f"{name} must be numeric")
            if float(value) <= 0:
                raise ValueError(f"{name} must be greater than zero")

    def to_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "gizmo": self.gizmo,
            "grid_visible": self.grid_visible,
            "snap_enabled": self.snap_enabled,
            "translation_snap": float(self.translation_snap),
            "rotation_snap": float(self.rotation_snap),
            "scale_snap": float(self.scale_snap),
        }

    @classmethod
    def from_dict(cls, payload: object) -> EditorViewportState:
        if not isinstance(payload, dict):
            raise TypeError("editor viewport state must be an object")
        mode = payload.get("mode", "3d")
        gizmo = payload.get("gizmo", "translate")
        grid_visible = payload.get("grid_visible", True)
        snap_enabled = payload.get("snap_enabled", False)
        translation_snap = payload.get("translation_snap", 1.0)
        rotation_snap = payload.get("rotation_snap", 15.0)
        scale_snap = payload.get("scale_snap", 0.1)
        if not isinstance(mode, str):
            raise TypeError("viewport mode must be a string")
        if not isinstance(gizmo, str):
            raise TypeError("viewport gizmo must be a string")
        if not isinstance(grid_visible, bool) or not isinstance(snap_enabled, bool):
            raise TypeError("viewport grid/snap flags must be boolean")
        numeric = (translation_snap, rotation_snap, scale_snap)
        if any(not isinstance(value, (int, float)) or isinstance(value, bool) for value in numeric):
            raise TypeError("viewport snap values must be numeric")
        return cls(
            mode,
            gizmo,
            grid_visible,
            snap_enabled,
            float(translation_snap),
            float(rotation_snap),
            float(scale_snap),
        )


@dataclass(frozen=True, slots=True)
class EditorSceneState:
    scene_id: str
    hierarchy: EditorHierarchyState
    viewport: EditorViewportState = EditorViewportState()

    def __post_init__(self) -> None:
        if not self.scene_id.strip():
            raise ValueError("scene_id cannot be empty")

    def to_dict(self) -> dict[str, Any]:
        return {
            "scene_id": self.scene_id,
            "hierarchy": self.hierarchy.to_dict(),
            "viewport": self.viewport.to_dict(),
        }

    @classmethod
    def from_dict(cls, payload: object) -> EditorSceneState:
        if not isinstance(payload, dict):
            raise TypeError("editor scene state must be an object")
        scene_id = payload.get("scene_id")
        if not isinstance(scene_id, str):
            raise TypeError("editor scene state needs a string scene_id")
        return cls(
            scene_id,
            EditorHierarchyState.from_dict(payload.get("hierarchy")),
            EditorViewportState.from_dict(payload.get("viewport", {})),
        )


@dataclass(frozen=True, slots=True)
class EditorProjectState:
    """Versioned project-level editor metadata.

    Runtime scene data stays owned by ``SceneSerializer``; this document stores only editor
    concerns such as per-scene hierarchy/selection, viewport preferences and panel layout.
    """

    project_name: str
    asset_root: str
    scenes: tuple[EditorSceneState, ...]
    active_scene_id: str
    panels: tuple[EditorPanelState, ...]
    version: int = EDITOR_PROJECT_VERSION

    def __post_init__(self) -> None:
        if self.version != EDITOR_PROJECT_VERSION:
            raise ValueError(
                f"unsupported editor project version {self.version}; "
                f"expected {EDITOR_PROJECT_VERSION}"
            )
        if not self.project_name.strip():
            raise ValueError("project_name cannot be empty")
        if not self.asset_root.strip():
            raise ValueError("asset_root cannot be empty")
        scene_ids = [scene.scene_id for scene in self.scenes]
        if len(scene_ids) != len(set(scene_ids)):
            raise ValueError("editor project contains duplicate scene ids")
        if self.active_scene_id not in set(scene_ids):
            raise ValueError("active_scene_id must reference a saved scene")
        panel_ids = [panel.panel_id for panel in self.panels]
        if len(panel_ids) != len(set(panel_ids)):
            raise ValueError("editor project contains duplicate panel ids")

    def to_dict(self) -> dict[str, Any]:
        return {
            "format": EDITOR_PROJECT_FORMAT,
            "version": self.version,
            "project_name": self.project_name,
            "asset_root": self.asset_root,
            "active_scene_id": self.active_scene_id,
            "scenes": [scene.to_dict() for scene in self.scenes],
            "panels": [panel.to_dict() for panel in self.panels],
        }

    @classmethod
    def from_dict(cls, payload: object) -> EditorProjectState:
        if not isinstance(payload, dict):
            raise TypeError("editor project document must be an object")
        if payload.get("format") != EDITOR_PROJECT_FORMAT:
            raise ValueError(f"expected {EDITOR_PROJECT_FORMAT!r} document")
        version = payload.get("version")
        project_name = payload.get("project_name")
        asset_root = payload.get("asset_root")
        active_scene_id = payload.get("active_scene_id")
        scenes = payload.get("scenes")
        panels = payload.get("panels")
        if not isinstance(version, int) or isinstance(version, bool):
            raise TypeError("editor project document needs an integer version")
        if not isinstance(project_name, str):
            raise TypeError("editor project document needs a string project_name")
        if not isinstance(asset_root, str):
            raise TypeError("editor project document needs a string asset_root")
        if not isinstance(active_scene_id, str):
            raise TypeError("editor project document needs a string active_scene_id")
        if not isinstance(scenes, list):
            raise TypeError("editor project document scenes must be a list")
        if not isinstance(panels, list):
            raise TypeError("editor project document panels must be a list")
        return cls(
            project_name,
            asset_root,
            tuple(EditorSceneState.from_dict(scene) for scene in scenes),
            active_scene_id,
            tuple(EditorPanelState.from_dict(panel) for panel in panels),
            version,
        )

    def dumps(self, *, indent: int | None = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, sort_keys=True)

    @classmethod
    def loads(cls, data: str) -> EditorProjectState:
        return cls.from_dict(json.loads(data))

    def save(self, path: str | Path) -> None:
        destination = Path(path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(self.dumps() + "\n", encoding="utf-8")

    @classmethod
    def load(cls, path: str | Path) -> EditorProjectState:
        return cls.loads(Path(path).read_text(encoding="utf-8"))


def default_editor_panels() -> tuple[EditorPanelState, ...]:
    """Return the canonical first-pass layout for the SwirEngine visual editor."""

    return (
        EditorPanelState("hierarchy", "Hierarchy", "left", True, 0, 0.24),
        EditorPanelState("viewport", "Viewport", "center", True, 0, 1.0),
        EditorPanelState("inspector", "Inspector", "right", True, 0, 0.28),
        EditorPanelState("assets", "Assets", "bottom", True, 0, 0.35),
        EditorPanelState("console", "Console", "bottom", True, 1, 0.35),
        EditorPanelState("profiler", "Profiler", "bottom", False, 2, 0.30),
    )


@dataclass(frozen=True, slots=True)
class EditorShellFrame:
    """Immutable view-model consumed by a visual editor front-end for one frame."""

    project_name: str
    scene_id: str
    hierarchy: tuple[HierarchyItem, ...]
    inspector: InspectorSnapshot | None
    panels: tuple[EditorPanelState, ...]
    viewport: EditorViewportState
    can_undo: bool
    can_redo: bool
    hierarchy_query: str = ""


class EditorWorkspace:
    """Project/editor shell model built around ``SceneInspector``.

    The class owns no windowing toolkit. It deliberately concentrates project persistence,
    scene switching, layout, selection, filtering and undo/redo state in one place so a native,
    web or in-game visual editor can render the same deterministic model.
    """

    def __init__(
        self,
        scene: Scene,
        *,
        scene_id: str = "main",
        project_name: str = "Untitled",
        asset_root: str = "assets",
        history_limit: int = 100,
        panels: tuple[EditorPanelState, ...] | None = None,
    ) -> None:
        if not scene_id.strip():
            raise ValueError("scene_id cannot be empty")
        if not project_name.strip():
            raise ValueError("project_name cannot be empty")
        if not asset_root.strip():
            raise ValueError("asset_root cannot be empty")
        self.project_name = project_name
        self.asset_root = asset_root
        self.history_limit = history_limit
        self.scene_id = scene_id
        self.inspector = SceneInspector(scene, history_limit=history_limit)
        self.viewport = EditorViewportState()
        initial_panels = default_editor_panels() if panels is None else panels
        self._panels = self._panel_map(initial_panels)
        self._scene_states: dict[str, EditorSceneState] = {}
        self._hierarchy_query = ""
        self._hierarchy_tag: str | None = None
        self._include_disabled = True

    @property
    def scene(self) -> Scene:
        return self.inspector.scene

    @property
    def panels(self) -> tuple[EditorPanelState, ...]:
        return tuple(
            sorted(self._panels.values(), key=lambda panel: (panel.region, panel.order, panel.panel_id))
        )

    def frame(self) -> EditorShellFrame:
        hierarchy = self.inspector.hierarchy(
            query=self._hierarchy_query,
            tag=self._hierarchy_tag,
            include_disabled=self._include_disabled,
        )
        return EditorShellFrame(
            self.project_name,
            self.scene_id,
            hierarchy,
            self.inspector.inspect(),
            self.panels,
            self.viewport,
            self.inspector.can_undo,
            self.inspector.can_redo,
            self._hierarchy_query,
        )

    def select(self, target_or_key: object | str | None) -> object | None:
        return self.inspector.select(target_or_key)

    def undo(self) -> HistoryEdit | None:
        return self.inspector.undo()

    def redo(self) -> HistoryEdit | None:
        return self.inspector.redo()

    def set_hierarchy_filter(
        self,
        query: str = "",
        *,
        tag: str | None = None,
        include_disabled: bool = True,
    ) -> None:
        self._hierarchy_query = query.strip()
        self._hierarchy_tag = tag
        self._include_disabled = include_disabled

    def configure_panel(
        self,
        panel_id: str,
        *,
        visible: bool | None = None,
        region: str | None = None,
        order: int | None = None,
        weight: float | None = None,
    ) -> EditorPanelState:
        try:
            current = self._panels[panel_id]
        except KeyError as exc:
            raise KeyError(f"unknown editor panel {panel_id!r}") from exc
        updated = replace(
            current,
            visible=current.visible if visible is None else visible,
            region=current.region if region is None else region,
            order=current.order if order is None else order,
            weight=current.weight if weight is None else weight,
        )
        self._panels[panel_id] = updated
        return updated

    def configure_viewport(
        self,
        *,
        mode: str | None = None,
        gizmo: str | None = None,
        grid_visible: bool | None = None,
        snap_enabled: bool | None = None,
        translation_snap: float | None = None,
        rotation_snap: float | None = None,
        scale_snap: float | None = None,
    ) -> EditorViewportState:
        current = self.viewport
        self.viewport = replace(
            current,
            mode=current.mode if mode is None else mode,
            gizmo=current.gizmo if gizmo is None else gizmo,
            grid_visible=current.grid_visible if grid_visible is None else grid_visible,
            snap_enabled=current.snap_enabled if snap_enabled is None else snap_enabled,
            translation_snap=(
                current.translation_snap if translation_snap is None else translation_snap
            ),
            rotation_snap=current.rotation_snap if rotation_snap is None else rotation_snap,
            scale_snap=current.scale_snap if scale_snap is None else scale_snap,
        )
        return self.viewport

    def stash_scene(self) -> EditorSceneState:
        state = EditorSceneState(
            self.scene_id,
            capture_editor_hierarchy(self.inspector),
            self.viewport,
        )
        self._scene_states[self.scene_id] = state
        return state

    def switch_scene(self, scene_id: str, scene: Scene, *, restore: bool = True) -> None:
        if not scene_id.strip():
            raise ValueError("scene_id cannot be empty")
        self.stash_scene()
        saved = self._scene_states.get(scene_id)
        inspector = SceneInspector(scene, history_limit=self.history_limit)
        viewport = EditorViewportState()
        if restore and saved is not None:
            restore_editor_hierarchy(inspector, saved.hierarchy)
            viewport = saved.viewport
        self.scene_id = scene_id
        self.inspector = inspector
        self.viewport = viewport

    def forget_scene_state(self, scene_id: str) -> bool:
        """Forget saved editor-only metadata for one non-active scene."""
        if scene_id == self.scene_id:
            raise ValueError("cannot forget the active editor scene state")
        return self._scene_states.pop(scene_id, None) is not None

    def capture_project(self) -> EditorProjectState:
        self.stash_scene()
        return EditorProjectState(
            self.project_name,
            self.asset_root,
            tuple(self._scene_states.values()),
            self.scene_id,
            self.panels,
        )

    def restore_project(
        self,
        state: EditorProjectState,
        scene: Scene,
        *,
        scene_id: str | None = None,
    ) -> None:
        target_scene_id = state.active_scene_id if scene_id is None else scene_id
        scene_states = {saved.scene_id: saved for saved in state.scenes}
        try:
            saved = scene_states[target_scene_id]
        except KeyError as exc:
            raise KeyError(f"project does not contain scene {target_scene_id!r}") from exc

        inspector = SceneInspector(scene, history_limit=self.history_limit)
        restore_editor_hierarchy(inspector, saved.hierarchy)
        panels = self._panel_map(state.panels)

        self.project_name = state.project_name
        self.asset_root = state.asset_root
        self.scene_id = target_scene_id
        self.inspector = inspector
        self.viewport = saved.viewport
        self._panels = panels
        self._scene_states = scene_states
        self._hierarchy_query = ""
        self._hierarchy_tag = None
        self._include_disabled = True

    @staticmethod
    def _panel_map(panels: tuple[EditorPanelState, ...]) -> dict[str, EditorPanelState]:
        result: dict[str, EditorPanelState] = {}
        for panel in panels:
            if panel.panel_id in result:
                raise ValueError(f"duplicate editor panel id {panel.panel_id!r}")
            result[panel.panel_id] = panel
        return result
