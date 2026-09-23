from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field

GRAPH_FORMAT_22 = "swirengine.node-graph"
GRAPH_VERSION_22 = 1


class VisualScriptError22(ValueError):
    """Base error for deterministic SwirEngine 2.2 visual scripting."""


class VisualScriptValidationError22(VisualScriptError22):
    """Raised when a node graph cannot be compiled safely."""

    def __init__(self, issues: tuple[GraphValidationIssue22, ...]) -> None:
        self.issues = issues
        super().__init__("; ".join(issue.message for issue in issues))


class VisualScriptExecutionError22(RuntimeError):
    """Raised when a compiled graph violates its bounded runtime contract."""


@dataclass(frozen=True, slots=True)
class GraphPinSpec22:
    name: str
    direction: str
    value_type: str
    required: bool = False
    default: object = None


@dataclass(frozen=True, slots=True)
class GraphNodeType22:
    kind: str
    label: str
    pins: tuple[GraphPinSpec22, ...]

    def pin(self, name: str) -> GraphPinSpec22:
        for pin in self.pins:
            if pin.name == name:
                return pin
        raise VisualScriptError22(f"{self.kind!r} has no pin {name!r}")


@dataclass(frozen=True, slots=True)
class NodeGraphNode22:
    node_id: str
    kind: str
    x: float = 0.0
    y: float = 0.0
    parameters: tuple[tuple[str, object], ...] = ()

    def parameter(self, name: str, default: object = None) -> object:
        return dict(self.parameters).get(name, default)


@dataclass(frozen=True, slots=True)
class NodeGraphLink22:
    from_node: str
    from_pin: str
    to_node: str
    to_pin: str


@dataclass(frozen=True, slots=True)
class NodeGraphAsset22:
    name: str
    nodes: tuple[NodeGraphNode22, ...] = ()
    links: tuple[NodeGraphLink22, ...] = ()

    @property
    def fingerprint(self) -> str:
        return hashlib.sha256(dumps_node_graph22(self).encode()).hexdigest()


@dataclass(frozen=True, slots=True)
class GraphValidationIssue22:
    code: str
    message: str
    node_id: str | None = None
    link_index: int | None = None


@dataclass(slots=True)
class GraphExecutionContext22:
    variables: dict[str, object] = field(default_factory=dict)
    emitted: list[tuple[str, object]] = field(default_factory=list)
    handlers: dict[str, Callable[[object], None]] = field(default_factory=dict)

    def emit(self, name: str, value: object) -> None:
        self.emitted.append((name, value))
        handler = self.handlers.get(name)
        if handler is not None:
            handler(value)


@dataclass(frozen=True, slots=True)
class GraphExecutionResult22:
    steps: int
    variables: tuple[tuple[str, object], ...]
    emitted: tuple[tuple[str, object], ...]


NODE_TYPES_22 = {
    "event.start": GraphNodeType22("event.start", "Start", (GraphPinSpec22("flow", "output", "exec"),)),
    "value.bool": GraphNodeType22("value.bool", "Boolean", (GraphPinSpec22("value", "output", "bool"),)),
    "value.float": GraphNodeType22("value.float", "Number", (GraphPinSpec22("value", "output", "float"),)),
    "value.string": GraphNodeType22("value.string", "Text", (GraphPinSpec22("value", "output", "string"),)),
    "variable.get": GraphNodeType22("variable.get", "Get Variable", (GraphPinSpec22("value", "output", "any"),)),
    "variable.set": GraphNodeType22(
        "variable.set", "Set Variable", (
            GraphPinSpec22("flow_in", "input", "exec", required=True),
            GraphPinSpec22("value", "input", "any"),
            GraphPinSpec22("flow", "output", "exec"),
        )
    ),
    "math.add": GraphNodeType22(
        "math.add", "Add", (
            GraphPinSpec22("a", "input", "float", required=True),
            GraphPinSpec22("b", "input", "float", required=True),
            GraphPinSpec22("value", "output", "float"),
        )
    ),
    "logic.greater": GraphNodeType22(
        "logic.greater", "Greater Than", (
            GraphPinSpec22("a", "input", "float", required=True),
            GraphPinSpec22("b", "input", "float", required=True),
            GraphPinSpec22("value", "output", "bool"),
        )
    ),
    "logic.branch": GraphNodeType22(
        "logic.branch", "Branch", (
            GraphPinSpec22("flow_in", "input", "exec", required=True),
            GraphPinSpec22("condition", "input", "bool", required=True),
            GraphPinSpec22("true", "output", "exec"),
            GraphPinSpec22("false", "output", "exec"),
        )
    ),
    "event.emit": GraphNodeType22(
        "event.emit", "Emit Event", (
            GraphPinSpec22("flow_in", "input", "exec", required=True),
            GraphPinSpec22("value", "input", "any"),
            GraphPinSpec22("flow", "output", "exec"),
        )
    ),
    "flow.end": GraphNodeType22("flow.end", "End", (GraphPinSpec22("flow_in", "input", "exec", required=True),)),
}


