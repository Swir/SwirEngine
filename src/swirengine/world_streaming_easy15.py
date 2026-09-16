from __future__ import annotations

from collections.abc import Callable, Iterable, Sequence
from typing import TypeAlias

from typing_extensions import Self

from .core.scene import Scene
from .ecs import Entity
from .large_world import ChunkContent, ChunkKey
from .math.types import Vec2, Vec3
from .world_streaming15 import (
    WorldCellContext,
    WorldCellLifecycleHook,
    WorldPartitionCell,
    WorldPartitionRegistry,
    WorldStreamingDiagnostics,
    WorldStreamingFailure,
    WorldStreamingRuntime,
    WorldStreamingSettings,
    WorldStreamingUpdate,
)

WorldChunkResult: TypeAlias = ChunkContent | object | Iterable[object] | None
WorldChunkFactory: TypeAlias = Callable[[WorldCellContext], WorldChunkResult]


def chunk_content(*objects: object, entities: Iterable[Entity] = ()) -> ChunkContent:
    """Create explicit chunk content without boilerplate tuple conversions."""
    return ChunkContent(tuple(objects), tuple(entities))


def _normalize_content(value: WorldChunkResult) -> ChunkContent:
    if value is None:
        return ChunkContent()
    if isinstance(value, ChunkContent):
        return value
    if isinstance(value, Entity):
        return ChunkContent(entities=(value,))
    if isinstance(value, (str, bytes, bytearray)):
        return ChunkContent(objects=(value,))

    try:
        items = tuple(value)  # type: ignore[arg-type]
    except TypeError:
        return ChunkContent(objects=(value,))

    objects: list[object] = []
    entities: list[Entity] = []
    for item in items:
        if isinstance(item, Entity):
            entities.append(item)
        else:
            objects.append(item)
    return ChunkContent(tuple(objects), tuple(entities))


def _chunk_key(value: ChunkKey | Sequence[int], *, dimensions: int) -> ChunkKey:
    if isinstance(value, ChunkKey):
        if dimensions == 2 and value.z != 0:
            raise ValueError("2D world stream chunk keys must use z=0")
        return value
    if isinstance(value, (str, bytes)):
        raise TypeError("world stream chunk key must contain integer coordinates")
    coords = tuple(value)
    expected = 2 if dimensions == 2 else 3
    if len(coords) != expected:
        raise ValueError(
            f"world stream chunk key must contain exactly {expected} integer coordinates"
        )
    normalized = []
    for coordinate in coords:
        if not isinstance(coordinate, int) or isinstance(coordinate, bool):
            raise TypeError("world stream chunk coordinates must be integers")
        normalized.append(coordinate)
    if dimensions == 2:
        return ChunkKey(normalized[0], normalized[1], 0)
    return ChunkKey(normalized[0], normalized[1], normalized[2])


def _dependencies(value: Iterable[str]) -> tuple[str, ...]:
    if isinstance(value, (str, bytes)):
        raise TypeError("world stream dependencies must be an iterable of cell ids, not a string")
    return tuple(value)


