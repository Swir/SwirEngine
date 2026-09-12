from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Any, TypeVar

T = TypeVar("T")
SystemCallable = Callable[["ECSWorld", float], None]


class Entity:
    """Lightweight component container owned by an :class:`ECSWorld`.

    Components can be any Python object. One component per concrete type is stored; querying
    by a base class is supported through ``isinstance`` so creator-defined component
    hierarchies remain ergonomic without requiring inheritance from an engine base class.
    """

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
        if component_type in self._components and not replace:
            raise ValueError(f"entity {self.id} already has component {component_type.__name__}")
        self._components[component_type] = component
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
            return exact  # type: ignore[return-value]
        for stored_type, component in tuple(self._components.items()):
            if isinstance(component, component_type):
                del self._components[stored_type]
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
    """Deterministic entity/component/system runtime with no mandatory base component type."""

    def __init__(self) -> None:
        self._entities: dict[int, Entity] = {}
        self._systems: list[_SystemEntry] = []
        self._next_entity_id = 1
        self._next_system_order = 0

    @property
    def entities(self) -> tuple[Entity, ...]:
        return tuple(self._entities.values())

    @property
    def systems(self) -> tuple[object, ...]:
        return tuple(entry.system for entry in self._ordered_systems())

    def create_entity(
        self,
        *,
        name: str = "",
        enabled: bool = True,
        tags: Iterable[str] = (),
    ) -> Entity:
        entity = Entity(
            self._next_entity_id,
            name=name,
            enabled=enabled,
            tags=tags,
            world=self,
        )
        self._next_entity_id += 1
        self._entities[entity.id] = entity
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
        del self._entities[entity_id]
        existing._world = None
        return True

    def clear(self) -> None:
        for entity in self._entities.values():
            entity._world = None
        self._entities.clear()

    def query(
        self,
        *component_types: type[object],
        enabled_only: bool = True,
        tags: Iterable[str] = (),
    ) -> tuple[Entity, ...]:
        required_tags = frozenset(tags)
        return tuple(
            entity
            for entity in self._entities.values()
            if (entity.enabled or not enabled_only)
            and required_tags.issubset(entity.tags)
            and entity.has(*component_types)
        )

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
        return system

    def remove_system(self, system: object) -> bool:
        for index, entry in enumerate(self._systems):
            if entry.system is system:
                del self._systems[index]
                return True
        return False

    def _ordered_systems(self) -> tuple[_SystemEntry, ...]:
        return tuple(sorted(self._systems, key=lambda entry: (entry.priority, entry.order)))

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