def node_type22(kind: str) -> GraphNodeType22:
    try:
        return NODE_TYPES_22[str(kind).strip()]
    except KeyError as exc:
        raise VisualScriptError22(f"unsupported node type {kind!r}") from exc


def graph_node22(
    node_id: str,
    kind: str,
    *,
    x: float = 0.0,
    y: float = 0.0,
    parameters: Mapping[str, object] | None = None,
) -> NodeGraphNode22:
    node_type22(kind)
    clean_id = str(node_id).strip()
    if not clean_id:
        raise VisualScriptError22("node id cannot be empty")
    normalized: list[tuple[str, object]] = []
    for key, value in sorted((parameters or {}).items(), key=lambda item: str(item[0])):
        clean_key = str(key).strip()
        if not clean_key:
            raise VisualScriptError22("parameter name cannot be empty")
        if not isinstance(value, (str, int, float, bool, type(None))):
            raise VisualScriptError22(f"parameter {clean_key!r} must be a JSON scalar")
        normalized.append((clean_key, value))
    return NodeGraphNode22(clean_id, str(kind).strip(), float(x), float(y), tuple(normalized))


def validate_node_graph22(graph: NodeGraphAsset22) -> tuple[GraphValidationIssue22, ...]:
    issues: list[GraphValidationIssue22] = []
    nodes: dict[str, NodeGraphNode22] = {}
    for node in graph.nodes:
        if not node.node_id:
            issues.append(GraphValidationIssue22("node.id", "node id cannot be empty"))
            continue
        if node.node_id in nodes:
            issues.append(GraphValidationIssue22("node.duplicate", f"duplicate node id {node.node_id!r}", node.node_id))
            continue
        nodes[node.node_id] = node
        if node.kind not in NODE_TYPES_22:
            issues.append(GraphValidationIssue22("node.kind", f"unsupported node type {node.kind!r}", node.node_id))
            continue
        params = dict(node.parameters)
        if node.kind == "value.bool" and "value" in params and not isinstance(params["value"], bool):
            issues.append(GraphValidationIssue22("node.parameter", "Boolean value must be bool", node.node_id))
        if node.kind == "value.float" and "value" in params:
            value = params["value"]
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                issues.append(GraphValidationIssue22("node.parameter", "Number value must be numeric", node.node_id))
        if node.kind in {"variable.get", "variable.set", "event.emit"}:
            label = "event name" if node.kind == "event.emit" else "variable name"
            if not str(params.get("name") or "").strip():
                issues.append(GraphValidationIssue22("node.parameter", f"{label} cannot be empty", node.node_id))
    starts = [node for node in graph.nodes if node.kind == "event.start"]
    if len(starts) != 1:
        issues.append(GraphValidationIssue22("graph.start", f"graph must contain exactly one Start node (found {len(starts)})"))

    incoming: dict[tuple[str, str], int] = {}
    outgoing: dict[tuple[str, str], int] = {}
    data_edges: dict[str, set[str]] = {}
    seen: set[NodeGraphLink22] = set()
    for index, link in enumerate(graph.links):
        if link in seen:
            issues.append(GraphValidationIssue22("link.duplicate", "duplicate graph link", link_index=index))
            continue
        seen.add(link)
        source, target = nodes.get(link.from_node), nodes.get(link.to_node)
        if source is None or target is None:
            issues.append(GraphValidationIssue22("link.node", "link references a missing node", link_index=index))
            continue
        if source.kind not in NODE_TYPES_22 or target.kind not in NODE_TYPES_22:
            continue
        try:
            source_pin = NODE_TYPES_22[source.kind].pin(link.from_pin)
            target_pin = NODE_TYPES_22[target.kind].pin(link.to_pin)
        except VisualScriptError22 as exc:
            issues.append(GraphValidationIssue22("link.pin", str(exc), link_index=index))
            continue
        if source_pin.direction != "output" or target_pin.direction != "input":
            issues.append(GraphValidationIssue22("link.direction", "links must connect output pins to input pins", link_index=index))
            continue
        compatible = source_pin.value_type == target_pin.value_type
        if source_pin.value_type != "exec" and target_pin.value_type != "exec":
            compatible = compatible or source_pin.value_type == "any" or target_pin.value_type == "any"
        if not compatible:
            issues.append(GraphValidationIssue22("link.type", f"cannot connect {source_pin.value_type} to {target_pin.value_type}", link_index=index))
            continue
        input_key = (target.node_id, target_pin.name)
        incoming[input_key] = incoming.get(input_key, 0) + 1
        if incoming[input_key] > 1:
            issues.append(GraphValidationIssue22("link.input", f"input pin {target.node_id}.{target_pin.name} has multiple links", target.node_id, index))
        if source_pin.value_type == "exec":
            output_key = (source.node_id, source_pin.name)
            outgoing[output_key] = outgoing.get(output_key, 0) + 1
            if outgoing[output_key] > 1:
                issues.append(GraphValidationIssue22("link.flow", f"flow output {source.node_id}.{source_pin.name} has multiple links", source.node_id, index))
        else:
            data_edges.setdefault(source.node_id, set()).add(target.node_id)

    for node in graph.nodes:
        definition = NODE_TYPES_22.get(node.kind)
        if definition is None:
            continue
        for pin in definition.pins:
            if pin.direction == "input" and pin.required and not incoming.get((node.node_id, pin.name)):
                issues.append(GraphValidationIssue22("pin.required", f"required pin {node.node_id}.{pin.name} is not connected", node.node_id))

    visiting: list[str] = []
    visited: set[str] = set()

    def visit(node_id: str) -> bool:
        if node_id in visiting:
            return True
        if node_id in visited:
            return False
        visiting.append(node_id)
        if any(visit(target) for target in sorted(data_edges.get(node_id, set()))):
            return True
        visiting.pop()
        visited.add(node_id)
        return False

    if any(visit(node_id) for node_id in sorted(data_edges)):
        issues.append(GraphValidationIssue22("graph.data_cycle", "data dependency graph contains a cycle"))
    return tuple(issues)


