from __future__ import annotations

import hashlib
import json
import math
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
    """Raised when creator navigation configuration cannot be authored safely."""


@dataclass(frozen=True, slots=True)
class NavigationNodeSpec21:
    name: str
    position: tuple[float, float, float]

    def __post_init__(self) -> None:
        name = _name(self.name, label="navigation node name")
        position = _float_tuple(self.position, 3, label="navigation node position")
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
        name = _name(self.name, label="navigation edge name")
        source = _name(self.source, label="navigation edge source")
        target = _name(self.target, label="navigation edge target")
        area = _name(self.area, label="navigation edge area")
        if source == target:
            raise EditorNavigationToolingError("navigation self-edges are not supported")
        cost = self.cost
        if cost is not None:
            cost = _finite_float(cost, label="navigation edge cost")
            if cost < 0.0:
                raise EditorNavigationToolingError("navigation edge cost must be >= 0")
        object.__setattr__(self, "name", name)
        object.__setattr__(self, "source", source)
        object.__setattr__(self, "target", target)
        object.__setattr__(self, "area", area)
        object.__setattr__(self, "cost", cost)
        object.__setattr__(self, "bidirectional", bool(self.bidirectional))
        object.__setattr__(self, "enabled", bool(self.enabled))
        NavigationEdge(source, target, cost=cost, area=area, bidirectional=self.bidirectional, enabled=self.enabled)


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
        name = _name(self.name, label="navigation agent name")
        position = _float_tuple(self.position, 3, label="navigation agent position")
        settings = NavigationAgentSettings(
            radius=self.radius,
            max_speed=self.max_speed,
            arrival_tolerance=self.arrival_tolerance,
            neighbor_distance=self.neighbor_distance,
            avoidance_strength=self.avoidance_strength,
            max_neighbors=self.max_neighbors,
        )
        object.__setattr__(self, "name", name)
        object.__setattr__(self, "position", position)
        object.__setattr__(self, "radius", settings.radius)
        object.__setattr__(self, "max_speed", settings.max_speed)
        object.__setattr__(self, "arrival_tolerance", settings.arrival_tolerance)
        object.__setattr__(self, "neighbor_distance", settings.neighbor_distance)
        object.__setattr__(self, "avoidance_strength", settings.avoidance_strength)
        object.__setattr__(self, "max_neighbors", settings.max_neighbors)

    def runtime_settings(self) -> NavigationAgentSettings:
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

    @property
    def node_count(self) -> int:
        return len(self.nodes)

    @property
    def edge_count(self) -> int:
        return len(self.edges)

    @property
    def agent_count(self) -> int:
        return len(self.agents)


