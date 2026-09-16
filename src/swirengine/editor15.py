from __future__ import annotations

import copy
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, fields, is_dataclass
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any, Literal

from .assets import AssetManager
from .core.scene import Scene
from .editor_assets import classify_editor_asset
from .prefab import Prefab, PrefabInstance, PrefabOverrides, PrefabSelector


def _public_field_names(obj: object) -> tuple[str, ...]:
    if is_dataclass(obj):
        return tuple(field.name for field in fields(obj) if not field.name.startswith("_"))
    names: set[str] = set()
    namespace = getattr(obj, "__dict__", None)
    if isinstance(namespace, dict):
        names.update(
            name
            for name, value in namespace.items()
            if not name.startswith("_") and not callable(value)
        )
    for cls in type(obj).__mro__:
        for name, descriptor in vars(cls).items():
            if name.startswith("_") or isinstance(descriptor, property):
                continue
            if hasattr(descriptor, "__set__") and hasattr(obj, name):
                value = getattr(obj, name)
                if not callable(value):
                    names.add(name)
    return tuple(sorted(names))


def _safe_copy(value: Any, memo: dict[int, object] | None = None) -> Any:
    return copy.deepcopy(value, {} if memo is None else memo)


def _values_equal(left: Any, right: Any) -> bool:
    try:
        result = left == right
        return result if isinstance(result, bool) else bool(result)
    except Exception:  # noqa: BLE001 - editor values can define arbitrary equality.
        return left is right


def _normalize_relative_asset_path(value: str | Path) -> str:
    raw = str(value).strip()
    normalized = raw.replace("\\", "/")
    if not normalized or normalized == ".":
        raise ValueError("asset path cannot be empty")
    posix = PurePosixPath(normalized)
    windows = PureWindowsPath(raw)
    if (
        posix.is_absolute()
        or windows.is_absolute()
        or bool(windows.drive)
        or bool(windows.root)
        or ".." in posix.parts
    ):
        raise ValueError("asset path must stay project-relative")
    return posix.as_posix()


@dataclass(frozen=True, slots=True)
class EditorHistoryItem:
    sequence: int
    label: str
    kind: str
    affected: int


@dataclass(frozen=True, slots=True)
class EditorHistoryFrame:
    undo: tuple[EditorHistoryItem, ...]
    redo: tuple[EditorHistoryItem, ...]
    capacity: int

    @property
    def can_undo(self) -> bool:
        return bool(self.undo)

    @property
    def can_redo(self) -> bool:
        return bool(self.redo)


@dataclass(slots=True)
class _HistoryCommand:
    item: EditorHistoryItem
    undo: Callable[[], None]
    redo: Callable[[], None]


class EditorCommandHistory:
    """Bounded creator command history shared by additive 1.5 authoring tools."""

    def __init__(self, *, capacity: int = 128) -> None:
        if isinstance(capacity, bool) or capacity < 1:
            raise ValueError("history capacity must be at least 1")
        self.capacity = int(capacity)
        self._undo: list[_HistoryCommand] = []
        self._redo: list[_HistoryCommand] = []
        self._next_sequence = 1

    def frame(self) -> EditorHistoryFrame:
        return EditorHistoryFrame(
            tuple(command.item for command in self._undo),
            tuple(command.item for command in self._redo),
            self.capacity,
        )

    def clear(self) -> None:
        self._undo.clear()
        self._redo.clear()

    def record_applied(
        self,
        label: str,
        *,
        kind: str,
        affected: int,
        undo: Callable[[], None],
        redo: Callable[[], None],
    ) -> EditorHistoryItem:
        normalized_label = str(label).strip()
        normalized_kind = str(kind).strip()
        if not normalized_label:
            raise ValueError("history label cannot be empty")
        if not normalized_kind:
            raise ValueError("history kind cannot be empty")
        if isinstance(affected, bool) or affected < 1:
            raise ValueError("history affected count must be at least 1")
        if not callable(undo) or not callable(redo):
            raise TypeError("history undo/redo callbacks must be callable")
        item = EditorHistoryItem(
            self._next_sequence,
            normalized_label,
            normalized_kind,
            int(affected),
        )
        self._next_sequence += 1
        self._undo.append(_HistoryCommand(item, undo, redo))
        if len(self._undo) > self.capacity:
            del self._undo[: len(self._undo) - self.capacity]
        self._redo.clear()
        return item

    def undo(self) -> EditorHistoryItem:
        if not self._undo:
            raise RuntimeError("editor history has nothing to undo")
        command = self._undo[-1]
        command.undo()
        self._undo.pop()
        self._redo.append(command)
        return command.item

    def redo(self) -> EditorHistoryItem:
        if not self._redo:
            raise RuntimeError("editor history has nothing to redo")
        command = self._redo[-1]
        command.redo()
        self._redo.pop()
        self._undo.append(command)
        return command.item


