from __future__ import annotations

from pathlib import Path

import numpy as np

from .mesh import MeshData


def _resolve_index(raw: str, length: int) -> int:
    index = int(raw)
    if index == 0:
        raise ValueError("OBJ indices are 1-based and cannot be zero")
    resolved = index - 1 if index > 0 else length + index
    if not 0 <= resolved < length:
        raise ValueError(f"OBJ index {index} is out of range")
    return resolved


def load_obj(path: str | Path) -> MeshData:
    """Load triangle geometry from a Wavefront OBJ file.

    Supports positions, normals, positive/negative indices and polygon fan triangulation.
    Texture coordinates/materials are intentionally ignored until the material milestone.
    """

    source = Path(path).expanduser().resolve()
    if not source.is_file():
        raise FileNotFoundError(f"OBJ file not found: {source}")

    positions: list[tuple[float, float, float]] = []
    normals: list[tuple[float, float, float]] = []
    out_positions: list[tuple[float, float, float]] = []
    out_normals: list[tuple[float, float, float] | None] = []

    for line_number, raw_line in enumerate(source.read_text(encoding="utf-8").splitlines(), 1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        kind = parts[0]
        try:
            if kind == "v" and len(parts) >= 4:
                positions.append(tuple(map(float, parts[1:4])))
            elif kind == "vn" and len(parts) >= 4:
                normals.append(tuple(map(float, parts[1:4])))
            elif kind == "f":
                if len(parts) < 4:
                    raise ValueError("face needs at least 3 vertices")
                refs = parts[1:]
                for i in range(1, len(refs) - 1):
                    for ref in (refs[0], refs[i], refs[i + 1]):
                        fields = ref.split("/")
                        vertex_index = _resolve_index(fields[0], len(positions))
                        out_positions.append(positions[vertex_index])
                        normal = None
                        if len(fields) >= 3 and fields[2]:
                            normal_index = _resolve_index(fields[2], len(normals))
                            normal = normals[normal_index]
                        out_normals.append(normal)
        except (ValueError, IndexError) as exc:
            raise ValueError(f"{source}:{line_number}: invalid OBJ data: {exc}") from exc

    if not out_positions:
        raise ValueError(f"{source}: OBJ contains no faces")

    vertices = np.asarray(out_positions, dtype="f4")
    generated = np.zeros_like(vertices)
    for i in range(0, len(vertices), 3):
        edge_a = vertices[i + 1] - vertices[i]
        edge_b = vertices[i + 2] - vertices[i]
        normal = np.cross(edge_a, edge_b)
        length = float(np.linalg.norm(normal))
        if length == 0.0:
            normal = np.asarray((0.0, 1.0, 0.0), dtype="f4")
        else:
            normal /= length
        generated[i:i + 3] = normal

    resolved_normals = np.asarray(
        [generated[i] if value is None else value for i, value in enumerate(out_normals)],
        dtype="f4",
    )
    lengths = np.linalg.norm(resolved_normals, axis=1)
    nonzero = lengths > 0
    resolved_normals[nonzero] /= lengths[nonzero, None]
    resolved_normals[~nonzero] = (0.0, 1.0, 0.0)
    return MeshData(vertices, resolved_normals)
