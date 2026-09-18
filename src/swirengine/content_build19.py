from __future__ import annotations

import hashlib
import heapq
import json
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from enum import Enum
from pathlib import Path, PurePosixPath
from types import MappingProxyType
from typing import TYPE_CHECKING, Any, TypeVar

try:  # Python 3.11+
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - exercised by the Python 3.10 CI job
    import tomli as tomllib

from .project19 import ProjectDiagnostic, ProjectManifest

if TYPE_CHECKING:
    from concurrent.futures import Future

    from .asset_pipeline import AssetLoadResult, AssetPreloadReport, AssetPreloader
    from .asset_streaming import AssetStreamingManager

_MAX_NODES = 1024
_MAX_DEPENDENCIES = 128
_MAX_DIAGNOSTICS = 64
_IDENTIFIER_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,95}$")
_EnumT = TypeVar("_EnumT", bound=Enum)


class ContentBuildError(ValueError):
    """Raised when a 1.9 production content build declaration is invalid or unsafe."""


class ContentBuildKind(str, Enum):
    """Portable content categories understood by the production build graph."""

    ASSET = "asset"
    SCENE = "scene"
    SHADER = "shader"
    GENERATED = "generated"


class ContentLoadPolicy(str, Enum):
    """When prepared content is intended to enter the runtime."""

    WARMUP = "warmup"
    PRELOAD = "preload"
    STREAM = "stream"


@dataclass(slots=True, frozen=True)
class ContentBuildNode:
    """One immutable shipping-content declaration."""

    name: str
    kind: ContentBuildKind
    path: str
    load: ContentLoadPolicy
    depends_on: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "kind": self.kind.value,
            "path": self.path,
            "load": self.load.value,
            "depends_on": list(self.depends_on),
        }


@dataclass(slots=True, frozen=True)
class ContentBuildPlan:
    """Dependency-first build/runtime plan derived from one validated graph."""

    targets: tuple[str, ...]
    ordered_nodes: tuple[str, ...]
    ordered_paths: tuple[str, ...]
    warmup_paths: tuple[str, ...]
    preload_paths: tuple[str, ...]
    stream_paths: tuple[str, ...]
    generated_paths: tuple[str, ...]
    fingerprint: str

    @property
    def all_paths(self) -> tuple[str, ...]:
        """Return all shipping paths in exact dependency-first order."""
        return self.ordered_paths

    def to_dict(self) -> dict[str, object]:
        return {
            "targets": list(self.targets),
            "ordered_nodes": list(self.ordered_nodes),
            "ordered_paths": list(self.ordered_paths),
            "warmup_paths": list(self.warmup_paths),
            "preload_paths": list(self.preload_paths),
            "stream_paths": list(self.stream_paths),
            "generated_paths": list(self.generated_paths),
            "fingerprint": self.fingerprint,
        }

    def preload_with(self, preloader: AssetPreloader) -> AssetPreloadReport:
        """Execute the plan's preload group using the established AssetPreloader runtime."""
        return preloader.preload(self.preload_paths)

    def preload_async_with(self, preloader: AssetPreloader) -> Future[AssetPreloadReport]:
        """Queue the plan's preload group using the established non-blocking runtime path."""
        return preloader.preload_async(self.preload_paths)

    def stage_streaming_with(
        self,
        streaming: AssetStreamingManager,
        *,
        pin: bool = False,
    ) -> tuple[Future[AssetLoadResult], ...]:
        """Stage the plan's streaming group through AssetStreamingManager."""
        return streaming.stage_many(self.stream_paths, pin=pin)