@dataclass(frozen=True, slots=True)
class EditorPrefabFieldDiff:
    object_index: int
    object_name: str
    field: str
    template_value: Any
    instance_value: Any


@dataclass(frozen=True, slots=True)
class EditorPrefabDiff:
    prefab_name: str
    fields: tuple[EditorPrefabFieldDiff, ...]

    @property
    def empty(self) -> bool:
        return not self.fields

    @property
    def changed_fields(self) -> int:
        return len(self.fields)

    @property
    def changed_objects(self) -> int:
        return len({change.object_index for change in self.fields})


@dataclass(frozen=True, slots=True)
class EditorPrefabMutationResult:
    operation: Literal["apply", "revert"]
    changed: EditorPrefabDiff
    remaining: EditorPrefabDiff

    @property
    def changed_fields(self) -> int:
        return self.changed.changed_fields


@dataclass(frozen=True, slots=True)
class EditorPrefabVariant:
    """Materialized prefab variant that has no runtime dependency on its source document."""

    name: str
    source_name: str
    changes: EditorPrefabDiff
    _prefab: Prefab

    def templates(self) -> tuple[object, ...]:
        return self._prefab.templates()

    def build(self) -> Prefab:
        return Prefab(*self._prefab.templates(), name=self.name)

    def instantiate(
        self,
        scene: Scene | None = None,
        *,
        overrides: PrefabOverrides | None = None,
    ) -> PrefabInstance:
        return self._prefab.instantiate(scene, overrides=overrides)