@dataclass(frozen=True, slots=True)
class CompiledNodeGraph22:
    graph: NodeGraphAsset22
    nodes: Mapping[str, NodeGraphNode22]
    incoming: Mapping[tuple[str, str], NodeGraphLink22]
    flow: Mapping[tuple[str, str], NodeGraphLink22]

    def execute(self, context: GraphExecutionContext22 | None = None, *, max_steps: int = 1024) -> GraphExecutionResult22:
        if isinstance(max_steps, bool) or not isinstance(max_steps, int) or max_steps < 1:
            raise ValueError("max_steps must be a positive integer")
        active = context or GraphExecutionContext22()
        current = next(node for node in self.graph.nodes if node.kind == "event.start")
        steps = 0
        while current is not None:
            steps += 1
            if steps > max_steps:
                raise VisualScriptExecutionError22(f"graph exceeded bounded execution limit ({max_steps} steps)")
            if current.kind == "event.start":
                next_link = self.flow.get((current.node_id, "flow"))
            elif current.kind == "logic.branch":
                condition = bool(self._input(current, "condition", active, set()))
                next_link = self.flow.get((current.node_id, "true" if condition else "false"))
            elif current.kind == "variable.set":
                name = str(current.parameter("name")).strip()
                active.variables[name] = self._input(current, "value", active, set())
                next_link = self.flow.get((current.node_id, "flow"))
            elif current.kind == "event.emit":
                name = str(current.parameter("name")).strip()
                active.emit(name, self._input(current, "value", active, set()))
                next_link = self.flow.get((current.node_id, "flow"))
            elif current.kind == "flow.end":
                break
            else:
                raise VisualScriptExecutionError22(f"data node {current.node_id!r} cannot execute on the flow path")
            if next_link is None:
                break
            current = self.nodes[next_link.to_node]
        return GraphExecutionResult22(steps, tuple(sorted(active.variables.items())), tuple(active.emitted))

    def _input(self, node: NodeGraphNode22, pin: str, context: GraphExecutionContext22, stack: set[str]) -> object:
        link = self.incoming.get((node.node_id, pin))
        if link is None:
            return NODE_TYPES_22[node.kind].pin(pin).default
        return self._output(self.nodes[link.from_node], context, stack)

    def _output(self, node: NodeGraphNode22, context: GraphExecutionContext22, stack: set[str]) -> object:
        if node.node_id in stack:
            raise VisualScriptExecutionError22("unexpected data dependency cycle")
        nested = set(stack)
        nested.add(node.node_id)
        if node.kind == "value.bool":
            return bool(node.parameter("value", False))
        if node.kind == "value.float":
            return float(node.parameter("value", 0.0))
        if node.kind == "value.string":
            return str(node.parameter("value", ""))
        if node.kind == "variable.get":
            return context.variables.get(str(node.parameter("name")).strip())
        if node.kind == "math.add":
            return float(self._input(node, "a", context, nested)) + float(self._input(node, "b", context, nested))
        if node.kind == "logic.greater":
            return float(self._input(node, "a", context, nested)) > float(self._input(node, "b", context, nested))
        raise VisualScriptExecutionError22(f"node {node.node_id!r} cannot provide a data value")


