from __future__ import annotations

import heapq
import math
from collections import OrderedDict
from dataclasses import dataclass
from typing import Any, Protocol, cast, runtime_checkable

from .math.types import Vec2, Vec3

GridCell = tuple[int, int]


@dataclass(frozen=True, slots=True)
class NavigationDiagnostics:
    """Deterministic diagnostics from the latest path query plus cache totals."""

    revision: int = 0
    searches: int = 0
    cache_hits: int = 0
    cache_misses: int = 0
    expanded_nodes: int = 0
    queued_nodes: int = 0
    path_cells: int = 0
    path_cost: float = 0.0


@dataclass(frozen=True, slots=True)
class NavigationPath2D:
    """A world-space 2D path plus the grid cells used by A*."""

    cells: tuple[GridCell, ...]
    points: tuple[Vec2, ...]
    cost: float


@dataclass(frozen=True, slots=True)
class NavigationPath3D:
    """An XZ-plane 3D navigation path with world-space points."""

    cells: tuple[GridCell, ...]
    points: tuple[Vec3, ...]
    cost: float


@runtime_checkable
class NavigationProvider2D(Protocol):
    """Provider contract so future navmeshes can drive the same creator-facing agents."""

    @property
    def revision(self) -> int: ...

    def find_path(
        self,
        start: Vec2,
        goal: Vec2,
        *,
        max_expansions: int | None = None,
    ) -> NavigationPath2D | None: ...


@runtime_checkable
class NavigationProvider3D(Protocol):
    """3D provider contract shared by grid navigation and future navmesh backends."""

    @property
    def revision(self) -> int: ...

    def find_path(
        self,
        start: Vec3,
        goal: Vec3,
        *,
        max_expansions: int | None = None,
    ) -> NavigationPath3D | None: ...


@dataclass(frozen=True, slots=True)
class _CachedRoute:
    cells: tuple[GridCell, ...]
    cost: float


