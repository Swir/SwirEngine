from __future__ import annotations

import json
import os
import shutil
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Iterable


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
            include=tuple(str(value) for value in data.get("include", ("assets", "scenes", "scripts"))),
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
            metadata={str(key): str(value) for key, value in dict(data.get("metadata", {})).items()},
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
            raise ValueError("packaging profile must contain a JSON object")
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


class ProjectExporter:
    """Create portable export staging directories for desktop/mobile/web targets.

    Desktop profiles include a ready-to-run PyInstaller command but do not execute third-party
    build tools implicitly. Android and Web exports are intentionally marked experimental and emit
    a machine-readable manifest describing the target so external toolchains can consume the same
    staged project without changing game source code.
    """

    def __init__(self, project_root: str | Path) -> None:
        self.project_root = Path(project_root).expanduser().resolve()
        if not self.project_root.is_dir():
            raise FileNotFoundError(f"project directory does not exist: {self.project_root}")

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

    def _collect_files(self, profile: PackagingProfile) -> tuple[Path, ...]:
        entrypoint = Path(profile.entrypoint)
        candidates: set[Path] = set()
        entrypoint_path = self.project_root / entrypoint
        if not entrypoint_path.is_file():
            raise FileNotFoundError(f"entrypoint does not exist: {entrypoint_path}")
        candidates.add(entrypoint)

        for value in profile.include:
            relative = Path(value)
            source = self.project_root / relative
            if source.is_file():
                candidates.add(relative)
                continue
            if source.is_dir():
                for child in source.rglob("*"):
                    if child.is_file():
                        candidates.add(child.relative_to(self.project_root))

        for optional in ("swirproject.toml", "requirements.txt", "pyproject.toml"):
            path = self.project_root / optional
            if path.is_file():
                candidates.add(Path(optional))

        filtered = [
            path for path in candidates if not self._is_excluded(path, profile.exclude)
        ]
        return tuple(sorted(filtered, key=lambda path: path.as_posix().casefold()))

    @staticmethod
    def _native_command(profile: PackagingProfile) -> tuple[str, ...] | None:
        if not profile.target.desktop:
            return None
        command = [
            "python",
            "-m",
            "PyInstaller",
            "--noconfirm",
            "--clean",
            "--name",
            profile.effective_app_name,
        ]
        if profile.onefile:
            command.append("--onefile")
        if not profile.console:
            command.append("--windowed")
        if profile.icon:
            command.extend(("--icon", profile.icon))
        command.append(profile.entrypoint)
        return tuple(command)

    def plan(
        self,
        profile: PackagingProfile,
        output_dir: str | Path | None = None,
    ) -> ExportPlan:
        destination = (
            Path(output_dir).expanduser().resolve()
            if output_dir is not None
            else self.project_root / "dist" / f"{profile.effective_app_name}-{profile.target.value}"
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
        if plan.output_dir == self.project_root or self.project_root in plan.output_dir.parents:
            if plan.output_dir.parent != self.project_root / "dist":
                raise ValueError("output directory must not overlap project source")

        if clean and plan.output_dir.exists():
            shutil.rmtree(plan.output_dir)
        plan.output_dir.mkdir(parents=True, exist_ok=True)

        copied: list[Path] = []
        for relative in plan.files:
            source = self.project_root / relative
            destination = plan.output_dir / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)
            copied.append(destination)

        manifest_payload = {
            "format": "swirengine-export",
            "version": 1,
            "target": profile.target.value,
            "experimental": plan.experimental,
            "entrypoint": profile.entrypoint,
            "app_name": profile.effective_app_name,
            "files": [path.as_posix() for path in plan.files],
            "native_build_command": list(plan.native_build_command or ()),
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
        )
