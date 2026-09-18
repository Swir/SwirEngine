from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, ClassVar

try:  # Python 3.11+
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - exercised by the Python 3.10 CI job
    import tomli as tomllib


class ExportTarget(str, Enum):
    """Supported SwirEngine export targets."""

    WINDOWS = "windows"
    LINUX = "linux"
    MACOS = "macos"
    ANDROID = "android"
    WEB = "web"

    @property
    def desktop(self) -> bool:
        return self in {ExportTarget.WINDOWS, ExportTarget.LINUX, ExportTarget.MACOS}


class NativeBuildError(RuntimeError):
    """Raised when an explicit native desktop build cannot be completed safely."""


@dataclass(slots=True, frozen=True)
class PackagingProfile:
    """Serializable build/export configuration for a SwirEngine project."""

    name: str = "default"
    target: ExportTarget = ExportTarget.WINDOWS
    entrypoint: str = "main.py"
    app_name: str | None = None
    include: tuple[str, ...] = ("assets", "scenes", "scripts")
    exclude: tuple[str, ...] = (
        ".git",
        ".venv",
        "__pycache__",
        ".pytest_cache",
        ".ruff_cache",
        "build",
        "dist",
    )
    icon: str | None = None
    onefile: bool = False
    console: bool = True
    metadata: dict[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("profile name must not be empty")
        if not self.entrypoint.strip():
            raise ValueError("entrypoint must not be empty")

    @property
    def effective_app_name(self) -> str:
        return self.app_name or self.name

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "target": self.target.value,
            "entrypoint": self.entrypoint,
            "app_name": self.app_name,
            "include": list(self.include),
            "exclude": list(self.exclude),
            "icon": self.icon,
            "onefile": self.onefile,
            "console": self.console,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> PackagingProfile:
        return cls(
            name=str(data.get("name", "default")),
            target=ExportTarget(str(data.get("target", ExportTarget.WINDOWS.value))),
            entrypoint=str(data.get("entrypoint", "main.py")),
            app_name=(None if data.get("app_name") is None else str(data["app_name"])),
            include=tuple(
                str(value)
                for value in data.get("include", ("assets", "scenes", "scripts"))
            ),
            exclude=tuple(
                str(value)
                for value in data.get(
                    "exclude",
                    (
                        ".git",
                        ".venv",
                        "__pycache__",
                        ".pytest_cache",
                        ".ruff_cache",
                        "build",
                        "dist",
                    ),
                )
            ),
            icon=None if data.get("icon") is None else str(data["icon"]),
            onefile=bool(data.get("onefile", False)),
            console=bool(data.get("console", True)),
            metadata={
                str(key): str(value) for key, value in dict(data.get("metadata", {})).items()
            },
        )

    def save(self, path: str | Path) -> Path:
        destination = Path(path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(json.dumps(self.to_dict(), indent=2) + "\n", encoding="utf-8")
        return destination

    @classmethod
    def load(cls, path: str | Path) -> PackagingProfile:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise TypeError("packaging profile must contain a JSON object")
        return cls.from_dict(data)


@dataclass(slots=True, frozen=True)
class ExportPlan:
    """A deterministic, inspectable export plan before any files are copied."""

    project_root: Path
    output_dir: Path
    profile: PackagingProfile
    files: tuple[Path, ...]
    native_build_command: tuple[str, ...] | None
    experimental: bool

    @property
    def target(self) -> ExportTarget:
        return self.profile.target


@dataclass(slots=True, frozen=True)
class ExportResult:
    output_dir: Path
    manifest: Path
    copied_files: tuple[Path, ...]
    native_build_command: tuple[str, ...] | None
    experimental: bool
    native_spec: Path | None = None


@dataclass(slots=True, frozen=True)
class NativeBuildResult:
    """Result of an explicitly requested host-native desktop build."""

    export: ExportResult
    command: tuple[str, ...]
    artifacts: tuple[Path, ...]
    returncode: int


Runner = Callable[..., Any]


class ProjectExporter:
    """Create portable staging directories and explicit host-native desktop builds.

    ``export()`` remains side-effect-light: it stages project files, writes a deterministic manifest
    and generates a portable PyInstaller spec for desktop targets. ``build_native()`` is an explicit
    opt-in that executes PyInstaller only when the requested desktop target matches the current host.
    Android and Web exports remain experimental staging targets.
    """

    _DESKTOP_HOSTS: ClassVar[dict[ExportTarget, str]] = {
        ExportTarget.WINDOWS: "win32",
        ExportTarget.LINUX: "linux",
        ExportTarget.MACOS: "darwin",
    }

    def __init__(self, project_root: str | Path) -> None:
        self.project_root = Path(project_root).expanduser().resolve()
        if not self.project_root.is_dir():
            raise FileNotFoundError(f"project directory does not exist: {self.project_root}")

    @staticmethod
    def _safe_relative(value: str | Path, *, label: str) -> Path:
        relative = Path(value)
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError(f"{label} must stay inside the project: {value}")
        return relative

    @staticmethod
    def _is_excluded(relative: Path, patterns: Iterable[str]) -> bool:
        parts = relative.parts
        for pattern in patterns:
            normalized = pattern.strip().replace("\\", "/").strip("/")
            if not normalized:
                continue
            if normalized in parts or relative.as_posix() == normalized:
                return True
        return False

    def _scene_package_files(self) -> tuple[Path, ...]:
        """Return validated scene-package files that must ship with a 1.9 project.

        Scene opt-in detection is performed with the TOML parser rather than a textual header scan,
        so valid whitespace/dotted-table forms cannot bypass shipping preflight and strings/comments
        that merely contain ``[scenes]`` cannot accidentally activate it. Malformed legacy manifests
        remain on the established exporter path.
        """

        manifest_path = self.project_root / "swirproject.toml"
        if not manifest_path.is_file():
            return ()

        try:
            raw = tomllib.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, tomllib.TOMLDecodeError):
            return ()
        if not isinstance(raw, dict) or "scenes" not in raw:
            return ()

        from .project19 import ProjectManifest
        from .scene_packages19 import ScenePackageRegistry

        manifest = ProjectManifest.load(manifest_path)
        registry = ScenePackageRegistry.load_optional(manifest)
        if registry is None:
            return ()

        errors = tuple(item for item in registry.diagnostics() if item.severity == "error")
        if errors:
            details = "; ".join(
                f"{item.code}: {item.message}"
                + (f" ({item.path})" if item.path is not None else "")
                for item in errors
            )
            raise ValueError(f"scene package export preflight failed: {details}")

        files = {
            Path(value)
            for package in registry.packages.values()
            for value in (package.scene_path, *package.prefab_paths)
        }
        return tuple(sorted(files, key=lambda path: path.as_posix().casefold()))

    def _content_build_files(self) -> tuple[Path, ...]:
        """Return validated production content graph files that must ship with the project.

        Like the scene package path, this is semantic opt-in. Old or malformed pre-1.9 project files
        do not suddenly enter a stricter code path unless a valid ``[content.build]`` table exists.
        Once opted in, missing/generated outputs and symlink escapes fail the export before staging.
        """

        manifest_path = self.project_root / "swirproject.toml"
        if not manifest_path.is_file():
            return ()
        try:
            raw = tomllib.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, tomllib.TOMLDecodeError):
            return ()
        if not isinstance(raw, dict):
            return ()
        content = raw.get("content")
        if not isinstance(content, dict) or "build" not in content:
            return ()

        from .content_build19 import ContentBuildError, ContentBuildGraph
        from .project19 import ProjectManifest

        manifest = ProjectManifest.load(manifest_path)
        graph = ContentBuildGraph.load_optional(manifest)
        if graph is None:
            return ()
        try:
            paths = graph.shipping_paths()
        except ContentBuildError as exc:
            raise ValueError(f"content build export preflight failed: {exc}") from exc
        return tuple(Path(value) for value in paths)

    def _collect_files(self, profile: PackagingProfile) -> tuple[Path, ...]:
        entrypoint = self._safe_relative(profile.entrypoint, label="entrypoint")
        candidates: set[Path] = set()
        entrypoint_path = self.project_root / entrypoint
        if not entrypoint_path.is_file():
            raise FileNotFoundError(f"entrypoint does not exist: {entrypoint_path}")
        candidates.add(entrypoint)

        for value in profile.include:
            relative = self._safe_relative(value, label="include path")
            source = self.project_root / relative
            if source.is_file():
                candidates.add(relative)
                continue
            if source.is_dir():
                for child in source.rglob("*"):
                    if child.is_file():
                        candidates.add(child.relative_to(self.project_root))

        scene_package_files = self._scene_package_files()
        content_build_files = self._content_build_files()
        candidates.update(scene_package_files)
        candidates.update(content_build_files)

        if profile.icon:
            icon = self._safe_relative(profile.icon, label="icon path")
            if not (self.project_root / icon).is_file():
                raise FileNotFoundError(f"icon does not exist: {self.project_root / icon}")
            candidates.add(icon)

        for optional in ("swirproject.toml", "requirements.txt", "pyproject.toml"):
            path = self.project_root / optional
            if path.is_file():
                candidates.add(Path(optional))

        filtered = [path for path in candidates if not self._is_excluded(path, profile.exclude)]
        excluded_scene_files = tuple(path for path in scene_package_files if path not in filtered)
        if excluded_scene_files:
            values = ", ".join(path.as_posix() for path in excluded_scene_files)
            raise ValueError(f"packaging profile excludes declared scene package content: {values}")
        excluded_build_files = tuple(path for path in content_build_files if path not in filtered)
        if excluded_build_files:
            values = ", ".join(path.as_posix() for path in excluded_build_files)
            raise ValueError(f"packaging profile excludes declared content build files: {values}")
        return tuple(sorted(filtered, key=lambda path: path.as_posix().casefold()))

    @staticmethod
    def _native_command(profile: PackagingProfile) -> tuple[str, ...] | None:
        if not profile.target.desktop:
            return None
        return (
            "python",
            "-m",
            "PyInstaller",
            "--noconfirm",
            "--clean",
            "--distpath",
            "native-dist",
            "--workpath",
            "native-build",
            "swirengine-build.spec",
        )

    @staticmethod
    def _data_files(files: Sequence[Path], entrypoint: Path) -> tuple[Path, ...]:
        # Keep dynamically loaded project scripts as data. Only the entrypoint is consumed directly
        # by PyInstaller; .pyc files remain excluded because source scripts are the portable form.
        return tuple(path for path in files if path != entrypoint and path.suffix.casefold() != ".pyc")

    @classmethod
    def _render_pyinstaller_spec(cls, plan: ExportPlan) -> str:
        profile = plan.profile
        entrypoint = cls._safe_relative(profile.entrypoint, label="entrypoint")
        datas = [
            (path.as_posix(), path.parent.as_posix() if path.parent != Path(".") else ".")
            for path in cls._data_files(plan.files, entrypoint)
        ]
        icon_expr = "None" if profile.icon is None else repr(Path(profile.icon).as_posix())
        common = (
            "# Generated by SwirEngine; portable across matching desktop hosts.\n"
            "a = Analysis(\n"
            f"    [{entrypoint.as_posix()!r}],\n"
            "    pathex=['.'],\n"
            "    binaries=[],\n"
            f"    datas={datas!r},\n"
            "    hiddenimports=[],\n"
            "    hookspath=[],\n"
            "    hooksconfig={},\n"
            "    runtime_hooks=[],\n"
            "    excludes=[],\n"
            "    noarchive=False,\n"
            ")\n"
            "pyz = PYZ(a.pure)\n"
        )
        if profile.onefile:
            return common + (
                "exe = EXE(\n"
                "    pyz, a.scripts, a.binaries, a.datas, [],\n"
                f"    name={profile.effective_app_name!r}, console={profile.console!r}, "
                f"icon={icon_expr},\n"
                ")\n"
            )
        return common + (
            "exe = EXE(\n"
            "    pyz, a.scripts, [], exclude_binaries=True,\n"
            f"    name={profile.effective_app_name!r}, console={profile.console!r}, "
            f"icon={icon_expr},\n"
            ")\n"
            "coll = COLLECT(\n"
            "    exe, a.binaries, a.datas,\n"
            f"    name={profile.effective_app_name!r},\n"
            ")\n"
        )

    @staticmethod
    def _sha256(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    def plan(
        self,
        profile: PackagingProfile,
        output_dir: str | Path | None = None,
    ) -> ExportPlan:
        destination = (
            Path(output_dir).expanduser().resolve()
            if output_dir is not None
            else self.project_root
            / "dist"
            / f"{profile.effective_app_name}-{profile.target.value}"
        )
        return ExportPlan(
            project_root=self.project_root,
            output_dir=destination,
            profile=profile,
            files=self._collect_files(profile),
            native_build_command=self._native_command(profile),
            experimental=profile.target in {ExportTarget.ANDROID, ExportTarget.WEB},
        )

    def export(
        self,
        profile: PackagingProfile,
        output_dir: str | Path | None = None,
        *,
        clean: bool = True,
    ) -> ExportResult:
        plan = self.plan(profile, output_dir)
        overlaps_source = (
            plan.output_dir == self.project_root or self.project_root in plan.output_dir.parents
        )
        if overlaps_source and plan.output_dir.parent != self.project_root / "dist":
            raise ValueError("output directory must not overlap project source")

        if clean and plan.output_dir.exists():
            shutil.rmtree(plan.output_dir)
        plan.output_dir.mkdir(parents=True, exist_ok=True)

        copied: list[Path] = []
        checksums: dict[str, str] = {}
        for relative in plan.files:
            source = self.project_root / relative
            destination = plan.output_dir / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)
            copied.append(destination)
            checksums[relative.as_posix()] = self._sha256(destination)

        native_spec: Path | None = None
        if profile.target.desktop:
            native_spec = plan.output_dir / "swirengine-build.spec"
            native_spec.write_text(self._render_pyinstaller_spec(plan), encoding="utf-8")

        manifest_payload = {
            "format": "swirengine-export",
            "version": 2,
            "target": profile.target.value,
            "experimental": plan.experimental,
            "entrypoint": profile.entrypoint,
            "app_name": profile.effective_app_name,
            "files": [path.as_posix() for path in plan.files],
            "sha256": checksums,
            "native_build_command": list(plan.native_build_command or ()),
            "native_spec": None if native_spec is None else native_spec.name,
            "metadata": dict(profile.metadata),
            "host": os.name,
        }
        manifest = plan.output_dir / "swir-export.json"
        manifest.write_text(json.dumps(manifest_payload, indent=2) + "\n", encoding="utf-8")

        return ExportResult(
            output_dir=plan.output_dir,
            manifest=manifest,
            copied_files=tuple(copied),
            native_build_command=plan.native_build_command,
            experimental=plan.experimental,
            native_spec=native_spec,
        )

    @classmethod
    def _validate_native_host(cls, target: ExportTarget) -> None:
        if not target.desktop:
            raise NativeBuildError(f"native build is not available for {target.value}")
        expected = cls._DESKTOP_HOSTS[target]
        if sys.platform != expected:
            raise NativeBuildError(
                f"{target.value} builds must run on a matching host; current platform is {sys.platform}"
            )

    def build_native(
        self,
        profile: PackagingProfile,
        output_dir: str | Path | None = None,
        *,
        clean: bool = True,
        runner: Runner = subprocess.run,
    ) -> NativeBuildResult:
        """Stage and execute a host-native desktop build using the generated portable spec.

        SwirEngine deliberately does not cross-compile desktop games. Windows builds run on Windows,
        Linux builds on Linux and macOS builds on macOS. The caller must install PyInstaller in the
        selected build environment; no dependency installation is performed implicitly.
        """

        self._validate_native_host(profile.target)
        exported = self.export(profile, output_dir, clean=clean)
        if exported.native_build_command is None or exported.native_spec is None:
            raise NativeBuildError("desktop export did not produce a native build plan")

        command = (sys.executable, *exported.native_build_command[1:])
        completed = runner(
            command,
            cwd=exported.output_dir,
            capture_output=True,
            text=True,
            check=False,
        )
        returncode = int(completed.returncode)
        if returncode != 0:
            stderr = str(getattr(completed, "stderr", "")).strip()
            tail = stderr[-2000:] if stderr else "no stderr was captured"
            raise NativeBuildError(f"native build failed with exit code {returncode}: {tail}")

        native_dist = exported.output_dir / "native-dist"
        if not native_dist.is_dir():
            raise NativeBuildError("native build succeeded but native-dist was not created")
        artifacts = tuple(sorted(native_dist.iterdir(), key=lambda path: path.name.casefold()))
        if not artifacts:
            raise NativeBuildError("native build succeeded but produced no artifacts")

        return NativeBuildResult(
            export=exported,
            command=command,
            artifacts=artifacts,
            returncode=returncode,
        )
