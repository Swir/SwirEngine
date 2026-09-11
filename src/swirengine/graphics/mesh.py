from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from ..math.types import Color, Transform, Vec3


@dataclass(slots=True)
class MeshData:
    """CPU-side triangle mesh with tightly packed position/normal data."""

    vertices: np.ndarray
    normals: np.ndarray

    def __post_init__(self) -> None:
        vertices = np.asarray(self.vertices, dtype="f4")
        normals = np.asarray(self.normals, dtype="f4")
        if vertices.ndim != 2 or vertices.shape[1] != 3:
            raise ValueError("vertices must have shape (N, 3)")
        if normals.shape != vertices.shape:
            raise ValueError("normals must have the same shape as vertices")
        if len(vertices) == 0 or len(vertices) % 3 != 0:
            raise ValueError("mesh must contain a non-zero multiple of 3 vertices")
        self.vertices = np.ascontiguousarray(vertices)
        self.normals = np.ascontiguousarray(normals)

    @property
    def vertex_count(self) -> int:
        return len(self.vertices)

    @property
    def triangle_count(self) -> int:
        return self.vertex_count // 3

    def interleaved(self) -> np.ndarray:
        values = np.concatenate((self.vertices, self.normals), axis=1)
        return np.ascontiguousarray(values, dtype="f4")


@dataclass(slots=True)
class Mesh3D:
    mesh: MeshData
    position: Vec3 = field(default_factory=Vec3)
    rotation: Vec3 = field(default_factory=Vec3)
    scale: Vec3 = field(default_factory=lambda: Vec3(1.0, 1.0, 1.0))
    color: Color = field(default_factory=Color)
    enabled: bool = True
    visible: bool = True
    name: str = ""
    tags: set[str] = field(default_factory=set)

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
    for normal, (a, b, c, d) in faces:
        for position in (a, b, c, a, c, d):
            vertices.append(position)
            normals.append(normal)
    return MeshData(np.asarray(vertices, dtype="f4"), np.asarray(normals, dtype="f4"))
