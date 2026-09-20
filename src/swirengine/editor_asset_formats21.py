from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .graphics.gltf import _load_document
from .graphics.gltf_dependencies import gltf_asset_dependencies


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
