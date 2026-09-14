from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Any, TypeVar

T = TypeVar("T")
SystemCallable = Callable[["ECSWorld", float], None]


@dataclass(slots=True)
class ECSDiagnostics:
    """Deterministic counters for ECS query/update work."""

    query_calls: int = 0
    query_candidates: int = 0
    query_matches: int = 0
    system_updates: int = 0

    def reset(self) -> None:
        self.query_calls = 0
        self.query_candidates = 0
        self.query_matches = 0
        self.system_updates = 0


class Entity:
    """Lightweight component container owned by an :class:`ECSWorld`."""

    __slots__ = ("_components", "_world", "enabled", "id", "name", "tags")

    def __init__(
        self,
        entity_id: int,
        *,
        name: str = "",
        enabled: bool = True,
        tags: Iterable[str] = (),
        world: ECSWorld | None = None,
    ) -> None:
        self.id = int(entity_id)
        self.name = str(name)
        self.enabled = bool(enabled)
        self.tags = set(tags)
        self._components: dict[type[object], object] = {}
        self._world = world

    @property
    def components(self) -> tuple[object, ...]:
        return tuple(self._components.values())

    def add(self, component: T, *, replace: bool = False) -> T:
        """Attach a component and return it for fluent creator-facing setup."""
        component_type = type(component)
        previous = self._components.get(component_type)
        if previous is not None and not replace:
            raise ValueError(f"entity {self.id} already has component {component_type.__name__}")
        self._components[component_type] = component
        if previous is None and self._world is not None:
            self._world._index_component(self.id, component_type)
        return component

    def set(self, component: T) -> T:
        """Attach or replace the component with the same concrete type."""
        return self.add(component, replace=True)

    def get(self, component_type: type[T]) -> T | None:
        exact = self._components.get(component_type)
        if exact is not None:
            return exact  # type: ignore[return-value]
        for component in self._components.values():
            if isinstance(component, component_type):
                return component
        return None

    def require(self, component_type: type[T]) -> T:
        component = self.get(component_type)
        if component is None:
            raise KeyError(f"entity {self.id} does not have component {component_type.__name__}")
        return component

    def has(self, *component_types: type[object]) -> bool:
        return all(self.get(component_type) is not None for component_type in component_types)

    def remove(self, component_type: type[T]) -> T | None:
        exact = self._components.pop(component_type, None)
        if exact is not None:
            if self._world is not None:
                self._world._unindex_component(self.id, type(exact))
            return exact  # type: ignore[return-value]
        for stored_type, component in tuple(self._components.items()):
            if isinstance(component, component_type):
                del self._components[stored_type]
                if self._world is not None:
                    self._world._unindex_component(self.id, stored_type)
                return component
        return None

    def destroy(self) -> bool:
        """Destroy this entity through its owning world, when still attached."""
        if self._world is None:
            return False
        return self._world.destroy(self)


@dataclass(frozen=True, slots=True)
class _SystemEntry:
    priority: int
    order: int
    system: object


