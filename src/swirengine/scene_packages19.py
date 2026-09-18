from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from types import MappingProxyType
from typing import Any

try:  # Python 3.11+
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - exercised by the Python 3.10 CI job
    import tomli as tomllib

from .core.scene import Scene
from .prefab import Prefab
from .project19 import ProjectDiagnostic, ProjectManifest
from .serialization import SceneSerializationError, SceneSerializer

_MAX_PACKAGES = 256
_MAX_LINKS = 128
_MAX_DOCUMENT_BYTES = 16 * 1024 * 1024
_IDENTIFIER_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")


class ScenePackageError(ValueError):
    """Raised when a 1.9 production scene package is invalid or unsafe."""


@dataclass(slots=True, frozen=True)
class ScenePackageSpec:
    """Portable declaration for one packaged scene and its direct dependencies."""

    name: str
    scene_path: str
    prefab_paths: tuple[str, ...] = ()
    depends_on: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "scene_path": self.scene_path,
            "prefab_paths": list(self.prefab_paths),
            "depends_on": list(self.depends_on),
        }


@dataclass(slots=True, frozen=True)
class ScenePackagePlan:
    """Deterministic dependency-ordered plan for loading or packaging one scene."""

    target: str
    ordered_packages: tuple[str, ...]
    scene_paths: tuple[str, ...]
    prefab_paths: tuple[str, ...]
    fingerprint: str

    def to_dict(self) -> dict[str, object]:
        return {
            "target": self.target,
            "ordered_packages": list(self.ordered_packages),
            "scene_paths": list(self.scene_paths),
            "prefab_paths": list(self.prefab_paths),
            "fingerprint": self.fingerprint,
        }


@dataclass(slots=True, frozen=True)
class LoadedScenePackage:
    """One decoded target scene plus reusable prefabs declared by that package."""

    name: str
    scene: Scene
    prefabs: Mapping[str, Prefab]
    plan: ScenePackagePlan


