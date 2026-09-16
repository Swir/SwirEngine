from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from pathlib import PurePath
from typing import Any, Literal, cast

from .ecs import Entity
from .editor import PropertyEdit
from .editor_authoring import EditorAuthoringSession, EditorAuthoringTransaction
from .graphics.material import Material3D
from .math.types import Color
from .navigation import NavigationAgent2D, NavigationAgent3D
from .physics.rigidbody2d import RigidBody2D
from .physics.rigidbody3d import RigidBody3D

SpecializedInspectorKind = Literal["material", "physics", "navigation"]

_MATERIAL_FIELDS = (
    "texture",
    "tint",
    "ambient",
    "diffuse",
    "specular",
    "shininess",
    "metallic",
    "roughness",
    "metallic_roughness_texture",
    "normal_texture",
    "normal_scale",
    "occlusion_texture",
    "occlusion_strength",
    "emissive_texture",
    "emissive_factor",
    "alpha_mode",
    "alpha_cutoff",
    "double_sided",
)
_PHYSICS_FIELDS = (
    "body_type",
    "mass",
    "gravity_scale",
    "linear_damping",
    "restitution",
    "enabled",
)
_NAVIGATION_FIELDS = ("speed", "stopping_distance", "auto_repath")
_TEXTURE_FIELDS = {
    "texture",
    "metallic_roughness_texture",
    "normal_texture",
    "occlusion_texture",
    "emissive_texture",
}


@dataclass(frozen=True, slots=True)
class EditorSpecializedField:
    """One safe creator-facing field shared by the current specialized selection."""

    name: str
    value: object
    type_name: str
    mixed: bool = False


@dataclass(frozen=True, slots=True)
class EditorSpecializedSnapshot:
    """Toolkit-neutral material/physics/navigation inspector view."""

    kind: SpecializedInspectorKind
    label: str
    target_keys: tuple[str, ...]
    fields: tuple[EditorSpecializedField, ...]
    target_types: tuple[str, ...]

    def field(self, name: str) -> EditorSpecializedField:
        try:
            return next(field for field in self.fields if field.name == name)
        except StopIteration as exc:
            raise KeyError(name) from exc


@dataclass(frozen=True, slots=True)
class EditorSpecializedPropertyResult:
    kind: SpecializedInspectorKind
    property_name: str
    value: object
    target_keys: tuple[str, ...]
    transaction: EditorAuthoringTransaction


@dataclass(frozen=True, slots=True)
class _Binding:
    target: object
    source: object
    component_type: type[object] | None


