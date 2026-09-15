from __future__ import annotations

from collections.abc import Callable, Iterable
from concurrent.futures import Future
from dataclasses import dataclass, field
from math import floor
from pathlib import Path
from typing import TYPE_CHECKING, TypeAlias

from .asset_pipeline import AssetLoadResult
from .asset_streaming import AssetStreamingManager
from .core.scene import Scene, SceneMount
from .ecs import Entity
from .math.types import Vec2, Vec3

if TYPE_CHECKING:
    from collections.abc import Mapping


@dataclass(frozen=True, order=True, slots=True)
class ChunkKey:
    """Integer chunk address shared by 2D and 3D large worlds."""

    x: int
    y: int
    z: int = 0


@dataclass(frozen=True, slots=True)
class ChunkContent:
    """Scene content produced when a ready chunk becomes active."""

    objects: tuple[object, ...] = ()
    entities: tuple[Entity, ...] = ()


@dataclass(frozen=True, slots=True)
class ChunkBuildContext:
    """Creator-facing build context for one chunk activation."""

    scene: Scene
    key: ChunkKey
    origin: Vec3
    center: Vec3
    chunk_size: float
    asset_streamer: AssetStreamingManager | None


ChunkFactory: TypeAlias = Callable[[ChunkBuildContext], ChunkContent]
ChunkProvider: TypeAlias = Callable[[ChunkKey], "ChunkDefinition | None"]
ChunkVisibility: TypeAlias = Callable[[ChunkBuildContext, "ChunkDefinition"], bool]
ChunkLifecycleHook: TypeAlias = Callable[[ChunkBuildContext, ChunkContent], None]


@dataclass(frozen=True, slots=True)
class ChunkDefinition:
    """Declarative chunk metadata plus a factory invoked only on activation."""

    key: ChunkKey
    factory: ChunkFactory
    assets: tuple[str | Path, ...] = ()
    name: str = ""
    on_deactivate: ChunkLifecycleHook | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "assets", tuple(self.assets))


class ChunkRegistry:
    """O(1) chunk lookup registry suitable for authored finite worlds."""

    def __init__(self, definitions: Iterable[ChunkDefinition] = ()) -> None:
        self._definitions: dict[ChunkKey, ChunkDefinition] = {}
        for definition in definitions:
            self.add(definition)

    def add(self, definition: ChunkDefinition) -> ChunkDefinition:
        self._definitions[definition.key] = definition
        return definition

    def remove(self, key: ChunkKey) -> ChunkDefinition | None:
        return self._definitions.pop(key, None)

    def get(self, key: ChunkKey) -> ChunkDefinition | None:
        return self._definitions.get(key)

    def __call__(self, key: ChunkKey) -> ChunkDefinition | None:
        return self.get(key)

    def __len__(self) -> int:
        return len(self._definitions)

    def snapshot(self) -> Mapping[ChunkKey, ChunkDefinition]:
        return dict(self._definitions)


@dataclass(frozen=True, slots=True)
class LargeWorldSettings:
    """Chunk-window and per-frame work budgets for :class:`LargeWorldStreamer`."""

    chunk_size: float = 64.0
    dimensions: int = 3
    active_radius_chunks: int = 1
    preload_radius_chunks: int = 2
    retention_radius_chunks: int = 3
    max_activations_per_update: int = 4
    max_deactivations_per_update: int = 16
    max_asset_completions_per_update: int = 4

    def __post_init__(self) -> None:
        if self.chunk_size <= 0:
            raise ValueError("chunk_size must be greater than zero")
        if self.dimensions not in (2, 3):
            raise ValueError("dimensions must be 2 or 3")
        if self.active_radius_chunks < 0:
            raise ValueError("active_radius_chunks must be non-negative")
        if self.preload_radius_chunks < self.active_radius_chunks:
            raise ValueError("preload_radius_chunks must be >= active_radius_chunks")
        if self.retention_radius_chunks < self.preload_radius_chunks:
            raise ValueError("retention_radius_chunks must be >= preload_radius_chunks")
        if self.max_activations_per_update < 1:
            raise ValueError("max_activations_per_update must be >= 1")
        if self.max_deactivations_per_update < 1:
            raise ValueError("max_deactivations_per_update must be >= 1")
        if self.max_asset_completions_per_update < 1:
            raise ValueError("max_asset_completions_per_update must be >= 1")


@dataclass(frozen=True, slots=True)
class ChunkFailure:
    key: ChunkKey
    message: str