class EditorNavigationTooling21:
    """Project-scoped navigation/agent authoring backed by the shipping Navigation 2 runtime."""

    def __init__(
        self,
        project_root: str | Path,
        *,
        path: str = DEFAULT_NAVIGATION_PATH,
    ) -> None:
        self.project_root = Path(project_root).expanduser().resolve()
        self.relative_path = _project_relative_path(path, label="navigation path")
        self._nodes: dict[str, NavigationNodeSpec21] = {}
        self._edges: dict[str, NavigationEdgeSpec21] = {}
        self._agents: dict[str, NavigationAgentSpec21] = {}
        self._saved_fingerprint = self._fingerprint()
        if self.target.is_file():
            self.load()

    @property
    def target(self) -> Path:
        return _project_target(self.project_root, self.relative_path, label="navigation path")

    @property
    def dirty(self) -> bool:
        return self._fingerprint() != self._saved_fingerprint

    def snapshot(self) -> EditorNavigationSnapshot21:
        return EditorNavigationSnapshot21(
            path=self.relative_path,
            nodes=tuple(self._nodes[name] for name in sorted(self._nodes)),
            edges=tuple(self._edges[name] for name in sorted(self._edges)),
            agents=tuple(self._agents[name] for name in sorted(self._agents)),
            dirty=self.dirty,
        )

    def create_node(
        self, name: str, position: tuple[float, float, float]
    ) -> EditorNavigationSnapshot21:
        node = NavigationNodeSpec21(name, position)
        if node.name in self._nodes:
            raise EditorNavigationToolingError(f"navigation node {node.name!r} already exists")
        self._nodes[node.name] = node
        return self.snapshot()

    def update_node(
        self, name: str, *, position: tuple[float, float, float]
    ) -> EditorNavigationSnapshot21:
        current = self._require_node(name)
        self._nodes[name] = replace(current, position=position)
        self._validate_graph_if_possible()
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
        self._validate_graph_if_possible()
        return self.snapshot()

    def remove_node(self, name: str) -> EditorNavigationSnapshot21:
        self._require_node(name)
        used_by = sorted(
            edge.name
            for edge in self._edges.values()
            if edge.source == name or edge.target == name
        )
        if used_by:
            raise EditorNavigationToolingError(
                f"navigation node {name!r} is referenced by edges: {', '.join(used_by)}"
            )
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
        edge = NavigationEdgeSpec21(
            name,
            source,
            target,
            cost=cost,
            area=area,
            bidirectional=bidirectional,
            enabled=enabled,
        )
        if edge.name in self._edges:
            raise EditorNavigationToolingError(f"navigation edge {edge.name!r} already exists")
        self._require_node(edge.source)
        self._require_node(edge.target)
        self._edges[edge.name] = edge
        self._validate_graph_if_possible()
        return self.snapshot()

    def update_edge(self, name: str, **changes: Any) -> EditorNavigationSnapshot21:
        current = self._require_edge(name)
        if "name" in changes and str(changes["name"]).strip() != current.name:
            raise EditorNavigationToolingError("use rename_edge() to change an edge name")
        updated = replace(current, **changes)
        self._require_node(updated.source)
        self._require_node(updated.target)
        self._edges[name] = updated
        self._validate_graph_if_possible()
        return self.snapshot()

    def rename_edge(self, name: str, new_name: str) -> EditorNavigationSnapshot21:
        current = self._require_edge(name)
        renamed = replace(current, name=new_name)
        if renamed.name != name and renamed.name in self._edges:
            raise EditorNavigationToolingError(f"navigation edge {renamed.name!r} already exists")
        del self._edges[name]
        self._edges[renamed.name] = renamed
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
        current = self._require_agent(name)
        if "name" in changes and str(changes["name"]).strip() != current.name:
            raise EditorNavigationToolingError("use rename_agent() to change an agent name")
        self._agents[name] = replace(current, **changes)
        return self.snapshot()

    def rename_agent(self, name: str, new_name: str) -> EditorNavigationSnapshot21:
        current = self._require_agent(name)
        renamed = replace(current, name=new_name)
        if renamed.name != name and renamed.name in self._agents:
            raise EditorNavigationToolingError(f"navigation agent {renamed.name!r} already exists")
        del self._agents[name]
        self._agents[renamed.name] = renamed
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
                (
                    NavigationNode(node.name, node.position)
                    for node in self.snapshot().nodes
                ),
                (
                    NavigationEdge(
                        edge.source,
                        edge.target,
                        cost=edge.cost,
                        area=edge.area,
                        bidirectional=edge.bidirectional,
                        enabled=edge.enabled,
                    )
                    for edge in self.snapshot().edges
                ),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise EditorNavigationToolingError(str(exc)) from exc

    def build_runtime(self) -> NavigationRuntime:
        runtime = NavigationRuntime(self.build_graph())
        for spec in self.snapshot().agents:
            runtime.add_agent(
                NavigationAgent(spec.name, spec.position, settings=spec.runtime_settings())
            )
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
        query_filter = NavigationQueryFilter(
            allowed_areas=allowed_areas,
            area_costs=area_costs,
        )
        return self.build_graph().query_path(
            start,
            goal,
            query_filter=query_filter,
            max_snap_distance=max_snap_distance,
        )

    def load(self) -> EditorNavigationSnapshot21:
        target = self.target
        try:
            payload = json.loads(target.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise EditorNavigationToolingError(
                f"cannot load navigation configuration: {exc}"
            ) from exc
        nodes, edges, agents = _decode_payload(payload)
        self._nodes = {node.name: node for node in nodes}
        self._edges = {edge.name: edge for edge in edges}
        self._agents = {agent.name: agent for agent in agents}
        if len(self._nodes) != len(nodes):
            raise EditorNavigationToolingError("duplicate navigation node name")
        if len(self._edges) != len(edges):
            raise EditorNavigationToolingError("duplicate navigation edge name")
        if len(self._agents) != len(agents):
            raise EditorNavigationToolingError("duplicate navigation agent name")
        self._validate_graph_if_possible()
        self._saved_fingerprint = self._fingerprint()
        return self.snapshot()

    def save(self) -> EditorNavigationSnapshot21:
        self._validate_graph_if_possible()
        target = self.target
        target.parent.mkdir(parents=True, exist_ok=True)
        target = self.target
        content = self._serialized_text()
        temporary: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                "w",
                encoding="utf-8",
                newline="\n",
                dir=target.parent,
                prefix=f".{target.name}.",
                suffix=".tmp",
                delete=False,
            ) as handle:
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
                temporary = Path(handle.name)
            target = self.target
            os.replace(temporary, target)
            temporary = None
        except OSError as exc:
            raise EditorNavigationToolingError(
                f"cannot save navigation configuration: {exc}"
            ) from exc
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
        self._saved_fingerprint = self._fingerprint()
        return self.snapshot()

    def _require_node(self, name: str) -> NavigationNodeSpec21:
        try:
            return self._nodes[str(name)]
        except KeyError as exc:
            raise EditorNavigationToolingError(f"unknown navigation node {name!r}") from exc

    def _require_edge(self, name: str) -> NavigationEdgeSpec21:
        try:
            return self._edges[str(name)]
        except KeyError as exc:
            raise EditorNavigationToolingError(f"unknown navigation edge {name!r}") from exc

    def _require_agent(self, name: str) -> NavigationAgentSpec21:
        try:
            return self._agents[str(name)]
        except KeyError as exc:
            raise EditorNavigationToolingError(f"unknown navigation agent {name!r}") from exc

    def _validate_graph_if_possible(self) -> None:
        if self._nodes:
            self.build_graph()
        elif self._edges:
            raise EditorNavigationToolingError("navigation edges require at least one node")

    def _payload(self) -> dict[str, Any]:
        snapshot = self.snapshot()
        return {
            "format": NAVIGATION_ASSET_FORMAT,
            "version": NAVIGATION_ASSET_VERSION,
            "nodes": [asdict(node) for node in snapshot.nodes],
            "edges": [asdict(edge) for edge in snapshot.edges],
            "agents": [asdict(agent) for agent in snapshot.agents],
        }

    def _serialized_text(self) -> str:
        return json.dumps(
            self._payload(),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
            allow_nan=False,
        ) + "\n"

    def _fingerprint(self) -> str:
        content = json.dumps(
            self._payload(),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
        return hashlib.sha256(content).hexdigest()


def _decode_payload(
    payload: Any,
) -> tuple[
    tuple[NavigationNodeSpec21, ...],
    tuple[NavigationEdgeSpec21, ...],
    tuple[NavigationAgentSpec21, ...],
]:
    if not isinstance(payload, dict):
        raise EditorNavigationToolingError("navigation configuration must be a JSON object")
    expected = {"format", "version", "nodes", "edges", "agents"}
    extra = set(payload) - expected
    if extra:
        raise EditorNavigationToolingError(
            f"unknown navigation configuration fields: {', '.join(sorted(extra))}"
        )
    if payload.get("format") != NAVIGATION_ASSET_FORMAT:
        raise EditorNavigationToolingError("unsupported navigation configuration format")
    if payload.get("version") != NAVIGATION_ASSET_VERSION:
        raise EditorNavigationToolingError("unsupported navigation configuration version")
    nodes = _decode_items(payload.get("nodes"), NavigationNodeSpec21, "nodes")
    edges = _decode_items(payload.get("edges"), NavigationEdgeSpec21, "edges")
    agents = _decode_items(payload.get("agents"), NavigationAgentSpec21, "agents")
    return nodes, edges, agents


def _decode_items(value: Any, model: type[Any], label: str) -> tuple[Any, ...]:
    if not isinstance(value, list):
        raise EditorNavigationToolingError(f"navigation {label} must be a JSON array")
    result = []
    fields = set(model.__dataclass_fields__)
    for index, item in enumerate(value):
        if not isinstance(item, dict):
            raise EditorNavigationToolingError(
                f"navigation {label}[{index}] must be a JSON object"
            )
        extra = set(item) - fields
        if extra:
            raise EditorNavigationToolingError(
                f"unknown navigation {label}[{index}] fields: {', '.join(sorted(extra))}"
            )
        try:
            result.append(model(**item))
        except (TypeError, ValueError) as exc:
            raise EditorNavigationToolingError(
                f"invalid navigation {label}[{index}]: {exc}"
            ) from exc
    return tuple(result)


def _name(value: str, *, label: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{label} must be a string")
    result = value.strip()
    if not result:
        raise EditorNavigationToolingError(f"{label} cannot be empty")
    return result


def _finite_float(value: float, *, label: str) -> float:
    result = float(value)
    if not math.isfinite(result):
        raise EditorNavigationToolingError(f"{label} must be finite")
    return result


def _float_tuple(value: Any, length: int, *, label: str) -> tuple[float, ...]:
    if isinstance(value, (str, bytes)):
        raise EditorNavigationToolingError(f"{label} must contain {length} numeric values")
    try:
        values = tuple(value)
    except TypeError as exc:
        raise EditorNavigationToolingError(
            f"{label} must contain {length} numeric values"
        ) from exc
    if len(values) != length:
        raise EditorNavigationToolingError(f"{label} must contain {length} numeric values")
    return tuple(_finite_float(item, label=label) for item in values)


def _project_relative_path(value: str | Path, *, label: str) -> str:
    raw = str(value).strip()
    normalized = raw.replace("\\", "/")
    if not normalized or normalized == ".":
        raise EditorNavigationToolingError(f"{label} cannot be empty")
    posix = PurePosixPath(normalized)
    windows = PureWindowsPath(raw)
    if (
        posix.is_absolute()
        or windows.is_absolute()
        or bool(windows.drive)
        or bool(windows.root)
        or ".." in posix.parts
    ):
        raise EditorNavigationToolingError(f"{label} must stay project-relative")
    return posix.as_posix()


def _project_target(root: Path, relative: str, *, label: str) -> Path:
    resolved = (root / PurePosixPath(relative)).resolve(strict=False)
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise EditorNavigationToolingError(f"{label} escapes the project root") from exc
    return resolved
