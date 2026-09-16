from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import Literal

from .editor import HistoryEdit, PropertyEdit, SceneInspector
from .editor_gizmo import EditorTransformGizmo, GizmoApplyResult

SelectionMode = Literal["replace", "add", "toggle"]


@dataclass(frozen=True, slots=True)
class EditorSelectionSnapshot:
    """Ordered multi-selection with one backwards-compatible primary target."""

    keys: tuple[str, ...]
    primary_key: str | None

    @property
    def count(self) -> int:
        return len(self.keys)


@dataclass(frozen=True, slots=True)
class EditorAuthoringTransaction:
    """One creator action represented by one or more legacy inspector history edits."""

    label: str
    edits: tuple[HistoryEdit, ...]

    @property
    def edit_count(self) -> int:
        return len(self.edits)


@dataclass(frozen=True, slots=True)
class EditorBatchPropertyResult:
    property_name: str
    value: object
    target_keys: tuple[str, ...]
    transaction: EditorAuthoringTransaction


@dataclass(frozen=True, slots=True)
class EditorMultiGizmoResult:
    mode: str
    axis: str
    results: tuple[GizmoApplyResult, ...]
    transaction: EditorAuthoringTransaction


class EditorSelectionModel:
    """Toolkit-neutral multi-selection layered over ``SceneInspector``.

    The last/primary item is mirrored into ``SceneInspector.select``. Existing editor front-ends
    therefore keep seeing one selected target while 1.4-aware authoring tools can operate on the
    entire ordered selection.
    """

    def __init__(self, inspector: SceneInspector) -> None:
        self.inspector = inspector
        self._keys: list[str] = []
        if inspector.selected_key is not None:
            self._keys.append(inspector.selected_key)

    @property
    def snapshot(self) -> EditorSelectionSnapshot:
        self._drop_stale()
        primary = self._keys[-1] if self._keys else None
        return EditorSelectionSnapshot(tuple(self._keys), primary)

    @property
    def selected_targets(self) -> tuple[object, ...]:
        self._drop_stale()
        return tuple(
            target
            for key in self._keys
            if (target := self.inspector.resolve(key)) is not None
        )

    @property
    def primary_target(self) -> object | None:
        snapshot = self.snapshot
        return None if snapshot.primary_key is None else self.inspector.resolve(snapshot.primary_key)

    def clear(self) -> EditorSelectionSnapshot:
        self._keys.clear()
        self.inspector.select(None)
        return self.snapshot

    def select(
        self,
        target_or_key: object | str,
        *,
        mode: SelectionMode = "replace",
    ) -> EditorSelectionSnapshot:
        if mode not in {"replace", "add", "toggle"}:
            raise ValueError(f"unsupported selection mode {mode!r}")
        key = self._key(target_or_key)
        self._drop_stale()

        if mode == "replace":
            self._keys[:] = [key]
        elif mode == "add":
            if key in self._keys:
                self._keys.remove(key)
            self._keys.append(key)
        elif key in self._keys:
            self._keys.remove(key)
        else:
            self._keys.append(key)

        self._sync_primary()
        return self.snapshot

    def select_range(
        self,
        anchor: object | str,
        target: object | str,
        *,
        additive: bool = False,
    ) -> EditorSelectionSnapshot:
        """Select an inclusive visual-hierarchy range in deterministic depth-first order."""

        anchor_key = self._key(anchor)
        target_key = self._key(target)
        ordered = [row.key for row in self.inspector.hierarchy()]
        try:
            left = ordered.index(anchor_key)
            right = ordered.index(target_key)
        except ValueError as exc:
            raise LookupError("range endpoint is not present in the current hierarchy") from exc
        start, stop = sorted((left, right))
        chosen = ordered[start : stop + 1]

        if additive:
            existing = set(self._keys)
            for key in chosen:
                if key not in existing:
                    self._keys.append(key)
                    existing.add(key)
        else:
            self._keys[:] = chosen

        # Make the requested target, not merely the highest hierarchy row, the primary selection.
        if target_key in self._keys:
            self._keys.remove(target_key)
            self._keys.append(target_key)
        self._sync_primary()
        return self.snapshot

    def _key(self, target_or_key: object | str) -> str:
        if isinstance(target_or_key, str):
            if self.inspector.resolve(target_or_key) is None:
                raise KeyError(target_or_key)
            return target_or_key
        return self.inspector.key_for(target_or_key)

    def _drop_stale(self) -> None:
        current = [key for key in self._keys if self.inspector.resolve(key) is not None]
        if current == self._keys:
            return
        self._keys[:] = current
        self._sync_primary()

    def _sync_primary(self) -> None:
        if not self._keys:
            self.inspector.select(None)
            return
        self.inspector.select(self._keys[-1])


