from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import PurePath

from .editor import InspectorField
from .editor_authoring import EditorAuthoringSession, EditorBatchPropertyResult


@dataclass(frozen=True, slots=True)
class InspectorEditorSpec:
    """Toolkit-neutral editor description for one shared Inspector field."""

    name: str
    kind: str
    type_name: str
    value: object
    editable: bool
    mixed: bool = False
    choices: tuple[str, ...] = ()


class EditorTypedInspector:
    """Typed field model layered on the active ``EditorAuthoringSession`` selection.

    The model intentionally describes controls instead of rendering them. Native, web and in-game
    SwirEditor front-ends can therefore share the same coercion, mixed-value and editability rules.
    Mutations are delegated to ``EditorAuthoringSession`` so multi-selection stays one logical
    undo/redo transaction.
    """

    def __init__(self, authoring: EditorAuthoringSession) -> None:
        self.authoring = authoring

    def fields(self) -> tuple[InspectorEditorSpec, ...]:
        targets = self.authoring.selected_targets
        if not targets:
            return ()

        snapshots = [self.authoring.inspector.inspect(target) for target in targets]
        field_maps = [
            {field.name: field for field in snapshot.fields}
            for snapshot in snapshots
            if snapshot is not None
        ]
        if len(field_maps) != len(targets):
            return ()

        common = set(field_maps[0])
        for fields in field_maps[1:]:
            common.intersection_update(fields)

        specs: list[InspectorEditorSpec] = []
        for name in sorted(common):
            fields = [items[name] for items in field_maps]
            values = [field.value for field in fields]
            first = values[0]
            same_type = all(type(value) is type(first) for value in values[1:])
            mixed = any(value != first for value in values[1:])
            kind, choices = self._kind(first) if same_type else ("mixed", ())
            specs.append(
                InspectorEditorSpec(
                    name=name,
                    kind=kind,
                    type_name=type(first).__name__ if same_type else "mixed",
                    value=first,
                    editable=same_type and all(field.editable for field in fields),
                    mixed=mixed,
                    choices=choices,
                )
            )
        return tuple(specs)

    def field(self, name: str) -> InspectorEditorSpec:
        for field in self.fields():
            if field.name == name:
                return field
        raise AttributeError(name)

    def set(self, name: str, raw_value: object) -> EditorBatchPropertyResult:
        """Validate/coerce one UI value, then update the full current selection atomically."""
        spec = self.field(name)
        if not spec.editable:
            raise AttributeError(f"property {name!r} is not editable across the current selection")
        targets = self.authoring.selected_targets
        converted = [
            self.coerce(raw_value, self._field_value(target, name))
            for target in targets
        ]
        if not converted:
            raise RuntimeError("no editor targets selected")
        first = converted[0]
        if any(value != first for value in converted[1:]):
            raise TypeError("typed conversion produced inconsistent values across the selection")
        return self.authoring.set_property(name, first)

    @staticmethod
    def coerce(raw_value: object, current: object) -> object:
        if isinstance(current, bool):
            if isinstance(raw_value, bool):
                return raw_value
            if isinstance(raw_value, str):
                value = raw_value.strip().casefold()
                if value in {"true", "1", "yes", "on"}:
                    return True
                if value in {"false", "0", "no", "off"}:
                    return False
            raise TypeError("boolean fields accept true/false, yes/no, on/off or 0/1")

        if isinstance(current, Enum):
            enum_type = type(current)
            if isinstance(raw_value, enum_type):
                return raw_value
            if isinstance(raw_value, str):
                try:
                    return enum_type[raw_value]
                except KeyError:
                    pass
            try:
                return enum_type(raw_value)
            except (TypeError, ValueError) as exc:
                raise TypeError(f"invalid {enum_type.__name__} value {raw_value!r}") from exc

        if isinstance(current, int) and not isinstance(current, bool):
            if isinstance(raw_value, bool):
                raise TypeError("integer fields do not accept booleans")
            try:
                return int(raw_value)
            except (TypeError, ValueError) as exc:
                raise TypeError(f"invalid integer value {raw_value!r}") from exc

        if isinstance(current, float):
            if isinstance(raw_value, bool):
                raise TypeError("numeric fields do not accept booleans")
            try:
                return float(raw_value)
            except (TypeError, ValueError) as exc:
                raise TypeError(f"invalid numeric value {raw_value!r}") from exc

        if isinstance(current, str):
            if not isinstance(raw_value, str):
                raise TypeError("text fields require a string")
            return raw_value

        if isinstance(current, PurePath):
            if not isinstance(raw_value, (str, PurePath)):
                raise TypeError("path fields require a string or PurePath")
            return type(current)(raw_value)

        if isinstance(current, tuple) and 2 <= len(current) <= 4:
            if all(isinstance(item, (int, float)) and not isinstance(item, bool) for item in current):
                if not isinstance(raw_value, (tuple, list)) or len(raw_value) != len(current):
                    raise TypeError(f"vector field requires {len(current)} numeric values")
                return tuple(
                    float(value) if isinstance(original, float) else int(value)
                    for value, original in zip(raw_value, current, strict=True)
                )

        if type(raw_value) is type(current):
            return raw_value
        raise TypeError(
            f"unsupported typed conversion from {type(raw_value).__name__} "
            f"to {type(current).__name__}"
        )

    @staticmethod
    def _kind(value: object) -> tuple[str, tuple[str, ...]]:
        if isinstance(value, bool):
            return "boolean", ()
        if isinstance(value, Enum):
            return "choice", tuple(member.name for member in type(value))
        if isinstance(value, PurePath):
            return "asset_path", ()
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return "number", ()
        if isinstance(value, str):
            return "text", ()
        if isinstance(value, set) and all(isinstance(item, str) for item in value):
            return "tags", ()
        if isinstance(value, tuple) and 2 <= len(value) <= 4:
            if all(isinstance(item, (int, float)) and not isinstance(item, bool) for item in value):
                return "vector", ()
        return "object", ()

    def _field_value(self, target: object, name: str) -> object:
        snapshot = self.authoring.inspector.inspect(target)
        if snapshot is None:
            raise LookupError("selected target no longer exists")
        field: InspectorField | None = next(
            (item for item in snapshot.fields if item.name == name),
            None,
        )
        if field is None:
            raise AttributeError(name)
        return field.value
