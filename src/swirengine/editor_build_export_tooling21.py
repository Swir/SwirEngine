from __future__ import annotations

import json
import os
import uuid
from collections.abc import Mapping
from dataclasses import dataclass, replace
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any

from .exporting import (
    ExportPlan,
    ExportResult,
    NativeBuildResult,
    PackagingProfile,
    ProjectExporter,
)

DEFAULT_BUILD_EXPORT_PATH = "config/build-export.json"
_FORMAT = "swirengine.build-export"
_FORMAT_VERSION = 1


class EditorBuildExportToolingError(ValueError):
    """Raised when creator-authored build/export configuration is invalid."""


@dataclass(frozen=True, slots=True)
class BuildExportConfig21:
    """Deterministic creator configuration for SwirEngine's shipping exporter."""

    active_profile: str
    output_root: str
    profiles: tuple[PackagingProfile, ...]

    def __post_init__(self) -> None:
        output_root = _project_relative_path(self.output_root, label="output root")
        object.__setattr__(self, "output_root", output_root)
        if not self.profiles:
            raise EditorBuildExportToolingError("at least one export profile is required")
        names = [profile.name for profile in self.profiles]
        if len(names) != len(set(names)):
            raise EditorBuildExportToolingError("export profile names must be unique")
        if self.active_profile not in names:
            raise EditorBuildExportToolingError(
                f"active export profile does not exist: {self.active_profile}"
            )

    @property
    def active(self) -> PackagingProfile:
        return self.profile(self.active_profile)

    def profile(self, name: str) -> PackagingProfile:
        for profile in self.profiles:
            if profile.name == name:
                return profile
        raise EditorBuildExportToolingError(f"unknown export profile: {name}")

    def portable(self) -> dict[str, Any]:
        return {
            "format": _FORMAT,
            "format_version": _FORMAT_VERSION,
            "active_profile": self.active_profile,
            "output_root": self.output_root,
            "profiles": [profile.to_dict() for profile in self.profiles],
        }

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> BuildExportConfig21:
        if payload.get("format") != _FORMAT:
            raise EditorBuildExportToolingError("unsupported build/export configuration format")
        if payload.get("format_version") != _FORMAT_VERSION:
            raise EditorBuildExportToolingError("unsupported build/export configuration version")
        raw_profiles = payload.get("profiles")
        if not isinstance(raw_profiles, list):
            raise EditorBuildExportToolingError("profiles must be an array")
        profiles: list[PackagingProfile] = []
        for raw in raw_profiles:
            if not isinstance(raw, Mapping):
                raise EditorBuildExportToolingError("each export profile must be an object")
            try:
                profiles.append(PackagingProfile.from_dict(dict(raw)))
            except (TypeError, ValueError) as exc:
                raise EditorBuildExportToolingError(str(exc)) from exc
        return cls(
            active_profile=str(payload.get("active_profile", "")),
            output_root=str(payload.get("output_root", "dist")),
            profiles=tuple(profiles),
        )


@dataclass(frozen=True, slots=True)
class EditorBuildExportSnapshot21:
    path: str
    config: BuildExportConfig21
    dirty: bool