class NavigationGrid2D:
    """Deterministic weighted A* grid with revision-aware bounded route caching.

    The grid is intentionally creator-facing rather than tied to rendering or tilemaps. Dynamic
    obstacles update a revision counter and invalidate cached routes. Traversal costs are >= 1 so
    Manhattan/octile heuristics remain admissible.
    """

    _CARDINALS: tuple[tuple[int, int, float], ...] = (
        (1, 0, 1.0),
        (0, 1, 1.0),
        (-1, 0, 1.0),
        (0, -1, 1.0),
    )
    _DIAGONALS: tuple[tuple[int, int, float], ...] = (
        (1, 1, math.sqrt(2.0)),
        (-1, 1, math.sqrt(2.0)),
        (-1, -1, math.sqrt(2.0)),
        (1, -1, math.sqrt(2.0)),
    )

    def __init__(
        self,
        width: int,
        height: int,
        *,
        cell_size: float = 1.0,
        origin: Vec2 | None = None,
        diagonal: bool = True,
        allow_corner_cutting: bool = False,
        cache_size: int = 256,
    ) -> None:
        if width <= 0 or height <= 0:
            raise ValueError("navigation grid width and height must be greater than zero")
        if cell_size <= 0:
            raise ValueError("cell_size must be greater than zero")
        if cache_size <= 0:
            raise ValueError("cache_size must be greater than zero")
        self.width = int(width)
        self.height = int(height)
        self.cell_size = float(cell_size)
        self.origin = origin or Vec2()
        self.diagonal = bool(diagonal)
        self.allow_corner_cutting = bool(allow_corner_cutting)
        self.cache_size = int(cache_size)
        self._blocked: set[GridCell] = set()
        self._costs: dict[GridCell, float] = {}
        self._revision = 0
        self._cache: OrderedDict[tuple[GridCell, GridCell, int], _CachedRoute | None] = OrderedDict()
        self._searches = 0
        self._cache_hits = 0
        self._cache_misses = 0
        self._diagnostics = NavigationDiagnostics()

    @property
    def revision(self) -> int:
        return self._revision

    @property
    def diagnostics(self) -> NavigationDiagnostics:
        return self._diagnostics

    @property
    def blocked_cells(self) -> frozenset[GridCell]:
        return frozenset(self._blocked)

    def in_bounds(self, cell: GridCell) -> bool:
        x, y = cell
        return 0 <= x < self.width and 0 <= y < self.height

    def world_to_cell(self, point: Vec2) -> GridCell:
        return (
            math.floor((float(point.x) - float(self.origin.x)) / self.cell_size),
            math.floor((float(point.y) - float(self.origin.y)) / self.cell_size),
        )

    def cell_center(self, cell: GridCell) -> Vec2:
        self._require_cell(cell)
        return Vec2(
            float(self.origin.x) + (cell[0] + 0.5) * self.cell_size,
            float(self.origin.y) + (cell[1] + 0.5) * self.cell_size,
        )

    def _require_cell(self, cell: GridCell) -> None:
        if not self.in_bounds(cell):
            raise ValueError(f"navigation cell {cell!r} is outside the grid")

    def _changed(self) -> None:
        self._revision += 1
        self._cache.clear()

    def set_blocked(self, cell: GridCell, blocked: bool = True) -> None:
        self._require_cell(cell)
        before = cell in self._blocked
        if blocked:
            self._blocked.add(cell)
        else:
            self._blocked.discard(cell)
        if before != bool(blocked):
            self._changed()

    def set_blocked_many(self, cells: list[GridCell] | tuple[GridCell, ...], blocked: bool = True) -> None:
        changed = False
        for cell in cells:
            self._require_cell(cell)
            before = cell in self._blocked
            if blocked:
                self._blocked.add(cell)
            else:
                self._blocked.discard(cell)
            changed = changed or before != bool(blocked)
        if changed:
            self._changed()

    def set_cost(self, cell: GridCell, cost: float) -> None:
        self._require_cell(cell)
        value = float(cost)
        if not math.isfinite(value) or value < 1.0:
            raise ValueError("navigation traversal cost must be finite and >= 1.0")
        previous = self._costs.get(cell, 1.0)
        if value == 1.0:
            self._costs.pop(cell, None)
        else:
            self._costs[cell] = value
        if previous != value:
            self._changed()

    def cost_at(self, cell: GridCell) -> float:
        self._require_cell(cell)
        return self._costs.get(cell, 1.0)

    def clear_dynamic_data(self) -> None:
        if self._blocked or self._costs:
            self._blocked.clear()
            self._costs.clear()
            self._changed()

    def _heuristic(self, cell: GridCell, goal: GridCell) -> float:
        dx = abs(goal[0] - cell[0])
        dy = abs(goal[1] - cell[1])
        if not self.diagonal:
            return float(dx + dy)
        diagonal = min(dx, dy)
        straight = max(dx, dy) - diagonal
        return diagonal * math.sqrt(2.0) + straight

    def _neighbors(self, cell: GridCell):
        x, y = cell
        for dx, dy, distance in self._CARDINALS:
            candidate = (x + dx, y + dy)
            if self.in_bounds(candidate) and candidate not in self._blocked:
                yield candidate, distance * self._costs.get(candidate, 1.0)
        if not self.diagonal:
            return
        for dx, dy, distance in self._DIAGONALS:
            candidate = (x + dx, y + dy)
            if not self.in_bounds(candidate) or candidate in self._blocked:
                continue
            if not self.allow_corner_cutting:
                if (x + dx, y) in self._blocked or (x, y + dy) in self._blocked:
                    continue
            yield candidate, distance * self._costs.get(candidate, 1.0)

    def _remember(self, key: tuple[GridCell, GridCell, int], route: _CachedRoute | None) -> None:
        self._cache[key] = route
        self._cache.move_to_end(key)
        while len(self._cache) > self.cache_size:
            self._cache.popitem(last=False)

    def _set_diagnostics(
        self,
        *,
        expanded: int,
        queued: int,
        route: _CachedRoute | None,
    ) -> None:
        self._diagnostics = NavigationDiagnostics(
            revision=self._revision,
            searches=self._searches,
            cache_hits=self._cache_hits,
            cache_misses=self._cache_misses,
            expanded_nodes=expanded,
            queued_nodes=queued,
            path_cells=0 if route is None else len(route.cells),
            path_cost=0.0 if route is None else route.cost,
        )

    def _search(
        self,
        start: GridCell,
        goal: GridCell,
        *,
        max_expansions: int | None,
    ) -> _CachedRoute | None:
        if start in self._blocked or goal in self._blocked:
            self._set_diagnostics(expanded=0, queued=0, route=None)
            return None
        if start == goal:
            route = _CachedRoute((start,), 0.0)
            self._set_diagnostics(expanded=0, queued=1, route=route)
            return route

        frontier: list[tuple[float, float, int, GridCell]] = []
        sequence = 0
        start_h = self._heuristic(start, goal)
        heapq.heappush(frontier, (start_h, start_h, sequence, start))
        came_from: dict[GridCell, GridCell] = {}
        g_score: dict[GridCell, float] = {start: 0.0}
        expanded = 0
        queued = 1

        while frontier:
            _, _, _, current = heapq.heappop(frontier)
            current_cost = g_score[current]
            if current == goal:
                cells: list[GridCell] = [goal]
                while cells[-1] != start:
                    cells.append(came_from[cells[-1]])
                cells.reverse()
                route = _CachedRoute(tuple(cells), current_cost)
                self._set_diagnostics(expanded=expanded, queued=queued, route=route)
                return route

            expanded += 1
            if max_expansions is not None and expanded > max_expansions:
                break

            for neighbor, move_cost in self._neighbors(current):
                tentative = current_cost + move_cost
                previous = g_score.get(neighbor)
                if previous is not None and tentative >= previous:
                    continue
                came_from[neighbor] = current
                g_score[neighbor] = tentative
                sequence += 1
                heuristic = self._heuristic(neighbor, goal)
                heapq.heappush(frontier, (tentative + heuristic, heuristic, sequence, neighbor))
                queued += 1

        self._set_diagnostics(expanded=expanded, queued=queued, route=None)
        return None

    def find_path(
        self,
        start: Vec2,
        goal: Vec2,
        *,
        max_expansions: int | None = None,
    ) -> NavigationPath2D | None:
        if max_expansions is not None and max_expansions <= 0:
            raise ValueError("max_expansions must be greater than zero when provided")
        start_cell = self.world_to_cell(start)
        goal_cell = self.world_to_cell(goal)
        self._require_cell(start_cell)
        self._require_cell(goal_cell)
        self._searches += 1

        key = (start_cell, goal_cell, self._revision)
        use_cache = max_expansions is None
        if use_cache and key in self._cache:
            self._cache_hits += 1
            route = self._cache[key]
            self._cache.move_to_end(key)
            self._set_diagnostics(expanded=0, queued=0, route=route)
        else:
            self._cache_misses += 1
            route = self._search(start_cell, goal_cell, max_expansions=max_expansions)
            if use_cache:
                self._remember(key, route)

        if route is None:
            return None
        points = [self.cell_center(cell) for cell in route.cells]
        points[0] = Vec2(float(start.x), float(start.y))
        if len(points) > 1:
            points[-1] = Vec2(float(goal.x), float(goal.y))
        return NavigationPath2D(route.cells, tuple(points), route.cost * self.cell_size)