class ScenePackageRegistry:
    """Validated scene/prefab shipping registry stored in ``swirproject.toml``.

    Dependency edges describe deterministic validation/load ordering. They do not merge scenes or
    instantiate prefabs automatically, which keeps the established Scene/Prefab semantics intact.
    """

    def __init__(
        self,
        manifest: ProjectManifest,
        *,
        boot: str,
        packages: Mapping[str, ScenePackageSpec],
    ) -> None:
        self.manifest = manifest
        self.boot = boot
        self.packages = MappingProxyType(dict(packages))
        self._validate_graph()

    @classmethod
    def load_optional(cls, manifest: ProjectManifest) -> ScenePackageRegistry | None:
        try:
            raw = tomllib.loads(manifest.path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, tomllib.TOMLDecodeError) as exc:
            raise ScenePackageError(f"cannot parse {manifest.path.name}: {exc}") from exc
        if not isinstance(raw, dict):
            raise ScenePackageError("project manifest must contain a TOML table")
        scenes = raw.get("scenes")
        if scenes is None:
            return None
        if not isinstance(scenes, dict):
            raise ScenePackageError("[scenes] must be a TOML table")

        boot = _identifier(scenes.get("boot"), "scenes.boot")
        registry = scenes.get("registry")
        if not isinstance(registry, dict) or not registry:
            raise ScenePackageError("[scenes.registry] must contain at least one scene package")
        if len(registry) > _MAX_PACKAGES:
            raise ScenePackageError(f"scenes.registry must contain at most {_MAX_PACKAGES} packages")

        packages: dict[str, ScenePackageSpec] = {}
        for raw_name in sorted(registry, key=str.casefold):
            name = _identifier(raw_name, "scene package name")
            data = registry[raw_name]
            if not isinstance(data, dict):
                raise ScenePackageError(f"[scenes.registry.{name}] must be a TOML table")
            default_path = f"scenes/{name}.swirscene"
            scene_path = _safe_project_path(
                _string(data.get("path", default_path), f"scenes.registry.{name}.path", 256),
                label=f"scenes.registry.{name}.path",
            )
            prefabs = _path_list(
                data.get("prefabs", ()),
                f"scenes.registry.{name}.prefabs",
            )
            dependencies = _identifier_list(
                data.get("depends_on", ()),
                f"scenes.registry.{name}.depends_on",
            )
            packages[name] = ScenePackageSpec(
                name=name,
                scene_path=scene_path,
                prefab_paths=prefabs,
                depends_on=dependencies,
            )

        if boot not in packages:
            raise ScenePackageError(f"scenes.boot refers to unknown scene package {boot!r}")
        return cls(manifest, boot=boot, packages=packages)

    @property
    def fingerprint(self) -> str:
        payload = {
            "boot": self.boot,
            "packages": {
                name: package.to_dict()
                for name, package in sorted(self.packages.items(), key=lambda item: item[0])
            },
        }
        return _fingerprint(payload)

    def package(self, name: str | None = None) -> ScenePackageSpec:
        target = self.boot if name is None else _identifier(name, "scene package")
        try:
            return self.packages[target]
        except KeyError as exc:
            available = ", ".join(sorted(self.packages))
            raise ScenePackageError(
                f"unknown scene package {target!r}; available packages: {available}"
            ) from exc

    def plan(self, name: str | None = None) -> ScenePackagePlan:
        target = self.package(name).name
        ordered: list[str] = []
        visited: set[str] = set()

        def visit(package_name: str) -> None:
            if package_name in visited:
                return
            package = self.packages[package_name]
            for dependency in package.depends_on:
                visit(dependency)
            visited.add(package_name)
            ordered.append(package_name)

        visit(target)
        scene_paths = tuple(self.packages[item].scene_path for item in ordered)
        prefab_paths = tuple(
            path
            for item in ordered
            for path in self.packages[item].prefab_paths
        )
        payload = {
            "registry": self.fingerprint,
            "target": target,
            "ordered_packages": ordered,
            "scene_paths": scene_paths,
            "prefab_paths": prefab_paths,
        }
        return ScenePackagePlan(
            target=target,
            ordered_packages=tuple(ordered),
            scene_paths=scene_paths,
            prefab_paths=prefab_paths,
            fingerprint=_fingerprint(payload),
        )

    def resolve_path(self, value: str) -> Path:
        root = self.manifest.root.resolve()
        candidate = (root / PurePosixPath(value)).resolve(strict=False)
        try:
            candidate.relative_to(root)
        except ValueError as exc:
            raise ScenePackageError(f"scene package path escapes project root: {value}") from exc
        return candidate

    def diagnostics(self) -> tuple[ProjectDiagnostic, ...]:
        diagnostics: list[ProjectDiagnostic] = []
        for package in self.packages.values():
            diagnostics.extend(
                self._path_diagnostics(
                    package.scene_path,
                    missing_code="scene-package-missing",
                    label=f"scene package {package.name!r}",
                )
            )
            for prefab_path in package.prefab_paths:
                diagnostics.extend(
                    self._path_diagnostics(
                        prefab_path,
                        missing_code="scene-prefab-missing",
                        label=f"prefab for scene package {package.name!r}",
                    )
                )
        return tuple(diagnostics)

    def validate_documents(
        self,
        serializer: SceneSerializer | None = None,
    ) -> tuple[ProjectDiagnostic, ...]:
        resolved_serializer = serializer or SceneSerializer()
        diagnostics = list(self.diagnostics())
        if any(item.severity == "error" for item in diagnostics):
            return tuple(diagnostics)

        checked_prefabs: set[str] = set()
        for package in self.packages.values():
            try:
                text = self._read_text(package.scene_path)
                resolved_serializer.loads_scene(text)
            except (OSError, UnicodeError, SceneSerializationError, ScenePackageError) as exc:
                diagnostics.append(
                    ProjectDiagnostic(
                        "error",
                        "scene-package-invalid",
                        f"cannot validate scene package {package.name!r}: {exc}",
                        package.scene_path,
                    )
                )
            for prefab_path in package.prefab_paths:
                if prefab_path in checked_prefabs:
                    continue
                checked_prefabs.add(prefab_path)
                try:
                    text = self._read_text(prefab_path)
                    resolved_serializer.loads_prefab(text)
                except (OSError, UnicodeError, SceneSerializationError, ScenePackageError) as exc:
                    diagnostics.append(
                        ProjectDiagnostic(
                            "error",
                            "scene-prefab-invalid",
                            f"cannot validate prefab: {exc}",
                            prefab_path,
                        )
                    )
        return tuple(diagnostics)

    def _path_diagnostics(
        self,
        value: str,
        *,
        missing_code: str,
        label: str,
    ) -> list[ProjectDiagnostic]:
        try:
            path = self.resolve_path(value)
        except ScenePackageError as exc:
            return [ProjectDiagnostic("error", "scene-path-escape", str(exc), value)]
        if not path.is_file():
            return [ProjectDiagnostic("error", missing_code, f"{label} does not exist", value)]
        try:
            size = path.stat().st_size
        except OSError as exc:
            return [ProjectDiagnostic("error", "scene-path-unreadable", str(exc), value)]
        if size > _MAX_DOCUMENT_BYTES:
            return [
                ProjectDiagnostic(
                    "error",
                    "scene-document-too-large",
                    f"{label} exceeds the {_MAX_DOCUMENT_BYTES} byte validation limit",
                    value,
                )
            ]
        return []

    def _read_text(self, value: str) -> str:
        path = self.resolve_path(value)
        size = path.stat().st_size
        if size > _MAX_DOCUMENT_BYTES:
            raise ScenePackageError(
                f"{value} exceeds the {_MAX_DOCUMENT_BYTES} byte scene document limit"
            )
        return path.read_text(encoding="utf-8")

    def _validate_graph(self) -> None:
        for package in self.packages.values():
            for dependency in package.depends_on:
                if dependency == package.name:
                    raise ScenePackageError(f"scene package {package.name!r} cannot depend on itself")
                if dependency not in self.packages:
                    raise ScenePackageError(
                        f"scene package {package.name!r} depends on unknown package {dependency!r}"
                    )

        states: dict[str, int] = {}
        stack: list[str] = []

        def visit(name: str) -> None:
            state = states.get(name, 0)
            if state == 2:
                return
            if state == 1:
                try:
                    index = stack.index(name)
                except ValueError:
                    index = 0
                cycle = stack[index:] + [name]
                raise ScenePackageError(
                    "scene package dependency cycle: " + " -> ".join(cycle)
                )
            states[name] = 1
            stack.append(name)
            for dependency in self.packages[name].depends_on:
                visit(dependency)
            stack.pop()
            states[name] = 2

        for name in sorted(self.packages):
            visit(name)


