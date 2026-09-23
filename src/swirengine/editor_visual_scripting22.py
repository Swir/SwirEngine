from __future__ import annotations

import hashlib
import os
import re
from collections.abc import Mapping
from dataclasses import dataclass, replace
from pathlib import Path, PurePosixPath, PureWindowsPath

from .visual_scripting22 import (
    CompiledNodeGraph22,
    GraphExecutionContext22,
    GraphExecutionResult22,
    GraphValidationIssue22,
    NodeGraphAsset22,
    NodeGraphLink22,
    VisualScriptError22,
    compile_node_graph22,
    dumps_node_graph22,
    graph_node22,
    loads_node_graph22,
    validate_node_graph22,
)

DEFAULT_NODE_GRAPH_DIR_22 = "assets/graphs"
_GRAPH_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$")


class EditorVisualScriptingError22(ValueError):
    """Raised when project node-graph assets cannot be authored safely."""


@dataclass(frozen=True, slots=True)
class EditorVisualScriptingSnapshot22:
    graphs: tuple[NodeGraphAsset22, ...]
    relative_dir: str
    dirty: bool

    @property
    def graph_count(self) -> int:
        return len(self.graphs)


class EditorVisualScriptingTooling22:
    """Project-scoped node-graph authoring backed by the shipping graph runtime."""

    def __init__(
        self,
        project_root: str | Path,
        *,
        relative_dir: str = DEFAULT_NODE_GRAPH_DIR_22,
    ) -> None:
        self.project_root = Path(project_root).expanduser().resolve()
        self.relative_dir = _project_relative_path(relative_dir, label="node graph directory")
        self._graphs: dict[str, NodeGraphAsset22] = {}
        self._loaded_files: set[str] = set()
        self._saved_fingerprint = ""
        self.reload()

    @property
    def graph_dir(self) -> Path:
        return _project_target(self.project_root, self.relative_dir, label="node graph directory")

    @property
    def dirty(self) -> bool:
        return self._fingerprint() != self._saved_fingerprint

    def snapshot(self) -> EditorVisualScriptingSnapshot22:
        return EditorVisualScriptingSnapshot22(
            tuple(self._graphs[name] for name in sorted(self._graphs)),
            self.relative_dir,
            self.dirty,
        )

    def graph(self, name: str) -> NodeGraphAsset22:
        clean = _graph_name(name)
        try:
            return self._graphs[clean]
        except KeyError as exc:
            raise EditorVisualScriptingError22(f"unknown node graph {name!r}") from exc

    def reload(self) -> EditorVisualScriptingSnapshot22:
        graph_dir = self.graph_dir
        graphs: dict[str, NodeGraphAsset22] = {}
        loaded: set[str] = set()
        if graph_dir.exists():
            if not graph_dir.is_dir():
                raise EditorVisualScriptingError22("node graph directory is not a directory")
            for path in sorted(graph_dir.glob("*.swirgraph"), key=lambda item: item.name):
                safe = _safe_existing_target(self.project_root, path, label="node graph asset")
                try:
                    graph = loads_node_graph22(safe.read_text(encoding="utf-8"))
                except (OSError, UnicodeError, VisualScriptError22) as exc:
                    raise EditorVisualScriptingError22(
                        f"cannot load node graph {path.name!r}: {exc}"
                    ) from exc
                clean = _graph_name(graph.name)
                if path.name != f"{clean}.swirgraph":
                    raise EditorVisualScriptingError22(
                        f"node graph filename {path.name!r} must match asset name"
                    )
                if clean in graphs:
                    raise EditorVisualScriptingError22(f"duplicate node graph {clean!r}")
                graphs[clean] = graph
                loaded.add(path.name)
        self._graphs = graphs
        self._loaded_files = loaded
        self._saved_fingerprint = self._fingerprint()
        return self.snapshot()

    def create_graph(self, name: str) -> NodeGraphAsset22:
        clean = _graph_name(name)
        if clean in self._graphs:
            raise EditorVisualScriptingError22(f"node graph {clean!r} already exists")
        graph = NodeGraphAsset22(clean)
        self._graphs[clean] = graph
        return graph

    def duplicate_graph(self, name: str, new_name: str) -> NodeGraphAsset22:
        source = self.graph(name)
        clean = _graph_name(new_name)
        if clean in self._graphs:
            raise EditorVisualScriptingError22(f"node graph {clean!r} already exists")
        graph = replace(source, name=clean)
        self._graphs[clean] = graph
        return graph

    def remove_graph(self, name: str) -> None:
        clean = _graph_name(name)
        if clean not in self._graphs:
            raise EditorVisualScriptingError22(f"unknown node graph {name!r}")
        del self._graphs[clean]

    def add_node(
        self,
        graph_name: str,
        node_id: str,
        kind: str,
        *,
        x: float = 0.0,
        y: float = 0.0,
        parameters: Mapping[str, object] | None = None,
    ) -> NodeGraphAsset22:
        graph = self.graph(graph_name)
        clean_id = str(node_id).strip()
        if not clean_id or len(clean_id) > 96:
            raise EditorVisualScriptingError22("node id must contain 1..96 characters")
        if any(node.node_id == clean_id for node in graph.nodes):
            raise EditorVisualScriptingError22(f"node id {clean_id!r} already exists")
        try:
            node = graph_node22(clean_id, kind, x=x, y=y, parameters=parameters)
        except (TypeError, ValueError, VisualScriptError22) as exc:
            raise EditorVisualScriptingError22(str(exc)) from exc
        updated = replace(graph, nodes=(*graph.nodes, node))
        self._graphs[graph.name] = updated
        return updated

    def move_node(self, graph_name: str, node_id: str, *, x: float, y: float) -> NodeGraphAsset22:
        graph = self.graph(graph_name)
        found = False
        nodes = []
        for node in graph.nodes:
            if node.node_id == node_id:
                nodes.append(replace(node, x=float(x), y=float(y)))
                found = True
            else:
                nodes.append(node)
        if not found:
            raise EditorVisualScriptingError22(f"unknown node {node_id!r}")
        updated = replace(graph, nodes=tuple(nodes))
        self._graphs[graph.name] = updated
        return updated

    def update_parameters(
        self,
        graph_name: str,
        node_id: str,
        parameters: Mapping[str, object],
    ) -> NodeGraphAsset22:
        graph = self.graph(graph_name)
        current = next((node for node in graph.nodes if node.node_id == node_id), None)
        if current is None:
            raise EditorVisualScriptingError22(f"unknown node {node_id!r}")
        replacement = graph_node22(
            current.node_id,
            current.kind,
            x=current.x,
            y=current.y,
            parameters=parameters,
        )
        updated = replace(
            graph,
            nodes=tuple(replacement if node.node_id == node_id else node for node in graph.nodes),
        )
        self._graphs[graph.name] = updated
        return updated

    def remove_node(self, graph_name: str, node_id: str) -> NodeGraphAsset22:
        graph = self.graph(graph_name)
        if not any(node.node_id == node_id for node in graph.nodes):
            raise EditorVisualScriptingError22(f"unknown node {node_id!r}")
        updated = replace(
            graph,
            nodes=tuple(node for node in graph.nodes if node.node_id != node_id),
            links=tuple(
                link for link in graph.links
                if link.from_node != node_id and link.to_node != node_id
            ),
        )
        self._graphs[graph.name] = updated
        return updated

    def connect(
        self,
        graph_name: str,
        from_node: str,
        from_pin: str,
        to_node: str,
        to_pin: str,
    ) -> NodeGraphAsset22:
        graph = self.graph(graph_name)
        updated = replace(
            graph,
            links=(*graph.links, NodeGraphLink22(from_node, from_pin, to_node, to_pin)),
        )
        structural = tuple(
            issue for issue in validate_node_graph22(updated)
            if issue.code.startswith("link.") or issue.code == "graph.data_cycle"
        )
        if structural:
            raise EditorVisualScriptingError22("; ".join(issue.message for issue in structural))
        self._graphs[graph.name] = updated
        return updated

    def disconnect(
        self,
        graph_name: str,
        from_node: str,
        from_pin: str,
        to_node: str,
        to_pin: str,
    ) -> NodeGraphAsset22:
        graph = self.graph(graph_name)
        target = NodeGraphLink22(from_node, from_pin, to_node, to_pin)
        links = list(graph.links)
        try:
            links.remove(target)
        except ValueError as exc:
            raise EditorVisualScriptingError22("node graph link does not exist") from exc
        updated = replace(graph, links=tuple(links))
        self._graphs[graph.name] = updated
        return updated

    def diagnostics(self, graph_name: str) -> tuple[GraphValidationIssue22, ...]:
        return validate_node_graph22(self.graph(graph_name))

    def compile(self, graph_name: str) -> CompiledNodeGraph22:
        try:
            return compile_node_graph22(self.graph(graph_name))
        except VisualScriptError22 as exc:
            raise EditorVisualScriptingError22(str(exc)) from exc

    def execute(
        self,
        graph_name: str,
        context: GraphExecutionContext22 | None = None,
        *,
        max_steps: int = 1024,
    ) -> GraphExecutionResult22:
        return self.compile(graph_name).execute(context, max_steps=max_steps)

    def save(self) -> EditorVisualScriptingSnapshot22:
        graph_dir = self.graph_dir
        graph_dir.mkdir(parents=True, exist_ok=True)
        graph_dir = self.graph_dir
        current_files: set[str] = set()
        for name in sorted(self._graphs):
            filename = f"{name}.swirgraph"
            target = _safe_target(self.project_root, graph_dir / filename, label="node graph asset")
            temporary = target.with_name(f".{target.name}.tmp")
            temporary.write_text(
                dumps_node_graph22(self._graphs[name]), encoding="utf-8", newline="\n"
            )
            os.replace(temporary, target)
            current_files.add(filename)
        for filename in sorted(self._loaded_files - current_files):
            target = _safe_target(self.project_root, graph_dir / filename, label="node graph asset")
            if target.exists():
                target.unlink()
        self._loaded_files = current_files
        self._saved_fingerprint = self._fingerprint()
        return self.snapshot()

    def _fingerprint(self) -> str:
        digest = hashlib.sha256()
        for name in sorted(self._graphs):
            digest.update(name.encode())
            digest.update(b"\0")
            digest.update(dumps_node_graph22(self._graphs[name]).encode())
        return digest.hexdigest()


