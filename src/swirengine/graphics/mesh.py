from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from ..math.types import Color, Transform, Vec3
from .material import Material3D


@dataclass(slots=True)
class MeshData:
    """CPU-side triangle mesh with positions, normals and optional texture coordinates."""

    vertices: np.ndarray
    normals: np.ndarray
    uvs: np.ndarray | None = None

    def __post_init__(self) -> None:
        vertices = np.asarray(self.vertices, dtype="f4")
        normals = np.asarray(self.normals, dtype="f4")
        if vertices.ndim != 2 or vertices.shape[1] != 3:
            raise ValueError("vertices must have shape (N, 3)")
        if normals.shape != vertices.shape:
            raise ValueError("normals must have the same shape as vertices")
        if len(vertices) == 0 or len(vertices) % 3 != 0:
            raise ValueError("mesh must contain a non-zero multiple of 3 vertices")

        uvs = None
        if self.uvs is not None:
            uvs = np.asarray(self.uvs, dtype="f4")
            if uvs.ndim != 2 or uvs.shape != (len(vertices), 2):
                raise ValueError("uvs must have shape (N, 2) matching vertices")
            uvs = np.ascontiguousarray(uvs)

        self.vertices = np.ascontiguousarray(vertices)
        self.normals = np.ascontiguousarray(normals)
        self.uvs = uvs

    @property
    def vertex_count(self) -> int:
        return len(self.vertices)

    @property
    def triangle_count(self) -> int:
        return self.vertex_count // 3

    @property
    def has_uvs(self) -> bool:
        return self.uvs is not None

    def interleaved(self, *, include_uvs: bool = False) -> np.ndarray:
        """Return packed vertex data.

        The default remains position+normal (6 floats) for 0.4 compatibility. Renderers
        can request UVs, which appends two floats and substitutes zeros when UVs are absent.
        """
        values: tuple[np.ndarray, ...] = (self.vertices, self.normals)
        if include_uvs:
            uvs = self.uvs
            if uvs is None:
                uvs = np.zeros((self.vertex_count, 2), dtype="f4")
            values = (*values, uvs)
        return np.ascontiguousarray(np.concatenate(values, axis=1), dtype="f4")


@dataclass(slots=True)
class Mesh3D:
    mesh: MeshData
    position: Vec3 = field(default_factory=Vec3)
    rotation: Vec3 = field(default_factory=Vec3)
    scale: Vec3 = field(default_factory=lambda: Vec3(1.0, 1.0, 1.0))
    color: Color = field(default_factory=Color)
    material: Material3D | None = None
    enabled: bool = True
    visible: bool = True
    name: str = ""
    tags: set[str] = field(default_factory=set)
    visibility_dynamic: bool = False

    @property
    def transform(self) -> Transform:
        return Transform(self.position, self.rotation, self.scale)

    def update(self, dt: float) -> None:
        pass


def cube_mesh() -> MeshData:
    p = 0.5
    faces = (
        ((0, 0, 1), ((-p, -p, p), (p, -p, p), (p, p, p), (-p, p, p))),
        ((0, 0, -1), ((p, -p, -p), (-p, -p, -p), (-p, p, -p), (p, p, -p))),
        ((1, 0, 0), ((p, -p, p), (p, -p, -p), (p, p, -p), (p, p, p))),
        ((-1, 0, 0), ((-p, -p, -p), (-p, -p, p), (-p, p, p), (-p, p, -p))),
        ((0, 1, 0), ((-p, p, p), (p, p, p), (p, p, -p), (-p, p, -p))),
        ((0, -1, 0), ((-p, -p, -p), (p, -p, -p), (p, -p, p), (-p, -p, p))),
    )
    vertices: list[tuple[float, float, float]] = []
    normals: list[tuple[float, float, float]] = []
    uvs: list[tuple[float, float]] = []
    quad_uvs = ((0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0))
    indices = (0, 1, 2, 0, 2, 3)
    for normal, positions in faces:
        for index in indices:
            vertices.append(positions[index])
            normals.append(normal)
            uvs.append(quad_uvs[index])
    return MeshData(
        np.asarray(vertices, dtype="f4"),
        np.asarray(normals, dtype="f4"),
        np.asarray(uvs, dtype="f4"),
    )
