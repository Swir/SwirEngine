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

from .exporting import ExportTarget, PackagingProfile

_DEFAULT_INCLUDE = ("assets", "scenes", "scripts")
_DEFAULT_EXCLUDE = (
    ".git",
    ".venv",
    "__pycache__",
    ".pytest_cache",
    ".ruff_cache",
    "build",
    "dist",
)
_IDENTIFIER_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
_ENVIRONMENT_KEY_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,127}$")


class ProjectManifestError(ValueError):
    """Raised when a SwirEngine project manifest is malformed or unsafe."""


@dataclass(slots=True, frozen=True)
class ProjectDiagnostic:
    severity: str
    code: str
    message: str
    path: str | None = None

    def to_dict(self) -> dict[str, str]:
        data = {"severity": self.severity, "code": self.code, "message": self.message}
        if self.path is not None:
            data["path"] = self.path
        return data


@dataclass(slots=True, frozen=True)
class DevelopmentRunConfig:
    """Portable development-session settings stored in ``swirproject.toml``."""

    entrypoint: str
    working_directory: str
    arguments: tuple[str, ...]
    environment: Mapping[str, str]
    inherit_environment: bool = True

    def to_dict(self) -> dict[str, object]:
        return {
            "entrypoint": self.entrypoint,
            "working_directory": self.working_directory,
            "arguments": list(self.arguments),
            "environment": dict(sorted(self.environment.items())),
            "inherit_environment": self.inherit_environment,
        }


@dataclass(slots=True, frozen=True)
class ProjectManifest:
    """Validated, portable project-production configuration for SwirEngine 1.9."""

    root: Path
    path: Path
    name: str
    mode: str
    engine: str
    entrypoint: str
    include: tuple[str, ...]
    profiles: Mapping[str, PackagingProfile]
    run: DevelopmentRunConfig

    @classmethod
    def load(cls, project: str | Path = ".") -> ProjectManifest:
        source = Path(project).expanduser()
        path = source / "swirproject.toml" if source.is_dir() else source
        path = path.resolve()
        if not path.is_file():
            raise FileNotFoundError(f"SwirEngine project manifest does not exist: {path}")
        try:
            raw = tomllib.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, tomllib.TOMLDecodeError) as exc:
            raise ProjectManifestError(f"cannot parse {path.name}: {exc}") from exc
        if not isinstance(raw, dict):
            raise ProjectManifestError("project manifest must contain a TOML table")

        project_table = raw.get("project")
        if project_table is None:
            project_table = raw
        if not isinstance(project_table, dict):
            raise ProjectManifestError("[project] must be a TOML table")

        name = _required_string(project_table, "name", max_length=128)
        mode = _string(project_table.get("mode", "2d"), "mode", max_length=16)
        if mode not in {"2d", "3d"}:
            raise ProjectManifestError("mode must be either '2d' or '3d'")
        engine = _string(project_table.get("engine", ">=1.0,<2.0"), "engine", max_length=128)
        entrypoint = _safe_project_path(
            _string(project_table.get("entrypoint", "main.py"), "entrypoint", max_length=256),
            label="entrypoint",
        )

        content_table = raw.get("content", {})
        if not isinstance(content_table, dict):
            raise ProjectManifestError("[content] must be a TOML table")
        include = _path_list(content_table.get("include", _DEFAULT_INCLUDE), "content.include")

        profiles_table = raw.get("profiles", {})
        if not isinstance(profiles_table, dict):
            raise ProjectManifestError("[profiles] must be a TOML table")
        profiles: dict[str, PackagingProfile] = {}
        for profile_name in sorted(profiles_table, key=str.casefold):
            if not isinstance(profile_name, str) or not _IDENTIFIER_RE.fullmatch(profile_name):
                raise ProjectManifestError(
                    "profile names must use 1-64 letters, numbers, '.', '_' or '-'"
                )
            profile_data = profiles_table[profile_name]
            if not isinstance(profile_data, dict):
                raise ProjectManifestError(f"[profiles.{profile_name}] must be a TOML table")
            profiles[profile_name] = _parse_profile(
                profile_name,
                profile_data,
                project_name=name,
                project_entrypoint=entrypoint,
                project_include=include,
            )

        run = _parse_run_config(raw.get("run", {}), project_entrypoint=entrypoint)

        return cls(
            root=path.parent,
            path=path,
            name=name,
            mode=mode,
            engine=engine,
            entrypoint=entrypoint,
            include=include,
            profiles=MappingProxyType(profiles),
            run=run,
        )

    @staticmethod
    def validate_environment_pair(key: str, value: str, *, label: str) -> None:
        _environment_pair(key, value, label=label)

    def packaging_profile(self, name: str) -> PackagingProfile:
        try:
            return self.profiles[name]
        except KeyError as exc:
            available = ", ".join(sorted(self.profiles)) or "<none>"
            raise ProjectManifestError(
                f"unknown packaging profile {name!r}; available profiles: {available}"
            ) from exc

    def diagnostics(self, *, profile_name: str | None = None) -> tuple[ProjectDiagnostic, ...]:
        diagnostics: list[ProjectDiagnostic] = []
        profiles = (
            ((profile_name, self.packaging_profile(profile_name)),)
            if profile_name is not None
            else tuple(sorted(self.profiles.items()))
        )

        entrypoint_path = self.root / PurePosixPath(self.entrypoint)
        if not entrypoint_path.is_file():
            diagnostics.append(
                ProjectDiagnostic(
                    "error",
                    "entrypoint-missing",
                    "project entrypoint does not exist",
                    self.entrypoint,
                )
            )

        diagnostics.extend(self._content_diagnostics())

        for name, profile in profiles:
            profile_entrypoint = self.root / PurePosixPath(profile.entrypoint)
            if not profile_entrypoint.is_file():
                diagnostics.append(
                    ProjectDiagnostic(
                        "error",
                        "profile-entrypoint-missing",
                        f"profile {name!r} entrypoint does not exist",
                        profile.entrypoint,
                    )
                )
            if profile.icon and not (self.root / PurePosixPath(profile.icon)).is_file():
                diagnostics.append(
                    ProjectDiagnostic(
                        "error",
                        "profile-icon-missing",
                        f"profile {name!r} icon does not exist",
                        profile.icon,
                    )
                )
            for value in profile.include:
                if value in self.include:
                    continue
                if not (self.root / PurePosixPath(value)).exists():
                    diagnostics.append(
                        ProjectDiagnostic(
                            "warning",
                            "profile-content-missing",
                            f"profile {name!r} include path does not exist",
                            value,
                        )
                    )
        return tuple(diagnostics)

    def run_diagnostics(self) -> tuple[ProjectDiagnostic, ...]:
        """Return diagnostics relevant to starting a development session only."""

        diagnostics = list(self._content_diagnostics())
        entrypoint_path = self.root / PurePosixPath(self.run.entrypoint)
        if not entrypoint_path.is_file():
            diagnostics.append(
                ProjectDiagnostic(
                    "error",
                    "run-entrypoint-missing",
                    "development entrypoint does not exist",
                    self.run.entrypoint,
                )
            )
        working_directory = (
            self.root
            if self.run.working_directory == "."
            else self.root / PurePosixPath(self.run.working_directory)
        )
        if not working_directory.is_dir():
            diagnostics.append(
                ProjectDiagnostic(
                    "error",
                    "run-working-directory-missing",
                    "development working directory does not exist",
                    self.run.working_directory,
                )
            )
        return tuple(diagnostics)

    def _content_diagnostics(self) -> list[ProjectDiagnostic]:
        diagnostics: list[ProjectDiagnostic] = []
        for value in self.include:
            if not (self.root / PurePosixPath(value)).exists():
                diagnostics.append(
                    ProjectDiagnostic(
                        "warning",
                        "content-missing",
                        "configured content path does not exist",
                        value,
                    )
                )
        return diagnostics

    @property
    def fingerprint(self) -> str:
        payload = json.dumps(
            self.to_dict(),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
        ).encode("utf-8")
        return hashlib.sha256(payload).hexdigest()

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "mode": self.mode,
            "engine": self.engine,
            "entrypoint": self.entrypoint,
            "include": list(self.include),
            "profiles": {
                name: profile.to_dict()
                for name, profile in sorted(self.profiles.items(), key=lambda item: item[0])
            },
            "run": self.run.to_dict(),
        }


