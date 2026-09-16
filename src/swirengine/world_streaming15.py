from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from types import MappingProxyType
from typing import TypeAlias

from .core.scene import Scene, SceneMount
from .large_world import ChunkContent, ChunkKey
from .math.types import Vec2, Vec3


def _cell_id(value: str) -> str:
    if not isinstance(value, str):
        raise TypeError("world partition cell id must be a string")
    result = value.strip()
    if not result:
        raise ValueError("world partition cell id must not be empty")
    return result


def _positive_int(value: int, *, label: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise TypeError(f"{label} must be an integer")
    if value < 1:
        raise ValueError(f"{label} must be >= 1")
    return value


@dataclass(frozen=True, slots=True)
class WorldCellContext:
    """Creator-facing context supplied to World Streaming 2.0 cell hooks."""

    scene: Scene
    cell_id: str
    key: ChunkKey
    origin: Vec3
    center: Vec3
    chunk_size: float
    update_index: int


WorldCellFactory: TypeAlias = Callable[[WorldCellContext], ChunkContent]
WorldCellLifecycleHook: TypeAlias = Callable[[WorldCellContext, ChunkContent], None]


@dataclass(frozen=True, slots=True)
class WorldPartitionCell:
    """One independently streamed scene partition cell.

    ``cost`` is a creator-defined budget unit. It can represent a coarse memory/content weight,
    but it is deliberately not described as bytes because the runtime does not measure resident
    GPU/CPU memory. ``priority`` only affects deterministic admission order when multiple desired
    cells compete for the same budget.
    """

    cell_id: str
    key: ChunkKey
    factory: WorldCellFactory
    cost: int = 1
    priority: int = 0
    dependencies: tuple[str, ...] = ()
    on_activate: WorldCellLifecycleHook | None = None
    on_deactivate: WorldCellLifecycleHook | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "cell_id", _cell_id(self.cell_id))
        if not isinstance(self.key, ChunkKey):
            raise TypeError("world partition cell key must be a ChunkKey")
        if not callable(self.factory):
            raise TypeError("world partition cell factory must be callable")
        object.__setattr__(self, "cost", _positive_int(self.cost, label="world cell cost"))
        if not isinstance(self.priority, int) or isinstance(self.priority, bool):
            raise TypeError("world cell priority must be an integer")
        if isinstance(self.dependencies, (str, bytes)):
            raise TypeError("world cell dependencies must be an iterable of cell ids, not a string")
        dependencies = tuple(_cell_id(value) for value in self.dependencies)
        if len(set(dependencies)) != len(dependencies):
            raise ValueError("world cell dependencies must not contain duplicates")
        if self.cell_id in dependencies:
            raise ValueError("world cell cannot depend on itself")
        object.__setattr__(self, "dependencies", dependencies)
        if self.on_activate is not None and not callable(self.on_activate):
            raise TypeError("world cell on_activate hook must be callable")
        if self.on_deactivate is not None and not callable(self.on_deactivate):
            raise TypeError("world cell on_deactivate hook must be callable")


