from __future__ import annotations

from pathlib import Path
from typing import Any

from .gltf import _load_document


def _external_uri_path(source: Path, spec: dict[str, Any]) -> Path | None:
    uri = spec.get("uri")
    if not isinstance(uri, str) or uri.startswith("data:"):
        return None
    return (source.parent / uri).resolve()


def gltf_asset_dependencies(path: str | Path) -> tuple[Path, ...]:
    """Return deterministic external file dependencies for one glTF/GLB asset.

    Embedded GLB binary chunks, data-URI buffers and data-URI images do not produce external
    dependencies. Missing external paths are still returned so Asset Pipeline 2.0 can track their
    appearance and surface creator diagnostics without silently dropping graph edges.
    """
    source = Path(path).expanduser().resolve()
    if not source.is_file():
        raise FileNotFoundError(f"glTF file not found: {source}")
    document, _binary_chunk = _load_document(source)
    dependencies: set[Path] = set()
    for spec in document.get("buffers", ()):
        if isinstance(spec, dict):
            dependency = _external_uri_path(source, spec)
            if dependency is not None:
                dependencies.add(dependency)
    for spec in document.get("images", ()):
        if isinstance(spec, dict):
            dependency = _external_uri_path(source, spec)
            if dependency is not None:
                dependencies.add(dependency)
    dependencies.discard(source)
    return tuple(sorted(dependencies, key=lambda item: item.as_posix().lower()))
