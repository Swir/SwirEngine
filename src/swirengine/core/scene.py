from __future__ import annotations

from collections.abc import Callable, Iterable, Iterator
from dataclasses import dataclass
from typing import TYPE_CHECKING, TypeVar

from typing_extensions import Self

from ..ecs import ECSDiagnostics, ECSWorld, Entity

if TYPE_CHECKING:
    from ..prefab import Prefab, PrefabInstance, PrefabOverrides

T = TypeVar("T")


@dataclass(slots=True)
class SceneDiagnostics:
    """Creator-visible counters for scene update/render snapshot work."""

    snapshot_rebuilds: int = 0
    render_snapshot_rebuilds: int = 0
    object_updates: int = 0

    def reset(self) -> None:
        self.snapshot_rebuilds = 0
        self.render_snapshot_rebuilds = 0
        self.object_updates = 0


@dataclass(slots=True)
class SceneMount:
    """Grouped scene ownership for rooms, encounters and streamed world chunks."""

    scene: Scene
    objects: tuple[object, ...] = ()
    entities: tuple[Entity, ...] = ()
    active: bool = True

    def unmount(self) -> tuple[int, int]:
        """Remove all mounted content once and return ``(objects, entities)`` counts."""
        if not self.active:
            return (0, 0)
        removed_objects = len(self.scene.remove_many(*self.objects))
        removed_entities = sum(int(self.scene.ecs.destroy(entity)) for entity in self.entities)
        self.active = False
        return removed_objects, removed_entities

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_exc: object) -> None:
        self.unmount()


class Scene:
    def __init__(self) -> None:
        self._objects: list[object] = []
        self._update_snapshot: tuple[object, ...] = ()
        self._render_snapshot: tuple[object, ...] = ()
        self._snapshot_dirty = False
        self._render_snapshot_dirty = False
        self._started_ids: set[int] = set()
        self.ecs = ECSWorld()
        self.diagnostics = SceneDiagnostics()

    @property
    def objects(self) -> tuple[object, ...]:
        return tuple(self._objects)

    @property
    def render_objects(self) -> tuple[object, ...]:
        """Return scene-level render roots without parent-managed child submissions.

        Tilemaps and future aggregate render sources can keep their child objects registered for
        compatibility/lifecycle purposes while the renderer avoids sorting/scanning those children
        every frame. The snapshot rebuilds only when scene membership changes.
        """
        if self._render_snapshot_dirty:
            self._render_snapshot = tuple(
                obj for obj in self._objects if not getattr(obj, "render_managed", False)
            )
            self._render_snapshot_dirty = False
            self.diagnostics.render_snapshot_rebuilds += 1
        return self._render_snapshot

    @property
    def entities(self) -> tuple[Entity, ...]:
        return self.ecs.entities

    @property
    def ecs_diagnostics(self) -> ECSDiagnostics:
        return self.ecs.diagnostics

    def __iter__(self) -> Iterator[object]:
        return iter(tuple(self._objects))

    def __len__(self) -> int:
        return len(self._objects)

    def __contains__(self, obj: object) -> bool:
        return any(existing is obj for existing in self._objects)

    @staticmethod
    def _lifecycle(obj: object, name: str, scene: Scene) -> None:
        hook = getattr(obj, name, None)
        if callable(hook):
            hook(scene)

    def _invalidate_snapshot(self) -> None:
        self._snapshot_dirty = True
        self._render_snapshot_dirty = True

    def _objects_for_update(self) -> tuple[object, ...]:
        if self._snapshot_dirty:
            self._update_snapshot = tuple(
                obj for obj in self._objects if not getattr(obj, "update_managed", False)
            )
            self._snapshot_dirty = False
            self.diagnostics.snapshot_rebuilds += 1
        return self._update_snapshot

    def add(self, obj: T) -> T:
        if not any(existing is obj for existing in self._objects):
            self._objects.append(obj)
            self._invalidate_snapshot()
            self._lifecycle(obj, "on_added_to_scene", self)
        return obj

    def add_many(self, *objects: object) -> tuple[object, ...]:
        for obj in objects:
            self.add(obj)
        return objects

    def mount(
        self,
        *objects: object,
        entities: Iterable[Entity] = (),
    ) -> SceneMount:
        """Take grouped ownership of scene content so it can be unloaded with one call.

        Objects may already be registered or may be new; either way, passing them to ``mount``
        transfers removal ownership to the returned mount. Entities must already belong to this
        scene's ECS world, avoiding silent entity migration between worlds.
        """
        mounted_entities = tuple(entities)
        for entity in mounted_entities:
            if self.ecs.entity(entity.id) is not entity:
                raise ValueError("mounted entities must belong to this scene")

        self.add_many(*objects)
        return SceneMount(self, tuple(objects), mounted_entities)

    def remove(self, obj: object) -> bool:
        for index, existing in enumerate(self._objects):
            if existing is obj:
                if id(existing) in self._started_ids:
                    self._lifecycle(existing, "on_stop", self)
                    self._started_ids.discard(id(existing))
                self._lifecycle(existing, "on_removed_from_scene", self)
                del self._objects[index]
                self._invalidate_snapshot()
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
        self.remove_many(*tuple(self._objects))
        if clear_entities:
            self.ecs.clear()

    def update(self, dt: float) -> None:
        for obj in self._objects_for_update():
            if not getattr(obj, "enabled", True):
                continue
            object_id = id(obj)
            if object_id not in self._started_ids:
                self._lifecycle(obj, "on_start", self)
                self._started_ids.add(object_id)
            update = getattr(obj, "update", None)
            if callable(update):
                update(dt)
                self.diagnostics.object_updates += 1
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

    def compose_entity(
        self,
        *components: object,
        name: str = "",
        enabled: bool = True,
        tags: Iterable[str] = (),
    ) -> Entity:
        """Create and populate an ECS entity in one call."""
        return self.ecs.compose_entity(*components, name=name, enabled=enabled, tags=tags)

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
