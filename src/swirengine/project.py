from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any, Mapping

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - exercised by Python 3.10 CI
    import tomli as tomllib

PROJECT_FILE_NAME = "swirproject.toml"
PROJECT_SCHEMA_VERSION = 1
SUPPORTED_PROJECT_MODES = frozenset({"2d", "3d"})


class ProjectConfigError(ValueError):
    """Raised when a SwirEngine project manifest is malformed or unsafe."""


@dataclass(frozen=True, slots=True)
class ProjectDiagnostic:
    code: str
    ok: bool
    message: str


@dataclass(frozen=True, slots=True)
class ProjectManifest:
    """Validated, portable configuration for one SwirEngine project."""

    root: Path
    name: str
    mode: str
    engine: str
    entrypoint: Path = Path("main.py")
    assets_dir: Path = Path("assets")
    scenes_dir: Path = Path("scenes")
    scripts_dir: Path = Path("scripts")
    schema: int = PROJECT_SCHEMA_VERSION

    @property
    def manifest_path(self) -> Path:
        return self.root / PROJECT_FILE_NAME

    @property
    def entrypoint_path(self) -> Path:
        return self.root / self.entrypoint

    @property
    def assets_path(self) -> Path:
        return self.root / self.assets_dir

    @property
    def scenes_path(self) -> Path:
        return self.root / self.scenes_dir

    @property
    def scripts_path(self) -> Path:
        return self.root / self.scripts_dir

    def diagnostics(self) -> tuple[ProjectDiagnostic, ...]:
        checks = (
            ("manifest", self.manifest_path, "project manifest"),
            ("entrypoint", self.entrypoint_path, "entrypoint"),
            ("assets", self.assets_path, "assets directory"),
            ("scenes", self.scenes_path, "scenes directory"),
            ("scripts", self.scripts_path, "scripts directory"),
        )
        diagnostics: list[ProjectDiagnostic] = []
        for code, path, label in checks:
            ok = path.is_file() if code in {"manifest", "entrypoint"} else path.is_dir()
            diagnostics.append(
                ProjectDiagnostic(
                    code=code,
                    ok=ok,
                    message=(f"{label}: {path}" if ok else f"missing {label}: {path}"),
                )
            )
        return tuple(diagnostics)

    @property
    def layout_ok(self) -> bool:
        return all(item.ok for item in self.diagnostics())


def _portable_relative_path(value: Any, *, field: str) -> Path:
    if not isinstance(value, str) or not value.strip():
        raise ProjectConfigError(f"{field} must be a non-empty relative path")
    raw = value.strip()
    windows = PureWindowsPath(raw)
    normalized = raw.replace("\\", "/")
    posix = PurePosixPath(normalized)
    if (
        posix.is_absolute()
        or windows.is_absolute()
        or windows.drive
        or raw.startswith(("//", "\\\\"))
    ):
        raise ProjectConfigError(f"{field} must stay inside the project root: {value!r}")
    if ".." in posix.parts or ".." in windows.parts:
        raise ProjectConfigError(f"{field} may not contain parent traversal: {value!r}")
    if normalized in {".", "./"}:
        raise ProjectConfigError(f"{field} must identify a project-relative child path")
    return Path(*posix.parts)


def _required_text(data: Mapping[str, Any], key: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ProjectConfigError(f"{key} must be a non-empty string")
    return value.strip()


def _read_manifest_data(path: Path) -> Mapping[str, Any]:
    try:
        with path.open("rb") as handle:
            data = tomllib.load(handle)
    except FileNotFoundError:
        raise
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise ProjectConfigError(f"could not parse {path}: {exc}") from exc
    if not isinstance(data, Mapping):
        raise ProjectConfigError("project manifest root must be a TOML table")
    return data


def load_project_manifest(project: str | Path = ".") -> ProjectManifest:
    """Load and validate ``swirproject.toml`` from a project directory or explicit file."""

    requested = Path(project).expanduser()
    manifest_path = requested if requested.name == PROJECT_FILE_NAME else requested / PROJECT_FILE_NAME
    manifest_path = manifest_path.resolve()
    data = _read_manifest_data(manifest_path)

    schema = data.get("schema", PROJECT_SCHEMA_VERSION)
    if not isinstance(schema, int) or isinstance(schema, bool):
        raise ProjectConfigError("schema must be an integer")
    if schema != PROJECT_SCHEMA_VERSION:
        raise ProjectConfigError(
            f"unsupported project schema {schema}; expected {PROJECT_SCHEMA_VERSION}"
        )

    name = _required_text(data, "name")
    mode = _required_text(data, "mode").lower()
    if mode not in SUPPORTED_PROJECT_MODES:
        supported = ", ".join(sorted(SUPPORTED_PROJECT_MODES))
        raise ProjectConfigError(f"mode must be one of: {supported}")
    engine = _required_text(data, "engine")

    entrypoint = _portable_relative_path(data.get("entrypoint", "main.py"), field="entrypoint")
    paths = data.get("paths", {})
    if not isinstance(paths, Mapping):
        raise ProjectConfigError("paths must be a TOML table")

    return ProjectManifest(
        root=manifest_path.parent,
        name=name,
        mode=mode,
        engine=engine,
        entrypoint=entrypoint,
        assets_dir=_portable_relative_path(paths.get("assets", "assets"), field="paths.assets"),
        scenes_dir=_portable_relative_path(paths.get("scenes", "scenes"), field="paths.scenes"),
        scripts_dir=_portable_relative_path(paths.get("scripts", "scripts"), field="paths.scripts"),
        schema=schema,
    )


def discover_project(start: str | Path = ".") -> ProjectManifest:
    """Find the nearest SwirEngine project by walking toward the filesystem root."""

    candidate = Path(start).expanduser().resolve()
    if candidate.is_file():
        candidate = candidate.parent
    for directory in (candidate, *candidate.parents):
        manifest = directory / PROJECT_FILE_NAME
        if manifest.is_file():
            return load_project_manifest(manifest)
    raise FileNotFoundError(f"no {PROJECT_FILE_NAME} found from {candidate}")


def project_diagnostics(project: str | Path = ".") -> tuple[ProjectDiagnostic, ...]:
    return load_project_manifest(project).diagnostics()


__all__ = [
    "PROJECT_FILE_NAME",
    "PROJECT_SCHEMA_VERSION",
    "SUPPORTED_PROJECT_MODES",
    "ProjectConfigError",
    "ProjectDiagnostic",
    "ProjectManifest",
    "discover_project",
    "load_project_manifest",
    "project_diagnostics",
]