class WorldPartitionRegistry:
    """Finite cell registry with O(1) id lookup and O(1) key bucket lookup."""

    def __init__(self, cells: Iterable[WorldPartitionCell] = ()) -> None:
        self._cells: dict[str, WorldPartitionCell] = {}
        self._by_key: dict[ChunkKey, list[str]] = {}
        for cell in cells:
            self.add(cell)

    @property
    def cells(self) -> Mapping[str, WorldPartitionCell]:
        return MappingProxyType(self._cells)

    def add(self, cell: WorldPartitionCell) -> WorldPartitionCell:
        if cell.cell_id in self._cells:
            raise ValueError(f"duplicate world partition cell: {cell.cell_id}")
        self._cells[cell.cell_id] = cell
        self._by_key.setdefault(cell.key, []).append(cell.cell_id)
        self._by_key[cell.key].sort()
        return cell

    def cell(self, cell_id: str) -> WorldPartitionCell:
        try:
            return self._cells[cell_id]
        except KeyError as exc:
            raise KeyError(f"unknown world partition cell: {cell_id}") from exc

    def cells_for_key(self, key: ChunkKey) -> tuple[WorldPartitionCell, ...]:
        return tuple(self._cells[cell_id] for cell_id in self._by_key.get(key, ()))

    def validate(self) -> None:
        for cell in self._cells.values():
            for dependency in cell.dependencies:
                if dependency not in self._cells:
                    raise KeyError(
                        f"world partition cell {cell.cell_id!r} depends on unknown cell {dependency!r}"
                    )

        visiting: set[str] = set()
        visited: set[str] = set()

        def visit(cell_id: str) -> None:
            if cell_id in visited:
                return
            if cell_id in visiting:
                raise ValueError("world partition dependencies must not contain a cycle")
            visiting.add(cell_id)
            for dependency in self._cells[cell_id].dependencies:
                visit(dependency)
            visiting.remove(cell_id)
            visited.add(cell_id)

        for cell_id in sorted(self._cells):
            visit(cell_id)

    def fingerprint(self) -> str:
        payload = [
            {
                "id": cell_id,
                "key": [cell.key.x, cell.key.y, cell.key.z],
                "cost": cell.cost,
                "priority": cell.priority,
                "dependencies": list(cell.dependencies),
            }
            for cell_id, cell in sorted(self._cells.items())
        ]
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class WorldStreamingSettings:
    """Deterministic scene-partition admission and per-update work budgets."""

    chunk_size: float = 64.0
    dimensions: int = 3
    active_radius_chunks: int = 1
    max_active_cost: int = 32
    max_activations_per_update: int = 4
    max_deactivations_per_update: int = 8
    retention_updates: int = 1

    def __post_init__(self) -> None:
        chunk_size = float(self.chunk_size)
        if not math.isfinite(chunk_size) or chunk_size <= 0.0:
            raise ValueError("world streaming chunk_size must be finite and greater than zero")
        object.__setattr__(self, "chunk_size", chunk_size)
        if not isinstance(self.dimensions, int) or isinstance(self.dimensions, bool):
            raise TypeError("world streaming dimensions must be an integer")
        if self.dimensions not in (2, 3):
            raise ValueError("world streaming dimensions must be 2 or 3")
        if not isinstance(self.active_radius_chunks, int) or isinstance(
            self.active_radius_chunks, bool
        ):
            raise TypeError("active_radius_chunks must be an integer")
        if self.active_radius_chunks < 0:
            raise ValueError("active_radius_chunks must be >= 0")
        object.__setattr__(
            self,
            "max_active_cost",
            _positive_int(self.max_active_cost, label="max_active_cost"),
        )
        object.__setattr__(
            self,
            "max_activations_per_update",
            _positive_int(
                self.max_activations_per_update,
                label="max_activations_per_update",
            ),
        )
        object.__setattr__(
            self,
            "max_deactivations_per_update",
            _positive_int(
                self.max_deactivations_per_update,
                label="max_deactivations_per_update",
            ),
        )
        if not isinstance(self.retention_updates, int) or isinstance(self.retention_updates, bool):
            raise TypeError("retention_updates must be an integer")
        if self.retention_updates < 0:
            raise ValueError("retention_updates must be >= 0")


@dataclass(frozen=True, slots=True)
class WorldStreamingFailure:
    cell_id: str
    message: str


@dataclass(frozen=True, slots=True)
class WorldStreamingDiagnostics:
    update_index: int
    focus_key: ChunkKey
    local_keys: int
    desired_cells: int
    target_cells: int
    active_cells: int
    active_cost: int
    blocked_by_budget: int
    failed_cells: int
    total_activations: int
    total_deactivations: int

    def portable(self) -> dict[str, object]:
        return {
            "update_index": self.update_index,
            "focus_key": [self.focus_key.x, self.focus_key.y, self.focus_key.z],
            "local_keys": self.local_keys,
            "desired_cells": self.desired_cells,
            "target_cells": self.target_cells,
            "active_cells": self.active_cells,
            "active_cost": self.active_cost,
            "blocked_by_budget": self.blocked_by_budget,
            "failed_cells": self.failed_cells,
            "total_activations": self.total_activations,
            "total_deactivations": self.total_deactivations,
        }


@dataclass(frozen=True, slots=True)
class WorldStreamingUpdate:
    target: tuple[str, ...]
    activated: tuple[str, ...]
    deactivated: tuple[str, ...]
    blocked: tuple[str, ...]
    failed: tuple[WorldStreamingFailure, ...]
    diagnostics: WorldStreamingDiagnostics


@dataclass(slots=True)
class _CellState:
    active: bool = False
    content: ChunkContent | None = None
    mount: SceneMount | None = None
    failure: str = ""
    last_desired_update: int = -1


