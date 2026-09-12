from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import Any

from .core.scene import Scene
from .ecs import Entity


@dataclass(frozen=True, slots=True)
class HierarchyItem:
    key: str
    label: str
    kind: str
    type_name: str
    enabled: bool
    tags: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class InspectorField:
    name: str
    value: object
    type_name: str
    editable: bool


@dataclass(frozen=True, slots=True)
class InspectorSnapshot:
    key: str
    type_name: str
    fields: tuple[InspectorField, ...]
    components: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class PropertyEdit:
    target_key: str
    property_name: str
    before: object
    after: object


class SceneInspector:
    """GUI-agnostic hierarchy/inspector model with selection and undo/redo."""

    def __init__(self, scene: Scene, *, history_limit: int = 100) -> None:
        if history_limit < 1:
            raise ValueError("history_limit must be >= 1")
        self.scene = scene
        self.history_limit = int(history_limit)
        self._selected_key: str | None = None
        self._undo: list[PropertyEdit] = []
        self._redo: list[PropertyEdit] = []

    @property
    def selected_key(self) -> str | None:
        return self._selected_key

    @property
    def selected_target(self) -> object | None:
        return None if self._selected_key is None else self.resolve(self._selected_key)

    @property
    def can_undo(self) -> bool:
        return bool(self._undo)

    @property
    def can_redo(self) -> bool:
        return bool(self._redo)

    @property
    def undo_history(self) -> tuple[PropertyEdit, ...]:
        return tuple(self._undo)

    @property
    def redo_history(self) -> tuple[PropertyEdit, ...]:
        return tuple(self._redo)

    def key_for(self, target: object) -> str:
        if isinstance(target, Entity):
            if self.scene.ecs.entity(target.id) is not target:
                raise ValueError("entity does not belong to this scene")
            return f"entity:{target.id}"
        if target not in self.scene:
            raise ValueError("object does not belong to this scene")
        return f"object:{id(target):x}"

    def resolve(self, key: str) -> object | None:
        if key.startswith("entity:"):
            try:
                return self.scene.ecs.entity(int(key.removeprefix("entity:")))
            except ValueError:
                return None
        if key.startswith("object:"):
            identity = key.removeprefix("object:")
            return next((obj for obj in self.scene.objects if f"{id(obj):x}" == identity), None)
        return None

    def hierarchy(
        self,
        *,
        query: str = "",
        tag: str | None = None,
        include_disabled: bool = True,
    ) -> tuple[HierarchyItem, ...]:
        needle = query.casefold().strip()
        items: list[HierarchyItem] = []
        for obj in (*self.scene.objects, *self.scene.entities):
            kind = "entity" if isinstance(obj, Entity) else "object"
            item = self._hierarchy_item(obj, kind)
            if self._matches(item, needle, tag, include_disabled):
                items.append(item)
        return tuple(items)

    def select(self, target_or_key: object | str | None) -> object | None:
        if target_or_key is None:
            self._selected_key = None
            return None
        if isinstance(target_or_key, str):
            target = self.resolve(target_or_key)
            if target is None:
                raise KeyError(target_or_key)
            self._selected_key = target_or_key
            return target
        self._selected_key = self.key_for(target_or_key)
        return target_or_key

    def inspect(self, target: object | str | None = None) -> InspectorSnapshot | None:
        resolved = self._resolve_target(target)
        if resolved is None:
            return None
        fields = tuple(
            InspectorField(name, value, type(value).__name__, self._is_editable(resolved, name))
            for name, value in self._public_state(resolved)
        )
        components = (
            tuple(type(component).__name__ for component in resolved.components)
            if isinstance(resolved, Entity)
            else ()
        )
        return InspectorSnapshot(self.key_for(resolved), type(resolved).__name__, fields, components)

    def set_property(
        self,
        name: str,
        value: object,
        *,
        target: object | str | None = None,
    ) -> PropertyEdit:
        resolved = self._resolve_target(target)
        if resolved is None:
            raise RuntimeError("no inspector target selected")
        if name.startswith("_") or not hasattr(resolved, name):
            raise AttributeError(name)
        if not self._is_editable(resolved, name):
            raise AttributeError(f"property {name!r} is read-only")

        before = deepcopy(getattr(resolved, name))
        setattr(resolved, name, value)
        after = deepcopy(getattr(resolved, name))
        edit = PropertyEdit(self.key_for(resolved), name, before, after)
        if before != after:
            self._undo.append(edit)
            if len(self._undo) > self.history_limit:
                del self._undo[0]
            self._redo.clear()
        return edit

    def undo(self) -> PropertyEdit | None:
        if not self._undo:
            return None
        edit = self._undo.pop()
        target = self.resolve(edit.target_key)
        if target is None:
            self._undo.append(edit)
            raise LookupError(f"edit target no longer exists: {edit.target_key}")
        setattr(target, edit.property_name, deepcopy(edit.before))
        self._redo.append(edit)
        return edit

    def redo(self) -> PropertyEdit | None:
        if not self._redo:
            return None
        edit = self._redo.pop()
        target = self.resolve(edit.target_key)
        if target is None:
            self._redo.append(edit)
            raise LookupError(f"edit target no longer exists: {edit.target_key}")
        setattr(target, edit.property_name, deepcopy(edit.after))
        self._undo.append(edit)
        return edit

    def clear_history(self) -> None:
        self._undo.clear()
        self._redo.clear()

    def _resolve_target(self, target: object | str | None) -> object | None:
        if target is None:
            return self.selected_target
        if isinstance(target, str):
            resolved = self.resolve(target)
            if resolved is None:
                raise KeyError(target)
            return resolved
        self.key_for(target)
        return target

    def _hierarchy_item(self, target: object, kind: str) -> HierarchyItem:
        label = str(getattr(target, "name", "") or type(target).__name__)
        tags = tuple(sorted(str(tag) for tag in getattr(target, "tags", set())))
        return HierarchyItem(
            self.key_for(target),
            label,
            kind,
            type(target).__name__,
            bool(getattr(target, "enabled", True)),
            tags,
        )

    @staticmethod
    def _matches(item: HierarchyItem, needle: str, tag: str | None, include_disabled: bool) -> bool:
        if not include_disabled and not item.enabled:
            return False
        if tag is not None and tag not in item.tags:
            return False
        if not needle:
            return True
        return needle in " ".join((item.label, item.type_name, *item.tags)).casefold()

    @staticmethod
    def _public_state(target: object) -> tuple[tuple[str, Any], ...]:
        names: set[str] = set()
        namespace = getattr(target, "__dict__", None)
        if isinstance(namespace, dict):
            names.update(name for name in namespace if not name.startswith("_"))
        for cls in type(target).__mro__:
            slots = getattr(cls, "__slots__", ())
            if isinstance(slots, str):
                slots = (slots,)
            names.update(name for name in slots if not name.startswith("_"))
        fields: list[tuple[str, Any]] = []
        for name in sorted(names):
            try:
                value = getattr(target, name)
            except AttributeError:
                continue
            if not callable(value):
                fields.append((name, value))
        return tuple(fields)

    @staticmethod
    def _is_editable(target: object, name: str) -> bool:
        descriptor = getattr(type(target), name, None)
        if isinstance(descriptor, property) and descriptor.fset is None:
            return False
        try:
            return not callable(getattr(target, name))
        except AttributeError:
            return False
