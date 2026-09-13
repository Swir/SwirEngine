from __future__ import annotations

from dataclasses import dataclass
from collections.abc import Iterable

import numpy as np

from ..math.types import Color
from .mesh import Mesh3D, MeshData, cube_mesh
from .primitives import Cube3D


@dataclass(frozen=True, slots=True)
class StaticBatchMetrics:
    source_objects: int
    output_batches: int
    draw_calls_before: int
    draw_calls_after: int

    @property
    def draw_call_reduction(self) -> float:
        if self.draw_calls_before <= 0:
            return 0.0
        return 1.0 - (self.draw_calls_after / self.draw_calls_before)


@dataclass(frozen=True, slots=True)
class StaticCubeBatchResult:
    meshes: tuple[Mesh3D, ...]
    metrics: StaticBatchMetrics


def _color_key(color: Color) -> tuple[float, float, float, float]:
    value = color.clamped()
    return (value.r, value.g, value.b, value.a)


def _bake_cube_group(cubes: list[Cube3D], color: Color) -> Mesh3D:
    source = cube_mesh()
    count = len(cubes)
    vertices = np.empty((source.vertex_count * count, 3), dtype="f4")
    normals = np.empty_like(vertices)
    uvs = np.empty((source.vertex_count * count, 2), dtype="f4")

    start = 0
    ones = np.ones((source.vertex_count, 1), dtype="f4")
    homogeneous = np.concatenate((source.vertices, ones), axis=1)
    for cube in cubes:
        model = np.asarray(cube.transform.matrix(), dtype="f4")
        end = start + source.vertex_count
        vertices[start:end] = (model @ homogeneous.T).T[:, :3]

        normal_matrix = np.linalg.inv(model[:3, :3]).T
        transformed_normals = (normal_matrix @ source.normals.T).T
        lengths = np.linalg.norm(transformed_normals, axis=1, keepdims=True)
        normals[start:end] = transformed_normals / np.maximum(lengths, 1e-8)
        uvs[start:end] = source.uvs
        start = end

    return Mesh3D(
        MeshData(vertices, normals, uvs),
        color=color.clamped(),
        name=f"static-cube-batch-{count}",
        tags={"static-batch", "cube-batch"},
    )


def build_static_cube_batches(cubes: Iterable[Cube3D]) -> StaticCubeBatchResult:
    """Bake visible static cubes into one renderer draw per shared color.

    This is intended for scenery that does not move every frame: walls, floor blocks,
    buildings, props and level geometry. Transforms are baked into a combined MeshData,
    so callers should rebuild the batch when any source cube moves, rotates, changes size
    or changes color.
    """
    groups: dict[tuple[float, float, float, float], list[Cube3D]] = {}
    colors: dict[tuple[float, float, float, float], Color] = {}
    source_objects = 0
    for cube in cubes:
        if not cube.enabled or not cube.visible:
            continue
        source_objects += 1
        key = _color_key(cube.color)
        groups.setdefault(key, []).append(cube)
        colors.setdefault(key, cube.color)

    meshes = tuple(_bake_cube_group(group, colors[key]) for key, group in groups.items())
    metrics = StaticBatchMetrics(
        source_objects=source_objects,
        output_batches=len(meshes),
        draw_calls_before=source_objects,
        draw_calls_after=len(meshes),
    )
    return StaticCubeBatchResult(meshes=meshes, metrics=metrics)