class WorldStreamingRuntime:
    """World Streaming 2.0 partition scheduler layered above stable scene primitives.

    The runtime deliberately keeps the released ``large_world`` API unchanged. It adds a higher
    level finite-world partition contract for dependency ordering, active-cost admission, explicit
    lifecycle hooks, hysteresis and deterministic diagnostics. Asset preloading can remain handled
    by ``LargeWorldStreamer`` / ``AssetStreamingManager``; this layer focuses on scene residency.
    """

    def __init__(
        self,
        scene: Scene,
        registry: WorldPartitionRegistry,
        *,
        settings: WorldStreamingSettings | None = None,
    ) -> None:
        registry.validate()
        self.scene = scene
        self.registry = registry
        self.settings = settings or WorldStreamingSettings()
        if self.settings.dimensions == 2:
            invalid_2d = sorted(
                cell.cell_id for cell in registry.cells.values() if cell.key.z != 0
            )
            if invalid_2d:
                raise ValueError(
                    "2D world streaming cells must use z=0: " + ", ".join(invalid_2d)
                )
        self._states = {cell_id: _CellState() for cell_id in registry.cells}
        self._active_ids: set[str] = set()
        self._failed_ids: set[str] = set()
        self._active_cost = 0
        self._update_index = 0
        self._total_activations = 0
        self._total_deactivations = 0
        zero = ChunkKey(0, 0, 0)
        self._diagnostics = WorldStreamingDiagnostics(0, zero, 0, 0, 0, 0, 0, 0, 0, 0, 0)

    @property
    def diagnostics(self) -> WorldStreamingDiagnostics:
        return self._diagnostics

    @property
    def active_ids(self) -> tuple[str, ...]:
        return tuple(sorted(self._active_ids))

    @property
    def active_cost(self) -> int:
        return self._active_cost

    def failures(self) -> tuple[WorldStreamingFailure, ...]:
        return tuple(
            WorldStreamingFailure(cell_id, self._states[cell_id].failure)
            for cell_id in sorted(self._failed_ids)
        )

    def retry(self, cell_id: str) -> bool:
        state = self._states.get(cell_id)
        if state is None:
            raise KeyError(f"unknown world partition cell: {cell_id}")
        if not state.failure or state.active:
            return False
        state.failure = ""
        self._failed_ids.discard(cell_id)
        return True

    def focus_key(self, focus: Vec2 | Vec3 | Sequence[float]) -> ChunkKey:
        x, y, z = self._focus_components(focus)
        size = self.settings.chunk_size
        z_key = math.floor(z / size) if self.settings.dimensions == 3 else 0
        return ChunkKey(math.floor(x / size), math.floor(y / size), z_key)

    def context(self, cell_id: str) -> WorldCellContext:
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
            self._update_index,
        )

    def _iter_window(self, focus: ChunkKey) -> Iterable[ChunkKey]:
        radius = self.settings.active_radius_chunks
        if self.settings.dimensions == 2:
            for y in range(focus.y - radius, focus.y + radius + 1):
                for x in range(focus.x - radius, focus.x + radius + 1):
                    yield ChunkKey(x, y, 0)
            return
        for z in range(focus.z - radius, focus.z + radius + 1):
            for y in range(focus.y - radius, focus.y + radius + 1):
                for x in range(focus.x - radius, focus.x + radius + 1):
                    yield ChunkKey(x, y, z)

    def _distance_sq(self, focus: ChunkKey, cell_id: str) -> int:
        key = self.registry.cell(cell_id).key
        dx = focus.x - key.x
        dy = focus.y - key.y
        dz = 0 if self.settings.dimensions == 2 else focus.z - key.z
        return dx * dx + dy * dy + dz * dz

    def _rank(self, focus: ChunkKey, cell_id: str) -> tuple[int, int, str]:
        cell = self.registry.cell(cell_id)
        return (-cell.priority, self._distance_sq(focus, cell_id), cell_id)

    def _dependency_closure(self, cell_id: str) -> tuple[str, ...]:
        ordered: list[str] = []
        seen: set[str] = set()

        def add(current: str) -> None:
            if current in seen:
                return
            seen.add(current)
            for dependency in sorted(self.registry.cell(current).dependencies):
                add(dependency)
            ordered.append(current)

        add(cell_id)
        return tuple(ordered)

    def _dependency_depth(self, cell_id: str, cache: dict[str, int]) -> int:
        if cell_id in cache:
            return cache[cell_id]
        dependencies = self.registry.cell(cell_id).dependencies
        depth = 0 if not dependencies else 1 + max(
            self._dependency_depth(dependency, cache) for dependency in dependencies
        )
        cache[cell_id] = depth
        return depth

    def _target_set(
        self,
        focus: ChunkKey,
        desired: set[str],
    ) -> tuple[set[str], tuple[str, ...]]:
        target: set[str] = set()
        target_cost = 0
        blocked: list[str] = []
        for cell_id in sorted(desired, key=lambda item: self._rank(focus, item)):
            closure = self._dependency_closure(cell_id)
            missing = tuple(item for item in closure if item not in target)
            extra_cost = sum(self.registry.cell(item).cost for item in missing)
            if target_cost + extra_cost > self.settings.max_active_cost:
                blocked.append(cell_id)
                continue
            target.update(missing)
            target_cost += extra_cost
        return target, tuple(blocked)

    def _activate(self, cell_id: str) -> bool:
        state = self._states[cell_id]
        if state.active or state.failure:
            return False
        cell = self.registry.cell(cell_id)
        context = self.context(cell_id)
        content: ChunkContent | None = None
        mount: SceneMount | None = None
        try:
            content = cell.factory(context)
            if not isinstance(content, ChunkContent):
                raise TypeError("world partition cell factory must return ChunkContent")
            mount = self.scene.mount(*content.objects, entities=content.entities)
            if cell.on_activate is not None:
                cell.on_activate(context, content)
        except Exception as exc:  # noqa: BLE001 - creator hooks are isolation boundaries
            if mount is not None:
                mount.unmount()
            elif content is not None:
                self.scene.remove_many(*content.objects)
                for entity in content.entities:
                    if self.scene.ecs.entity(entity.id) is entity:
                        self.scene.ecs.destroy(entity)
            state.failure = f"activation failed: {exc}"
            self._failed_ids.add(cell_id)
            return False
        state.active = True
        state.content = content
        state.mount = mount
        state.failure = ""
        self._active_ids.add(cell_id)
        self._active_cost += cell.cost
        self._failed_ids.discard(cell_id)
        self._total_activations += 1
        return True

    def _deactivate(self, cell_id: str) -> bool:
        state = self._states[cell_id]
        if not state.active:
            return False
        cell = self.registry.cell(cell_id)
        context = self.context(cell_id)
        content = state.content or ChunkContent()
        hook_error: Exception | None = None
        if cell.on_deactivate is not None:
            try:
                cell.on_deactivate(context, content)
            except Exception as exc:  # noqa: BLE001 - cleanup continues after creator hook failures
                hook_error = exc
        if state.mount is not None:
            state.mount.unmount()
        state.active = False
        state.content = None
        state.mount = None
        self._active_ids.discard(cell_id)
        self._active_cost -= cell.cost
        if hook_error is not None:
            state.failure = f"deactivation failed: {hook_error}"
            self._failed_ids.add(cell_id)
        else:
            state.failure = ""
            self._failed_ids.discard(cell_id)
        self._total_deactivations += 1
        return True

    def update(self, focus: Vec2 | Vec3 | Sequence[float]) -> WorldStreamingUpdate:
        self._update_index += 1
        focus_key = self.focus_key(focus)
        local_keys = tuple(self._iter_window(focus_key))
        desired: set[str] = set()
        for key in local_keys:
            for cell in self.registry.cells_for_key(key):
                desired.add(cell.cell_id)
                self._states[cell.cell_id].last_desired_update = self._update_index

        for cell_id in self.active_ids:
            state = self._states[cell_id]
            age = self._update_index - state.last_desired_update
            if state.last_desired_update >= 0 and age <= self.settings.retention_updates:
                desired.add(cell_id)

        target, blocked_by_target_budget = self._target_set(focus_key, desired)
        depth_cache: dict[str, int] = {}

        deactivation_candidates = [
            cell_id for cell_id in self.active_ids if cell_id not in target
        ]
        deactivation_candidates.sort(
            key=lambda item: (
                -self._dependency_depth(item, depth_cache),
                self.registry.cell(item).priority,
                -self._distance_sq(focus_key, item),
                item,
            )
        )
        deactivated: list[str] = []
        for cell_id in deactivation_candidates[: self.settings.max_deactivations_per_update]:
            if self._deactivate(cell_id):
                deactivated.append(cell_id)

        activation_candidates = [
            cell_id for cell_id in target if not self._states[cell_id].active
        ]
        activation_candidates.sort(
            key=lambda item: (
                self._dependency_depth(item, depth_cache),
                *self._rank(focus_key, item),
            )
        )
        activated: list[str] = []
        runtime_blocked: list[str] = []
        runtime_budget_blocked: list[str] = []
        for cell_id in activation_candidates:
            if len(activated) >= self.settings.max_activations_per_update:
                break
            state = self._states[cell_id]
            if state.failure:
                continue
            cell = self.registry.cell(cell_id)
            if any(not self._states[dependency].active for dependency in cell.dependencies):
                runtime_blocked.append(cell_id)
                continue
            if self.active_cost + cell.cost > self.settings.max_active_cost:
                runtime_blocked.append(cell_id)
                runtime_budget_blocked.append(cell_id)
                continue
            if self._activate(cell_id):
                activated.append(cell_id)

        blocked = tuple(dict.fromkeys((*blocked_by_target_budget, *runtime_blocked)))
        budget_blocked = tuple(
            dict.fromkeys((*blocked_by_target_budget, *runtime_budget_blocked))
        )
        failures = self.failures()
        active_ids = self.active_ids
        self._diagnostics = WorldStreamingDiagnostics(
            update_index=self._update_index,
            focus_key=focus_key,
            local_keys=len(local_keys),
            desired_cells=len(desired),
            target_cells=len(target),
            active_cells=len(active_ids),
            active_cost=self.active_cost,
            blocked_by_budget=len(budget_blocked),
            failed_cells=len(failures),
            total_activations=self._total_activations,
            total_deactivations=self._total_deactivations,
        )
        return WorldStreamingUpdate(
            target=tuple(sorted(target)),
            activated=tuple(activated),
            deactivated=tuple(deactivated),
            blocked=blocked,
            failed=failures,
            diagnostics=self._diagnostics,
        )

    def unload_all(self) -> tuple[str, ...]:
        depth_cache: dict[str, int] = {}
        active = list(self.active_ids)
        active.sort(
            key=lambda item: (-self._dependency_depth(item, depth_cache), item)
        )
        unloaded = []
        for cell_id in active:
            if self._deactivate(cell_id):
                unloaded.append(cell_id)
        failures = self.failures()
        self._diagnostics = WorldStreamingDiagnostics(
            update_index=self._update_index,
            focus_key=self._diagnostics.focus_key,
            local_keys=0,
            desired_cells=0,
            target_cells=0,
            active_cells=len(self._active_ids),
            active_cost=self._active_cost,
            blocked_by_budget=0,
            failed_cells=len(failures),
            total_activations=self._total_activations,
            total_deactivations=self._total_deactivations,
        )
        return tuple(unloaded)

    def state_fingerprint(self) -> str:
        payload = {
            "registry": self.registry.fingerprint(),
            "diagnostics": self.diagnostics.portable(),
            "active": list(self.active_ids),
            "failures": [[failure.cell_id, failure.message] for failure in self.failures()],
            "last_desired": [
                [cell_id, state.last_desired_update]
                for cell_id, state in sorted(self._states.items())
            ],
        }
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()

    def _focus_components(
        self,
        focus: Vec2 | Vec3 | Sequence[float],
    ) -> tuple[float, float, float]:
        if isinstance(focus, Vec3):
            values = (
                float(focus.x),
                float(focus.y),
                float(focus.z) if self.settings.dimensions == 3 else 0.0,
            )
        elif isinstance(focus, Vec2):
            values = (float(focus.x), float(focus.y), 0.0)
        else:
            if isinstance(focus, (str, bytes)):
                raise TypeError("world streaming focus must contain numeric coordinates")
            raw_values = tuple(float(value) for value in focus)
            if len(raw_values) != self.settings.dimensions:
                raise ValueError(
                    f"world streaming focus must contain exactly {self.settings.dimensions} coordinates"
                )
            values = (
                (raw_values[0], raw_values[1], 0.0)
                if self.settings.dimensions == 2
                else (raw_values[0], raw_values[1], raw_values[2])
            )
        if not all(math.isfinite(value) for value in values):
            raise ValueError("world streaming focus coordinates must be finite")
        return values