def _parse_run_config(data: Any, *, project_entrypoint: str) -> DevelopmentRunConfig:
    if not isinstance(data, dict):
        raise ProjectManifestError("[run] must be a TOML table")
    entrypoint = _safe_project_path(
        _string(data.get("entrypoint", project_entrypoint), "run.entrypoint", max_length=256),
        label="run.entrypoint",
    )
    working_directory = _safe_working_directory(
        _string(data.get("working_directory", "."), "run.working_directory", max_length=256),
        label="run.working_directory",
    )
    arguments = _argument_list(data.get("arguments", ()), "run.arguments")
    environment_raw = data.get("environment", {})
    if not isinstance(environment_raw, dict):
        raise ProjectManifestError("[run.environment] must be a TOML table")
    if len(environment_raw) > 128:
        raise ProjectManifestError("run.environment must contain at most 128 variables")
    environment: dict[str, str] = {}
    for key, value in sorted(environment_raw.items(), key=lambda item: str(item[0])):
        if not isinstance(key, str) or not isinstance(value, str):
            raise ProjectManifestError("run.environment keys and values must be strings")
        _environment_pair(key, value, label="run.environment")
        environment[key] = value
    return DevelopmentRunConfig(
        entrypoint=entrypoint,
        working_directory=working_directory,
        arguments=arguments,
        environment=MappingProxyType(environment),
        inherit_environment=_boolean(
            data.get("inherit_environment", True),
            "run.inherit_environment",
        ),
    )