class NavigationGrid3D:
    """Creator-friendly XZ navigation plane backed by the deterministic 2D A* core."""

    def __init__(
        self,
        width: int,
        depth: int,
        *,
        cell_size: float = 1.0,
        origin: Vec3 | None = None,
        diagonal: bool = True,
        allow_corner_cutting: bool = False,
        cache_size: int = 256,
    ) -> None:
        self.origin = origin or Vec3()
        self._grid = NavigationGrid2D(
            width,
            depth,
            cell_size=cell_size,
            origin=Vec2(float(self.origin.x), float(self.origin.z)),
            diagonal=diagonal,
            allow_corner_cutting=allow_corner_cutting,
            cache_size=cache_size,
        )

    @property
    def width(self) -> int:
        return self._grid.width

    @property
    def depth(self) -> int:
        return self._grid.height

    @property
    def cell_size(self) -> float:
        return self._grid.cell_size

    @property
    def revision(self) -> int:
        return self._grid.revision

    @property
    def diagnostics(self) -> NavigationDiagnostics:
        return self._grid.diagnostics

    @property
    def blocked_cells(self) -> frozenset[GridCell]:
        return self._grid.blocked_cells

    def world_to_cell(self, point: Vec3) -> GridCell:
        return self._grid.world_to_cell(Vec2(float(point.x), float(point.z)))

    def cell_center(self, cell: GridCell) -> Vec3:
        point = self._grid.cell_center(cell)
        return Vec3(point.x, float(self.origin.y), point.y)

    def set_blocked(self, cell: GridCell, blocked: bool = True) -> None:
        self._grid.set_blocked(cell, blocked)

    def set_blocked_many(self, cells: list[GridCell] | tuple[GridCell, ...], blocked: bool = True) -> None:
        self._grid.set_blocked_many(cells, blocked)

    def set_cost(self, cell: GridCell, cost: float) -> None:
        self._grid.set_cost(cell, cost)

    def cost_at(self, cell: GridCell) -> float:
        return self._grid.cost_at(cell)

    def clear_dynamic_data(self) -> None:
        self._grid.clear_dynamic_data()

    def find_path(
        self,
        start: Vec3,
        goal: Vec3,
        *,
        max_expansions: int | None = None,
    ) -> NavigationPath3D | None:
        path = self._grid.find_path(
            Vec2(float(start.x), float(start.z)),
            Vec2(float(goal.x), float(goal.z)),
            max_expansions=max_expansions,
        )
        if path is None:
            return None
        points = tuple(Vec3(point.x, float(self.origin.y), point.y) for point in path.points)
        return NavigationPath3D(path.cells, points, path.cost)