@dataclass(frozen=True, slots=True)
class LargeWorldDiagnostics:
    """Work counters from the most recent streaming update."""

    focus_key: ChunkKey
    candidate_keys: int
    provider_queries: int
    tracked_chunks: int
    ready_chunks: int
    active_chunks: int
    waiting_assets: int
    failed_chunks: int
    total_activations: int
    total_deactivations: int
    total_unloads: int


@dataclass(frozen=True, slots=True)
class ChunkUpdateResult:
    focus_key: ChunkKey
    ready: tuple[ChunkKey, ...]
    activated: tuple[ChunkKey, ...]
    deactivated: tuple[ChunkKey, ...]
    unloaded: tuple[ChunkKey, ...]
    diagnostics: LargeWorldDiagnostics


@dataclass(slots=True)
class _ChunkState:
    definition: ChunkDefinition
    futures: tuple[Future[AssetLoadResult], ...] = ()
    ready: bool = False
    active: bool = False
    failed: bool = False
    failure: str = ""
    content: ChunkContent | None = None
    mount: SceneMount | None = None
    canonical_assets: tuple[Path, ...] = ()


class LargeWorldStreamer:
    """Budgeted chunk residency and activation for large 2D/3D scenes.

    The streamer never scans the complete authored world. Each update enumerates only the local
    preload window around the focus chunk and asks the provider for those keys. Chunk assets are
    staged asynchronously when an :class:`AssetStreamingManager` is supplied, while scene content
    is created only once the chunk becomes visible/near enough and an activation budget is
    available.
    """

    def __init__(
        self,
        scene: Scene,
        provider: ChunkProvider | ChunkRegistry,
        *,
        settings: LargeWorldSettings | None = None,
        asset_streamer: AssetStreamingManager | None = None,
    ) -> None:
        self.scene = scene
        self.provider = provider
        self.settings = settings or LargeWorldSettings()
        self.asset_streamer = asset_streamer
        self._states: dict[ChunkKey, _ChunkState] = {}
        self._asset_refs: dict[Path, int] = {}
        self._desired_preload: set[ChunkKey] = set()
        self._desired_active: set[ChunkKey] = set()
        self._activation_scratch: list[tuple[int, ChunkKey]] = []
        self._stale_scratch: list[ChunkKey] = []
        self._ready_scratch: list[ChunkKey] = []
        self._total_activations = 0
        self._total_deactivations = 0
        self._total_unloads = 0
        zero = ChunkKey(0, 0, 0)
        self._diagnostics = LargeWorldDiagnostics(zero, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0)

    @property
    def diagnostics(self) -> LargeWorldDiagnostics:
        return self._diagnostics

    @property
    def tracked_keys(self) -> tuple[ChunkKey, ...]:
        return tuple(sorted(self._states))

    @property
    def active_keys(self) -> tuple[ChunkKey, ...]:
        return tuple(sorted(key for key, state in self._states.items() if state.active))

    def failures(self) -> tuple[ChunkFailure, ...]:
        return tuple(
            ChunkFailure(key, state.failure)
            for key, state in sorted(self._states.items())
            if state.failed
        )

    def focus_key(self, focus: Vec2 | Vec3 | tuple[float, ...]) -> ChunkKey:
        x, y, z = self._focus_components(focus)
        size = self.settings.chunk_size
        return ChunkKey(floor(x / size), floor(y / size), floor(z / size))

    def chunk_origin(self, key: ChunkKey) -> Vec3:
        size = self.settings.chunk_size
        z = key.z * size if self.settings.dimensions == 3 else 0.0
        return Vec3(key.x * size, key.y * size, z)

    def chunk_center(self, key: ChunkKey) -> Vec3:
        origin = self.chunk_origin(key)
        half = self.settings.chunk_size * 0.5
        z = origin.z + half if self.settings.dimensions == 3 else 0.0
        return Vec3(origin.x + half, origin.y + half, z)

    def context(self, key: ChunkKey) -> ChunkBuildContext:
        return ChunkBuildContext(
            scene=self.scene,
            key=key,
            origin=self.chunk_origin(key),
            center=self.chunk_center(key),
            chunk_size=self.settings.chunk_size,
            asset_streamer=self.asset_streamer,
        )

    def update(
        self,
        focus: Vec2 | Vec3 | tuple[float, ...],
        *,
        visibility: ChunkVisibility | None = None,
    ) -> ChunkUpdateResult:
        focus_key = self.focus_key(focus)
        if self.asset_streamer is not None:
            self.asset_streamer.pump(
                max_completions=self.settings.max_asset_completions_per_update
            )

        self._desired_preload.clear()
        self._desired_active.clear()
        self._activation_scratch.clear()
        self._stale_scratch.clear()
        self._ready_scratch.clear()

        candidate_keys = 0
        provider_queries = 0
        for key in self._iter_window(focus_key, self.settings.preload_radius_chunks):
            candidate_keys += 1
            self._desired_preload.add(key)
            state = self._states.get(key)
            if state is None:
                provider_queries += 1
                definition = self.provider(key)
                if definition is None:
                    continue
                if definition.key != key:
                    raise ValueError(
                        f"chunk provider returned definition {definition.key!r} for requested {key!r}"
                    )
                state = self._create_state(definition)
                self._states[key] = state

            became_ready = self._refresh_readiness(state)
            if became_ready:
                self._ready_scratch.append(key)
            if not state.ready or state.failed:
                continue
            if self._key_distance(focus_key, key) > self.settings.active_radius_chunks:
                continue
            context = self.context(key)
            if visibility is not None and not visibility(context, state.definition):
                continue
            self._desired_active.add(key)
            if not state.active:
                self._activation_scratch.append((self._distance_sq(focus_key, key), key))

        deactivated: list[ChunkKey] = []
        remaining_deactivations = self.settings.max_deactivations_per_update
        for key, state in sorted(self._states.items()):
            if remaining_deactivations <= 0:
                break
            if state.active and key not in self._desired_active:
                self._deactivate(key, state)
                deactivated.append(key)
                remaining_deactivations -= 1

        self._activation_scratch.sort(key=lambda item: (item[0], item[1]))
        activated: list[ChunkKey] = []
        for _, key in self._activation_scratch[: self.settings.max_activations_per_update]:
            state = self._states.get(key)
            if state is None or state.active or state.failed or not state.ready:
                continue
            self._activate(key, state)
            activated.append(key)

        for key in self._states:
            if self._key_distance(focus_key, key) > self.settings.retention_radius_chunks:
                self._stale_scratch.append(key)

        unloaded: list[ChunkKey] = []
        for key in self._stale_scratch:
            state = self._states.get(key)
            if state is None or state.active:
                continue
            self._release_state_assets(state)
            del self._states[key]
            unloaded.append(key)
            self._total_unloads += 1

        ready_count = 0
        active_count = 0
        waiting_assets = 0
        failed_count = 0
        for state in self._states.values():
            ready_count += int(state.ready)
            active_count += int(state.active)
            failed_count += int(state.failed)
            waiting_assets += int(not state.ready and not state.failed and bool(state.futures))

        self._diagnostics = LargeWorldDiagnostics(
            focus_key=focus_key,
            candidate_keys=candidate_keys,
            provider_queries=provider_queries,
            tracked_chunks=len(self._states),
            ready_chunks=ready_count,
            active_chunks=active_count,
            waiting_assets=waiting_assets,
            failed_chunks=failed_count,
            total_activations=self._total_activations,
            total_deactivations=self._total_deactivations,
            total_unloads=self._total_unloads,
        )
        return ChunkUpdateResult(
            focus_key=focus_key,
            ready=tuple(self._ready_scratch),
            activated=tuple(activated),
            deactivated=tuple(deactivated),
            unloaded=tuple(unloaded),
            diagnostics=self._diagnostics,
        )

    def unload_all(self) -> tuple[ChunkKey, ...]:
        """Deactivate and forget every tracked chunk while retaining shared asset-cache policy."""
        unloaded: list[ChunkKey] = []
        for key in sorted(tuple(self._states)):
            state = self._states[key]
            if state.active:
                self._deactivate(key, state)
            self._release_state_assets(state)
            del self._states[key]
            unloaded.append(key)
            self._total_unloads += 1
        return tuple(unloaded)

    def retry(self, key: ChunkKey) -> bool:
        """Retry a failed tracked chunk without affecting unrelated chunk state."""
        state = self._states.get(key)
        if state is None or not state.failed:
            return False
        self._release_state_assets(state)
        replacement = self._create_state(state.definition)
        self._states[key] = replacement
        return True

    def _create_state(self, definition: ChunkDefinition) -> _ChunkState:
        if definition.assets and self.asset_streamer is None:
            raise RuntimeError(
                f"chunk {definition.key!r} declares assets but no AssetStreamingManager was supplied"
            )
        canonical_assets: list[Path] = []
        futures: list[Future[AssetLoadResult]] = []
        if self.asset_streamer is not None:
            try:
                for asset in definition.assets:
                    path = self.asset_streamer.assets.require(asset).expanduser().resolve()
                    canonical_assets.append(path)
                    refs = self._asset_refs.get(path, 0)
                    self._asset_refs[path] = refs + 1
                    futures.append(self.asset_streamer.stage(path, pin=True))
            except Exception:
                for path in canonical_assets:
                    self._decrement_asset_ref(path)
                raise
        return _ChunkState(
            definition=definition,
            futures=tuple(futures),
            ready=not futures,
            canonical_assets=tuple(canonical_assets),
        )

    def _refresh_readiness(self, state: _ChunkState) -> bool:
        if state.ready or state.failed:
            return False
        if not state.futures or not all(future.done() for future in state.futures):
            return False
        try:
            results = tuple(future.result() for future in state.futures)
        except Exception as exc:  # background loader exceptions must become creator-visible state
            state.failed = True
            state.failure = f"asset staging failed: {exc}"
            return False
        failures = [result for result in results if not result.ok]
        if failures:
            first = failures[0]
            state.failed = True
            state.failure = f"asset staging failed for {first.path}"
            return False
        state.ready = True
        return True

    def _activate(self, key: ChunkKey, state: _ChunkState) -> None:
        if self.asset_streamer is not None:
            for path in state.canonical_assets:
                self.asset_streamer.touch(path)
        context = self.context(key)
        try:
            content = state.definition.factory(context)
            if not isinstance(content, ChunkContent):
                raise TypeError("chunk factory must return ChunkContent")
            mount = self.scene.mount(*content.objects, entities=content.entities)
        except Exception as exc:
            state.failed = True
            state.failure = f"chunk activation failed: {exc}"
            return
        state.content = content
        state.mount = mount
        state.active = True
        self._total_activations += 1

    def _deactivate(self, key: ChunkKey, state: _ChunkState) -> None:
        content = state.content or ChunkContent()
        context = self.context(key)
        if state.definition.on_deactivate is not None:
            state.definition.on_deactivate(context, content)
        if state.mount is not None:
            state.mount.unmount()
        state.mount = None
        state.content = None
        state.active = False
        self._total_deactivations += 1

    def _release_state_assets(self, state: _ChunkState) -> None:
        for path in state.canonical_assets:
            self._decrement_asset_ref(path)
        state.canonical_assets = ()
        state.futures = ()

    def _decrement_asset_ref(self, path: Path) -> None:
        current = self._asset_refs.get(path, 0)
        if current <= 1:
            self._asset_refs.pop(path, None)
            if self.asset_streamer is not None:
                self.asset_streamer.unpin(path)
            return
        self._asset_refs[path] = current - 1

    def _iter_window(self, focus: ChunkKey, radius: int) -> Iterable[ChunkKey]:
        if self.settings.dimensions == 2:
            for y in range(focus.y - radius, focus.y + radius + 1):
                for x in range(focus.x - radius, focus.x + radius + 1):
                    yield ChunkKey(x, y, 0)
            return
        for z in range(focus.z - radius, focus.z + radius + 1):
            for y in range(focus.y - radius, focus.y + radius + 1):
                for x in range(focus.x - radius, focus.x + radius + 1):
                    yield ChunkKey(x, y, z)

    def _key_distance(self, first: ChunkKey, second: ChunkKey) -> int:
        dx = abs(first.x - second.x)
        dy = abs(first.y - second.y)
        if self.settings.dimensions == 2:
            return max(dx, dy)
        return max(dx, dy, abs(first.z - second.z))

    def _distance_sq(self, first: ChunkKey, second: ChunkKey) -> int:
        dx = first.x - second.x
        dy = first.y - second.y
        dz = 0 if self.settings.dimensions == 2 else first.z - second.z
        return dx * dx + dy * dy + dz * dz

    def _focus_components(self, focus: Vec2 | Vec3 | tuple[float, ...]) -> tuple[float, float, float]:
        if isinstance(focus, Vec3):
            return float(focus.x), float(focus.y), float(focus.z)
        if isinstance(focus, Vec2):
            return float(focus.x), float(focus.y), 0.0
        values = tuple(float(value) for value in focus)
        expected = self.settings.dimensions
        if len(values) != expected:
            raise ValueError(f"focus tuple must contain exactly {expected} coordinates")
        if expected == 2:
            return values[0], values[1], 0.0
        return values[0], values[1], values[2]