def _graph_name(value: str) -> str:
    clean = str(value).strip()
    if not _GRAPH_NAME_RE.fullmatch(clean) or clean in {".", ".."}:
        raise EditorVisualScriptingError22(
            "node graph name must be 1..64 ASCII letters, digits, dot, dash or underscore"
        )
    return clean


def _project_relative_path(value: str | Path, *, label: str) -> str:
    raw = str(value).strip()
    normalized = raw.replace("\\", "/")
    posix = PurePosixPath(normalized)
    windows = PureWindowsPath(raw)
    if (
        not normalized
        or normalized == "."
        or posix.is_absolute()
        or windows.is_absolute()
        or bool(windows.drive)
        or bool(windows.root)
        or ".." in posix.parts
    ):
        raise EditorVisualScriptingError22(f"{label} must stay project-relative")
    return posix.as_posix()


def _project_target(root: Path, relative: str, *, label: str) -> Path:
    resolved = (root / PurePosixPath(relative)).resolve(strict=False)
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise EditorVisualScriptingError22(f"{label} must resolve inside project root") from exc
    return resolved


def _safe_target(root: Path, target: Path, *, label: str) -> Path:
    resolved = target.resolve(strict=False)
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise EditorVisualScriptingError22(f"{label} resolves outside project root") from exc
    return resolved


def _safe_existing_target(root: Path, target: Path, *, label: str) -> Path:
    resolved = target.resolve(strict=True)
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise EditorVisualScriptingError22(f"{label} resolves outside project root") from exc
    return resolved