class WorldStream:
    """Beginner-friendly facade over deterministic World Streaming 2.0.

    Typical use::

        world = WorldStream(game.scene, dimensions=2, chunk_size=512, radius=1)

        @world.chunk("village", (0, 0))
        def village(ctx):
            return [
                Sprite2D("house.png", x=ctx.center.x, y=ctx.center.y),
                Sprite2D("tree.png", x=ctx.center.x + 120, y=ctx.center.y),
            ]

        game.update(lambda _dt: world.update((player.x, player.y)))

    Chunk factories may return ``ChunkContent``, a single scene object, any iterable of scene
    objects, entities, a mixture of objects/entities, or ``None``. The facade normalizes that
    result to the strict World Streaming 2.0 runtime contract.
    """

    def __init__(
        self,
        scene: Scene,
        *,
        chunk_size: float = 64.0,
        dimensions: int = 3,
        radius: int = 1,
        budget: int = 32,
        loads_per_update: int = 4,
        unloads_per_update: int = 8,
        retention_updates: int = 1,
        remover: Callable[[object], bool] | None = None,
    ) -> None:
        if not isinstance(scene, Scene):
            raise TypeError("WorldStream requires a Scene")
        if remover is not None and not callable(remover):
            raise TypeError("WorldStream remover must be callable")
        self.scene = scene
        self.settings = WorldStreamingSettings(
            chunk_size=chunk_size,
            dimensions=dimensions,
            active_radius_chunks=radius,
            max_active_cost=budget,
            max_activations_per_update=loads_per_update,
            max_deactivations_per_update=unloads_per_update,
            retention_updates=retention_updates,
        )
        self.registry = WorldPartitionRegistry()
        self._runtime: WorldStreamingRuntime | None = None
        self._remover = remover

    @property
    def started(self) -> bool:
        return self._runtime is not None

    @property
    def runtime(self) -> WorldStreamingRuntime:
        if self._runtime is None:
            self._runtime = WorldStreamingRuntime(
                self.scene,
                self.registry,
                settings=self.settings,
            )
        return self._runtime

    @property
    def active(self) -> tuple[str, ...]:
        if self._runtime is None:
            return ()
        return self._runtime.active_ids

    @property
    def active_cost(self) -> int:
        if self._runtime is None:
            return 0
        return self._runtime.active_cost

    @property
    def diagnostics(self) -> WorldStreamingDiagnostics | None:
        if self._runtime is None:
            return None
        return self._runtime.diagnostics

    @property
    def failures(self) -> tuple[WorldStreamingFailure, ...]:
        if self._runtime is None:
            return ()
        return self._runtime.failures()

    def _require_registration_open(self) -> None:
        if self._runtime is not None:
            raise RuntimeError(
                "world stream registration is closed after the first update; "
                "register chunks before gameplay starts"
            )

    def _remove_owned_objects(self, content: ChunkContent) -> None:
        if self._remover is None:
            return
        for obj in content.objects:
            self._remover(obj)

    def add_chunk(
        self,
        cell_id: str,
        key: ChunkKey | Sequence[int],
        factory: WorldChunkFactory,
        *,
        cost: int = 1,
        priority: int = 0,
        dependencies: Iterable[str] = (),
        on_activate: WorldCellLifecycleHook | None = None,
        on_deactivate: WorldCellLifecycleHook | None = None,
    ) -> WorldPartitionCell:
        """Register one streamed chunk with an ergonomic creator factory."""
        self._require_registration_open()
        if not callable(factory):
            raise TypeError("world stream chunk factory must be callable")

        def strict_factory(context: WorldCellContext) -> ChunkContent:
            return _normalize_content(factory(context))

        def strict_activate(context: WorldCellContext, content: ChunkContent) -> None:
            if on_activate is None:
                return
            try:
                on_activate(context, content)
            except Exception as activation_error:  # noqa: BLE001 - creator hook boundary
                try:
                    self._remove_owned_objects(content)
                except Exception as cleanup_error:  # noqa: BLE001 - preserve both failures
                    raise RuntimeError(
                        "world stream activation hook failed and owner cleanup also failed: "
                        f"{cleanup_error}"
                    ) from activation_error
                raise

        def strict_deactivate(context: WorldCellContext, content: ChunkContent) -> None:
            try:
                if on_deactivate is not None:
                    on_deactivate(context, content)
            finally:
                self._remove_owned_objects(content)

        activate = strict_activate if on_activate is not None else None
        deactivate = (
            strict_deactivate
            if on_deactivate is not None or self._remover is not None
            else None
        )
        cell = WorldPartitionCell(
            cell_id,
            _chunk_key(key, dimensions=self.settings.dimensions),
            strict_factory,
            cost=cost,
            priority=priority,
            dependencies=_dependencies(dependencies),
            on_activate=activate,
            on_deactivate=deactivate,
        )
        return self.registry.add(cell)

    def chunk(
        self,
        cell_id: str,
        key: ChunkKey | Sequence[int],
        *,
        cost: int = 1,
        priority: int = 0,
        dependencies: Iterable[str] = (),
        on_activate: WorldCellLifecycleHook | None = None,
        on_deactivate: WorldCellLifecycleHook | None = None,
    ) -> Callable[[WorldChunkFactory], WorldChunkFactory]:
        """Decorator form of :meth:`add_chunk` for compact game code."""

        def decorator(factory: WorldChunkFactory) -> WorldChunkFactory:
            self.add_chunk(
                cell_id,
                key,
                factory,
                cost=cost,
                priority=priority,
                dependencies=dependencies,
                on_activate=on_activate,
                on_deactivate=on_deactivate,
            )
            return factory

        return decorator

    def update(self, focus: Vec2 | Vec3 | Sequence[float]) -> WorldStreamingUpdate:
        """Move the streaming focus and perform one bounded residency update."""
        return self.runtime.update(focus)

    move_focus = update

    def warmup(
        self,
        focus: Vec2 | Vec3 | Sequence[float],
        *,
        max_updates: int = 64,
    ) -> WorldStreamingUpdate:
        """Resolve bounded chunk activations for a loading screen or spawn transition.

        ``warmup`` never changes runtime budgets. It simply performs multiple normal deterministic
        updates until no further activation/deactivation work remains, or the caller-supplied
        safety limit is reached.
        """
        if not isinstance(max_updates, int) or isinstance(max_updates, bool):
            raise TypeError("world stream max_updates must be an integer")
        if max_updates < 1:
            raise ValueError("world stream max_updates must be >= 1")

        last = self.update(focus)
        for _ in range(max_updates - 1):
            if not last.activated and not last.deactivated:
                return last
            last = self.update(focus)
        return last

    def retry(self, cell_id: str) -> bool:
        if self._runtime is None:
            self.registry.cell(cell_id)
            return False
        return self._runtime.retry(cell_id)

    def unload_all(self) -> tuple[str, ...]:
        if self._runtime is None:
            return ()
        return self._runtime.unload_all()

    def state_fingerprint(self) -> str:
        return self.runtime.state_fingerprint()

    def context(self, cell_id: str) -> WorldCellContext:
        if self._runtime is not None:
            return self._runtime.context(cell_id)
        cell = self.registry.cell(cell_id)
        size = self.settings.chunk_size
        origin = Vec3(cell.key.x * size, cell.key.y * size, cell.key.z * size)
        center = Vec3(
            origin.x + size * 0.5,
            origin.y + size * 0.5,
            origin.z + size * 0.5 if self.settings.dimensions == 3 else 0.0,
        )
        return WorldCellContext(
            self.scene,
            cell.cell_id,
            cell.key,
            origin,
            center,
            size,
            0,
        )

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_exc: object) -> None:
        self.unload_all()


def world_stream(
    owner: Scene | object,
    **settings: object,
) -> WorldStream:
    """Create a :class:`WorldStream` from a ``Scene`` or any object exposing ``.scene``.

    This allows the natural ``world_stream(game, ...)`` form without changing the stable ``Game``
    API while SwirEngine 1.5 remains additive. If the owner exposes a callable ``remove`` method,
    streamed scene objects are routed through that method during unload and activation rollback
    before the Scene mount is released, preserving owner-specific cleanup such as Game physics/UI
    registration.
    """
    scene = owner if isinstance(owner, Scene) else getattr(owner, "scene", None)
    if not isinstance(scene, Scene):
        raise TypeError("world_stream(...) requires a Scene or an object exposing .scene")
    remover = None if isinstance(owner, Scene) else getattr(owner, "remove", None)
    if remover is not None and not callable(remover):
        remover = None
    return WorldStream(scene, remover=remover, **settings)