class EditorAuthoringSession:
    """High-level 1.4 authoring controller for multi-selection and grouped edits.

    Group edits continue to use ``SceneInspector`` as the authoritative mutation/history layer. The
    session records the exact contiguous history span generated by one creator gesture, allowing its
    ``undo``/``redo`` methods to replay that span as one logical action. If unrelated legacy edits are
    interleaved, the session detects the mismatch and safely falls back to a single inspector step.
    """

    def __init__(self, inspector: SceneInspector) -> None:
        self.inspector = inspector
        self.selection = EditorSelectionModel(inspector)
        self.gizmo = EditorTransformGizmo(inspector)
        self._undo_transactions: list[EditorAuthoringTransaction] = []
        self._redo_transactions: list[EditorAuthoringTransaction] = []

    @property
    def selection_snapshot(self) -> EditorSelectionSnapshot:
        return self.selection.snapshot

    @property
    def selected_targets(self) -> tuple[object, ...]:
        return self.selection.selected_targets

    def select(
        self,
        target_or_key: object | str,
        *,
        mode: SelectionMode = "replace",
    ) -> EditorSelectionSnapshot:
        return self.selection.select(target_or_key, mode=mode)

    def select_range(
        self,
        anchor: object | str,
        target: object | str,
        *,
        additive: bool = False,
    ) -> EditorSelectionSnapshot:
        return self.selection.select_range(anchor, target, additive=additive)

    def clear_selection(self) -> EditorSelectionSnapshot:
        return self.selection.clear()

    def set_property(self, name: str, value: object) -> EditorBatchPropertyResult:
        """Set one editable property across the current selection as one logical transaction."""

        targets = self._require_selection()
        for target in targets:
            snapshot = self.inspector.inspect(target)
            assert snapshot is not None
            field = next((item for item in snapshot.fields if item.name == name), None)
            if field is None:
                raise AttributeError(name)
            if not field.editable:
                raise AttributeError(f"property {name!r} is read-only")

        edits = tuple(
            self.inspector.set_property(name, deepcopy(value), target=target)
            for target in targets
        )
        transaction = self._record(f"Set {name}", edits)
        return EditorBatchPropertyResult(
            name,
            deepcopy(value),
            tuple(edit.target_key for edit in edits),
            transaction,
        )

    def apply_gizmo(
        self,
        mode: str,
        axis: str,
        delta: float,
        *,
        snap: float | None = None,
    ) -> EditorMultiGizmoResult:
        """Apply the same transform gesture to every selected target.

        Every target is preflighted before mutation so unsupported mixed selections fail before the
        first edit is committed.
        """

        targets = self._require_selection()
        planned: list[tuple[object, str, object, object]] = []
        for target in targets:
            property_name, before, after = self.gizmo._transform_value(
                target,
                mode,
                axis,
                float(delta),
                None if snap is None else float(snap),
            )
            planned.append((target, property_name, before, after))

        results: list[GizmoApplyResult] = []
        edits: list[PropertyEdit] = []
        for target, property_name, before, after in planned:
            edit = self.inspector.set_property(property_name, after, target=target)
            edits.append(edit)
            results.append(
                GizmoApplyResult(
                    edit.target_key,
                    mode,
                    axis,
                    deepcopy(before),
                    deepcopy(after),
                    edit,
                )
            )
        transaction = self._record(f"{mode.title()} selection", tuple(edits))
        return EditorMultiGizmoResult(mode, axis, tuple(results), transaction)

    def undo(self) -> HistoryEdit | EditorAuthoringTransaction | None:
        if self._undo_transactions:
            transaction = self._undo_transactions[-1]
            count = transaction.edit_count
            history = self.inspector.undo_history
            if count <= len(history) and history[-count:] == transaction.edits:
                self._undo_transactions.pop()
                for _ in range(count):
                    self.inspector.undo()
                self._redo_transactions.append(transaction)
                return transaction
        # A legacy edit was interleaved; do not guess transaction boundaries.
        self._redo_transactions.clear()
        self._undo_transactions.clear()
        return self.inspector.undo()

    def redo(self) -> HistoryEdit | EditorAuthoringTransaction | None:
        if self._redo_transactions:
            transaction = self._redo_transactions[-1]
            count = transaction.edit_count
            history = self.inspector.redo_history
            expected = tuple(reversed(transaction.edits))
            if count <= len(history) and history[-count:] == expected:
                self._redo_transactions.pop()
                for _ in range(count):
                    self.inspector.redo()
                self._undo_transactions.append(transaction)
                return transaction
        self._redo_transactions.clear()
        self._undo_transactions.clear()
        return self.inspector.redo()

    def _record(
        self,
        label: str,
        edits: tuple[HistoryEdit, ...],
    ) -> EditorAuthoringTransaction:
        transaction = EditorAuthoringTransaction(label, edits)
        if edits:
            self._undo_transactions.append(transaction)
            self._redo_transactions.clear()
        return transaction

    def _require_selection(self) -> tuple[object, ...]:
        targets = self.selected_targets
        if not targets:
            raise RuntimeError("no editor targets selected")
        if len(targets) > self.inspector.history_limit:
            raise RuntimeError("selection exceeds the inspector history limit for one grouped edit")
        return targets
