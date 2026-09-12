from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .ecs import Entity
from .editor import SceneInspector

EDITOR_HIERARCHY_FORMAT = "swirengine.editor_hierarchy"
EDITOR_HIERARCHY_VERSION = 1


@dataclass(frozen=True, slots=True)
class EditorTargetRef:
    """Portable reference to a scene object or ECS entity.

    Scene objects use their index in ``Scene.objects`` while ECS entities use their stable
    entity ID. This keeps editor hierarchy metadata independent from process-local ``id()``
    values used by the live inspector.
    """

    kind: str
    value: int

    def __post_init__(self) -> None:
        if self.kind not in {"object", "entity"}:
            raise ValueError(f"unsupported editor target kind {self.kind!r}")
        if not isinstance(self.value, int) or isinstance(self.value, bool) or self.value < 0:
            raise ValueError("editor target value must be a non-negative integer")
        if self.kind == "entity" and self.value < 1:
            raise ValueError("entity references require a positive entity ID")

    def to_dict(self) -> dict[str, Any]:
        return {"kind": self.kind, "value": self.value}

    @classmethod
    def from_dict(cls, payload: object) -> EditorTargetRef:
        if not isinstance(payload, dict):
            raise ValueError("editor target reference must be an object")
        kind = payload.get("kind")
        value = payload.get("value")
        if not isinstance(kind, str):
            raise ValueError("editor target reference needs a string kind")
        if not isinstance(value, int) or isinstance(value, bool):
            raise ValueError("editor target reference needs an integer value")
        return cls(kind, value)


@dataclass(frozen=True, slots=True)
class EditorHierarchyNode:
    target: EditorTargetRef
    parent: EditorTargetRef | None
    order: int

    def __post_init__(self) -> None:
        if not isinstance(self.order, int) or isinstance(self.order, bool) or self.order < 0:
            raise ValueError("hierarchy order must be a non-negative integer")
        if self.parent == self.target:
            raise ValueError("a hierarchy node cannot parent itself")

    def to_dict(self) -> dict[str, Any]:
        return {
            "target": self.target.to_dict(),
            "parent": None if self.parent is None else self.parent.to_dict(),
            "order": self.order,
        }

    @classmethod
    def from_dict(cls, payload: object) -> EditorHierarchyNode:
        if not isinstance(payload, dict):
            raise ValueError("hierarchy node must be an object")
        target = EditorTargetRef.from_dict(payload.get("target"))
        parent_payload = payload.get("parent")
        parent = None if parent_payload is None else EditorTargetRef.from_dict(parent_payload)
        order = payload.get("order")
        if not isinstance(order, int) or isinstance(order, bool):
            raise ValueError("hierarchy node needs an integer order")
        return cls(target, parent, order)


@dataclass(frozen=True, slots=True)
class EditorHierarchyState:
    """Serializable editor hierarchy metadata decoupled from runtime object identities."""

    nodes: tuple[EditorHierarchyNode, ...]
    selection: EditorTargetRef | None = None
    version: int = EDITOR_HIERARCHY_VERSION

    def __post_init__(self) -> None:
        if self.version != EDITOR_HIERARCHY_VERSION:
            raise ValueError(
                f"unsupported editor hierarchy version {self.version}; "
                f"expected {EDITOR_HIERARCHY_VERSION}"
            )
        targets = [node.target for node in self.nodes]
        if len(targets) != len(set(targets)):
            raise ValueError("editor hierarchy contains duplicate targets")
        target_set = set(targets)
        for node in self.nodes:
            if node.parent is not None and node.parent not in target_set:
                raise ValueError("editor hierarchy parent must also be present in the state")
        if self.selection is not None and self.selection not in target_set:
            raise ValueError("editor hierarchy selection must reference a saved target")
        self._validate_no_cycles()

    def _validate_no_cycles(self) -> None:
        parent_by_target = {node.target: node.parent for node in self.nodes}
        for start in parent_by_target:
            seen: set[EditorTargetRef] = set()
            cursor: EditorTargetRef | None = start
            while cursor is not None:
                if cursor in seen:
                    raise ValueError("editor hierarchy contains a parenting cycle")
                seen.add(cursor)
                cursor = parent_by_target.get(cursor)

    def to_dict(self) -> dict[str, Any]:
        return {
            "format": EDITOR_HIERARCHY_FORMAT,
            "version": self.version,
            "nodes": [node.to_dict() for node in self.nodes],
            "selection": None if self.selection is None else self.selection.to_dict(),
        }

    @classmethod
    def from_dict(cls, payload: object) -> EditorHierarchyState:
        if not isinstance(payload, dict):
            raise ValueError("editor hierarchy document must be an object")
        if payload.get("format") != EDITOR_HIERARCHY_FORMAT:
            raise ValueError(f"expected {EDITOR_HIERARCHY_FORMAT!r} document")
        version = payload.get("version")
        if not isinstance(version, int) or isinstance(version, bool):
            raise ValueError("editor hierarchy document needs an integer version")
        nodes_payload = payload.get("nodes")
        if not isinstance(nodes_payload, list):
            raise ValueError("editor hierarchy document nodes must be a list")
        selection_payload = payload.get("selection")
        selection = (
            None
            if selection_payload is None
            else EditorTargetRef.from_dict(selection_payload)
        )
        return cls(
            tuple(EditorHierarchyNode.from_dict(node) for node in nodes_payload),
            selection,
            version,
        )


