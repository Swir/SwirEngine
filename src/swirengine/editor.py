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
    parent_key: str | None = None
    depth: int = 0
    order: int = 0


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
    component_type: type[object] | None = None


class SceneInspector:
    """GUI-agnostic hierarchy/inspector model with selection and undo/redo.

    Hierarchy parenting is editor metadata only. It intentionally does not mutate object
    transforms, ECS ownership or scene serialization yet, keeping the runtime API compatible
    while providing a stable tree model for future visual-editor front-ends.
    """

    def __init__(self, scene: Scene, *, history_limit: int = 100) -> None:
        if history_limit < 1:
            raise ValueError("history_limit must be >= 1")
        self.scene = scene
        self.history_limit = int(history_limit)
        self._selected_key: str | None = None
        self._undo: list[PropertyEdit] = []
        self._redo: list[PropertyEdit] = []
        self._parent_by_key: dict[str, str | None] = {}
        self._children_by_parent: dict[str | None, list[str]] = {None: []}
        self._sync_hierarchy()

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
        self._sync_hierarchy()
        needle = query.casefold().strip()
        items: list[HierarchyItem] = []
        for key, parent_key, depth, order in self._walk_hierarchy(None, 0):
            target = self.resolve(key)
            if target is None:
                continue
            kind = "entity" if isinstance(target, Entity) else "object"
            item = self._hierarchy_item(target, kind, parent_key, depth, order)
            if self._matches(item, needle, tag, include_disabled):
                items.append(item)
        return tuple(items)

    def parent(self, target_or_key: object | str) -> object | None:
        """Return the editor-hierarchy parent for a scene target, if any."""
        self._sync_hierarchy()
        key = self._hierarchy_key(target_or_key)
        parent_key = self._parent_by_key[key]
        return None if parent_key is None else self.resolve(parent_key)

    def children(self, target_or_key: object | str | None = None) -> tuple[object, ...]:
        """Return direct hierarchy children; ``None`` returns the root targets."""
        self._sync_hierarchy()
        parent_key = None if target_or_key is None else self._hierarchy_key(target_or_key)
        return tuple(
            target
            for key in self._children_by_parent.get(parent_key, ())
            if (target := self.resolve(key)) is not None
        )

    def set_parent(
        self,
        child: object | str,
        parent: object | str | None,
        *,
        index: int | None = None,
    ) -> None:
        """Reparent a hierarchy target with cycle prevention and deterministic sibling order."""
        self._sync_hierarchy()
        child_key = self._hierarchy_key(child)
        parent_key = None if parent is None else self._hierarchy_key(parent)
        if child_key == parent_key:
            raise ValueError("a hierarchy item cannot parent itself")

        cursor = parent_key
        while cursor is not None:
            if cursor == child_key:
                raise ValueError("hierarchy parenting would create a cycle")
            cursor = self._parent_by_key.get(cursor)

        old_parent = self._parent_by_key[child_key]
        old_siblings = self._children_by_parent.setdefault(old_parent, [])
        if child_key in old_siblings:
            old_siblings.remove(child_key)

        new_siblings = self._children_by_parent.setdefault(parent_key, [])
        insert_at = self._normalize_insert_index(index, len(new_siblings))
        new_siblings.insert(insert_at, child_key)
        self._parent_by_key[child_key] = parent_key
        self._children_by_parent.setdefault(child_key, [])

    def move(self, target: object | str, index: int) -> None:
        """Move a target within its current sibling list."""
        self._sync_hierarchy()
        key = self._hierarchy_key(target)
        parent_key = self._parent_by_key[key]
        siblings = self._children_by_parent[parent_key]
        if index < 0 or index >= len(siblings):
            raise IndexError(index)
        current = siblings.index(key)
        if current == index:
            return
        siblings.pop(current)
        siblings.insert(index, key)

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
        fields = self._snapshot_fields(resolved)
        components = (
            tuple(type(component).__name__ for component in resolved.components)
            if isinstance(resolved, Entity)
            else ()
        )
        return InspectorSnapshot(self.key_for(resolved), type(resolved).__name__, fields, components)

    def inspect_component(
        self,
        component_type: type[object],
        *,
        target: object | str | None = None,
    ) -> InspectorSnapshot | None:
        entity = self._resolve_entity(target)
        if entity is None:
            return None
        component = entity.get(component_type)
        if component is None:
            raise KeyError(component_type.__name__)
        return InspectorSnapshot(
            self.key_for(entity),
            type(component).__name__,
            self._snapshot_fields(component),
        )

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
        return self._set_property(resolved, name, value, self.key_for(resolved))

    def set_component_property(
        self,
        component_type: type[object],
        name: str,
        value: object,
        *,
        target: object | str | None = None,
    ) -> PropertyEdit:
        entity = self._resolve_entity(target)
        if entity is None:
            raise RuntimeError("no entity inspector target selected")
        component = entity.get(component_type)
        if component is None:
            raise KeyError(component_type.__name__)
        return self._set_property(
            component,
            name,
            value,
            self.key_for(entity),
            component_type=type(component),
        )

    def undo(self) -> PropertyEdit | None:
        if not self._undo:
            return None
        edit = self._undo.pop()
        target = self._edit_target(edit)
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
        target = self._edit_target(edit)
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

    def _resolve_entity(self, target: object | str | None) -> Entity | None:
        resolved = self._resolve_target(target)
        if resolved is None:
            return None
        if not isinstance(resolved, Entity):
            raise TypeError("component inspection requires an Entity target")
        return resolved

    def _set_property(
        self,
        resolved: object,
        name: str,
        value: object,
        target_key: str,
        *,
        component_type: type[object] | None = None,
    ) -> PropertyEdit:
        if name.startswith("_") or not hasattr(resolved, name):
            raise AttributeError(name)
        if not self._is_editable(resolved, name):
            raise AttributeError(f"property {name!r} is read-only")
        before = deepcopy(getattr(resolved, name))
        setattr(resolved, name, value)
        after = deepcopy(getattr(resolved, name))
        edit = PropertyEdit(target_key, name, before, after, component_type)
        if before != after:
            self._undo.append(edit)
            if len(self._undo) > self.history_limit:
                del self._undo[0]
            self._redo.clear()
        return edit

    def _edit_target(self, edit: PropertyEdit) -> object | None:
        target = self.resolve(edit.target_key)
        if target is None or edit.component_type is None:
            return target
        if not isinstance(target, Entity):
            return None
        return target.get(edit.component_type)

    def _snapshot_fields(self, target: object) -> tuple[InspectorField, ...]:
        return tuple(
            InspectorField(name, value, type(value).__name__, self._is_editable(target, name))
            for name, value in self._public_state(target)
        )

    def _hierarchy_item(
        self,
        target: object,
        kind: str,
        parent_key: str | None,
        depth: int,
        order: int,
    ) -> HierarchyItem:
        label = str(getattr(target, "name", "") or type(target).__name__)
        tags = tuple(sorted(str(tag) for tag in getattr(target, "tags", set())))
        return HierarchyItem(
            self.key_for(target),
            label,
            kind,
            type(target).__name__,
            bool(getattr(target, "enabled", True)),
            tags,
            parent_key,
            depth,
            order,
        )

    def _hierarchy_key(self, target_or_key: object | str) -> str:
        if isinstance(target_or_key, str):
            if self.resolve(target_or_key) is None:
                raise KeyError(target_or_key)
            return target_or_key
        return self.key_for(target_or_key)

    def _sync_hierarchy(self) -> None:
        current_keys = [self.key_for(target) for target in (*self.scene.objects, *self.scene.entities)]
        current = set(current_keys)

        for parent_key, children in tuple(self._children_by_parent.items()):
            if parent_key is not None and parent_key not in current:
                del self._children_by_parent[parent_key]
                continue
            children[:] = [key for key in children if key in current]

        for key in tuple(self._parent_by_key):
            if key not in current:
                del self._parent_by_key[key]

        roots = self._children_by_parent.setdefault(None, [])
        for key in current_keys:
            parent_key = self._parent_by_key.get(key)
            if parent_key not in current:
                parent_key = None
                self._parent_by_key[key] = None
            siblings = self._children_by_parent.setdefault(parent_key, [])
            if key not in siblings:
                siblings.append(key)
            self._children_by_parent.setdefault(key, [])
            if parent_key is not None and key in roots:
                roots.remove(key)

        for key, parent_key in tuple(self._parent_by_key.items()):
            if parent_key is None and key not in roots:
                roots.append(key)

    def _walk_hierarchy(
        self,
        parent_key: str | None,
        depth: int,
    ) -> tuple[tuple[str, str | None, int, int], ...]:
        rows: list[tuple[str, str | None, int, int]] = []
        for order, key in enumerate(self._children_by_parent.get(parent_key, ())):
            rows.append((key, parent_key, depth, order))
            rows.extend(self._walk_hierarchy(key, depth + 1))
        return tuple(rows)

    @staticmethod
    def _normalize_insert_index(index: int | None, length: int) -> int:
        if index is None:
            return length
        if index < 0 or index > length:
            raise IndexError(index)
        return index

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
