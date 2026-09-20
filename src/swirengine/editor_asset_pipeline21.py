from __future__ import annotations

import os
import shutil
import tempfile
import wave
from collections.abc import Iterable
from dataclasses import dataclass
from enum import Enum
from pathlib import Path, PurePosixPath, PureWindowsPath

from .asset_pipeline import (
    AssetImportDiagnostics,
    AssetImportRequest,
    AssetImportResult,
    AssetPipeline,
)
from .assets import AssetManager
from .editor_assets import classify_editor_asset

_TEXT_PREVIEW_SUFFIXES = {
    ".csv",
    ".frag",
    ".geom",
    ".glsl",
    ".json",
    ".md",
    ".py",
    ".toml",
    ".txt",
    ".vert",
    ".yaml",
    ".yml",
}
_IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif", ".tga", ".hdr"}
_AUDIO_SUFFIXES = {".wav", ".mp3", ".ogg", ".flac", ".m4a"}


class EditorAssetIssueSeverity(str, Enum):
    """Creator-facing issue severity for asset import and validation."""

    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


@dataclass(frozen=True, slots=True)
class EditorAssetIssue:
    """Actionable creator-facing asset validation issue."""

    code: str
    message: str
    severity: EditorAssetIssueSeverity
    action: str | None = None

    @property
    def blocking(self) -> bool:
        return self.severity is EditorAssetIssueSeverity.ERROR


@dataclass(frozen=True, slots=True)
class EditorAssetImportTicket:
    """One background import/reimport request exposed to SwirEditor."""

    relative_path: str
    source: Path
    destination: Path
    request: AssetImportRequest | None
    copied: bool
    issues: tuple[EditorAssetIssue, ...] = ()

    @property
    def queued(self) -> bool:
        return self.request is not None

    @property
    def request_id(self) -> int | None:
        return None if self.request is None else self.request.request_id


@dataclass(frozen=True, slots=True)
class EditorAssetPreview:
    """Safe, bounded preview metadata for one project asset."""

    relative_path: str
    kind: str
    suffix: str
    size_bytes: int
    summary: str
    text: str | None = None
    width: int | None = None
    height: int | None = None
    duration_seconds: float | None = None


@dataclass(frozen=True, slots=True)
class EditorAssetDependencyView:
    """Dependency/dependent paths for one asset, normalized for creator display."""

    relative_path: str
    dependencies: tuple[str, ...]
    dependents: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class EditorAssetPipelineFrame:
    """Low-cost editor snapshot combining runtime pipeline diagnostics and recent results."""

    diagnostics: AssetImportDiagnostics
    recent_results: tuple[AssetImportResult, ...]
    tracked_origins: tuple[tuple[str, str], ...]


def _project_relative_path(value: str | Path, *, label: str) -> str:
    raw = str(value).strip()
    normalized = raw.replace("\\", "/")
    if not normalized or normalized == ".":
        raise ValueError(f"{label} cannot be empty")
    posix = PurePosixPath(normalized)
    windows = PureWindowsPath(raw)
    if (
        posix.is_absolute()
        or windows.is_absolute()
        or bool(windows.drive)
        or bool(windows.root)
        or ".." in posix.parts
    ):
        raise ValueError(f"{label} must stay project-relative")
    return posix.as_posix()


