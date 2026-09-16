from __future__ import annotations

from typing import TYPE_CHECKING

from .gltf_asset import GltfPrimitiveAsset, load_gltf_primitives
from .gltf_dependencies import gltf_asset_dependencies

if TYPE_CHECKING:
    from ..asset_pipeline import AssetPipeline


def register_gltf_asset_processor(
    pipeline: AssetPipeline,
    *,
    name: str = "gltf-primitives",
) -> str:
    """Register the built-in dependency-aware glTF primitive importer.

    CPU parsing is performed by the Asset Pipeline worker pool. The returned primitive/material
    objects contain CPU mesh data plus texture paths; renderer/GPU resource creation remains outside
    the background worker, preserving graphics-context ownership.
    """

    def loader(path) -> list[GltfPrimitiveAsset]:
        return load_gltf_primitives(path)

    pipeline.register_processor(
        name,
        suffixes=(".gltf", ".glb"),
        loader=loader,
        dependencies=gltf_asset_dependencies,
    )
    return name