def _parse_profile(
    name: str,
    data: dict[str, Any],
    *,
    project_name: str,
    project_entrypoint: str,
    project_include: tuple[str, ...],
) -> PackagingProfile:
    raw_target = data.get(
        "target", name if name in {target.value for target in ExportTarget} else "windows"
    )
    try:
        target = ExportTarget(_string(raw_target, f"profiles.{name}.target", max_length=32))
    except ValueError as exc:
        valid = ", ".join(target.value for target in ExportTarget)
        raise ProjectManifestError(f"profiles.{name}.target must be one of: {valid}") from exc

    entrypoint = _safe_project_path(
        _string(
            data.get("entrypoint", project_entrypoint),
            f"profiles.{name}.entrypoint",
            max_length=256,
        ),
        label=f"profiles.{name}.entrypoint",
    )
    include = _path_list(data.get("include", project_include), f"profiles.{name}.include")
    exclude = _path_list(data.get("exclude", _DEFAULT_EXCLUDE), f"profiles.{name}.exclude")
    icon_value = data.get("icon")
    icon = None
    if icon_value is not None:
        icon = _safe_project_path(
            _string(icon_value, f"profiles.{name}.icon", max_length=256),
            label=f"profiles.{name}.icon",
        )

    app_name_value = data.get("app_name", project_name)
    app_name = _string(app_name_value, f"profiles.{name}.app_name", max_length=128)
    metadata_raw = data.get("metadata", {})
    if not isinstance(metadata_raw, dict):
        raise ProjectManifestError(f"profiles.{name}.metadata must be a TOML table")
    metadata = {
        _string(key, f"profiles.{name}.metadata key", max_length=64): _string(
            value, f"profiles.{name}.metadata.{key}", max_length=256
        )
        for key, value in sorted(metadata_raw.items(), key=lambda item: str(item[0]))
    }

    return PackagingProfile(
        name=name,
        target=target,
        entrypoint=entrypoint,
        app_name=app_name,
        include=include,
        exclude=exclude,
        icon=icon,
        onefile=_boolean(data.get("onefile", False), f"profiles.{name}.onefile"),
        console=_boolean(data.get("console", True), f"profiles.{name}.console"),
        metadata=metadata,
    )


def _required_string(data: dict[str, Any], key: str, *, max_length: int) -> str:
    if key not in data:
        raise ProjectManifestError(f"{key} is required")
    return _string(data[key], key, max_length=max_length)


def _string(value: Any, label: str, *, max_length: int) -> str:
    if not isinstance(value, str):
        raise ProjectManifestError(f"{label} must be a string")
    cleaned = value.strip()
    if not cleaned:
        raise ProjectManifestError(f"{label} must not be empty")
    if len(cleaned) > max_length:
        raise ProjectManifestError(f"{label} must be at most {max_length} characters")
    if "\x00" in cleaned:
        raise ProjectManifestError(f"{label} must not contain NUL characters")
    return cleaned


def _boolean(value: Any, label: str) -> bool:
    if not isinstance(value, bool):
        raise ProjectManifestError(f"{label} must be a boolean")
    return value


def _path_list(value: Any, label: str) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple)):
        raise ProjectManifestError(f"{label} must be an array of project-relative paths")
    if len(value) > 128:
        raise ProjectManifestError(f"{label} must contain at most 128 paths")
    paths = tuple(
        _safe_project_path(_string(item, label, max_length=256), label=label) for item in value
    )
    if len(set(paths)) != len(paths):
        raise ProjectManifestError(f"{label} must not contain duplicate paths")
    return paths


def _argument_list(value: Any, label: str) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple)):
        raise ProjectManifestError(f"{label} must be an array of strings")
    if len(value) > 128:
        raise ProjectManifestError(f"{label} must contain at most 128 arguments")
    arguments: list[str] = []
    for item in value:
        if not isinstance(item, str):
            raise ProjectManifestError(f"{label} must contain only strings")
        if len(item) > 4096:
            raise ProjectManifestError(f"{label} arguments must be at most 4096 characters")
        if "\x00" in item:
            raise ProjectManifestError(f"{label} must not contain NUL characters")
        arguments.append(item)
    return tuple(arguments)


def _environment_pair(key: str, value: str, *, label: str) -> None:
    if not _ENVIRONMENT_KEY_RE.fullmatch(key):
        raise ProjectManifestError(
            f"{label} variable names must use letters, numbers and '_' and not start with a number"
        )
    if len(value) > 16384:
        raise ProjectManifestError(f"{label}.{key} must be at most 16384 characters")
    if "\x00" in value:
        raise ProjectManifestError(f"{label}.{key} must not contain NUL characters")


def _safe_working_directory(value: str, *, label: str) -> str:
    portable = value.replace("\\", "/")
    if portable in {"", "."}:
        return "."
    return _safe_project_path(portable, label=label)


def _safe_project_path(value: str, *, label: str) -> str:
    portable = value.replace("\\", "/")
    path = PurePosixPath(portable)
    first = path.parts[0] if path.parts else ""
    if path.is_absolute() or ".." in path.parts or first.endswith(":") or portable.startswith("//"):
        raise ProjectManifestError(f"{label} must stay inside the project: {value}")
    normalized = path.as_posix()
    if normalized in {"", "."}:
        raise ProjectManifestError(f"{label} must identify a project-relative path")
    return normalized