class ECSWorld:
    """Deterministic entity/component/system runtime with indexed component queries.

    Exact component membership is indexed as entities change. Queries use the smallest
    compatible component index as their candidate set, while preserving the public
    subclass-aware component semantics and deterministic entity insertion order.
    """

    def __init__(self) -> None:
        self._entities: dict[int, Entity] = {}
        self._component_index: dict[type[object], set[int]] = {}
        self._systems: list[_SystemEntry] = []
        self._ordered_system_cache: tuple[_SystemEntry, ...] = ()
        self._systems_dirty = False
        self._next_entity_id = 1
        self._next_system_order = 0
        self.diagnostics = ECSDiagnostics()

    @property
    def entities(self) -> tuple[Entity, ...]:
        return tuple(self._entities.values())

    @property
    def systems(self) -> tuple[object, ...]:
        return tuple(entry.system for entry in self._ordered_systems())

    def _index_component(self, entity_id: int, component_type: type[object]) -> None:
        self._component_index.setdefault(component_type, set()).add(entity_id)

    def _unindex_component(self, entity_id: int, component_type: type[object]) -> None:
        entity_ids = self._component_index.get(component_type)
        if entity_ids is None:
            return
        entity_ids.discard(entity_id)
        if not entity_ids:
            del self._component_index[component_type]

    def create_entity(
        self,
        *,
        name: str = "",
        enabled: bool = True,
        tags: Iterable[str] = (),
        entity_id: int | None = None,
    ) -> Entity:
        """Create an entity, optionally restoring a specific stable ID from persistence."""
        if entity_id is None:
            resolved_id = self._next_entity_id
        else:
            resolved_id = int(entity_id)
            if resolved_id < 1:
                raise ValueError("entity_id must be >= 1")
            if resolved_id in self._entities:
                raise ValueError(f"entity id {resolved_id} already exists")

        entity = Entity(
            resolved_id,
            name=name,
            enabled=enabled,
            tags=tags,
            world=self,
        )
        self._entities[entity.id] = entity
        self._next_entity_id = max(self._next_entity_id, entity.id + 1)
        return entity

    def compose_entity(
        self,
        *components: object,
        name: str = "",
        enabled: bool = True,
        tags: Iterable[str] = (),
    ) -> Entity:
        """Create an entity and attach a component bundle in one creator-facing call."""
        entity = self.create_entity(name=name, enabled=enabled, tags=tags)
        try:
            for component in components:
                entity.add(component)
        except ValueError:
            self.destroy(entity)
            raise
        return entity

    def entity(self, entity_id: int) -> Entity | None:
        return self._entities.get(int(entity_id))

    def find(self, name: str) -> Entity | None:
        return next((entity for entity in self._entities.values() if entity.name == name), None)

    def destroy(self, entity: Entity | int) -> bool:
        entity_id = entity.id if isinstance(entity, Entity) else int(entity)
        existing = self._entities.get(entity_id)
        if existing is None:
            return False
        if isinstance(entity, Entity) and existing is not entity:
            return False
        for component_type in tuple(existing._components):
            self._unindex_component(entity_id, component_type)
        del self._entities[entity_id]
        existing._world = None
        return True

    def clear(self) -> None:
        for entity in self._entities.values():
            entity._world = None
        self._entities.clear()
        self._component_index.clear()

    def _candidate_ids(self, component_types: tuple[type[object], ...]) -> set[int] | None:
        if not component_types:
            return None
        candidate_groups: list[set[int]] = []
        for requested_type in component_types:
            compatible: set[int] = set()
            for stored_type, entity_ids in self._component_index.items():
                if issubclass(stored_type, requested_type):
                    compatible.update(entity_ids)
            if not compatible:
                return set()
            candidate_groups.append(compatible)
        candidate_groups.sort(key=len)
        candidates = candidate_groups[0].copy()
        for group in candidate_groups[1:]:
            candidates.intersection_update(group)
            if not candidates:
                break
        return candidates

    def query(
        self,
        *component_types: type[object],
        enabled_only: bool = True,
        tags: Iterable[str] = (),
    ) -> tuple[Entity, ...]:
        required_tags = frozenset(tags)
        candidates = self._candidate_ids(component_types)
        self.diagnostics.query_calls += 1
        if candidates is None:
            candidate_count = len(self._entities)
        else:
            candidate_count = len(candidates)
        self.diagnostics.query_candidates += candidate_count
        if not candidate_count:
            return ()

        result = tuple(
            entity
            for entity in self._entities.values()
            if (candidates is None or entity.id in candidates)
            and (entity.enabled or not enabled_only)
            and required_tags.issubset(entity.tags)
        )
        self.diagnostics.query_matches += len(result)
        return result

    def rows(
        self,
        *component_types: type[object],
        enabled_only: bool = True,
        tags: Iterable[str] = (),
    ) -> tuple[tuple[Any, ...], ...]:
        """Return snapshot rows of ``(entity, component...)`` for system-style iteration."""
        return tuple(
            (entity, *(entity.require(component_type) for component_type in component_types))
            for entity in self.query(
                *component_types,
                enabled_only=enabled_only,
                tags=tags,
            )
        )

    def add_system(self, system: T, *, priority: int = 0) -> T:
        if any(entry.system is system for entry in self._systems):
            raise ValueError("system is already registered")
        if not callable(system) and not callable(getattr(system, "update", None)):
            raise TypeError("system must be callable or provide update(world, dt)")
        self._systems.append(
            _SystemEntry(priority=int(priority), order=self._next_system_order, system=system)
        )
        self._next_system_order += 1
        self._systems_dirty = True
        hook = getattr(system, "on_added_to_world", None)
        if callable(hook):
            hook(self)
        return system

    def remove_system(self, system: object) -> bool:
        for index, entry in enumerate(self._systems):
            if entry.system is system:
                del self._systems[index]
                self._systems_dirty = True
                hook = getattr(system, "on_removed_from_world", None)
                if callable(hook):
                    hook(self)
                return True
        return False

    def _ordered_systems(self) -> tuple[_SystemEntry, ...]:
        if self._systems_dirty or len(self._ordered_system_cache) != len(self._systems):
            self._ordered_system_cache = tuple(
                sorted(self._systems, key=lambda entry: (entry.priority, entry.order))
            )
            self._systems_dirty = False
        return self._ordered_system_cache

    def update(self, dt: float) -> None:
        delta = float(dt)
        if delta < 0.0:
            raise ValueError("dt must be >= 0")
        for entry in self._ordered_systems():
            system = entry.system
            if not getattr(system, "enabled", True):
                continue
            update = getattr(system, "update", None)
            if callable(update):
                update(self, delta)
            else:
                system(self, delta)  # type: ignore[operator]
            self.diagnostics.system_updates += 1
