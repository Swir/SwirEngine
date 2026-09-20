from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .asset_pipeline import AssetPipeline
from .assets import AssetManager
from .editor_asset_pipeline21 import (
    EditorAssetIssue,
    EditorAssetIssueSeverity,
    EditorAssetPipeline21,
    EditorAssetPreview,
)
from .graphics.gltf import _load_document
from .graphics.gltf_dependencies import gltf_asset_dependencies

_EDITOR_GENERIC_SUFFIXES_21 = (
    ".bmp",
    ".comp",
    ".csv",
    ".dae",
    ".fbx",
    ".flac",
    ".frag",
    ".geom",
    ".gif",
    ".glsl",
    ".hdr",
    ".jpeg",
    ".jpg",
    ".json",
    ".m4a",
    ".md",
    ".mp3",
    ".obj",
    ".ogg",
    ".otf",
    ".png",
    ".py",
    ".tga",
    ".toml",
    ".ttf",
    ".txt",
    ".vert",
    ".wav",
    ".webp",
    ".woff",
    ".woff2",
    ".yaml",
    ".yml",
)
_GLTF_SUFFIXES_21 = (".gltf", ".glb")


@dataclass(frozen=True, slots=True)
class EditorGltfInspection21:
    """Bounded creator-facing glTF/GLB structure and dependency summary."""

    scenes: int
    nodes: int
    meshes: int
    materials: int
    animations: int
    images: int
    buffers: int
    external_dependencies: tuple[Path, ...]
    missing_dependencies: tuple[Path, ...]

    @property
    def summary(self) -> str:
        return (
            "glTF 2.0 · "
            f"{self.scenes} scene(s) · {self.nodes} node(s) · {self.meshes} mesh(es) · "
            f"{self.materials} material(s) · {self.animations} animation(s)"
        )

    def as_text(self, source: Path) -> str:
        base = source.parent.resolve()

        def display(path: Path) -> str:
            try:
                return path.resolve().relative_to(base).as_posix()
            except ValueError:
                return path.resolve().as_posix()

        lines = [
            "glTF 2.0 structure",
            f"Scenes: {self.scenes}",
            f"Nodes: {self.nodes}",
            f"Meshes: {self.meshes}",
            f"Materials: {self.materials}",
            f"Animations: {self.animations}",
            f"Images: {self.images}",
            f"Buffers: {self.buffers}",
            f"External dependencies: {len(self.external_dependencies)}",
        ]
        if self.external_dependencies:
            lines.extend(f"- {display(path)}" for path in self.external_dependencies)
        if self.missing_dependencies:
            lines.append(f"Missing dependencies: {len(self.missing_dependencies)}")
            lines.extend(f"- {display(path)}" for path in self.missing_dependencies)
        return "\n".join(lines)


def _collection_size(document: dict[str, Any], key: str) -> int:
    value = document.get(key, ())
    return len(value) if isinstance(value, list) else 0


def source_metadata21(path: Path) -> dict[str, object]:
    """Return deterministic bounded-memory source metadata for editor background jobs."""

    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(1024 * 1024)
            if not chunk:
                break
            size += len(chunk)
            digest.update(chunk)
    return {"size_bytes": size, "sha256": digest.hexdigest()}


def inspect_gltf21(path: str | Path) -> EditorGltfInspection21:
    """Inspect glTF 2.0 structure without decoding mesh/image payloads."""

    source = Path(path).expanduser().resolve()
    document, _binary_chunk = _load_document(source)
    dependencies = gltf_asset_dependencies(source)
    missing = tuple(dependency for dependency in dependencies if not dependency.is_file())
    return EditorGltfInspection21(
        scenes=_collection_size(document, "scenes"),
        nodes=_collection_size(document, "nodes"),
        meshes=_collection_size(document, "meshes"),
        materials=_collection_size(document, "materials"),
        animations=_collection_size(document, "animations"),
        images=_collection_size(document, "images"),
        buffers=_collection_size(document, "buffers"),
        external_dependencies=dependencies,
        missing_dependencies=missing,
    )


def gltf_source_metadata21(path: Path) -> dict[str, object]:
    """Build source metadata plus cheap glTF structural counts on a pipeline worker."""

    metadata = source_metadata21(path)
    inspection = inspect_gltf21(path)
    metadata.update(
        {
            "scenes": inspection.scenes,
            "nodes": inspection.nodes,
            "meshes": inspection.meshes,
            "materials": inspection.materials,
            "animations": inspection.animations,
            "images": inspection.images,
            "buffers": inspection.buffers,
            "external_dependencies": len(inspection.external_dependencies),
            "missing_dependencies": len(inspection.missing_dependencies),
        }
    )
    return metadata


class FormatAwareEditorAssetPipeline21(EditorAssetPipeline21):
    """SwirEditor pipeline with safe format-level inspection for production assets."""

    def preview(self, asset: str | Path) -> EditorAssetPreview:
        base = super().preview(asset)
        if base.suffix not in _GLTF_SUFFIXES_21:
            return base
        source = self.manager.require(base.relative_path).expanduser().resolve()
        inspection = inspect_gltf21(source)
        return EditorAssetPreview(
            relative_path=base.relative_path,
            kind=base.kind,
            suffix=base.suffix,
            size_bytes=base.size_bytes,
            summary=inspection.summary,
            text=inspection.as_text(source),
        )

    def validate_asset(self, asset: str | Path) -> tuple[EditorAssetIssue, ...]:
        issues = list(super().validate_asset(asset))
        suffix = Path(str(asset)).suffix.lower()
        if suffix not in _GLTF_SUFFIXES_21 or any(issue.code == "asset_missing" for issue in issues):
            return tuple(issues)
        source = self.manager.resolve(asset).expanduser().resolve()
        try:
            inspection = inspect_gltf21(source)
        except (OSError, ValueError) as exc:
            issues.append(
                EditorAssetIssue(
                    "gltf_invalid",
                    f"Invalid glTF asset: {exc}",
                    EditorAssetIssueSeverity.ERROR,
                    "Fix the glTF/GLB source and reimport it.",
                )
            )
            return tuple(issues)

        known_missing = {issue.message for issue in issues if issue.code == "dependency_missing"}
        for dependency in inspection.missing_dependencies:
            message = f"Dependency is missing: {self._display_path(dependency)}"
            if message in known_missing:
                continue
            issues.append(
                EditorAssetIssue(
                    "dependency_missing",
                    message,
                    EditorAssetIssueSeverity.ERROR,
                    "Restore the referenced glTF buffer/image or update its URI and reimport.",
                )
            )
        return tuple(issues)


def create_format_aware_editor_asset_pipeline21(
    manager: AssetManager,
    *,
    max_workers: int = 2,
) -> FormatAwareEditorAssetPipeline21:
    """Create the default 2.1 editor pipeline with real glTF dependency tracking."""

    if not isinstance(manager, AssetManager):
        raise TypeError("manager must be an AssetManager")
    pipeline = AssetPipeline(manager, max_workers=max_workers)
    pipeline.register_processor(
        "editor-source-metadata",
        suffixes=_EDITOR_GENERIC_SUFFIXES_21,
        loader=source_metadata21,
    )
    pipeline.register_processor(
        "editor-gltf-metadata",
        suffixes=_GLTF_SUFFIXES_21,
        loader=gltf_source_metadata21,
        dependencies=gltf_asset_dependencies,
    )
    return FormatAwareEditorAssetPipeline21(manager, pipeline)