class EditorPrefabDocument:
    """Non-destructive 1.5 authoring document layered over the stable :class:`Prefab`.

    The source ``Prefab`` is never mutated. Applying instance values changes only this document;
    ``build()`` materializes a new stable prefab when the creator chooses to persist it.
    """

    def __init__(
        self,
        prefab: Prefab,
        *,
        history: EditorCommandHistory | None = None,
    ) -> None:
        if not isinstance(prefab, Prefab):
            raise TypeError("prefab must be a Prefab")
        self.name = prefab.name
        self._templates = prefab.templates()
        self.history = history or EditorCommandHistory()

    @property
    def size(self) -> int:
        return len(self._templates)

    def templates(self) -> tuple[object, ...]:
        return _safe_copy(self._templates)

    def build(self) -> Prefab:
        return Prefab(*self._templates, name=self.name)

    def instantiate(
        self,
        scene: Scene | None = None,
        *,
        overrides: PrefabOverrides | None = None,
    ) -> PrefabInstance:
        return self.build().instantiate(scene, overrides=overrides)

    def _validate_instance(self, instance: PrefabInstance) -> tuple[object, ...]:
        if not isinstance(instance, PrefabInstance):
            raise TypeError("instance must be a PrefabInstance")
        objects = instance.objects
        if len(objects) != self.size:
            raise ValueError(
                f"prefab instance size mismatch: expected {self.size}, got {len(objects)}"
            )
        for index, (template, obj) in enumerate(zip(self._templates, objects, strict=True)):
            if type(template) is not type(obj):
                raise TypeError(
                    f"prefab instance object {index} has type {type(obj).__name__}; "
                    f"expected {type(template).__name__}"
                )
        return objects

    @staticmethod
    def _object_name(obj: object, index: int) -> str:
        name = getattr(obj, "name", "")
        return str(name) if str(name) else f"#{index}"

    def diff(self, instance: PrefabInstance) -> EditorPrefabDiff:
        objects = self._validate_instance(instance)
        template_to_instance = {
            id(template): obj
            for template, obj in zip(self._templates, objects, strict=True)
        }
        changes: list[EditorPrefabFieldDiff] = []
        for index, (template, obj) in enumerate(zip(self._templates, objects, strict=True)):
            for field_name in _public_field_names(template):
                if not hasattr(obj, field_name):
                    raise TypeError(
                        f"prefab instance object {index} is missing field {field_name!r}"
                    )
                expected = _safe_copy(getattr(template, field_name), template_to_instance)
                actual = getattr(obj, field_name)
                if _values_equal(expected, actual):
                    continue
                changes.append(
                    EditorPrefabFieldDiff(
                        index,
                        self._object_name(obj, index),
                        field_name,
                        _safe_copy(getattr(template, field_name)),
                        _safe_copy(actual),
                    )
                )
        return EditorPrefabDiff(self.name, tuple(changes))

    def _selector_indexes(
        self,
        selectors: Iterable[PrefabSelector] | None,
        objects: tuple[object, ...],
    ) -> set[int] | None:
        if selectors is None:
            return None
        resolved: set[int] = set()
        for selector in selectors:
            if isinstance(selector, bool):
                raise TypeError("prefab selector must be an integer index or object name")
            if isinstance(selector, int):
                if selector < 0 or selector >= len(objects):
                    raise IndexError(f"prefab selector index {selector} is out of range")
                resolved.add(selector)
                continue
            if not isinstance(selector, str):
                raise TypeError("prefab selector must be an integer index or object name")
            matches = [
                index
                for index, obj in enumerate(objects)
                if str(getattr(obj, "name", "")) == selector
            ]
            if not matches:
                raise KeyError(f"prefab object name {selector!r} was not found")
            if len(matches) > 1:
                raise KeyError(f"prefab object name {selector!r} is ambiguous")
            resolved.add(matches[0])
        return resolved

    @staticmethod
    def _property_names(properties: Iterable[str] | None) -> set[str] | None:
        if properties is None:
            return None
        result: set[str] = set()
        for name in properties:
            normalized = str(name).strip()
            if not normalized or normalized.startswith("_"):
                raise ValueError("prefab property names must be non-private and non-empty")
            result.add(normalized)
        return result

    def _selected_diff(
        self,
        instance: PrefabInstance,
        *,
        selectors: Iterable[PrefabSelector] | None,
        properties: Iterable[str] | None,
    ) -> EditorPrefabDiff:
        objects = self._validate_instance(instance)
        indexes = self._selector_indexes(selectors, objects)
        names = self._property_names(properties)
        current = self.diff(instance)
        selected = tuple(
            change
            for change in current.fields
            if (indexes is None or change.object_index in indexes)
            and (names is None or change.field in names)
        )
        return EditorPrefabDiff(self.name, selected)

    def _restore_templates(self, snapshot: tuple[object, ...]) -> None:
        self._templates = _safe_copy(snapshot)

    @staticmethod
    def _restore_objects(
        targets: tuple[object, ...],
        snapshot: tuple[object, ...],
    ) -> None:
        if len(targets) != len(snapshot):
            raise RuntimeError("cannot restore prefab instance after its structure changed")
        memo = {id(source): target for source, target in zip(snapshot, targets, strict=True)}
        staged: list[tuple[object, str, Any]] = []
        for index, (target, source) in enumerate(zip(targets, snapshot, strict=True)):
            if type(target) is not type(source):
                raise RuntimeError(f"cannot restore prefab instance object {index}: type changed")
            for field_name in _public_field_names(source):
                if not hasattr(target, field_name):
                    raise RuntimeError(
                        f"cannot restore prefab instance object {index}: "
                        f"missing field {field_name!r}"
                    )
                staged.append(
                    (target, field_name, _safe_copy(getattr(source, field_name), memo))
                )
        for target, field_name, value in staged:
            setattr(target, field_name, value)

    def apply(
        self,
        instance: PrefabInstance,
        *,
        selectors: Iterable[PrefabSelector] | None = None,
        properties: Iterable[str] | None = None,
        label: str = "Apply prefab instance",
    ) -> EditorPrefabMutationResult:
        objects = self._validate_instance(instance)
        selected = self._selected_diff(
            instance,
            selectors=selectors,
            properties=properties,
        )
        if selected.empty:
            return EditorPrefabMutationResult("apply", selected, self.diff(instance))

        before = _safe_copy(self._templates)
        instance_to_template = {
            id(obj): template
            for template, obj in zip(self._templates, objects, strict=True)
        }
        try:
            for change in selected.fields:
                source = objects[change.object_index]
                target = self._templates[change.object_index]
                setattr(
                    target,
                    change.field,
                    _safe_copy(getattr(source, change.field), instance_to_template),
                )
        except Exception:
            self._restore_templates(before)
            raise
        after = _safe_copy(self._templates)
        self.history.record_applied(
            label,
            kind="prefab_apply",
            affected=selected.changed_fields,
            undo=lambda: self._restore_templates(before),
            redo=lambda: self._restore_templates(after),
        )
        return EditorPrefabMutationResult("apply", selected, self.diff(instance))

    def revert(
        self,
        instance: PrefabInstance,
        *,
        selectors: Iterable[PrefabSelector] | None = None,
        properties: Iterable[str] | None = None,
        label: str = "Revert prefab instance",
    ) -> EditorPrefabMutationResult:
        objects = self._validate_instance(instance)
        selected = self._selected_diff(
            instance,
            selectors=selectors,
            properties=properties,
        )
        if selected.empty:
            return EditorPrefabMutationResult("revert", selected, self.diff(instance))

        before = _safe_copy(objects)
        template_to_instance = {
            id(template): obj
            for template, obj in zip(self._templates, objects, strict=True)
        }
        try:
            for change in selected.fields:
                source = self._templates[change.object_index]
                target = objects[change.object_index]
                setattr(
                    target,
                    change.field,
                    _safe_copy(getattr(source, change.field), template_to_instance),
                )
        except Exception:
            self._restore_objects(objects, before)
            raise
        after = _safe_copy(objects)
        self.history.record_applied(
            label,
            kind="prefab_revert",
            affected=selected.changed_fields,
            undo=lambda: self._restore_objects(objects, before),
            redo=lambda: self._restore_objects(objects, after),
        )
        return EditorPrefabMutationResult("revert", selected, self.diff(instance))

    def create_variant(self, name: str, instance: PrefabInstance) -> EditorPrefabVariant:
        normalized_name = str(name).strip()
        if not normalized_name:
            raise ValueError("variant name cannot be empty")
        if "/" in normalized_name or "\\" in normalized_name:
            raise ValueError("variant name must not contain path separators")
        objects = self._validate_instance(instance)
        changes = self.diff(instance)
        return EditorPrefabVariant(
            normalized_name,
            self.name,
            changes,
            Prefab(*objects, name=normalized_name),
        )