class ContentBuildGraph:
    """Bounded deterministic content graph for production shipping.

    The graph is intentionally data-only. It prepares dependency order and runtime admission groups,
    while existing asset, shader and streaming systems keep ownership of decoding, GPU finalization
    and residency. This makes the 1.9 workflow additive instead of replacing stable 1.x runtimes.
    """

    def __init__(self, manifest: ProjectManifest, nodes: Mapping[str, ContentBuildNode]) -> None:
        if not nodes:
            raise ContentBuildError("content.build.nodes must contain at least one node")
        if len(nodes) > _MAX_NODES:
            raise ContentBuildError(f"content.build.nodes must contain at most {_MAX_NODES} nodes")
        self.manifest = manifest
        self.nodes = MappingProxyType(dict(nodes))
        self._validate_graph()
        self._fingerprint = _fingerprint(
            {
                "nodes": {
                    name: node.to_dict()
                    for name, node in sorted(self.nodes.items(), key=lambda item: item[0])
                }
            }
        )

    @classmethod
    def load_optional(cls, manifest: ProjectManifest) -> ContentBuildGraph | None:
        try:
            raw = tomllib.loads(manifest.path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, tomllib.TOMLDecodeError) as exc:
            raise ContentBuildError(f"cannot parse {manifest.path.name}: {exc}") from exc
        if not isinstance(raw, dict):
            raise ContentBuildError("project manifest must contain a TOML table")
        content = raw.get("content")
        if content is None:
            return None
        if not isinstance(content, dict):
            raise ContentBuildError("[content] must be a TOML table")
        build = content.get("build")
        if build is None:
            return None
        if not isinstance(build, dict):
            raise ContentBuildError("[content.build] must be a TOML table")
        raw_nodes = build.get("nodes")
        if not isinstance(raw_nodes, list) or not raw_nodes:
            raise ContentBuildError(
                "[[content.build.nodes]] must contain at least one content declaration"
            )
        if len(raw_nodes) > _MAX_NODES:
            raise ContentBuildError(f"content.build.nodes must contain at most {_MAX_NODES} nodes")

        nodes: dict[str, ContentBuildNode] = {}
        for index, data in enumerate(raw_nodes):
            label = f"content.build.nodes[{index}]"
            if not isinstance(data, dict):
                raise ContentBuildError(f"{label} must be a TOML table")
            name = _identifier(data.get("name"), f"{label}.name")
            if name in nodes:
                raise ContentBuildError(f"content build node {name!r} is declared more than once")
            kind = _enum_value(
                data.get("kind", ContentBuildKind.ASSET.value),
                ContentBuildKind,
                f"{label}.kind",
            )
            load = _enum_value(
                data.get("load", _default_load(kind).value),
                ContentLoadPolicy,
                f"{label}.load",
            )
            path = _safe_project_path(
                _string(data.get("path"), f"{label}.path", max_length=512),
                label=f"{label}.path",
            )
            depends_on = _identifier_list(
                data.get("depends_on", ()),
                f"{label}.depends_on",
            )
            nodes[name] = ContentBuildNode(
                name=name,
                kind=kind,
                path=path,
                load=load,
                depends_on=depends_on,
            )
        return cls(manifest, nodes)

    @property
    def fingerprint(self) -> str:
        return self._fingerprint

    def node(self, name: str) -> ContentBuildNode:
        normalized = _identifier(name, "content build node")
        try:
            return self.nodes[normalized]
        except KeyError as exc:
            available = ", ".join(sorted(self.nodes))
            raise ContentBuildError(
                f"unknown content build node {normalized!r}; available nodes: {available}"
            ) from exc

    def resolve_path(self, value: str) -> Path:
        root = self.manifest.root.resolve()
        candidate = (root / PurePosixPath(value)).resolve(strict=False)
        try:
            candidate.relative_to(root)
        except ValueError as exc:
            raise ContentBuildError(f"content build path escapes project root: {value}") from exc
        return candidate

    def diagnostics(self) -> tuple[ProjectDiagnostic, ...]:
        diagnostics: list[ProjectDiagnostic] = []
        truncated = False
        for node in self.nodes.values():
            issue: ProjectDiagnostic | None = None
            try:
                path = self.resolve_path(node.path)
            except ContentBuildError as exc:
                issue = ProjectDiagnostic(
                    "error", "content-build-path-escape", str(exc), node.path
                )
            else:
                if not path.exists():
                    issue = ProjectDiagnostic(
                        "error",
                        "content-build-missing",
                        f"content node {node.name!r} does not exist",
                        node.path,
                    )
                elif not path.is_file():
                    issue = ProjectDiagnostic(
                        "error",
                        "content-build-not-file",
                        f"content node {node.name!r} is not a regular file",
                        node.path,
                    )
            if issue is not None:
                if len(diagnostics) >= _MAX_DIAGNOSTICS - 1:
                    truncated = True
                    break
                diagnostics.append(issue)
        if truncated:
            diagnostics.append(
                ProjectDiagnostic(
                    "warning",
                    "content-build-diagnostics-truncated",
                    f"content diagnostics are capped at {_MAX_DIAGNOSTICS} entries",
                )
            )
        return tuple(diagnostics)

    def shipping_paths(self) -> tuple[str, ...]:
        """Return all graph paths in dependency-first order after filesystem preflight."""
        errors = tuple(item for item in self.diagnostics() if item.severity == "error")
        if errors:
            details = "; ".join(
                f"{item.code}: {item.message}"
                + (f" ({item.path})" if item.path is not None else "")
                for item in errors
            )
            raise ContentBuildError(f"content build preflight failed: {details}")
        return self.plan().all_paths

    def plan(self, targets: Iterable[str] | None = None) -> ContentBuildPlan:
        if targets is None:
            requested = tuple(sorted(self.nodes))
        else:
            submitted = tuple(_identifier(name, "content build target") for name in targets)
            if not submitted:
                raise ContentBuildError("content build plan requires at least one target")
            if len(submitted) != len(set(submitted)):
                raise ContentBuildError("content build targets must be unique")
            requested = tuple(sorted(submitted))
        if not requested:
            raise ContentBuildError("content build plan requires at least one target")
        for target in requested:
            if target not in self.nodes:
                self.node(target)  # raises an actionable error with available values

        selected: set[str] = set()
        pending = list(requested)
        while pending:
            name = pending.pop()
            if name in selected:
                continue
            selected.add(name)
            pending.extend(self.nodes[name].depends_on)
        ordered = self._topological_order(selected)

        ordered_paths: list[str] = []
        warmup: list[str] = []
        preload: list[str] = []
        stream: list[str] = []
        generated: list[str] = []
        for name in ordered:
            node = self.nodes[name]
            ordered_paths.append(node.path)
            group = {
                ContentLoadPolicy.WARMUP: warmup,
                ContentLoadPolicy.PRELOAD: preload,
                ContentLoadPolicy.STREAM: stream,
            }[node.load]
            group.append(node.path)
            if node.kind is ContentBuildKind.GENERATED:
                generated.append(node.path)

        payload = {
            "graph": self.fingerprint,
            "targets": requested,
            "ordered_nodes": ordered,
            "ordered_paths": ordered_paths,
            "warmup_paths": warmup,
            "preload_paths": preload,
            "stream_paths": stream,
            "generated_paths": generated,
        }
        return ContentBuildPlan(
            targets=requested,
            ordered_nodes=ordered,
            ordered_paths=tuple(ordered_paths),
            warmup_paths=tuple(warmup),
            preload_paths=tuple(preload),
            stream_paths=tuple(stream),
            generated_paths=tuple(generated),
            fingerprint=_fingerprint(payload),
        )

    def _topological_order(self, selected: set[str]) -> tuple[str, ...]:
        indegree = {
            name: sum(dependency in selected for dependency in self.nodes[name].depends_on)
            for name in selected
        }
        dependents: dict[str, list[str]] = {name: [] for name in selected}
        for name in selected:
            for dependency in self.nodes[name].depends_on:
                if dependency in selected:
                    dependents[dependency].append(name)
        for values in dependents.values():
            values.sort()

        ready = [name for name, count in indegree.items() if count == 0]
        heapq.heapify(ready)
        ordered: list[str] = []
        while ready:
            name = heapq.heappop(ready)
            ordered.append(name)
            for dependent in dependents[name]:
                indegree[dependent] -= 1
                if indegree[dependent] == 0:
                    heapq.heappush(ready, dependent)
        if len(ordered) != len(selected):
            unresolved = sorted(selected.difference(ordered))
            preview = ", ".join(unresolved[:8])
            if len(unresolved) > 8:
                preview += ", ..."
            raise ContentBuildError(f"content build dependency cycle involving: {preview}")
        return tuple(ordered)

    def _validate_graph(self) -> None:
        seen_paths: dict[str, tuple[str, str]] = {}
        for name, node in self.nodes.items():
            if name != node.name:
                raise ContentBuildError("content build node mapping key must match node.name")
            path_key = node.path.casefold()
            owner = seen_paths.get(path_key)
            if owner is not None:
                owner_name, owner_path = owner
                raise ContentBuildError(
                    f"content path collision between {owner_name!r} ({owner_path}) and "
                    f"{name!r} ({node.path})"
                )
            seen_paths[path_key] = (name, node.path)
            if len(node.depends_on) > _MAX_DEPENDENCIES:
                raise ContentBuildError(
                    f"content build node {name!r} may depend on at most {_MAX_DEPENDENCIES} nodes"
                )
            for dependency in node.depends_on:
                if dependency == name:
                    raise ContentBuildError(f"content build node {name!r} cannot depend on itself")
                if dependency not in self.nodes:
                    raise ContentBuildError(
                        f"content build node {name!r} depends on unknown node {dependency!r}"
                    )
        self._topological_order(set(self.nodes))