class EditorSpecializedInspectors:
    """High-safety adapters for common creator-facing authoring domains.

    The adapters deliberately reuse ``SceneInspector`` mutation/history primitives. Material edits
    replace the selected object's complete ``Material3D`` value, while physics/navigation edits use
    ECS component history. This keeps grouped undo/redo compatible with the rest of editor 1.x.
    """

    def __init__(self, authoring: EditorAuthoringSession) -> None:
        if not isinstance(authoring, EditorAuthoringSession):
            raise TypeError("authoring must be an EditorAuthoringSession")
        self.authoring = authoring
        self.inspector = authoring.inspector

    def inspect(self, kind: SpecializedInspectorKind) -> EditorSpecializedSnapshot:
        targets = self._targets()
        bindings = self._bindings(kind, targets)
        field_names = self._field_names(kind)
        fields = tuple(
            self._snapshot_field(name, tuple(getattr(binding.source, name) for binding in bindings))
            for name in field_names
        )
        return EditorSpecializedSnapshot(
            kind,
            self._label(kind),
            tuple(self.inspector.key_for(target) for target in targets),
            fields,
            tuple(type(binding.source).__name__ for binding in bindings),
        )

    def set_property(
        self,
        kind: SpecializedInspectorKind,
        name: str,
        value: object,
    ) -> EditorSpecializedPropertyResult:
        targets = self._targets()
        bindings = self._bindings(kind, targets)
        if name not in self._field_names(kind):
            raise AttributeError(name)
        normalized = self._normalize(kind, name, value)
        planned: list[tuple[_Binding, object]] = []
        if kind == "material":
            for binding in bindings:
                replacement = deepcopy(binding.source)
                setattr(replacement, name, deepcopy(normalized))
                planned.append((binding, replacement))
        else:
            planned.extend((binding, deepcopy(normalized)) for binding in bindings)

        edits: list[PropertyEdit] = []
        for binding, replacement in planned:
            if kind == "material":
                edit = self.inspector.set_property("material", replacement, target=binding.target)
            else:
                assert binding.component_type is not None
                edit = self.inspector.set_component_property(
                    binding.component_type,
                    name,
                    replacement,
                    target=binding.target,
                )
            edits.append(edit)

        transaction = self.authoring._record(
            f"Set {kind} {name}",
            tuple(edit for edit in edits if edit.before != edit.after),
        )
        return EditorSpecializedPropertyResult(
            kind,
            name,
            deepcopy(normalized),
            tuple(edit.target_key for edit in edits),
            transaction,
        )

    def _targets(self) -> tuple[object, ...]:
        return self.authoring._require_selection()

    def _bindings(self, kind: SpecializedInspectorKind, targets: tuple[object, ...]) -> tuple[_Binding, ...]:
        if kind == "material":
            return tuple(self._material_binding(target) for target in targets)
        if kind == "physics":
            return tuple(
                self._component_binding(target, (RigidBody2D, RigidBody3D), kind)
                for target in targets
            )
        if kind == "navigation":
            return tuple(
                self._component_binding(target, (NavigationAgent2D, NavigationAgent3D), kind)
                for target in targets
            )
        raise ValueError(f"unsupported specialized inspector kind {kind!r}")

    @staticmethod
    def _material_binding(target: object) -> _Binding:
        if not hasattr(target, "material"):
            raise TypeError(
                f"{type(target).__name__} does not expose a Material3D-compatible 'material' field"
            )
        material = cast(Any, target).material
        if material is None:
            material = Material3D()
        if not isinstance(material, Material3D):
            raise TypeError(f"{type(target).__name__}.material is not Material3D-compatible")
        return _Binding(target, material, None)

    @staticmethod
    def _component_binding(target: object, component_types: tuple[type[object], ...], kind: SpecializedInspectorKind) -> _Binding:
        if not isinstance(target, Entity):
            raise TypeError(f"{kind} inspector requires ECS Entity selections")
        matches = tuple(
            component
            for component_type in component_types
            if (component := target.get(component_type)) is not None
        )
        unique = tuple(dict.fromkeys(id(component) for component in matches))
        if not matches:
            expected = " or ".join(component_type.__name__ for component_type in component_types)
            raise TypeError(f"entity {target.id} needs {expected} for the {kind} inspector")
        if len(unique) != 1:
            raise TypeError(f"entity {target.id} has ambiguous {kind} components")
        component = matches[0]
        return _Binding(target, component, type(component))

    @staticmethod
    def _snapshot_field(name: str, values: tuple[object, ...]) -> EditorSpecializedField:
        first = values[0]
        mixed = any(value != first for value in values[1:])
        type_names = {type(value).__name__ for value in values}
        type_name = next(iter(type_names)) if len(type_names) == 1 else "mixed"
        return EditorSpecializedField(name, None if mixed else deepcopy(first), type_name, mixed)

    @staticmethod
    def _field_names(kind: SpecializedInspectorKind) -> tuple[str, ...]:
        if kind == "material":
            return _MATERIAL_FIELDS
        if kind == "physics":
            return _PHYSICS_FIELDS
        if kind == "navigation":
            return _NAVIGATION_FIELDS
        raise ValueError(f"unsupported specialized inspector kind {kind!r}")

    @staticmethod
    def _label(kind: SpecializedInspectorKind) -> str:
        return {"material": "Material", "physics": "Physics", "navigation": "Navigation"}[kind]

    @classmethod
    def _normalize(cls, kind: SpecializedInspectorKind, name: str, value: object) -> object:
        if kind == "material":
            return cls._normalize_material(name, value)
        if kind == "physics":
            return cls._normalize_physics(name, value)
        if kind == "navigation":
            return cls._normalize_navigation(name, value)
        raise ValueError(f"unsupported specialized inspector kind {kind!r}")

    @staticmethod
    def _number(value: object, name: str) -> float:
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            raise TypeError(f"{name} must be numeric")
        return float(value)

    @classmethod
    def _normalize_material(cls, name: str, value: object) -> object:
        if name in _TEXTURE_FIELDS:
            if value is None or isinstance(value, (str, PurePath)):
                return deepcopy(value)
            raise TypeError(f"{name} must be a string/path or None")
        if name in {"tint", "emissive_factor"}:
            if not isinstance(value, Color):
                raise TypeError(f"{name} must be Color")
            if name == "emissive_factor" and min(value.r, value.g, value.b) < 0.0:
                raise ValueError("emissive_factor RGB values must be >= 0")
            return deepcopy(value)
        if name == "alpha_mode":
            if not isinstance(value, str):
                raise TypeError("alpha_mode must be a string")
            normalized = value.upper()
            if normalized not in {"OPAQUE", "MASK", "BLEND"}:
                raise ValueError("alpha_mode must be one of OPAQUE, MASK or BLEND")
            return normalized
        if name == "double_sided":
            if not isinstance(value, bool):
                raise TypeError("double_sided must be boolean")
            return value
        if name in {"metallic", "roughness"} and value is None:
            return None
        number = cls._number(value, name)
        if name in {"ambient", "diffuse", "specular", "normal_scale"} and number < 0.0:
            raise ValueError(f"{name} must be >= 0")
        if name == "shininess" and number < 1.0:
            raise ValueError("shininess must be >= 1")
        if name in {"metallic", "roughness", "occlusion_strength", "alpha_cutoff"} and not (0.0 <= number <= 1.0):
            raise ValueError(f"{name} must be within 0..1")
        return number

    @classmethod
    def _normalize_physics(cls, name: str, value: object) -> object:
        if name == "body_type":
            if not isinstance(value, str) or value not in {"dynamic", "kinematic", "static"}:
                raise ValueError("body_type must be dynamic, kinematic or static")
            return value
        if name == "enabled":
            if not isinstance(value, bool):
                raise TypeError("enabled must be boolean")
            return value
        number = cls._number(value, name)
        if name == "mass" and number <= 0.0:
            raise ValueError("mass must be greater than zero")
        if name == "linear_damping" and number < 0.0:
            raise ValueError("linear_damping must be >= 0")
        if name == "restitution" and not 0.0 <= number <= 1.0:
            raise ValueError("restitution must be within 0..1")
        return number

    @classmethod
    def _normalize_navigation(cls, name: str, value: object) -> object:
        if name == "auto_repath":
            if not isinstance(value, bool):
                raise TypeError("auto_repath must be boolean")
            return value
        number = cls._number(value, name)
        if number < 0.0:
            raise ValueError(f"{name} must be non-negative")
        return number