@dataclass(frozen=True, slots=True)
class EditorBatchFieldChange:
    target_index: int
    target_name: str
    field: str
    before: Any
    after: Any


@dataclass(frozen=True, slots=True)
class EditorBatchPlan:
    label: str
    targets: tuple[object, ...]
    changes: tuple[EditorBatchFieldChange, ...]

    @property
    def affected_targets(self) -> int:
        return len({change.target_index for change in self.changes})

    @property
    def changed_fields(self) -> int:
        return len(self.changes)


@dataclass(frozen=True, slots=True)
class EditorBatchResult:
    label: str
    affected_targets: int
    changed_fields: int


class EditorBatchEditor:
    """Previewable, stale-safe and atomic batch property editing."""

    def __init__(self, *, history: EditorCommandHistory | None = None) -> None:
        self.history = history or EditorCommandHistory()

    @staticmethod
    def _target_name(target: object, index: int) -> str:
        name = getattr(target, "name", "")
        return str(name) if str(name) else f"#{index}"

    @staticmethod
    def _validate_writable(target: object, field_name: str) -> None:
        if not field_name or field_name.startswith("_"):
            raise ValueError("batch fields must be non-private and non-empty")
        if not hasattr(target, field_name):
            raise AttributeError(f"{type(target).__name__} has no field {field_name!r}")
        descriptor = getattr(type(target), field_name, None)
        if isinstance(descriptor, property) and descriptor.fset is None:
            raise AttributeError(
                f"{type(target).__name__}.{field_name} is a read-only property"
            )
        if callable(getattr(target, field_name)):
            raise TypeError(f"{type(target).__name__}.{field_name} is callable")

    def preview(
        self,
        targets: Iterable[object],
        updates: Mapping[str, Any],
        *,
        label: str = "Batch edit",
    ) -> EditorBatchPlan:
        resolved_targets = tuple(targets)
        if not resolved_targets:
            raise ValueError("batch edit requires at least one target")
        if not updates:
            raise ValueError("batch edit requires at least one property")
        normalized_label = str(label).strip()
        if not normalized_label:
            raise ValueError("batch edit label cannot be empty")

        if not all(isinstance(name, str) for name in updates):
            raise TypeError("batch property names must be strings")
        field_names = tuple(sorted(updates))
        changes: list[EditorBatchFieldChange] = []
        for index, target in enumerate(resolved_targets):
            for field_name in field_names:
                self._validate_writable(target, field_name)
                before = _safe_copy(getattr(target, field_name))
                after = _safe_copy(updates[field_name])
                if _values_equal(before, after):
                    continue
                changes.append(
                    EditorBatchFieldChange(
                        index,
                        self._target_name(target, index),
                        field_name,
                        before,
                        after,
                    )
                )
        return EditorBatchPlan(normalized_label, resolved_targets, tuple(changes))

    @staticmethod
    def _write(
        targets: tuple[object, ...],
        changes: Sequence[EditorBatchFieldChange],
        *,
        use_after: bool,
        verify_before: bool,
    ) -> None:
        applied: list[EditorBatchFieldChange] = []
        try:
            for change in changes:
                target = targets[change.target_index]
                current = getattr(target, change.field)
                expected = change.before if use_after else change.after
                if verify_before and not _values_equal(current, expected):
                    raise RuntimeError(
                        f"stale batch plan for {change.target_name}.{change.field}: "
                        "target changed after preview"
                    )
                value = change.after if use_after else change.before
                setattr(target, change.field, _safe_copy(value))
                applied.append(change)
        except Exception:
            for change in reversed(applied):
                target = targets[change.target_index]
                rollback = change.before if use_after else change.after
                setattr(target, change.field, _safe_copy(rollback))
            raise

    def commit(self, plan: EditorBatchPlan) -> EditorBatchResult:
        if not isinstance(plan, EditorBatchPlan):
            raise TypeError("plan must be an EditorBatchPlan")
        if not plan.changes:
            return EditorBatchResult(plan.label, 0, 0)

        # Check every source value first so stale plans fail without partial writes.
        for change in plan.changes:
            target = plan.targets[change.target_index]
            if not _values_equal(getattr(target, change.field), change.before):
                raise RuntimeError(
                    f"stale batch plan for {change.target_name}.{change.field}: "
                    "target changed after preview"
                )

        self._write(plan.targets, plan.changes, use_after=True, verify_before=False)
        self.history.record_applied(
            plan.label,
            kind="batch_edit",
            affected=plan.changed_fields,
            undo=lambda: self._write(
                plan.targets,
                plan.changes,
                use_after=False,
                verify_before=False,
            ),
            redo=lambda: self._write(
                plan.targets,
                plan.changes,
                use_after=True,
                verify_before=False,
            ),
        )
        return EditorBatchResult(
            plan.label,
            plan.affected_targets,
            plan.changed_fields,
        )