def capture_editor_hierarchy(inspector: SceneInspector) -> EditorHierarchyState:
    """Capture portable hierarchy metadata from a live ``SceneInspector``."""

    scene = inspector.scene
    object_indices = {id(obj): index for index, obj in enumerate(scene.objects)}

    def portable_ref(key: str) -> EditorTargetRef:
        target = inspector.resolve(key)
        if target is None:
            raise LookupError(f"hierarchy target no longer exists: {key}")
        if isinstance(target, Entity):
            return EditorTargetRef("entity", target.id)
        try:
            return EditorTargetRef("object", object_indices[id(target)])
        except KeyError as exc:
            raise LookupError(f"scene object is not indexable: {key}") from exc

    rows = inspector.hierarchy()
    nodes = tuple(
        EditorHierarchyNode(
            portable_ref(row.key),
            None if row.parent_key is None else portable_ref(row.parent_key),
            row.order,
        )
        for row in rows
    )
    selection = (
        None
        if inspector.selected_key is None
        else portable_ref(inspector.selected_key)
    )
    return EditorHierarchyState(nodes, selection)


def restore_editor_hierarchy(
    inspector: SceneInspector,
    state: EditorHierarchyState,
    *,
    clear_history: bool = True,
    restore_selection: bool = True,
) -> None:
    """Restore hierarchy metadata into a compatible scene.

    Restoration is transactional from the editor's point of view: all references are resolved
    before mutation begins. Structural operations use the public inspector API, then optionally
    clear the generated history so loading a project does not look like user edits.
    """

    scene = inspector.scene

    def resolve(ref: EditorTargetRef) -> object:
        if ref.kind == "entity":
            target = scene.ecs.entity(ref.value)
            if target is None:
                raise LookupError(f"missing ECS entity {ref.value} for editor hierarchy")
            return target
        if ref.value >= len(scene.objects):
            raise LookupError(f"missing scene object index {ref.value} for editor hierarchy")
        return scene.objects[ref.value]

    resolved = {node.target: resolve(node.target) for node in state.nodes}
    for node in state.nodes:
        if node.parent is not None:
            resolve(node.parent)
    if state.selection is not None:
        resolve(state.selection)

    # Reparent descendants first. Ordering is normalized in a second pass, so the result does
    # not depend on the runtime scene's initial object/entity ordering.
    for node in state.nodes:
        target = resolved[node.target]
        parent = None if node.parent is None else resolved[node.parent]
        inspector.set_parent(target, parent)

    groups: dict[EditorTargetRef | None, list[EditorHierarchyNode]] = {}
    for node in state.nodes:
        groups.setdefault(node.parent, []).append(node)
    for siblings in groups.values():
        siblings.sort(key=lambda node: node.order)
        for desired_index, node in enumerate(siblings):
            inspector.move(resolved[node.target], desired_index)

    if restore_selection:
        if state.selection is None:
            inspector.select(None)
        else:
            inspector.select(resolved[state.selection])
    if clear_history:
        inspector.clear_history()
