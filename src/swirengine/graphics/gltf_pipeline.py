from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING

from ..asset_optimization import optimize_mesh_data
from .gltf_asset import GltfPrimitiveAsset, load_gltf_primitives
from .gltf_dependencies import gltf_asset_dependencies

if TYPE_CHECKING:
    from ..asset_pipeline import AssetPipeline


def register_gltf_asset_processor(
    pipeline: AssetPipeline,
    *,
    name: str = "gltf-primitives",
    optimize_meshes: bool = False,
    mesh_area_epsilon: float = 1e-10,
) -> str:
    """Register the built-in dependency-aware glTF primitive importer.

    CPU parsing is performed by the Asset Pipeline worker pool. The returned primitive/material
    objects contain CPU mesh data plus texture paths; renderer/GPU resource creation remains outside
    the background worker, preserving graphics-context ownership.

    ``optimize_meshes`` is intentionally opt-in for 1.x compatibility. When enabled, degenerate
    triangles are removed from each expanded ``MeshData`` primitive without changing the order or
    attributes of surviving vertices.
    """

    def loader(path) -> list[GltfPrimitiveAsset]:
        primitives = load_gltf_primitives(path)
        if not optimize_meshes:
            return primitives
        return [
            replace(
                primitive,
                mesh=optimize_mesh_data(
                    primitive.mesh,
                    area_epsilon=mesh_area_epsilon,
                ).mesh,
            )
            for primitive in primitives
        ]

    pipeline.register_processor(
        name,
        suffixes=(".gltf", ".glb"),
        loader=loader,
        dependencies=gltf_asset_dependencies,
    )
    return name