@dataclass(frozen=True, slots=True)
class EditorAssetReference:
    object_index: int
    object_name: str
    field: str
    path: str
    kind: str
    status: Literal["ok", "missing", "unsafe"]


@dataclass(frozen=True, slots=True)
class EditorAssetAuditFrame:
    references: tuple[EditorAssetReference, ...]
    missing_aliases: tuple[str, ...]
    unused_assets: tuple[str, ...]

    @property
    def missing(self) -> tuple[EditorAssetReference, ...]:
        return tuple(reference for reference in self.references if reference.status == "missing")

    @property
    def unsafe(self) -> tuple[EditorAssetReference, ...]:
        return tuple(reference for reference in self.references if reference.status == "unsafe")

    @property
    def healthy(self) -> bool:
        return not self.missing and not self.unsafe and not self.missing_aliases


class EditorAssetAuditor:
    """Scan creator objects for portable asset references and missing project files."""

    def __init__(self, manager: AssetManager) -> None:
        if not isinstance(manager, AssetManager):
            raise TypeError("manager must be an AssetManager")
        self.manager = manager

    @staticmethod
    def _walk_values(value: Any, field: str) -> Iterable[tuple[str, str | Path]]:
        if isinstance(value, (str, Path)):
            yield field, value
            return
        if isinstance(value, Mapping):
            for key in sorted(value, key=lambda item: str(item)):
                yield from EditorAssetAuditor._walk_values(value[key], f"{field}[{key!r}]")
            return
        if isinstance(value, (list, tuple)):
            for index, item in enumerate(value):
                yield from EditorAssetAuditor._walk_values(item, f"{field}[{index}]")
            return
        if isinstance(value, (set, frozenset)):
            for index, item in enumerate(sorted(value, key=repr)):
                yield from EditorAssetAuditor._walk_values(item, f"{field}[{index}]")

    def scan(self, objects: Iterable[object]) -> EditorAssetAuditFrame:
        diagnostics = self.manager.diagnostics()
        known = {info.relative_path.as_posix() for info in diagnostics.files}
        root = diagnostics.root.expanduser().resolve()
        aliases = self.manager.aliases()
        references: list[EditorAssetReference] = []
        referenced: set[str] = set()

        for object_index, obj in enumerate(tuple(objects)):
            object_name = str(getattr(obj, "name", "")) or f"#{object_index}"
            for field_name in _public_field_names(obj):
                value = getattr(obj, field_name)
                for value_field, candidate in self._walk_values(value, field_name):
                    raw = str(candidate).strip()
                    if not raw:
                        continue
                    if raw in aliases:
                        resolved = aliases[raw].expanduser().resolve()
                        try:
                            relative = resolved.relative_to(root).as_posix()
                        except ValueError:
                            references.append(
                                EditorAssetReference(
                                    object_index,
                                    object_name,
                                    value_field,
                                    raw,
                                    "alias",
                                    "unsafe",
                                )
                            )
                            continue
                        status: Literal["ok", "missing", "unsafe"] = (
                            "ok" if resolved.is_file() else "missing"
                        )
                        references.append(
                            EditorAssetReference(
                                object_index,
                                object_name,
                                value_field,
                                relative,
                                classify_editor_asset(relative),
                                status,
                            )
                        )
                        referenced.add(relative)
                        continue

                    kind = classify_editor_asset(raw)
                    normalized_candidate: str | None = None
                    try:
                        normalized_candidate = _normalize_relative_asset_path(raw)
                    except ValueError:
                        if kind == "other":
                            continue
                        references.append(
                            EditorAssetReference(
                                object_index,
                                object_name,
                                value_field,
                                raw,
                                kind,
                                "unsafe",
                            )
                        )
                        continue

                    if normalized_candidate not in known and kind == "other":
                        continue
                    status = "ok" if normalized_candidate in known else "missing"
                    references.append(
                        EditorAssetReference(
                            object_index,
                            object_name,
                            value_field,
                            normalized_candidate,
                            classify_editor_asset(normalized_candidate),
                            status,
                        )
                    )
                    referenced.add(normalized_candidate)

        references.sort(
            key=lambda item: (
                item.status != "unsafe",
                item.status != "missing",
                item.object_index,
                item.field,
                item.path.casefold(),
            )
        )
        return EditorAssetAuditFrame(
            tuple(references),
            diagnostics.missing_aliases,
            tuple(sorted(known - referenced, key=str.casefold)),
        )


__all__ = [
    "EditorAssetAuditFrame",
    "EditorAssetAuditor",
    "EditorAssetReference",
    "EditorBatchEditor",
    "EditorBatchFieldChange",
    "EditorBatchPlan",
    "EditorBatchResult",
    "EditorCommandHistory",
    "EditorHistoryFrame",
    "EditorHistoryItem",
    "EditorPrefabDiff",
    "EditorPrefabDocument",
    "EditorPrefabFieldDiff",
    "EditorPrefabMutationResult",
    "EditorPrefabVariant",
]
