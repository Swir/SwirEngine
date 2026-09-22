from __future__ import annotations

import hashlib
import json
import os
import tempfile
from dataclasses import asdict, dataclass, replace
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any

from .navigation15 import (
    NavigationAgent,
    NavigationAgentSettings,
    NavigationEdge,
    NavigationGraph,
    NavigationNode,
    NavigationQueryFilter,
    NavigationQueryResult,
    NavigationRuntime,
)

NAVIGATION_ASSET_FORMAT = "swirengine.navigation-profile"
NAVIGATION_ASSET_VERSION = 1
DEFAULT_NAVIGATION_PATH = "config/navigation.json"


class EditorNavigationToolingError(ValueError):
    """Raised when project navigation data cannot be authored safely."""


@dataclass(frozen=True, slots=True)
class NavigationNodeSpec21:
    name: str
    position: tuple[float, float, float]

    def __post_init__(self) -> None:
        name = _name(self.name, "node name")
        position = _point(self.position, "node position")
        object.__setattr__(self, "name", name)
        object.__setattr__(self, "position", position)
        NavigationNode(name, position)


@dataclass(frozen=True, slots=True)
class NavigationEdgeSpec21:
    name: str
    source: str
    target: str
    cost: float | None = None
    area: str = "default"
    bidirectional: bool = True
    enabled: bool = True

    def __post_init__(self) -> None:
        name = _name(self.name, "edge name")
        source = _name(self.source, "edge source")
        target = _name(self.target, "edge target")
        area = _name(self.area, "edge area")
        edge = NavigationEdge(
            source,
            target,
            cost=self.cost,
            area=area,
            bidirectional=self.bidirectional,
            enabled=self.enabled,
        )
        object.__setattr__(self, "name", name)
        object.__setattr__(self, "source", edge.source)
        object.__setattr__(self, "target", edge.target)
        object.__setattr__(self, "cost", edge.cost)
        object.__setattr__(self, "area", edge.area)
        object.__setattr__(self, "bidirectional", edge.bidirectional)
        object.__setattr__(self, "enabled", edge.enabled)


@dataclass(frozen=True, slots=True)
class NavigationAgentSpec21:
    name: str
    position: tuple[float, float, float]
    radius: float = 0.4
    max_speed: float = 4.0
    arrival_tolerance: float = 0.05
    neighbor_distance: float = 2.5
    avoidance_strength: float = 1.0
    max_neighbors: int = 8

    def __post_init__(self) -> None:
        name = _name(self.name, "agent name")
        position = _point(self.position, "agent position")
        settings = self.settings()
        object.__setattr__(self, "name", name)
        object.__setattr__(self, "position", position)
        object.__setattr__(self, "radius", settings.radius)
        object.__setattr__(self, "max_speed", settings.max_speed)
        object.__setattr__(self, "arrival_tolerance", settings.arrival_tolerance)
        object.__setattr__(self, "neighbor_distance", settings.neighbor_distance)
        object.__setattr__(self, "avoidance_strength", settings.avoidance_strength)
        object.__setattr__(self, "max_neighbors", settings.max_neighbors)

    def settings(self) -> NavigationAgentSettings:
        return NavigationAgentSettings(
            radius=self.radius,
            max_speed=self.max_speed,
            arrival_tolerance=self.arrival_tolerance,
            neighbor_distance=self.neighbor_distance,
            avoidance_strength=self.avoidance_strength,
            max_neighbors=self.max_neighbors,
        )


@dataclass(frozen=True, slots=True)
class EditorNavigationSnapshot21:
    path: str
    nodes: tuple[NavigationNodeSpec21, ...]
    edges: tuple[NavigationEdgeSpec21, ...]
    agents: tuple[NavigationAgentSpec21, ...]
    dirty: bool