def compile_node_graph22(graph: NodeGraphAsset22) -> CompiledNodeGraph22:
    issues = validate_node_graph22(graph)
    if issues:
        raise VisualScriptValidationError22(issues)
    nodes = {node.node_id: node for node in graph.nodes}
    incoming: dict[tuple[str, str], NodeGraphLink22] = {}
    flow: dict[tuple[str, str], NodeGraphLink22] = {}
    for link in graph.links:
        source_pin = NODE_TYPES_22[nodes[link.from_node].kind].pin(link.from_pin)
        if source_pin.value_type == "exec":
            flow[(link.from_node, link.from_pin)] = link
        else:
            incoming[(link.to_node, link.to_pin)] = link
    return CompiledNodeGraph22(graph, nodes, incoming, flow)


def dumps_node_graph22(graph: NodeGraphAsset22) -> str:
    payload = {
        "format": GRAPH_FORMAT_22,
        "version": GRAPH_VERSION_22,
        "name": graph.name,
        "nodes": [
            {"id": node.node_id, "kind": node.kind, "position": [node.x, node.y], "parameters": dict(node.parameters)}
            for node in sorted(graph.nodes, key=lambda item: item.node_id)
        ],
        "links": [
            {"from": [link.from_node, link.from_pin], "to": [link.to_node, link.to_pin]}
            for link in sorted(graph.links, key=lambda item: (item.from_node, item.from_pin, item.to_node, item.to_pin))
        ],
    }
    return json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def loads_node_graph22(text: str) -> NodeGraphAsset22:
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise VisualScriptError22(f"invalid node graph JSON: {exc}") from exc
    if not isinstance(payload, dict) or payload.get("format") != GRAPH_FORMAT_22 or payload.get("version") != GRAPH_VERSION_22:
        raise VisualScriptError22("unsupported node graph format/version")
    raw_nodes, raw_links = payload.get("nodes", []), payload.get("links", [])
    if not isinstance(raw_nodes, list) or not isinstance(raw_links, list):
        raise VisualScriptError22("nodes and links must be arrays")
    nodes = []
    for raw in raw_nodes:
        if not isinstance(raw, dict):
            raise VisualScriptError22("node entry must be an object")
        position = raw.get("position", [0.0, 0.0])
        parameters = raw.get("parameters", {})
        if not isinstance(position, list) or len(position) != 2 or not isinstance(parameters, dict):
            raise VisualScriptError22("invalid node position or parameters")
        nodes.append(graph_node22(str(raw.get("id", "")), str(raw.get("kind", "")), x=float(position[0]), y=float(position[1]), parameters=parameters))
    links = []
    for raw in raw_links:
        if not isinstance(raw, dict):
            raise VisualScriptError22("link entry must be an object")
        source, target = raw.get("from"), raw.get("to")
        if not isinstance(source, list) or len(source) != 2 or not isinstance(target, list) or len(target) != 2:
            raise VisualScriptError22("invalid node graph link")
        links.append(NodeGraphLink22(str(source[0]), str(source[1]), str(target[0]), str(target[1])))
    return NodeGraphAsset22(str(payload.get("name", "")).strip(), tuple(nodes), tuple(links))
