from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .ecs import Entity
from .editor import SceneInspector
from .editor_authoring import EditorSelectionModel
from .editor_state import EditorTargetRef

EDITOR_AUTHORING_FORMAT = "swirengine.editor_authoring"
EDITOR_AUTHORING_VERSION = 1


@dataclass(frozen=True, slots=True)
class EditorAuthoringState:
    """Additive 1.4 editor state kept separate from the stable hierarchy/project formats."""

    selected: tuple[EditorTargetRef, ...] = ()
    primary: EditorTargetRef | None = None
    anchor: EditorTargetRef | None = None
    version: int = EDITOR_AUTHORING_VERSION

    def __post_init__(self) -> None:
        if self.version != EDITOR_AUTHORING_VERSION:
            raise ValueError(
                f"unsupported editor authoring version {self.version}; "
                f"expected {EDITOR_AUTHORING_VERSION}"
            )
        if len(self.selected) != len(set(self.selected)):
            raise ValueError("editor authoring state contains duplicate selected targets")
        selected = set(self.selected)
        if self.primary is not None and self.primary not in selected:
            raise ValueError("editor authoring primary target must be selected")
        if self.anchor is not None and self.anchor not in selected:
            raise ValueError("editor authoring anchor target must be selected")

    def to_dict(self) -> dict[str, Any]:
        return {
            "format": EDITOR_AUTHORING_FORMAT,
            "version": self.version,
            "selected": [item.to_dict() for item in self.selected],
            "primary": None if self.primary is None else self.primary.to_dict(),
            "anchor": None if self.anchor is None else self.anchor.to_dict(),
        }

    @classmethod
    def from_dict(cls, payload: object) -> EditorAuthoringState:
        if not isinstance(payload, dict):
            raise TypeError("editor authoring document must be an object")
        if payload.get("format") != EDITOR_AUTHORING_FORMAT:
            raise ValueError(f"expected {EDITOR_AUTHORING_FORMAT!r} document")
        version = payload.get("version")
        if not isinstance(version, int) or isinstance(version, bool):
            raise TypeError("editor authoring document needs an integer version")
        selected_payload = payload.get("selected", [])
        if not isinstance(selected_payload, list):
            raise TypeError("editor authoring selected targets must be a list")
        primary_payload = payload.get("primary")
        anchor_payload = payload.get("anchor")
        primary = None if primary_payload is None else EditorTargetRef.from_dict(primary_payload)
        anchor = None if anchor_payload is None else EditorTargetRef.from_dict(anchor_payload)
        return cls(
            tuple(EditorTargetRef.from_dict(item) for item in selected_payload),
            primary,
            anchor,
            version,
        )

    def dumps(self, *, indent: int | None = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, sort_keys=True)

    @classmethod
    def loads(cls, data: str) -> EditorAuthoringState:
        return cls.from_dict(json.loads(data))

    def save(self, path: str | Path) -> None:
        destination = Path(path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(self.dumps() + "\n", encoding="utf-8")

    @classmethod
    def load(cls, path: str | Path) -> EditorAuthoringState:
        return cls.loads(Path(path).read_text(encoding="utf-8"))


def _portable_ref(inspector: SceneInspector, key: str) -> EditorTargetRef:
    target = inspector.resolve(key)
    if target is None:
        raise LookupError(f"editor authoring target no longer exists: {key}")
    if isinstance(target, Entity):
        return EditorTargetRef("entity", target.id)
    for index, item in enumerate(inspector.scene.objects):
        if item is target:
            return EditorTargetRef("object", index)
    raise LookupError(f"scene object is not indexable: {key}")


def _resolve_ref(inspector: SceneInspector, ref: EditorTargetRef) -> object:
    scene = inspector.scene
    if ref.kind == "entity":
        target = scene.ecs.entity(ref.value)
        if target is None:
            raise LookupError(f"missing ECS entity {ref.value} for editor authoring state")
        return target
    if ref.value >= len(scene.objects):
        raise LookupError(f"missing scene object index {ref.value} for editor authoring state")
    return scene.objects[ref.value]


def capture_editor_authoring(
    inspector: SceneInspector,
    selection: EditorSelectionModel,
    *,
    anchor_key: str | None = None,
) -> EditorAuthoringState:
    snapshot = selection.snapshot
    selected = tuple(_portable_ref(inspector, key) for key in snapshot.keys)
    by_key = {
        key: ref
        for key, ref in zip(snapshot.keys, selected, strict=True)
    }
    primary = None if snapshot.primary_key is None else by_key[snapshot.primary_key]
    anchor = None if anchor_key is None else _portable_ref(inspector, anchor_key)
    if anchor is not None and anchor not in set(selected):
        raise ValueError("authoring anchor must belong to the current selection")
    return EditorAuthoringState(selected, primary, anchor)


def restore_editor_authoring(
    inspector: SceneInspector,
    selection: EditorSelectionModel,
    state: EditorAuthoringState,
) -> tuple[object, ...]:
    """Restore multi-selection transactionally after resolving every portable target first."""

    resolved = tuple(_resolve_ref(inspector, ref) for ref in state.selected)
    primary = None if state.primary is None else _resolve_ref(inspector, state.primary)

    selection.clear()
    for target in resolved:
        selection.select(target, mode="add")
    if primary is not None:
        selection.select(primary, mode="add")
    return selection.selected_targets