def _target_xy_owner(target: object) -> Any:
    raw = cast(Any, target)
    if hasattr(raw, "x") and hasattr(raw, "y"):
        return raw
    position = getattr(raw, "position", None)
    if position is not None and hasattr(position, "x") and hasattr(position, "y"):
        return position
    raise TypeError("2D navigation agent target must expose x/y or position.x/y")


def _target_xyz_owner(target: object) -> Any:
    raw = cast(Any, target)
    position = getattr(raw, "position", None)
    if position is not None and all(hasattr(position, axis) for axis in ("x", "y", "z")):
        return position
    if all(hasattr(raw, axis) for axis in ("x", "y", "z")):
        return raw
    raise TypeError("3D navigation agent target must expose position.x/y/z or x/y/z")


class NavigationAgent2D:
    """Path-following helper that automatically repaths after grid/provider revisions."""

    def __init__(
        self,
        target: object,
        provider: NavigationProvider2D,
        *,
        speed: float = 100.0,
        stopping_distance: float = 0.05,
        auto_repath: bool = True,
    ) -> None:
        if speed < 0 or stopping_distance < 0:
            raise ValueError("agent speed and stopping_distance must be non-negative")
        _target_xy_owner(target)
        self.target = target
        self.provider = provider
        self.speed = float(speed)
        self.stopping_distance = float(stopping_distance)
        self.auto_repath = bool(auto_repath)
        self.destination: Vec2 | None = None
        self.path: NavigationPath2D | None = None
        self._waypoint = 0
        self._path_revision = provider.revision

    @property
    def has_path(self) -> bool:
        return self.path is not None and self._waypoint < len(self.path.points)

    def set_destination(self, destination: Vec2) -> bool:
        owner = _target_xy_owner(self.target)
        self.destination = Vec2(float(destination.x), float(destination.y))
        path = self.provider.find_path(
            Vec2(float(owner.x), float(owner.y)),
            self.destination,
        )
        self.path = path
        self._waypoint = 1 if path is not None and len(path.points) > 1 else 0
        self._path_revision = self.provider.revision
        return path is not None

    def clear_path(self) -> None:
        self.destination = None
        self.path = None
        self._waypoint = 0

    def _maybe_repath(self) -> None:
        if (
            self.auto_repath
            and self.destination is not None
            and self.provider.revision != self._path_revision
        ):
            self.set_destination(self.destination)

    def update(self, dt: float) -> None:
        if dt <= 0 or self.speed <= 0:
            return
        self._maybe_repath()
        if not self.has_path or self.path is None:
            return
        owner = _target_xy_owner(self.target)
        budget = self.speed * float(dt)
        while budget > 0 and self._waypoint < len(self.path.points):
            point = self.path.points[self._waypoint]
            dx = float(point.x) - float(owner.x)
            dy = float(point.y) - float(owner.y)
            distance = math.hypot(dx, dy)
            final = self._waypoint == len(self.path.points) - 1
            tolerance = self.stopping_distance if final else 1e-6
            if distance <= tolerance:
                self._waypoint += 1
                continue
            travel = min(budget, max(0.0, distance - tolerance))
            if travel <= 0:
                self._waypoint += 1
                continue
            owner.x = float(owner.x) + dx / distance * travel
            owner.y = float(owner.y) + dy / distance * travel
            budget -= travel
            if travel >= distance - tolerance:
                self._waypoint += 1