def _default_load(kind: ContentBuildKind) -> ContentLoadPolicy:
    if kind is ContentBuildKind.SHADER:
        return ContentLoadPolicy.WARMUP
    if kind is ContentBuildKind.SCENE:
        return ContentLoadPolicy.STREAM
    return ContentLoadPolicy.PRELOAD


def _fingerprint(value: object) -> str:
    payload = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _string(value: Any, label: str, *, max_length: int) -> str:
    if not isinstance(value, str):
        raise ContentBuildError(f"{label} must be a string")
    cleaned = value.strip()
    if not cleaned:
        raise ContentBuildError(f"{label} must not be empty")
    if len(cleaned) > max_length:
        raise ContentBuildError(f"{label} must contain at most {max_length} characters")
    if "\x00" in cleaned:
        raise ContentBuildError(f"{label} must not contain NUL characters")
    return cleaned


def _identifier(value: Any, label: str) -> str:
    cleaned = _string(value, label, max_length=96)
    if not _IDENTIFIER_RE.fullmatch(cleaned):
        raise ContentBuildError(
            f"{label} must use 1-96 letters, numbers, '.', '_', ':' or '-'"
        )
    return cleaned


def _identifier_list(value: Any, label: str) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple)):
        raise ContentBuildError(f"{label} must be an array")
    if len(value) > _MAX_DEPENDENCIES:
        raise ContentBuildError(f"{label} must contain at most {_MAX_DEPENDENCIES} values")
    normalized = tuple(_identifier(item, label) for item in value)
    if len(normalized) != len(set(normalized)):
        raise ContentBuildError(f"{label} must not contain duplicate values")
    return normalized


def _safe_project_path(value: str, *, label: str) -> str:
    normalized = value.replace("\\", "/")
    pure = PurePosixPath(normalized)
    if pure.is_absolute() or ".." in pure.parts:
        raise ContentBuildError(f"{label} must stay inside the project")
    if not pure.parts or pure.parts == (".",):
        raise ContentBuildError(f"{label} must name a project file")
    if ":" in pure.parts[0]:
        raise ContentBuildError(f"{label} must not contain a drive prefix")
    return pure.as_posix()


def _enum_value(value: Any, enum_type: type[_EnumT], label: str) -> _EnumT:
    cleaned = _string(value, label, max_length=32)
    try:
        return enum_type(cleaned)
    except ValueError as exc:
        valid = ", ".join(item.value for item in enum_type)
        raise ContentBuildError(f"{label} must be one of: {valid}") from exc
