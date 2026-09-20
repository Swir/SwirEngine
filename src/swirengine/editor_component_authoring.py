from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import Literal

from .ecs import Entity
from .editor import HistoryEdit
from .editor_authoring import EditorAuthoringSession, EditorAuthoringTransaction


@dataclass(frozen=True, slots=True)
class EditorComponentMutation:
    """One reversible component add/remove mutation for a selected ECS entity."""

    target_key: str
    component: object
    action: Literal["add", "remove"]


@dataclass(frozen=True, slots=True)
class EditorComponentTransaction:
    """One creator-facing component gesture spanning one or more selected entities."""

    label: str
    mutations: tuple[EditorComponentMutation, ...]

    @property
    def edit_count(self) -> int:
        return len(self.mutations)


@dataclass(frozen=True, slots=True)
class EditorComponentResult:
    component_type: type[object]
    target_keys: tuple[str, ...]
    transaction: EditorComponentTransaction


CreatorTransaction = EditorAuthoringTransaction | EditorComponentTransaction


class EditorComponentAuthoringSession(EditorAuthoringSession):
    """Creator session that unifies property/gizmo and ECS component undo/redo.

    The existing ``EditorAuthoringSession`` remains source-compatible. This 2.1 session builds on
    its selection, asset assignment and gizmo APIs while adding transactional component authoring.
    Property/gizmo transactions and component mutations share one chronological creator history so
    Ctrl+Z behaves like a real editor rather than separate subsystem-specific undo stacks.
    """

    def __init__(self, inspector) -> None:  # type intentionally inherited from the stable session
        super().__init__(inspector)
        self._creator_undo: list[CreatorTransaction] = []
        self._creator_redo: list[CreatorTransaction] = []

    @property
    def creator_undo_history(self) -> tuple[CreatorTransaction, ...]:
        return tuple(self._creator_undo)

    @property
    def creator_redo_history(self) -> tuple[CreatorTransaction, ...]:
        return tuple(self._creator_redo)

    def add_component(self, component: object) -> EditorComponentResult:
        """Add one component type to every selected entity as a single creator action."""
        entities = self._selected_entities()
        component_type = type(component)
        for entity in entities:
            if entity.get(component_type) is not None:
                raise ValueError(
                    f"entity {entity.id} already has component {component_type.__name__}"
                )

        mutations = tuple(
            EditorComponentMutation(
                self.inspector.key_for(entity),
                deepcopy(component),
                "add",
            )
            for entity in entities
        )
        applied: list[Entity] = []
        try:
            for entity, mutation in zip(entities, mutations, strict=True):
                entity.add(deepcopy(mutation.component))
                applied.append(entity)
        except Exception:
            for entity in reversed(applied):
                entity.remove(component_type)
            raise

        transaction = EditorComponentTransaction(
            f"Add {component_type.__name__}",
            mutations,
        )
        self._record_creator(transaction)
        return EditorComponentResult(
            component_type,
            tuple(mutation.target_key for mutation in mutations),
            transaction,
        )

    def remove_component(self, component_type: type[object]) -> EditorComponentResult:
        """Remove one component type from every selected entity with lossless undo snapshots."""
        entities = self._selected_entities()
        mutations: list[EditorComponentMutation] = []
        for entity in entities:
            component = entity.get(component_type)
            if component is None:
                raise KeyError(
                    f"entity {entity.id} does not have component {component_type.__name__}"
                )
            mutations.append(
                EditorComponentMutation(
                    self.inspector.key_for(entity),
                    deepcopy(component),
                    "remove",
                )
            )

        removed: list[tuple[Entity, object]] = []
        try:
            for entity, mutation in zip(entities, mutations, strict=True):
                component = entity.remove(component_type)
                if component is None:
                    raise LookupError(component_type.__name__)
                removed.append((entity, mutation.component))
        except Exception:
            for entity, snapshot in reversed(removed):
                entity.add(deepcopy(snapshot))
            raise

        transaction = EditorComponentTransaction(
            f"Remove {component_type.__name__}",
            tuple(mutations),
        )
        self._record_creator(transaction)
        return EditorComponentResult(
            component_type,
            tuple(mutation.target_key for mutation in mutations),
            transaction,
        )

    def undo(self) -> HistoryEdit | CreatorTransaction | None:
        if not self._creator_undo:
            return self.inspector.undo()
        transaction = self._creator_undo[-1]
        if isinstance(transaction, EditorAuthoringTransaction):
            if not self._can_undo_history(transaction):
                self._creator_undo.clear()
                self._creator_redo.clear()
                return self.inspector.undo()
            self._creator_undo.pop()
            for _ in range(transaction.edit_count):
                self.inspector.undo()
        else:
            self._preflight_component_transaction(transaction, undo=True)
            self._creator_undo.pop()
            self._apply_component_transaction(transaction, undo=True)
        self._creator_redo.append(transaction)
        return transaction

    def redo(self) -> HistoryEdit | CreatorTransaction | None:
        if not self._creator_redo:
            return self.inspector.redo()
        transaction = self._creator_redo[-1]
        if isinstance(transaction, EditorAuthoringTransaction):
            if not self._can_redo_history(transaction):
                self._creator_undo.clear()
                self._creator_redo.clear()
                return self.inspector.redo()
            self._creator_redo.pop()
            for _ in range(transaction.edit_count):
                self.inspector.redo()
        else:
            self._preflight_component_transaction(transaction, undo=False)
            self._creator_redo.pop()
            self._apply_component_transaction(transaction, undo=False)
        self._creator_undo.append(transaction)
        return transaction

    def _record(
        self,
        label: str,
        edits: tuple[HistoryEdit, ...],
    ) -> EditorAuthoringTransaction:
        """Route inherited property/gizmo gestures into the unified creator history."""
        transaction = EditorAuthoringTransaction(label, edits)
        if edits:
            self._record_creator(transaction)
        return transaction

    def _record_creator(self, transaction: CreatorTransaction) -> None:
        self._creator_undo.append(transaction)
        self._creator_redo.clear()

    def _selected_entities(self) -> tuple[Entity, ...]:
        targets = self._require_selection()
        if not all(isinstance(target, Entity) for target in targets):
            raise TypeError("component authoring requires an Entity-only selection")
        return tuple(target for target in targets if isinstance(target, Entity))

    def _can_undo_history(self, transaction: EditorAuthoringTransaction) -> bool:
        count = transaction.edit_count
        history = self.inspector.undo_history
        return count <= len(history) and history[-count:] == transaction.edits

    def _can_redo_history(self, transaction: EditorAuthoringTransaction) -> bool:
        count = transaction.edit_count
        history = self.inspector.redo_history
        return count <= len(history) and history[-count:] == tuple(reversed(transaction.edits))

    def _preflight_component_transaction(
        self,
        transaction: EditorComponentTransaction,
        *,
        undo: bool,
    ) -> None:
        for mutation in transaction.mutations:
            target = self.inspector.resolve(mutation.target_key)
            if target is None:
                raise LookupError(f"component target no longer exists: {mutation.target_key}")
            if not isinstance(target, Entity):
                raise TypeError("component edit target is not an Entity")
            component_type = type(mutation.component)
            should_add = (mutation.action == "add" and not undo) or (
                mutation.action == "remove" and undo
            )
            existing = target.get(component_type)
            if should_add and existing is not None:
                raise ValueError(
                    f"entity {target.id} already has component {component_type.__name__}"
                )
            if not should_add and existing is None:
                raise LookupError(
                    f"entity {target.id} does not have component {component_type.__name__}"
                )

    def _apply_component_transaction(
        self,
        transaction: EditorComponentTransaction,
        *,
        undo: bool,
    ) -> None:
        ordered = tuple(reversed(transaction.mutations)) if undo else transaction.mutations
        for mutation in ordered:
            target = self.inspector.resolve(mutation.target_key)
            assert isinstance(target, Entity)
            component_type = type(mutation.component)
            should_add = (mutation.action == "add" and not undo) or (
                mutation.action == "remove" and undo
            )
            if should_add:
                target.add(deepcopy(mutation.component))
            else:
                removed = target.remove(component_type)
                if removed is None:
                    raise LookupError(component_type.__name__)