class NavigationAgent3D:
    """XZ-plane path follower compatible with future NavigationProvider3D navmeshes."""

    def __init__(
        self,
        target: object,
        provider: NavigationProvider3D,
        *,
        speed: float = 4.0,
        stopping_distance: float = 0.05,
        auto_repath: bool = True,
    ) -> None:
        if speed < 0 or stopping_distance < 0:
            raise ValueError("agent speed and stopping_distance must be non-negative")
        _target_xyz_owner(target)
        self.target = target
        self.provider = provider
        self.speed = float(speed)
        self.stopping_distance = float(stopping_distance)
        self.auto_repath = bool(auto_repath)
        self.destination: Vec3 | None = None
        self.path: NavigationPath3D | None = None
        self._waypoint = 0
        self._path_revision = provider.revision

    @property
    def has_path(self) -> bool:
        return self.path is not None and self._waypoint < len(self.path.points)

    def set_destination(self, destination: Vec3) -> bool:
        owner = _target_xyz_owner(self.target)
        self.destination = Vec3(float(destination.x), float(destination.y), float(destination.z))
        path = self.provider.find_path(
            Vec3(float(owner.x), float(owner.y), float(owner.z)),
            self.destination,
        )
        self.path = path
        self._waypoint = 1 if path is not None and len(path.points) > 1 else 0
        self._path_revision = self.provider.revision
        return path is not None

    def clear_path(self) -> None:
        self.destination = None
        self.path = None
        self._waypoint = 0

    def _maybe_repath(self) -> None:
        if (
            self.auto_repath
            and self.destination is not None
            and self.provider.revision != self._path_revision
        ):
            self.set_destination(self.destination)

    def update(self, dt: float) -> None:
        if dt <= 0 or self.speed <= 0:
            return
        self._maybe_repath()
        if not self.has_path or self.path is None:
            return
        owner = _target_xyz_owner(self.target)
        budget = self.speed * float(dt)
        while budget > 0 and self._waypoint < len(self.path.points):
            point = self.path.points[self._waypoint]
            dx = float(point.x) - float(owner.x)
            dz = float(point.z) - float(owner.z)
            distance = math.hypot(dx, dz)
            final = self._waypoint == len(self.path.points) - 1
            tolerance = self.stopping_distance if final else 1e-6
            if distance <= tolerance:
                self._waypoint += 1
                continue
            travel = min(budget, max(0.0, distance - tolerance))
            if travel <= 0:
                self._waypoint += 1
                continue
            owner.x = float(owner.x) + dx / distance * travel
            owner.z = float(owner.z) + dz / distance * travel
            budget -= travel
            if travel >= distance - tolerance:
                self._waypoint += 1