class ScenePackageLoader:
    """Creator-facing level loader preserving an existing Scene object's identity."""

    def __init__(
        self,
        registry: ScenePackageRegistry,
        serializer: SceneSerializer | None = None,
    ) -> None:
        self.registry = registry
        self.serializer = serializer or SceneSerializer()
        self.current_name: str | None = None

    def load(self, name: str | None = None) -> LoadedScenePackage:
        package = self.registry.package(name)
        plan = self.registry.plan(package.name)
        scene = self.serializer.loads_scene(self.registry._read_text(package.scene_path))
        prefabs = {
            path: self.serializer.loads_prefab(self.registry._read_text(path))
            for path in package.prefab_paths
        }
        return LoadedScenePackage(
            name=package.name,
            scene=scene,
            prefabs=MappingProxyType(prefabs),
            plan=plan,
        )

    def transition(self, scene: Scene, name: str | None = None) -> LoadedScenePackage:
        package = self.registry.package(name)
        plan = self.registry.plan(package.name)
        self.serializer.loads_scene(
            self.registry._read_text(package.scene_path),
            scene=scene,
            clear=True,
        )
        prefabs = {
            path: self.serializer.loads_prefab(self.registry._read_text(path))
            for path in package.prefab_paths
        }
        self.current_name = package.name
        return LoadedScenePackage(
            name=package.name,
            scene=scene,
            prefabs=MappingProxyType(prefabs),
            plan=plan,
        )

    def load_boot(self) -> LoadedScenePackage:
        return self.load(self.registry.boot)

    def transition_to_boot(self, scene: Scene) -> LoadedScenePackage:
        return self.transition(scene, self.registry.boot)


def _fingerprint(value: object) -> str:
    payload = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _string(value: Any, label: str, max_length: int) -> str:
    if not isinstance(value, str):
        raise ScenePackageError(f"{label} must be a string")
    cleaned = value.strip()
    if not cleaned:
        raise ScenePackageError(f"{label} must not be empty")
    if len(cleaned) > max_length:
        raise ScenePackageError(f"{label} must be at most {max_length} characters")
    if "\x00" in cleaned:
        raise ScenePackageError(f"{label} must not contain NUL characters")
    return cleaned


def _identifier(value: Any, label: str) -> str:
    cleaned = _string(value, label, 64)
    if not _IDENTIFIER_RE.fullmatch(cleaned):
        raise ScenePackageError(
            f"{label} must use 1-64 letters, numbers, '.', '_' or '-'"
        )
    return cleaned


def _identifier_list(value: Any, label: str) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple)):
        raise ScenePackageError(f"{label} must be an array of scene package names")
    if len(value) > _MAX_LINKS:
        raise ScenePackageError(f"{label} must contain at most {_MAX_LINKS} names")
    result = tuple(_identifier(item, label) for item in value)
    if len(set(result)) != len(result):
        raise ScenePackageError(f"{label} must not contain duplicate names")
    return result


def _path_list(value: Any, label: str) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple)):
        raise ScenePackageError(f"{label} must be an array of project-relative paths")
    if len(value) > _MAX_LINKS:
        raise ScenePackageError(f"{label} must contain at most {_MAX_LINKS} paths")
    result = tuple(
        _safe_project_path(_string(item, label, 256), label=label) for item in value
    )
    if len(set(result)) != len(result):
        raise ScenePackageError(f"{label} must not contain duplicate paths")
    return result


def _safe_project_path(value: str, *, label: str) -> str:
    portable = value.replace("\\", "/")
    path = PurePosixPath(portable)
    first = path.parts[0] if path.parts else ""
    if path.is_absolute() or ".." in path.parts or first.endswith(":") or portable.startswith("//"):
        raise ScenePackageError(f"{label} must stay inside the project: {value}")
    normalized = path.as_posix()
    if normalized in {"", "."}:
        raise ScenePackageError(f"{label} must identify a project-relative path")
    return normalized