class EditorNavigationTooling21:
    """Deterministic editor authoring over the shipping Navigation 2 runtime."""

    def __init__(self, project_root: str | Path, *, path: str = DEFAULT_NAVIGATION_PATH) -> None:
        self.project_root = Path(project_root).expanduser().resolve()
        self.relative_path = _relative_path(path)
        self._nodes: dict[str, NavigationNodeSpec21] = {}
        self._edges: dict[str, NavigationEdgeSpec21] = {}
        self._agents: dict[str, NavigationAgentSpec21] = {}
        self._saved_fingerprint = self._fingerprint()
        if self.target.is_file():
            self.load()

    @property
    def target(self) -> Path:
        return _target(self.project_root, self.relative_path)

    @property
    def dirty(self) -> bool:
        return self._fingerprint() != self._saved_fingerprint

    def snapshot(self) -> EditorNavigationSnapshot21:
        return EditorNavigationSnapshot21(
            self.relative_path,
            self._ordered_nodes(),
            self._ordered_edges(),
            self._ordered_agents(),
            self.dirty,
        )

    def create_node(self, name: str, position: tuple[float, float, float]) -> EditorNavigationSnapshot21:
        node = NavigationNodeSpec21(name, position)
        if node.name in self._nodes:
            raise EditorNavigationToolingError(f"navigation node {node.name!r} already exists")
        self._nodes[node.name] = node
        return self.snapshot()

    def update_node(self, name: str, position: tuple[float, float, float]) -> EditorNavigationSnapshot21:
        self._nodes[name] = replace(self._require_node(name), position=position)
        self._validate_graph()
        return self.snapshot()

    def rename_node(self, name: str, new_name: str) -> EditorNavigationSnapshot21:
        current = self._require_node(name)
        renamed = replace(current, name=new_name)
        if renamed.name != name and renamed.name in self._nodes:
            raise EditorNavigationToolingError(f"navigation node {renamed.name!r} already exists")
        edges = {
            edge_name: replace(
                edge,
                source=renamed.name if edge.source == name else edge.source,
                target=renamed.name if edge.target == name else edge.target,
            )
            for edge_name, edge in self._edges.items()
        }
        del self._nodes[name]
        self._nodes[renamed.name] = renamed
        self._edges = edges
        self._validate_graph()
        return self.snapshot()

    def remove_node(self, name: str) -> EditorNavigationSnapshot21:
        self._require_node(name)
        if any(edge.source == name or edge.target == name for edge in self._edges.values()):
            raise EditorNavigationToolingError("remove connected navigation edges first")
        del self._nodes[name]
        return self.snapshot()

    def create_edge(
        self,
        name: str,
        source: str,
        target: str,
        *,
        cost: float | None = None,
        area: str = "default",
        bidirectional: bool = True,
        enabled: bool = True,
    ) -> EditorNavigationSnapshot21:
        edge = NavigationEdgeSpec21(name, source, target, cost, area, bidirectional, enabled)
        if edge.name in self._edges:
            raise EditorNavigationToolingError(f"navigation edge {edge.name!r} already exists")
        self._require_node(edge.source)
        self._require_node(edge.target)
        self._edges[edge.name] = edge
        self._validate_graph()
        return self.snapshot()

    def update_edge(self, name: str, **changes: Any) -> EditorNavigationSnapshot21:
        if "name" in changes:
            raise EditorNavigationToolingError("edge name changes require remove/create")
        edge = replace(self._require_edge(name), **changes)
        self._require_node(edge.source)
        self._require_node(edge.target)
        self._edges[name] = edge
        self._validate_graph()
        return self.snapshot()

    def remove_edge(self, name: str) -> EditorNavigationSnapshot21:
        self._require_edge(name)
        del self._edges[name]
        return self.snapshot()

    def create_agent(
        self,
        name: str,
        position: tuple[float, float, float],
        **settings: Any,
    ) -> EditorNavigationSnapshot21:
        agent = NavigationAgentSpec21(name, position, **settings)
        if agent.name in self._agents:
            raise EditorNavigationToolingError(f"navigation agent {agent.name!r} already exists")
        self._agents[agent.name] = agent
        return self.snapshot()

    def update_agent(self, name: str, **changes: Any) -> EditorNavigationSnapshot21:
        if "name" in changes:
            raise EditorNavigationToolingError("agent name changes require remove/create")
        self._agents[name] = replace(self._require_agent(name), **changes)
        return self.snapshot()

    def remove_agent(self, name: str) -> EditorNavigationSnapshot21:
        self._require_agent(name)
        del self._agents[name]
        return self.snapshot()

    def build_graph(self) -> NavigationGraph:
        if not self._nodes:
            raise EditorNavigationToolingError("navigation graph must contain at least one node")
        try:
            return NavigationGraph(
                (NavigationNode(node.name, node.position) for node in self._ordered_nodes()),
                (
                    NavigationEdge(
                        edge.source,
                        edge.target,
                        cost=edge.cost,
                        area=edge.area,
                        bidirectional=edge.bidirectional,
                        enabled=edge.enabled,
                    )
                    for edge in self._ordered_edges()
                ),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise EditorNavigationToolingError(str(exc)) from exc

    def build_runtime(self) -> NavigationRuntime:
        runtime = NavigationRuntime(self.build_graph())
        for spec in self._ordered_agents():
            runtime.add_agent(NavigationAgent(spec.name, spec.position, settings=spec.settings()))
        return runtime

    def preview_path(
        self,
        start: tuple[float, float, float],
        goal: tuple[float, float, float],
        *,
        allowed_areas: frozenset[str] | None = None,
        area_costs: tuple[tuple[str, float], ...] = (),
        max_snap_distance: float | None = None,
    ) -> NavigationQueryResult:
        query_filter = NavigationQueryFilter(allowed_areas=allowed_areas, area_costs=area_costs)
        return self.build_graph().query_path(
            start, goal, query_filter=query_filter, max_snap_distance=max_snap_distance
        )

    def save(self) -> EditorNavigationSnapshot21:
        self._validate_graph()
        target = self.target
        target.parent.mkdir(parents=True, exist_ok=True)
        target = self.target
        temporary: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                "w", encoding="utf-8", newline="\n", dir=target.parent, delete=False
            ) as handle:
                handle.write(self._serialized_text())
                handle.flush()
                os.fsync(handle.fileno())
                temporary = Path(handle.name)
            target = self.target
            os.replace(temporary, target)
            temporary = None
        except OSError as exc:
            raise EditorNavigationToolingError(f"cannot save navigation configuration: {exc}") from exc
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
        self._saved_fingerprint = self._fingerprint()
        return self.snapshot()

    def load(self) -> EditorNavigationSnapshot21:
        try:
            payload = json.loads(self.target.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise EditorNavigationToolingError(f"cannot load navigation configuration: {exc}") from exc
        nodes, edges, agents = _decode(payload)
        self._nodes = _unique(nodes, "node")
        self._edges = _unique(edges, "edge")
        self._agents = _unique(agents, "agent")
        self._validate_graph()
        self._saved_fingerprint = self._fingerprint()
        return self.snapshot()

    def _validate_graph(self) -> None:
        if self._nodes:
            self.build_graph()
        elif self._edges:
            raise EditorNavigationToolingError("navigation edges require nodes")

    def _require_node(self, name: str) -> NavigationNodeSpec21:
        try:
            return self._nodes[name]
        except KeyError as exc:
            raise EditorNavigationToolingError(f"unknown navigation node {name!r}") from exc

    def _require_edge(self, name: str) -> NavigationEdgeSpec21:
        try:
            return self._edges[name]
        except KeyError as exc:
            raise EditorNavigationToolingError(f"unknown navigation edge {name!r}") from exc

    def _require_agent(self, name: str) -> NavigationAgentSpec21:
        try:
            return self._agents[name]
        except KeyError as exc:
            raise EditorNavigationToolingError(f"unknown navigation agent {name!r}") from exc

    def _ordered_nodes(self) -> tuple[NavigationNodeSpec21, ...]:
        return tuple(self._nodes[name] for name in sorted(self._nodes))

    def _ordered_edges(self) -> tuple[NavigationEdgeSpec21, ...]:
        return tuple(self._edges[name] for name in sorted(self._edges))

    def _ordered_agents(self) -> tuple[NavigationAgentSpec21, ...]:
        return tuple(self._agents[name] for name in sorted(self._agents))

    def _payload(self) -> dict[str, Any]:
        return {
            "format": NAVIGATION_ASSET_FORMAT,
            "version": NAVIGATION_ASSET_VERSION,
            "nodes": [asdict(item) for item in self._ordered_nodes()],
            "edges": [asdict(item) for item in self._ordered_edges()],
            "agents": [asdict(item) for item in self._ordered_agents()],
        }

    def _serialized_text(self) -> str:
        return json.dumps(
            self._payload(), ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False
        ) + "\n"

    def _fingerprint(self) -> str:
        encoded = json.dumps(
            self._payload(), sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode()
        return hashlib.sha256(encoded).hexdigest()


def _decode(
    payload: Any,
) -> tuple[tuple[NavigationNodeSpec21, ...], tuple[NavigationEdgeSpec21, ...], tuple[NavigationAgentSpec21, ...]]:
    if not isinstance(payload, dict):
        raise EditorNavigationToolingError("navigation configuration must be an object")
    expected = {"format", "version", "nodes", "edges", "agents"}
    if set(payload) != expected:
        raise EditorNavigationToolingError("navigation configuration fields do not match schema")
    if payload["format"] != NAVIGATION_ASSET_FORMAT or payload["version"] != NAVIGATION_ASSET_VERSION:
        raise EditorNavigationToolingError("unsupported navigation configuration")
    return (
        _items(payload["nodes"], NavigationNodeSpec21, "nodes"),
        _items(payload["edges"], NavigationEdgeSpec21, "edges"),
        _items(payload["agents"], NavigationAgentSpec21, "agents"),
    )


def _items(value: Any, model: type[Any], label: str) -> tuple[Any, ...]:
    if not isinstance(value, list):
        raise EditorNavigationToolingError(f"navigation {label} must be an array")
    fields = set(model.__dataclass_fields__)
    result = []
    for item in value:
        if not isinstance(item, dict) or set(item) - fields:
            raise EditorNavigationToolingError(f"invalid navigation {label} entry")
        try:
            result.append(model(**item))
        except (TypeError, ValueError) as exc:
            raise EditorNavigationToolingError(f"invalid navigation {label} entry: {exc}") from exc
    return tuple(result)


def _unique(items: tuple[Any, ...], label: str) -> dict[str, Any]:
    result = {item.name: item for item in items}
    if len(result) != len(items):
        raise EditorNavigationToolingError(f"duplicate navigation {label} name")
    return result


def _name(value: str, label: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{label} must be a string")
    value = value.strip()
    if not value:
        raise EditorNavigationToolingError(f"{label} cannot be empty")
    return value


def _point(value: Any, label: str) -> tuple[float, float, float]:
    if isinstance(value, (str, bytes)):
        raise EditorNavigationToolingError(f"{label} must contain three values")
    try:
        values = tuple(float(item) for item in value)
    except (TypeError, ValueError) as exc:
        raise EditorNavigationToolingError(f"{label} must contain three numeric values") from exc
    if len(values) != 3 or not all(map(__import__("math").isfinite, values)):
        raise EditorNavigationToolingError(f"{label} must contain three finite values")
    return values


def _relative_path(value: str | Path) -> str:
    raw = str(value).strip()
    normalized = raw.replace("\\", "/")
    posix = PurePosixPath(normalized)
    windows = PureWindowsPath(raw)
    if not normalized or posix.is_absolute() or windows.is_absolute() or windows.drive or ".." in posix.parts:
        raise EditorNavigationToolingError("navigation path must stay project-relative")
    return posix.as_posix()


def _target(root: Path, relative: str) -> Path:
    resolved = (root / PurePosixPath(relative)).resolve(strict=False)
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise EditorNavigationToolingError("navigation path escapes the project root") from exc
    return resolved
