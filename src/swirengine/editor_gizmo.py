from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import TYPE_CHECKING

from .editor import PropertyEdit, SceneInspector
from .math.types import Vec3

if TYPE_CHECKING:
    from .editor_workspace import EditorViewportState, EditorWorkspace

_AXES = {"x", "y", "z", "all"}
_MODES = {"translate", "rotate", "scale"}


@dataclass(frozen=True, slots=True)
class GizmoTransformSnapshot:
    """Immutable transform capabilities/state for the selected editor target."""

    target_key: str
    modes: tuple[str, ...]
    translation: tuple[float, float, float] | None
    rotation: tuple[float, float, float] | float | None
    scale: tuple[float, float, float] | float | None


@dataclass(frozen=True, slots=True)
class GizmoApplyResult:
    """Result of one gizmo drag/update applied through ``SceneInspector`` history."""

    target_key: str
    mode: str
    axis: str
    before: object
    after: object
    edit: PropertyEdit


class EditorTransformGizmo:
    """Toolkit-agnostic Move/Rotate/Scale controller for the visual editor.

    The gizmo deliberately routes every mutation through ``SceneInspector.set_property`` so
    normal undo/redo, stale-target protection and history limits stay authoritative. It supports
    native 3D ``Vec3`` transforms, the existing 2D primitive position/rotation convention and
    explicit 2D width/height scaling. Scalar ``scale`` and ``size`` remain uniform scaling.
    """

    def __init__(self, inspector: SceneInspector) -> None:
        self.inspector = inspector

    @classmethod
    def from_workspace(cls, workspace: EditorWorkspace) -> EditorTransformGizmo:
        return cls(workspace.inspector)

    def snapshot(self, target: object | str | None = None) -> GizmoTransformSnapshot | None:
        resolved = self._resolve(target)
        if resolved is None:
            return None
        key = self.inspector.key_for(resolved)

        translation = self._translation_state(resolved)
        rotation = self._rotation_state(resolved)
        scale = self._scale_state(resolved)
        modes = tuple(
            mode
            for mode, state in (
                ("translate", translation),
                ("rotate", rotation),
                ("scale", scale),
            )
            if state is not None
        )
        return GizmoTransformSnapshot(key, modes, translation, rotation, scale)

    def apply(
        self,
        mode: str,
        axis: str,
        delta: float,
        *,
        target: object | str | None = None,
        snap: float | None = None,
    ) -> GizmoApplyResult:
        if mode not in _MODES:
            raise ValueError(f"unsupported gizmo mode {mode!r}")
        if axis not in _AXES:
            raise ValueError(f"unsupported gizmo axis {axis!r}")
        if not isinstance(delta, (int, float)) or isinstance(delta, bool):
            raise TypeError("gizmo delta must be numeric")
        if snap is not None:
            if not isinstance(snap, (int, float)) or isinstance(snap, bool):
                raise TypeError("gizmo snap must be numeric")
            if float(snap) <= 0:
                raise ValueError("gizmo snap must be greater than zero")

        resolved = self._resolve(target)
        if resolved is None:
            raise RuntimeError("no gizmo target selected")
        key = self.inspector.key_for(resolved)

        property_name, before, after = self._transform_value(
            resolved,
            mode,
            axis,
            float(delta),
            None if snap is None else float(snap),
        )
        edit = self.inspector.set_property(property_name, after, target=resolved)
        return GizmoApplyResult(key, mode, axis, deepcopy(before), deepcopy(after), edit)

    def apply_viewport(
        self,
        viewport: EditorViewportState,
        axis: str,
        delta: float,
        *,
        target: object | str | None = None,
    ) -> GizmoApplyResult:
        if viewport.gizmo == "none":
            raise RuntimeError("viewport gizmo is disabled")
        snap = None
        if viewport.snap_enabled:
            snap = {
                "translate": viewport.translation_snap,
                "rotate": viewport.rotation_snap,
                "scale": viewport.scale_snap,
            }[viewport.gizmo]
        return self.apply(viewport.gizmo, axis, delta, target=target, snap=snap)

    def _resolve(self, target: object | str | None) -> object | None:
        if target is None:
            return self.inspector.selected_target
        if isinstance(target, str):
            resolved = self.inspector.resolve(target)
            if resolved is None:
                raise KeyError(target)
            return resolved
        self.inspector.key_for(target)
        return target

    @staticmethod
    def _translation_state(target: object) -> tuple[float, float, float] | None:
        position = getattr(target, "position", None)
        if isinstance(position, Vec3):
            return (float(position.x), float(position.y), float(position.z))
        x = getattr(target, "x", None)
        y = getattr(target, "y", None)
        if EditorTransformGizmo._numeric(x) and EditorTransformGizmo._numeric(y):
            return (float(x), float(y), 0.0)
        return None

    @staticmethod
    def _rotation_state(target: object) -> tuple[float, float, float] | float | None:
        rotation = getattr(target, "rotation", None)
        if isinstance(rotation, Vec3):
            return (float(rotation.x), float(rotation.y), float(rotation.z))
        if EditorTransformGizmo._numeric(rotation):
            return float(rotation)
        return None

    @staticmethod
    def _scale_state(target: object) -> tuple[float, float, float] | float | None:
        scale = getattr(target, "scale", None)
        if isinstance(scale, Vec3):
            return (float(scale.x), float(scale.y), float(scale.z))
        if EditorTransformGizmo._numeric(scale):
            return float(scale)
        size = getattr(target, "size", None)
        if EditorTransformGizmo._numeric(size):
            return float(size)
        width = getattr(target, "width", None)
        height = getattr(target, "height", None)
        if EditorTransformGizmo._numeric(width) and EditorTransformGizmo._numeric(height):
            return (float(width), float(height), 1.0)
        return None

    def _transform_value(
        self,
        target: object,
        mode: str,
        axis: str,
        delta: float,
        snap: float | None,
    ) -> tuple[str, object, object]:
        if mode == "translate":
            return self._translate_value(target, axis, delta, snap)
        if mode == "rotate":
            return self._rotate_value(target, axis, delta, snap)
        return self._scale_value(target, axis, delta, snap)

    def _translate_value(
        self, target: object, axis: str, delta: float, snap: float | None
    ) -> tuple[str, object, object]:
        if axis == "all":
            raise ValueError("translation requires a concrete axis")
        position = getattr(target, "position", None)
        if isinstance(position, Vec3):
            before = deepcopy(position)
            if axis not in {"x", "y", "z"}:
                raise ValueError(f"unsupported translation axis {axis!r}")
            values = {"x": position.x, "y": position.y, "z": position.z}
            values[axis] = self._snapped(float(values[axis]) + delta, snap)
            return "position", before, Vec3(values["x"], values["y"], values["z"])

        if axis not in {"x", "y"}:
            raise ValueError("2D translation supports only x/y axes")
        value = getattr(target, axis, None)
        if not self._numeric(value):
            raise TypeError("selected target does not expose a translatable position")
        before = float(value)
        return axis, before, self._snapped(before + delta, snap)

    def _rotate_value(
        self, target: object, axis: str, delta: float, snap: float | None
    ) -> tuple[str, object, object]:
        rotation = getattr(target, "rotation", None)
        if isinstance(rotation, Vec3):
            if axis == "all" or axis not in {"x", "y", "z"}:
                raise ValueError("3D rotation requires a concrete x/y/z axis")
            before = deepcopy(rotation)
            values = {"x": rotation.x, "y": rotation.y, "z": rotation.z}
            values[axis] = self._snapped(float(values[axis]) + delta, snap)
            return "rotation", before, Vec3(values["x"], values["y"], values["z"])
        if self._numeric(rotation):
            if axis not in {"z", "all"}:
                raise ValueError("2D rotation uses the z/all axis")
            before = float(rotation)
            return "rotation", before, self._snapped(before + delta, snap)
        raise TypeError("selected target does not expose a rotatable transform")

    def _scale_value(
        self, target: object, axis: str, delta: float, snap: float | None
    ) -> tuple[str, object, object]:
        scale = getattr(target, "scale", None)
        if isinstance(scale, Vec3):
            before = deepcopy(scale)
            values = {"x": scale.x, "y": scale.y, "z": scale.z}
            axes = ("x", "y", "z") if axis == "all" else (axis,)
            if any(name not in {"x", "y", "z"} for name in axes):
                raise ValueError(f"unsupported scale axis {axis!r}")
            for name in axes:
                values[name] = self._snapped(float(values[name]) + delta, snap)
            return "scale", before, Vec3(values["x"], values["y"], values["z"])

        for property_name in ("scale", "size"):
            value = getattr(target, property_name, None)
            if self._numeric(value):
                if axis != "all":
                    raise ValueError("uniform scalar scaling requires the all axis")
                before = float(value)
                return property_name, before, self._snapped(before + delta, snap)

        width = getattr(target, "width", None)
        height = getattr(target, "height", None)
        if self._numeric(width) and self._numeric(height):
            if axis not in {"x", "y"}:
                raise ValueError("2D dimension scaling supports x/y axes")
            property_name = "width" if axis == "x" else "height"
            before = float(width if axis == "x" else height)
            after = self._snapped(before + delta, snap)
            if after <= 0.0:
                raise ValueError("2D dimensions must remain greater than zero")
            return property_name, before, after
        raise TypeError("selected target does not expose a scalable transform")

    @staticmethod
    def _snapped(value: float, snap: float | None) -> float:
        if snap is None:
            return value
        return round(value / snap) * snap

    @staticmethod
    def _numeric(value: object) -> bool:
        return isinstance(value, (int, float)) and not isinstance(value, bool)