class EditorBuildExportTooling21:
    """Creator-facing Build/Export Wizard core backed by :class:`ProjectExporter`.

    The tooling authors deterministic packaging profiles, previews the exact runtime export plan,
    stages distributable files through the shipping exporter and delegates native builds to the
    same host-gated path. It never installs build dependencies or pretends to cross-compile.
    """

    def __init__(
        self,
        project_root: str | Path,
        *,
        project_name: str | None = None,
        path: str = DEFAULT_BUILD_EXPORT_PATH,
    ) -> None:
        self.project_root = Path(project_root).expanduser().resolve()
        if not self.project_root.is_dir():
            raise FileNotFoundError(f"project directory does not exist: {self.project_root}")
        self.relative_path = _project_relative_path(path, label="build/export path")
        app_name = (project_name or self.project_root.name).strip() or self.project_root.name
        default_profile = PackagingProfile(name="desktop", app_name=app_name)
        self._config = BuildExportConfig21(
            active_profile=default_profile.name,
            output_root="dist",
            profiles=(default_profile,),
        )
        self._saved_fingerprint = self._fingerprint(self._config)
        self.reload()

    @property
    def target(self) -> Path:
        return _project_target(self.project_root, self.relative_path, label="build/export path")

    @property
    def config(self) -> BuildExportConfig21:
        return self._config

    @property
    def dirty(self) -> bool:
        return self._fingerprint(self._config) != self._saved_fingerprint

    def snapshot(self) -> EditorBuildExportSnapshot21:
        return EditorBuildExportSnapshot21(self.relative_path, self._config, self.dirty)

    def select_profile(self, name: str) -> EditorBuildExportSnapshot21:
        self._config.profile(name)
        self._config = replace(self._config, active_profile=name)
        return self.snapshot()

    def set_output_root(self, path: str) -> EditorBuildExportSnapshot21:
        self._config = replace(
            self._config,
            output_root=_project_relative_path(path, label="output root"),
        )
        return self.snapshot()

    def upsert_profile(self, profile: PackagingProfile) -> EditorBuildExportSnapshot21:
        if not isinstance(profile, PackagingProfile):
            raise TypeError("profile must be a PackagingProfile")
        profiles = list(self._config.profiles)
        for index, current in enumerate(profiles):
            if current.name == profile.name:
                profiles[index] = profile
                break
        else:
            profiles.append(profile)
        self._config = replace(self._config, profiles=tuple(profiles))
        return self.snapshot()

    def remove_profile(self, name: str) -> EditorBuildExportSnapshot21:
        self._config.profile(name)
        if len(self._config.profiles) == 1:
            raise EditorBuildExportToolingError("cannot remove the last export profile")
        profiles = tuple(profile for profile in self._config.profiles if profile.name != name)
        active = self._config.active_profile
        if active == name:
            active = profiles[0].name
        self._config = replace(self._config, profiles=profiles, active_profile=active)
        return self.snapshot()

    def output_dir(self, profile_name: str | None = None) -> Path:
        profile = self._profile(profile_name)
        root = _project_target(self.project_root, self._config.output_root, label="output root")
        return root / f"{profile.effective_app_name}-{profile.target.value}"

    def preflight(self, profile_name: str | None = None) -> ExportPlan:
        """Return the exact shipping export plan without copying or building anything."""
        profile = self._profile(profile_name)
        return ProjectExporter(self.project_root).plan(profile, self.output_dir(profile.name))

    def stage(
        self,
        profile_name: str | None = None,
        *,
        clean: bool = True,
    ) -> ExportResult:
        """Stage a portable export and deterministic manifest through the shipping exporter."""
        profile = self._profile(profile_name)
        return ProjectExporter(self.project_root).export(
            profile,
            self.output_dir(profile.name),
            clean=clean,
        )

    def build_native(
        self,
        profile_name: str | None = None,
        *,
        clean: bool = True,
        runner: Any = None,
    ) -> NativeBuildResult:
        """Run an explicit host-native build; cross-compilation remains intentionally rejected."""
        profile = self._profile(profile_name)
        exporter = ProjectExporter(self.project_root)
        kwargs: dict[str, Any] = {"clean": clean}
        if runner is not None:
            kwargs["runner"] = runner
        return exporter.build_native(profile, self.output_dir(profile.name), **kwargs)

    def save(self) -> EditorBuildExportSnapshot21:
        target = self.target
        target.parent.mkdir(parents=True, exist_ok=True)
        text = _canonical_text(self._config.portable())
        temporary = target.with_name(f".{target.name}.{uuid.uuid4().hex}.tmp")
        try:
            with temporary.open("w", encoding="utf-8", newline="\n") as stream:
                stream.write(text)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, target)
        finally:
            if temporary.exists():
                temporary.unlink()
        self._saved_fingerprint = self._fingerprint(self._config)
        return self.snapshot()

    def reload(self) -> EditorBuildExportSnapshot21:
        target = self.target
        if target.exists():
            try:
                payload = json.loads(target.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                raise EditorBuildExportToolingError(
                    f"cannot read build/export configuration: {exc}"
                ) from exc
            if not isinstance(payload, Mapping):
                raise EditorBuildExportToolingError("build/export configuration must be an object")
            self._config = BuildExportConfig21.from_mapping(payload)
        self._saved_fingerprint = self._fingerprint(self._config)
        return self.snapshot()

    def _profile(self, name: str | None) -> PackagingProfile:
        return self._config.active if name is None else self._config.profile(name)

    @staticmethod
    def _fingerprint(config: BuildExportConfig21) -> str:
        return _canonical_text(config.portable())


def _canonical_text(payload: Mapping[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, allow_nan=False, indent=2, sort_keys=True) + "\n"


def _project_relative_path(value: str | Path, *, label: str) -> str:
    raw = str(value).strip()
    normalized = raw.replace("\\", "/")
    if not normalized or normalized == ".":
        raise EditorBuildExportToolingError(f"{label} cannot be empty")
    posix = PurePosixPath(normalized)
    windows = PureWindowsPath(raw)
    if (
        posix.is_absolute()
        or windows.is_absolute()
        or bool(windows.drive)
        or bool(windows.root)
        or ".." in posix.parts
    ):
        raise EditorBuildExportToolingError(f"{label} must stay project-relative")
    return posix.as_posix()


def _project_target(root: Path, relative: str, *, label: str) -> Path:
    resolved = (root / PurePosixPath(relative)).resolve(strict=False)
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise EditorBuildExportToolingError(f"{label} escapes the project root") from exc
    return resolved