class EditorAssetPipeline21:
    """Creator-facing asset import workflow backed by the runtime :class:`AssetPipeline`.

    The editor owns file-copy/origin tracking, safe previews and actionable validation while all
    processor selection, background work, cache invalidation and dependency tracking stay in the
    runtime ``AssetPipeline``. This keeps SwirEditor useful without creating a second import engine.
    """

    def __init__(
        self,
        manager: AssetManager,
        pipeline: AssetPipeline,
        *,
        preview_limit_bytes: int = 64 * 1024,
    ) -> None:
        if not isinstance(manager, AssetManager):
            raise TypeError("manager must be an AssetManager")
        if not isinstance(pipeline, AssetPipeline):
            raise TypeError("pipeline must be an AssetPipeline")
        if pipeline.assets is not manager:
            raise ValueError("pipeline must use the same AssetManager")
        if int(preview_limit_bytes) <= 0:
            raise ValueError("preview_limit_bytes must be greater than zero")
        self.manager = manager
        self.pipeline = pipeline.bind()
        self.preview_limit_bytes = int(preview_limit_bytes)
        self._origins: dict[str, Path] = {}
        self._recent_results: dict[int, AssetImportResult] = {}

    @property
    def root(self) -> Path:
        return self.manager.root.expanduser().resolve()

    def processor_for(self, asset: str | Path) -> str | None:
        """Return the configured runtime processor for an asset suffix, if one exists."""

        suffix = Path(asset).suffix.lower()
        mapping = getattr(self.pipeline, "_processor_by_suffix", None)
        if not isinstance(mapping, dict):
            return None
        owner = mapping.get(suffix)
        return None if owner is None else str(owner)

    def validate_import(
        self,
        source: str | Path,
        *,
        destination: str | Path | None = None,
        overwrite: bool = False,
    ) -> tuple[EditorAssetIssue, ...]:
        """Validate an import without touching project files or starting background work."""

        source_path = Path(source).expanduser()
        issues: list[EditorAssetIssue] = []
        if not source_path.exists():
            issues.append(
                EditorAssetIssue(
                    "source_missing",
                    f"Source file does not exist: {source_path}",
                    EditorAssetIssueSeverity.ERROR,
                    "Choose an existing file and retry the import.",
                )
            )
            return tuple(issues)
        if not source_path.is_file():
            issues.append(
                EditorAssetIssue(
                    "source_not_file",
                    f"Source is not a file: {source_path}",
                    EditorAssetIssueSeverity.ERROR,
                    "Drop a file or use import_paths() for a directory.",
                )
            )
            return tuple(issues)

        try:
            relative = self._destination_for(source_path, destination)
        except ValueError as exc:
            issues.append(
                EditorAssetIssue(
                    "destination_unsafe",
                    str(exc),
                    EditorAssetIssueSeverity.ERROR,
                    "Choose a project-relative destination inside the asset root.",
                )
            )
            return tuple(issues)

        target = self.root / PurePosixPath(relative)
        try:
            target.resolve(strict=False).relative_to(self.root)
        except ValueError:
            issues.append(
                EditorAssetIssue(
                    "destination_escape",
                    f"Destination escapes the project asset root: {relative}",
                    EditorAssetIssueSeverity.ERROR,
                    "Choose a destination under the project assets directory.",
                )
            )
        if target.exists() and target.resolve() != source_path.resolve() and not overwrite:
            issues.append(
                EditorAssetIssue(
                    "destination_exists",
                    f"Asset already exists: {relative}",
                    EditorAssetIssueSeverity.ERROR,
                    "Use reimport or explicitly allow overwrite.",
                )
            )
        if self.processor_for(relative) is None:
            suffix = Path(relative).suffix.lower() or "<none>"
            issues.append(
                EditorAssetIssue(
                    "processor_missing",
                    f"No runtime asset processor is registered for suffix {suffix!r}.",
                    EditorAssetIssueSeverity.WARNING,
                    "Register an AssetPipeline processor to enable background derived-data import.",
                )
            )
        return tuple(issues)

    def import_file(
        self,
        source: str | Path,
        *,
        destination: str | Path | None = None,
        overwrite: bool = False,
        submit: bool = True,
    ) -> EditorAssetImportTicket:
        """Copy one file into project assets and optionally queue runtime background processing."""

        source_path = Path(source).expanduser().resolve()
        issues = self.validate_import(source_path, destination=destination, overwrite=overwrite)
        blockers = tuple(issue for issue in issues if issue.blocking)
        if blockers:
            raise ValueError("; ".join(issue.message for issue in blockers))

        relative = self._destination_for(source_path, destination)
        target = self.root / PurePosixPath(relative)
        target.parent.mkdir(parents=True, exist_ok=True)
        copied = source_path != target.resolve(strict=False)
        if copied:
            self._atomic_copy(source_path, target)

        self._origins[relative] = source_path
        self.manager.invalidate(relative)

        request: AssetImportRequest | None = None
        if submit and self.processor_for(relative) is not None:
            request = self.pipeline.submit(relative, force=overwrite)
        return EditorAssetImportTicket(
            relative,
            source_path,
            target.resolve(),
            request,
            copied,
            issues,
        )

    def reimport(
        self,
        asset: str | Path,
        *,
        submit: bool = True,
    ) -> EditorAssetImportTicket:
        """Refresh a project asset from its tracked origin and force runtime reprocessing."""

        relative = _project_relative_path(asset, label="asset path")
        target = self.manager.require(relative).expanduser().resolve()
        source = self._origins.get(relative, target)
        if source != target:
            if not source.is_file():
                raise FileNotFoundError(source)
            self._atomic_copy(source, target)

        self.manager.invalidate(relative)
        issues = self.validate_asset(relative)
        request: AssetImportRequest | None = None
        if submit and self.processor_for(relative) is not None:
            request = self.pipeline.submit(relative, force=True)
        return EditorAssetImportTicket(
            relative,
            source,
            target,
            request,
            source != target,
            issues,
        )

    def import_paths(
        self,
        paths: Iterable[str | Path],
        *,
        destination_folder: str | Path = "",
        overwrite: bool = False,
        submit: bool = True,
    ) -> tuple[EditorAssetImportTicket, ...]:
        """Import a drag/drop-style batch, recursively preserving dropped directory structure."""

        folder = ""
        raw_folder = str(destination_folder).strip()
        if raw_folder and raw_folder != ".":
            folder = _project_relative_path(destination_folder, label="asset destination folder")
        tickets: list[EditorAssetImportTicket] = []
        for raw in paths:
            source = Path(raw).expanduser().resolve()
            if source.is_dir():
                base = PurePosixPath(folder) / source.name if folder else PurePosixPath(source.name)
                for child in sorted(
                    (item for item in source.rglob("*") if item.is_file()),
                    key=lambda item: item.as_posix().casefold(),
                ):
                    relative_child = child.relative_to(source)
                    destination = (base / PurePosixPath(relative_child.as_posix())).as_posix()
                    tickets.append(
                        self.import_file(
                            child,
                            destination=destination,
                            overwrite=overwrite,
                            submit=submit,
                        )
                    )
            else:
                destination = (
                    (PurePosixPath(folder) / source.name).as_posix() if folder else source.name
                )
                tickets.append(
                    self.import_file(
                        source,
                        destination=destination,
                        overwrite=overwrite,
                        submit=submit,
                    )
                )
        return tuple(tickets)

    def poll(self) -> tuple[AssetImportResult, ...]:
        """Finalize completed runtime jobs on the editor thread and retain result diagnostics."""

        results = self.pipeline.poll()
        for result in results:
            self._recent_results[result.request_id] = result
        return results

    def wait(
        self,
        ticket: EditorAssetImportTicket | AssetImportRequest | int,
        *,
        timeout: float | None = None,
    ) -> AssetImportResult:
        """Wait for one queued import and retain its result for editor diagnostics."""

        if isinstance(ticket, EditorAssetImportTicket):
            if ticket.request is None:
                raise ValueError(f"asset {ticket.relative_path!r} has no queued processor request")
            request: AssetImportRequest | int = ticket.request
        else:
            request = ticket
        result = self.pipeline.wait(request, timeout=timeout)
        self._recent_results[result.request_id] = result
        return result

    def validate_asset(self, asset: str | Path) -> tuple[EditorAssetIssue, ...]:
        """Return actionable issues for an existing project asset and its dependencies."""

        relative = _project_relative_path(asset, label="asset path")
        path = self.manager.resolve(relative).expanduser().resolve()
        issues: list[EditorAssetIssue] = []
        if not path.is_file():
            return (
                EditorAssetIssue(
                    "asset_missing",
                    f"Project asset is missing: {relative}",
                    EditorAssetIssueSeverity.ERROR,
                    "Restore, reimport or remove references to the missing asset.",
                ),
            )
        if self.processor_for(relative) is None:
            suffix = path.suffix.lower() or "<none>"
            issues.append(
                EditorAssetIssue(
                    "processor_missing",
                    f"No runtime asset processor is registered for suffix {suffix!r}.",
                    EditorAssetIssueSeverity.WARNING,
                    "Register an AssetPipeline processor if derived-data import is required.",
                )
            )
        for dependency in self.pipeline.dependencies.dependencies(path):
            if not dependency.is_file():
                issues.append(
                    EditorAssetIssue(
                        "dependency_missing",
                        f"Dependency is missing: {self._display_path(dependency)}",
                        EditorAssetIssueSeverity.ERROR,
                        "Restore the dependency or update the source asset reference.",
                    )
                )
        return tuple(issues)

    def preview(self, asset: str | Path) -> EditorAssetPreview:
        """Build a bounded preview without invoking arbitrary asset loaders."""

        relative = _project_relative_path(asset, label="asset path")
        path = self.manager.require(relative).expanduser().resolve()
        size = path.stat().st_size
        suffix = path.suffix.lower()
        kind = classify_editor_asset(relative)

        if suffix in _TEXT_PREVIEW_SUFFIXES:
            with path.open("rb") as handle:
                raw = handle.read(self.preview_limit_bytes)
            text = raw.decode("utf-8", errors="replace")
            truncated = size > len(raw)
            if truncated:
                text += "\n…"
            return EditorAssetPreview(
                relative,
                kind,
                suffix,
                size,
                f"{kind} text preview{' (truncated)' if truncated else ''}",
                text=text,
            )

        if suffix == ".png":
            width, height = self._png_size(path)
            detail = (
                f"PNG image · {width}×{height}"
                if width is not None and height is not None
                else "PNG image"
            )
            return EditorAssetPreview(
                relative,
                kind,
                suffix,
                size,
                detail,
                width=width,
                height=height,
            )

        if suffix == ".wav":
            duration: float | None = None
            summary = "WAV audio"
            try:
                with wave.open(str(path), "rb") as handle:
                    frames = handle.getnframes()
                    rate = handle.getframerate()
                    channels = handle.getnchannels()
                    duration = frames / rate if rate else 0.0
                    summary = f"WAV audio · {channels} channel(s) · {rate} Hz · {duration:.2f}s"
            except (EOFError, OSError, wave.Error):
                pass
            return EditorAssetPreview(
                relative,
                kind,
                suffix,
                size,
                summary,
                duration_seconds=duration,
            )

        if suffix in _IMAGE_SUFFIXES:
            category = "image"
        elif suffix in _AUDIO_SUFFIXES:
            category = "audio"
        else:
            category = kind
        return EditorAssetPreview(
            relative,
            kind,
            suffix,
            size,
            f"{category} asset · {size} bytes",
        )

    def dependencies(self, asset: str | Path) -> EditorAssetDependencyView:
        """Expose direct dependency and dependent relationships tracked by the runtime pipeline."""

        relative = _project_relative_path(asset, label="asset path")
        path = self.manager.require(relative).expanduser().resolve()
        dependencies = tuple(
            self._display_path(item) for item in self.pipeline.dependencies.dependencies(path)
        )
        dependents = tuple(
            self._display_path(item) for item in self.pipeline.dependencies.direct_dependents(path)
        )
        return EditorAssetDependencyView(relative, dependencies, dependents)

    def origin(self, asset: str | Path) -> Path | None:
        relative = _project_relative_path(asset, label="asset path")
        return self._origins.get(relative)

    def frame(self) -> EditorAssetPipelineFrame:
        tracked = tuple(
            sorted(
                ((relative, str(source)) for relative, source in self._origins.items()),
                key=lambda item: item[0].casefold(),
            )
        )
        results = tuple(self._recent_results[key] for key in sorted(self._recent_results))
        return EditorAssetPipelineFrame(self.pipeline.diagnostics, results, tracked)

    def close(self, *, wait: bool = True, cancel_futures: bool = False) -> None:
        self.pipeline.close(wait=wait, cancel_futures=cancel_futures)

    def _destination_for(self, source: Path, destination: str | Path | None) -> str:
        if destination is None:
            return _project_relative_path(source.name, label="asset destination")
        return _project_relative_path(destination, label="asset destination")

    def _display_path(self, path: Path) -> str:
        resolved = path.expanduser().resolve()
        try:
            return resolved.relative_to(self.root).as_posix()
        except ValueError:
            return str(resolved)

    @staticmethod
    def _atomic_copy(source: Path, destination: Path) -> None:
        fd, temp_name = tempfile.mkstemp(
            prefix=f".{destination.name}.",
            suffix=".swirtmp",
            dir=destination.parent,
        )
        os.close(fd)
        temp = Path(temp_name)
        try:
            shutil.copy2(source, temp)
            os.replace(temp, destination)
        finally:
            try:
                temp.unlink()
            except FileNotFoundError:
                pass

    @staticmethod
    def _png_size(path: Path) -> tuple[int | None, int | None]:
        try:
            with path.open("rb") as handle:
                header = handle.read(24)
        except OSError:
            return None, None
        if len(header) < 24 or header[:8] != b"\x89PNG\r\n\x1a\n" or header[12:16] != b"IHDR":
            return None, None
        return int.from_bytes(header[16:20], "big"), int.from_bytes(header[20:24], "big")
