from __future__ import annotations

from collections.abc import Callable, Iterable, Iterator
from typing import TYPE_CHECKING, TypeVar

from ..ecs import ECSWorld, Entity

if TYPE_CHECKING:
    from ..prefab import Prefab, PrefabInstance, PrefabOverrides

T = TypeVar("T")


class Scene:
    def __init__(self) -> None:
        self._objects: list[object] = []
        self.ecs = ECSWorld()

    @property
    def objects(self) -> tuple[object, ...]:
        return tuple(self._objects)

    @property
    def entities(self) -> tuple[Entity, ...]:
        return self.ecs.entities

    def __iter__(self) -> Iterator[object]:
        return iter(tuple(self._objects))

    def __len__(self) -> int:
        return len(self._objects)

    def __contains__(self, obj: object) -> bool:
        return any(existing is obj for existing in self._objects)

    def add(self, obj: T) -> T:
        if not any(existing is obj for existing in self._objects):
            self._objects.append(obj)
        return obj

    def add_many(self, *objects: object) -> tuple[object, ...]:
        for obj in objects:
            self.add(obj)
        return objects

    def remove(self, obj: object) -> bool:
        for index, existing in enumerate(self._objects):
            if existing is obj:
                del self._objects[index]
                return True
        return False

    def remove_many(self, *objects: object) -> tuple[object, ...]:
        """Remove every matching object and return the objects actually removed.

        Identity semantics match :meth:`remove`, duplicate arguments are harmless, and the
        return value preserves the caller's order. This is intentionally scene-level: games
        with registered physics/UI resources should continue using ``Game.remove`` for those
        individual managed objects so subsystem cleanup can run.
        """
        removed: list[object] = []
        for obj in objects:
            if self.remove(obj):
                removed.append(obj)
        return tuple(removed)

    def remove_tagged(self, tag: str) -> tuple[object, ...]:
        """Remove and return a stable snapshot of every object carrying ``tag``."""
        matches = self.tagged(tag)
        self.remove_many(*matches)
        return matches

    def clear(self, *, clear_entities: bool = True) -> None:
        self._objects.clear()
        if clear_entities:
            self.ecs.clear()

    def update(self, dt: float) -> None:
        for obj in tuple(self._objects):
            if not getattr(obj, "enabled", True):
                continue
            update = getattr(obj, "update", None)
            if callable(update):
                update(dt)
        self.ecs.update(dt)

    def by_type(self, cls: type[T]) -> tuple[T, ...]:
        return tuple(obj for obj in self._objects if isinstance(obj, cls))

    def find(self, name: str) -> object | None:
        return next((obj for obj in self._objects if getattr(obj, "name", None) == name), None)

    def require(self, name: str) -> object:
        """Return the first named object or raise a clear creator-facing ``LookupError``."""
        obj = self.find(name)
        if obj is None:
            raise LookupError(f"scene object not found: {name!r}")
        return obj

    def find_all(self, name: str) -> tuple[object, ...]:
        return tuple(obj for obj in self._objects if getattr(obj, "name", None) == name)

    def tagged(self, tag: str) -> tuple[object, ...]:
        return tuple(obj for obj in self._objects if tag in getattr(obj, "tags", set()))

    def create_entity(
        self,
        *,
        name: str = "",
        enabled: bool = True,
        tags: Iterable[str] = (),
    ) -> Entity:
        """Create an ECS entity owned by this scene's world."""
        return self.ecs.create_entity(name=name, enabled=enabled, tags=tags)

    def query_entities(
        self,
        *component_types: type[object],
        enabled_only: bool = True,
        tags: Iterable[str] = (),
    ) -> tuple[Entity, ...]:
        """Query ECS entities without exposing world internals in common game code."""
        return self.ecs.query(*component_types, enabled_only=enabled_only, tags=tags)

    def prefab(
        self,
        *,
        name: str = "",
        predicate: Callable[[object], bool] | None = None,
    ) -> Prefab:
        """Capture this scene (or a filtered subset) as an independent prefab blueprint."""
        from ..prefab import Prefab

        return Prefab.from_scene(self, name=name, predicate=predicate)

    def instantiate(
        self,
        prefab: Prefab,
        *,
        overrides: PrefabOverrides | None = None,
    ) -> PrefabInstance:
        """Instantiate ``prefab`` directly into this scene."""
        return prefab.instantiate(self, overrides=overrides)
