from __future__ import annotations

import hashlib
import heapq
import json
import math
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from itertools import pairwise
from types import MappingProxyType
from typing import Any


def _finite(value: float, *, label: str) -> float:
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{label} must be finite")
    return result


def _nonnegative(value: float, *, label: str) -> float:
    result = _finite(value, label=label)
    if result < 0.0:
        raise ValueError(f"{label} must be >= 0")
    return result


def _name(value: str, *, label: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{label} must be a string")
    result = value.strip()
    if not result:
        raise ValueError(f"{label} must not be empty")
    return result


@dataclass(frozen=True, slots=True)
class NavPoint:
    x: float
    y: float = 0.0
    z: float = 0.0

    def __post_init__(self) -> None:
        object.__setattr__(self, "x", _finite(self.x, label="navigation x"))
        object.__setattr__(self, "y", _finite(self.y, label="navigation y"))
        object.__setattr__(self, "z", _finite(self.z, label="navigation z"))

    def __add__(self, other: NavPoint) -> NavPoint:
        return NavPoint(self.x + other.x, self.y + other.y, self.z + other.z)

    def __sub__(self, other: NavPoint) -> NavPoint:
        return NavPoint(self.x - other.x, self.y - other.y, self.z - other.z)

    def __mul__(self, scalar: float) -> NavPoint:
        scalar = _finite(scalar, label="navigation scalar")
        return NavPoint(self.x * scalar, self.y * scalar, self.z * scalar)

    __rmul__ = __mul__

    @property
    def length(self) -> float:
        return math.sqrt(self.x * self.x + self.y * self.y + self.z * self.z)

    def normalized(self) -> NavPoint:
        length = self.length
        if length <= 1e-12:
            return NavPoint(0.0, 0.0, 0.0)
        return NavPoint(self.x / length, self.y / length, self.z / length)

    def distance_to(self, other: NavPoint) -> float:
        return (self - other).length

    def portable(self) -> tuple[float, float, float]:
        return (self.x, self.y, self.z)


PointLike = NavPoint | Sequence[float]


def nav_point(value: PointLike) -> NavPoint:
    if isinstance(value, NavPoint):
        return value
    if isinstance(value, (str, bytes)) or len(value) != 3:
        raise ValueError("navigation point must contain exactly three values")
    return NavPoint(value[0], value[1], value[2])


@dataclass(frozen=True, slots=True)
class NavigationNode:
    node_id: str
    position: NavPoint | Sequence[float]

    def __post_init__(self) -> None:
        object.__setattr__(self, "node_id", _name(self.node_id, label="navigation node id"))
        object.__setattr__(self, "position", nav_point(self.position))


@dataclass(frozen=True, slots=True)
class NavigationEdge:
    source: str
    target: str
    cost: float | None = None
    area: str = "default"
    bidirectional: bool = True
    enabled: bool = True

    def __post_init__(self) -> None:
        object.__setattr__(self, "source", _name(self.source, label="navigation edge source"))
        object.__setattr__(self, "target", _name(self.target, label="navigation edge target"))
        object.__setattr__(self, "area", _name(self.area, label="navigation edge area"))
        if self.cost is not None:
            object.__setattr__(
                self,
                "cost",
                _nonnegative(self.cost, label="navigation edge cost"),
            )


@dataclass(frozen=True, slots=True)
class NavigationQueryFilter:
    blocked_nodes: frozenset[str] = frozenset()
    blocked_edges: frozenset[tuple[str, str]] = frozenset()
    allowed_areas: frozenset[str] | None = None
    area_costs: tuple[tuple[str, float], ...] = ()
    _area_cost_map: Mapping[str, float] = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        blocked_nodes = frozenset(
            _name(value, label="blocked node") for value in self.blocked_nodes
        )
        blocked_edges = frozenset(
            (
                _name(source, label="blocked edge source"),
                _name(target, label="blocked edge target"),
            )
            for source, target in self.blocked_edges
        )
        allowed_areas = self.allowed_areas
        if allowed_areas is not None:
            allowed_areas = frozenset(
                _name(value, label="allowed navigation area") for value in allowed_areas
            )
        costs: dict[str, float] = {}
        for area, multiplier in self.area_costs:
            area = _name(area, label="navigation area cost name")
            if area in costs:
                raise ValueError(f"duplicate navigation area cost: {area}")
            multiplier = _finite(multiplier, label=f"navigation area cost {area!r}")
            if multiplier <= 0.0:
                raise ValueError("navigation area cost multipliers must be > 0")
            costs[area] = multiplier
        ordered_costs = tuple(sorted(costs.items()))
        object.__setattr__(self, "blocked_nodes", blocked_nodes)
        object.__setattr__(self, "blocked_edges", blocked_edges)
        object.__setattr__(self, "allowed_areas", allowed_areas)
        object.__setattr__(self, "area_costs", ordered_costs)
        object.__setattr__(self, "_area_cost_map", MappingProxyType(dict(ordered_costs)))

    def allows_area(self, area: str) -> bool:
        return self.allowed_areas is None or area in self.allowed_areas

    def multiplier(self, area: str) -> float:
        return self._area_cost_map.get(area, 1.0)

    @property
    def minimum_multiplier(self) -> float:
        return min((1.0, *(multiplier for _, multiplier in self.area_costs)))


@dataclass(frozen=True, slots=True)
class NavigationPath:
    node_ids: tuple[str, ...]
    points: tuple[NavPoint, ...]
    total_cost: float

    def __post_init__(self) -> None:
        object.__setattr__(self, "node_ids", tuple(self.node_ids))
        object.__setattr__(self, "points", tuple(nav_point(point) for point in self.points))
        object.__setattr__(
            self,
            "total_cost",
            _nonnegative(self.total_cost, label="navigation path cost"),
        )
        if not self.points:
            raise ValueError("navigation path must contain at least one point")

    @property
    def total_length(self) -> float:
        return sum(left.distance_to(right) for left, right in pairwise(self.points))


@dataclass(frozen=True, slots=True)
class NavigationQueryDiagnostics:
    found: bool
    start_node: str | None
    goal_node: str | None
    expanded_nodes: int
    visited_nodes: int
    queue_pushes: int
    path_nodes: int
    total_cost: float | None
    start_snap_distance: float | None = None
    goal_snap_distance: float | None = None

    def portable(self) -> dict[str, Any]:
        return {
            "found": self.found,
            "start_node": self.start_node,
            "goal_node": self.goal_node,
            "expanded_nodes": self.expanded_nodes,
            "visited_nodes": self.visited_nodes,
            "queue_pushes": self.queue_pushes,
            "path_nodes": self.path_nodes,
            "total_cost": self.total_cost,
            "start_snap_distance": self.start_snap_distance,
            "goal_snap_distance": self.goal_snap_distance,
        }


@dataclass(frozen=True, slots=True)
class NavigationQueryResult:
    path: NavigationPath | None
    diagnostics: NavigationQueryDiagnostics

    @property
    def found(self) -> bool:
        return self.path is not None


@dataclass(frozen=True, slots=True)
class _Arc:
    target: str
    base_cost: float
    area: str


class NavigationGraph:
    def __init__(
        self,
        nodes: Iterable[NavigationNode],
        edges: Iterable[NavigationEdge],
    ) -> None:
        node_map: dict[str, NavigationNode] = {}
        for node in nodes:
            if node.node_id in node_map:
                raise ValueError(f"duplicate navigation node: {node.node_id}")
            node_map[node.node_id] = node
        if not node_map:
            raise ValueError("navigation graph must contain at least one node")

        adjacency: dict[str, list[_Arc]] = {node_id: [] for node_id in node_map}
        normalized_edges: list[NavigationEdge] = []
        min_ratio = math.inf
        for edge in edges:
            if edge.source not in node_map:
                raise KeyError(f"unknown navigation edge source: {edge.source}")
            if edge.target not in node_map:
                raise KeyError(f"unknown navigation edge target: {edge.target}")
            if edge.source == edge.target:
                raise ValueError("navigation self-edges are not supported")
            normalized_edges.append(edge)
            if not edge.enabled:
                continue
            distance = node_map[edge.source].position.distance_to(node_map[edge.target].position)
            base_cost = distance if edge.cost is None else edge.cost
            min_ratio = 0.0 if distance <= 1e-12 else min(min_ratio, base_cost / distance)
            adjacency[edge.source].append(_Arc(edge.target, base_cost, edge.area))
            if edge.bidirectional:
                adjacency[edge.target].append(_Arc(edge.source, base_cost, edge.area))

        for arcs in adjacency.values():
            arcs.sort(key=lambda arc: (arc.target, arc.area, arc.base_cost))
        self._nodes = MappingProxyType(dict(sorted(node_map.items())))
        self._edges = tuple(normalized_edges)
        self._adjacency = {
            node_id: tuple(arcs) for node_id, arcs in sorted(adjacency.items())
        }
        self._min_cost_ratio = 0.0 if math.isinf(min_ratio) else min_ratio

    @property
    def nodes(self) -> Mapping[str, NavigationNode]:
        return self._nodes

    def node(self, node_id: str) -> NavigationNode:
        try:
            return self._nodes[node_id]
        except KeyError as exc:
            raise KeyError(f"unknown navigation node: {node_id}") from exc

    def nearest_node(
        self,
        position: PointLike,
        *,
        query_filter: NavigationQueryFilter | None = None,
        max_distance: float | None = None,
    ) -> tuple[NavigationNode, float] | None:
        point = nav_point(position)
        query_filter = query_filter or NavigationQueryFilter()
        if max_distance is not None:
            max_distance = _nonnegative(max_distance, label="navigation max snap distance")
        best: tuple[float, str, NavigationNode] | None = None
        for node_id, node in self._nodes.items():
            if node_id in query_filter.blocked_nodes:
                continue
            distance = point.distance_to(node.position)
            candidate = (distance, node_id, node)
            if best is None or candidate[:2] < best[:2]:
                best = candidate
        if best is None or (max_distance is not None and best[0] > max_distance):
            return None
        return (best[2], best[0])

    def _heuristic(
        self,
        node_id: str,
        goal_id: str,
        query_filter: NavigationQueryFilter,
    ) -> float:
        if self._min_cost_ratio <= 0.0:
            return 0.0
        return (
            self.node(node_id).position.distance_to(self.node(goal_id).position)
            * self._min_cost_ratio
            * query_filter.minimum_multiplier
        )

    def find_path(
        self,
        start_node: str,
        goal_node: str,
        *,
        query_filter: NavigationQueryFilter | None = None,
    ) -> NavigationQueryResult:
        self.node(start_node)
        self.node(goal_node)
        query_filter = query_filter or NavigationQueryFilter()
        if start_node in query_filter.blocked_nodes or goal_node in query_filter.blocked_nodes:
            return NavigationQueryResult(
                None,
                NavigationQueryDiagnostics(
                    False, start_node, goal_node, 0, 0, 0, 0, None
                ),
            )

        queue = [(self._heuristic(start_node, goal_node, query_filter), 0.0, start_node)]
        costs = {start_node: 0.0}
        parents: dict[str, str] = {}
        expanded = 0
        pushes = 1
        while queue:
            _, current_cost, current = heapq.heappop(queue)
            if current_cost != costs.get(current):
                continue
            expanded += 1
            if current == goal_node:
                break
            for arc in self._adjacency[current]:
                if arc.target in query_filter.blocked_nodes:
                    continue
                if (current, arc.target) in query_filter.blocked_edges:
                    continue
                if not query_filter.allows_area(arc.area):
                    continue
                candidate = current_cost + arc.base_cost * query_filter.multiplier(arc.area)
                previous = costs.get(arc.target)
                if previous is not None and candidate >= previous - 1e-12:
                    continue
                costs[arc.target] = candidate
                parents[arc.target] = current
                priority = candidate + self._heuristic(arc.target, goal_node, query_filter)
                heapq.heappush(queue, (priority, candidate, arc.target))
                pushes += 1

        if goal_node not in costs:
            return NavigationQueryResult(
                None,
                NavigationQueryDiagnostics(
                    False,
                    start_node,
                    goal_node,
                    expanded,
                    len(costs),
                    pushes,
                    0,
                    None,
                ),
            )

        node_ids = [goal_node]
        while node_ids[-1] != start_node:
            node_ids.append(parents[node_ids[-1]])
        node_ids.reverse()
        path = NavigationPath(
            tuple(node_ids),
            tuple(self.node(node_id).position for node_id in node_ids),
            costs[goal_node],
        )
        return NavigationQueryResult(
            path,
            NavigationQueryDiagnostics(
                True,
                start_node,
                goal_node,
                expanded,
                len(costs),
                pushes,
                len(node_ids),
                costs[goal_node],
            ),
        )

    def query_path(
        self,
        start: PointLike,
        goal: PointLike,
        *,
        query_filter: NavigationQueryFilter | None = None,
        max_snap_distance: float | None = None,
    ) -> NavigationQueryResult:
        start_point = nav_point(start)
        goal_point = nav_point(goal)
        query_filter = query_filter or NavigationQueryFilter()
        start_match = self.nearest_node(
            start_point, query_filter=query_filter, max_distance=max_snap_distance
        )
        goal_match = self.nearest_node(
            goal_point, query_filter=query_filter, max_distance=max_snap_distance
        )
        if start_match is None or goal_match is None:
            return NavigationQueryResult(
                None,
                NavigationQueryDiagnostics(
                    False,
                    start_match[0].node_id if start_match else None,
                    goal_match[0].node_id if goal_match else None,
                    0,
                    0,
                    0,
                    0,
                    None,
                    start_match[1] if start_match else None,
                    goal_match[1] if goal_match else None,
                ),
            )
        result = self.find_path(
            start_match[0].node_id,
            goal_match[0].node_id,
            query_filter=query_filter,
        )
        diagnostics = NavigationQueryDiagnostics(
            result.found,
            start_match[0].node_id,
            goal_match[0].node_id,
            result.diagnostics.expanded_nodes,
            result.diagnostics.visited_nodes,
            result.diagnostics.queue_pushes,
            result.diagnostics.path_nodes,
            result.diagnostics.total_cost,
            start_match[1],
            goal_match[1],
        )
        if result.path is None:
            return NavigationQueryResult(None, diagnostics)
        points = list(result.path.points)
        if start_point.distance_to(points[0]) > 1e-9:
            points.insert(0, start_point)
        if goal_point.distance_to(points[-1]) > 1e-9:
            points.append(goal_point)
        return NavigationQueryResult(
            NavigationPath(result.path.node_ids, tuple(points), result.path.total_cost),
            diagnostics,
        )

    def fingerprint(self) -> str:
        payload = {
            "nodes": [
                [node_id, *node.position.portable()]
                for node_id, node in self._nodes.items()
            ],
            "edges": sorted(
                (
                    edge.source,
                    edge.target,
                    edge.cost,
                    edge.area,
                    edge.bidirectional,
                    edge.enabled,
                )
                for edge in self._edges
            ),
        }
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class NavigationAgentSettings:
    radius: float = 0.4
    max_speed: float = 4.0
    arrival_tolerance: float = 0.05
    neighbor_distance: float = 2.5
    avoidance_strength: float = 1.0
    max_neighbors: int = 8

    def __post_init__(self) -> None:
        object.__setattr__(self, "radius", _nonnegative(self.radius, label="agent radius"))
        object.__setattr__(
            self, "max_speed", _nonnegative(self.max_speed, label="agent max speed")
        )
        object.__setattr__(
            self,
            "arrival_tolerance",
            _nonnegative(self.arrival_tolerance, label="arrival tolerance"),
        )
        object.__setattr__(
            self,
            "neighbor_distance",
            _nonnegative(self.neighbor_distance, label="neighbor distance"),
        )
        object.__setattr__(
            self,
            "avoidance_strength",
            _nonnegative(self.avoidance_strength, label="avoidance strength"),
        )
        if not isinstance(self.max_neighbors, int) or isinstance(self.max_neighbors, bool):
            raise TypeError("navigation max_neighbors must be an integer")
        if self.max_neighbors < 0:
            raise ValueError("navigation max_neighbors must be >= 0")


@dataclass(frozen=True, slots=True)
class NavigationNeighbor:
    agent_id: str
    position: NavPoint | Sequence[float]
    velocity: NavPoint | Sequence[float] = (0.0, 0.0, 0.0)
    radius: float = 0.4

    def __post_init__(self) -> None:
        object.__setattr__(self, "agent_id", _name(self.agent_id, label="agent id"))
        object.__setattr__(self, "position", nav_point(self.position))
        object.__setattr__(self, "velocity", nav_point(self.velocity))
        object.__setattr__(self, "radius", _nonnegative(self.radius, label="neighbor radius"))


class NavigationAgent:
    def __init__(
        self,
        agent_id: str,
        position: PointLike,
        *,
        settings: NavigationAgentSettings | None = None,
    ) -> None:
        self.agent_id = _name(agent_id, label="agent id")
        self.position = nav_point(position)
        self.velocity = NavPoint(0.0, 0.0, 0.0)
        self.settings = settings or NavigationAgentSettings()
        self._path: tuple[NavPoint, ...] = ()
        self._waypoint = 0
        self.avoidance_neighbors = 0

    @property
    def path(self) -> tuple[NavPoint, ...]:
        return self._path

    @property
    def waypoint_index(self) -> int:
        return self._waypoint

    @property
    def arrived(self) -> bool:
        return not self._path or self._waypoint >= len(self._path)

    def clear_path(self) -> None:
        self._path = ()
        self._waypoint = 0
        self.velocity = NavPoint(0.0, 0.0, 0.0)

    def set_path(self, path: NavigationPath | Sequence[PointLike]) -> None:
        points = path.points if isinstance(path, NavigationPath) else path
        self._path = tuple(nav_point(point) for point in points)
        self._waypoint = 0
        self._skip_reached()
        self.velocity = NavPoint(0.0, 0.0, 0.0)

    def _skip_reached(self) -> None:
        while self._waypoint < len(self._path):
            target = self._path[self._waypoint]
            if self.position.distance_to(target) > self.settings.arrival_tolerance:
                return
            self.position = target
            self._waypoint += 1

    def remaining_distance(self) -> float:
        if self.arrived:
            return 0.0
        total = self.position.distance_to(self._path[self._waypoint])
        total += sum(
            left.distance_to(right)
            for left, right in pairwise(self._path[self._waypoint :])
        )
        return total

    def desired_velocity(self) -> NavPoint:
        self._skip_reached()
        if self.arrived or self.settings.max_speed <= 0.0:
            return NavPoint(0.0, 0.0, 0.0)
        return (
            self._path[self._waypoint] - self.position
        ).normalized() * self.settings.max_speed

    def _neighbors(
        self, neighbors: Iterable[NavigationNeighbor]
    ) -> list[tuple[float, NavigationNeighbor]]:
        candidates = []
        for neighbor in neighbors:
            if neighbor.agent_id == self.agent_id:
                continue
            distance = self.position.distance_to(neighbor.position)
            if distance <= self.settings.neighbor_distance:
                candidates.append((distance, neighbor.agent_id, neighbor))
        candidates.sort(key=lambda item: (item[0], item[1]))
        return [
            (distance, neighbor)
            for distance, _, neighbor in candidates[: self.settings.max_neighbors]
        ]

    def compute_velocity(
        self, neighbors: Iterable[NavigationNeighbor] = ()
    ) -> NavPoint:
        desired = self.desired_velocity()
        if self.arrived:
            self.avoidance_neighbors = 0
            return desired
        influential = self._neighbors(neighbors)
        self.avoidance_neighbors = len(influential)
        if not influential or self.settings.avoidance_strength <= 0.0:
            return desired
        separation = NavPoint(0.0, 0.0, 0.0)
        for distance, neighbor in influential:
            offset = self.position - neighbor.position
            if distance <= 1e-9:
                direction = NavPoint(
                    1.0 if self.agent_id < neighbor.agent_id else -1.0,
                    0.0,
                    0.0,
                )
            else:
                direction = offset * (1.0 / distance)
            safe = max(
                self.settings.radius + neighbor.radius,
                self.settings.neighbor_distance * 0.25,
                1e-9,
            )
            proximity = max(
                0.0,
                (self.settings.neighbor_distance - distance)
                / max(self.settings.neighbor_distance, 1e-9),
            )
            overlap = 1.0 + max(0.0, safe - distance) / safe
            separation = separation + direction * (
                self.settings.max_speed
                * self.settings.avoidance_strength
                * proximity
                * overlap
            )
        adjusted = desired + separation
        speed = adjusted.length
        if speed > self.settings.max_speed > 0.0:
            adjusted = adjusted * (self.settings.max_speed / speed)
        return adjusted

    def _advance(self, distance_budget: float) -> None:
        remaining = max(0.0, distance_budget)
        while remaining > 0.0 and not self.arrived:
            target = self._path[self._waypoint]
            delta = target - self.position
            distance = delta.length
            if remaining >= distance:
                self.position = target
                self._waypoint += 1
                remaining -= distance
            else:
                self.position = self.position + delta * (remaining / distance)
                remaining = 0.0
        self._skip_reached()

    def step(
        self,
        dt: float,
        neighbors: Iterable[NavigationNeighbor] = (),
    ) -> NavPoint:
        dt = _nonnegative(dt, label="navigation dt")
        if dt == 0.0 or self.arrived:
            self.velocity = NavPoint(0.0, 0.0, 0.0)
            return self.position
        influential = self._neighbors(neighbors)
        previous = self.position
        if not influential or self.settings.avoidance_strength <= 0.0:
            self.avoidance_neighbors = len(influential)
            self._advance(self.settings.max_speed * dt)
        else:
            velocity = self.compute_velocity(neighbor for _, neighbor in influential)
            self.position = self.position + velocity * dt
            self._skip_reached()
        self.velocity = (self.position - previous) * (1.0 / dt)
        if self.arrived:
            self.velocity = NavPoint(0.0, 0.0, 0.0)
        return self.position

    def snapshot(self) -> NavigationNeighbor:
        return NavigationNeighbor(
            self.agent_id, self.position, self.velocity, self.settings.radius
        )


@dataclass(frozen=True, slots=True)
class NavigationRuntimeDiagnostics:
    query_count: int
    failed_queries: int
    expanded_nodes: int
    agent_count: int
    moving_agents: int
    arrived_agents: int
    total_remaining_distance: float
    steps: int
    last_avoidance_candidate_checks: int
    peak_avoidance_candidate_checks: int

    def portable(self) -> dict[str, Any]:
        return {
            "query_count": self.query_count,
            "failed_queries": self.failed_queries,
            "expanded_nodes": self.expanded_nodes,
            "agent_count": self.agent_count,
            "moving_agents": self.moving_agents,
            "arrived_agents": self.arrived_agents,
            "total_remaining_distance": self.total_remaining_distance,
            "steps": self.steps,
            "last_avoidance_candidate_checks": self.last_avoidance_candidate_checks,
            "peak_avoidance_candidate_checks": self.peak_avoidance_candidate_checks,
        }


class NavigationRuntime:
    def __init__(self, graph: NavigationGraph) -> None:
        self.graph = graph
        self._agents: dict[str, NavigationAgent] = {}
        self.query_count = 0
        self.failed_queries = 0
        self.expanded_nodes = 0
        self.steps = 0
        self.last_avoidance_candidate_checks = 0
        self.peak_avoidance_candidate_checks = 0
        self.last_query: NavigationQueryDiagnostics | None = None

    @property
    def agents(self) -> Mapping[str, NavigationAgent]:
        return MappingProxyType(self._agents)

    def add_agent(self, agent: NavigationAgent) -> NavigationAgent:
        if agent.agent_id in self._agents:
            raise ValueError(f"duplicate navigation agent: {agent.agent_id}")
        self._agents[agent.agent_id] = agent
        return agent

    def agent(self, agent_id: str) -> NavigationAgent:
        try:
            return self._agents[agent_id]
        except KeyError as exc:
            raise KeyError(f"unknown navigation agent: {agent_id}") from exc

    def query_path(
        self,
        start: PointLike,
        goal: PointLike,
        *,
        query_filter: NavigationQueryFilter | None = None,
        max_snap_distance: float | None = None,
    ) -> NavigationQueryResult:
        result = self.graph.query_path(
            start,
            goal,
            query_filter=query_filter,
            max_snap_distance=max_snap_distance,
        )
        self.query_count += 1
        self.expanded_nodes += result.diagnostics.expanded_nodes
        self.failed_queries += int(not result.found)
        self.last_query = result.diagnostics
        return result

    def set_target(
        self,
        agent_id: str,
        target: PointLike,
        *,
        query_filter: NavigationQueryFilter | None = None,
        max_snap_distance: float | None = None,
    ) -> NavigationQueryResult:
        agent = self.agent(agent_id)
        result = self.query_path(
            agent.position,
            target,
            query_filter=query_filter,
            max_snap_distance=max_snap_distance,
        )
        agent.clear_path() if result.path is None else agent.set_path(result.path)
        return result

    @staticmethod
    def _cell(point: NavPoint, size: float) -> tuple[int, int, int]:
        return (
            math.floor(point.x / size),
            math.floor(point.y / size),
            math.floor(point.z / size),
        )

    def step(self, dt: float) -> None:
        dt = _nonnegative(dt, label="navigation dt")
        snapshots = {
            agent_id: agent.snapshot()
            for agent_id, agent in sorted(self._agents.items())
        }
        max_distance = max(
            (agent.settings.neighbor_distance for agent in self._agents.values()),
            default=0.0,
        )
        cell_size = max(max_distance, 1e-6)
        buckets: dict[tuple[int, int, int], list[NavigationNeighbor]] = {}
        for snapshot in snapshots.values():
            buckets.setdefault(self._cell(snapshot.position, cell_size), []).append(snapshot)
        checks = 0
        for agent_id, agent in sorted(self._agents.items()):
            center = self._cell(snapshots[agent_id].position, cell_size)
            neighbors = []
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    for dz in (-1, 0, 1):
                        cell = (center[0] + dx, center[1] + dy, center[2] + dz)
                        for neighbor in buckets.get(cell, ()):
                            if neighbor.agent_id == agent_id:
                                continue
                            checks += 1
                            if (
                                snapshots[agent_id].position.distance_to(neighbor.position)
                                <= agent.settings.neighbor_distance
                            ):
                                neighbors.append(neighbor)
            agent.step(dt, neighbors)
        self.steps += 1
        self.last_avoidance_candidate_checks = checks
        self.peak_avoidance_candidate_checks = max(
            self.peak_avoidance_candidate_checks, checks
        )

    def diagnostics(self) -> NavigationRuntimeDiagnostics:
        arrived = sum(agent.arrived for agent in self._agents.values())
        return NavigationRuntimeDiagnostics(
            self.query_count,
            self.failed_queries,
            self.expanded_nodes,
            len(self._agents),
            len(self._agents) - arrived,
            arrived,
            sum(agent.remaining_distance() for agent in self._agents.values()),
            self.steps,
            self.last_avoidance_candidate_checks,
            self.peak_avoidance_candidate_checks,
        )

    def state_fingerprint(self) -> str:
        payload = {
            "graph": self.graph.fingerprint(),
            "diagnostics": self.diagnostics().portable(),
            "agents": [
                {
                    "id": agent_id,
                    "position": list(agent.position.portable()),
                    "velocity": list(agent.velocity.portable()),
                    "waypoint": agent.waypoint_index,
                    "path": [list(point.portable()) for point in agent.path],
                }
                for agent_id, agent in sorted(self._agents.items())
            ],
            "last_query": self.last_query.portable() if self.last_query else None,
        }
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()
