from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO

import numpy as np
from PIL import Image, ImageOps

from .asset_pipeline import AssetPipeline
from .graphics.mesh import MeshData


@dataclass(frozen=True, slots=True)
class MeshOptimizationResult:
    """Result of deterministic CPU-side triangle cleanup."""

    mesh: MeshData
    input_triangles: int
    output_triangles: int
    removed_degenerate: int

    @property
    def changed(self) -> bool:
        return self.removed_degenerate > 0


@dataclass(frozen=True, slots=True)
class TextureOptimizationResult:
    """Optimized texture payload plus creator-facing diagnostics."""

    data: bytes
    input_size: tuple[int, int]
    output_size: tuple[int, int]
    input_bytes: int
    output_bytes: int
    output_format: str

    @property
    def changed_dimensions(self) -> bool:
        return self.input_size != self.output_size

    @property
    def saved_bytes(self) -> int:
        return self.input_bytes - self.output_bytes


def optimize_mesh_data(mesh: MeshData, *, area_epsilon: float = 1e-10) -> MeshOptimizationResult:
    """Remove degenerate triangles while preserving expanded vertex attributes.

    SwirEngine's stable ``MeshData`` representation is an expanded triangle list. This optimizer
    therefore avoids index-topology changes and only removes triangles whose geometric area is at or
    below ``area_epsilon``. Vertex order, normals and UVs of surviving triangles remain unchanged.
    """
    epsilon = float(area_epsilon)
    if epsilon < 0.0:
        raise ValueError("area_epsilon must be >= 0")

    triangles = mesh.vertices.reshape((-1, 3, 3))
    edges_a = triangles[:, 1] - triangles[:, 0]
    edges_b = triangles[:, 2] - triangles[:, 0]
    doubled_areas = np.linalg.norm(np.cross(edges_a, edges_b), axis=1)
    keep = doubled_areas > (epsilon * 2.0)
    input_triangles = mesh.triangle_count
    output_triangles = int(np.count_nonzero(keep))
    removed = input_triangles - output_triangles

    if output_triangles == 0:
        raise ValueError("mesh contains no non-degenerate triangles")
    if removed == 0:
        return MeshOptimizationResult(mesh, input_triangles, input_triangles, 0)

    vertex_mask = np.repeat(keep, 3)
    optimized = MeshData(
        mesh.vertices[vertex_mask],
        mesh.normals[vertex_mask],
        None if mesh.uvs is None else mesh.uvs[vertex_mask],
    )
    return MeshOptimizationResult(
        mesh=optimized,
        input_triangles=input_triangles,
        output_triangles=output_triangles,
        removed_degenerate=removed,
    )


def optimize_texture_bytes(
    data: bytes | bytearray | memoryview,
    *,
    max_dimension: int = 2048,
    output_format: str = "PNG",
    quality: int = 90,
) -> TextureOptimizationResult:
    """Resize and re-encode an image without changing aspect ratio.

    The operation is opt-in. It never enlarges a texture and does not silently change the source
    asset on disk. Returned bytes can be stored in ``DerivedAssetCache`` or consumed by a creator
    tool/export pipeline.
    """
    payload = bytes(data)
    dimension = int(max_dimension)
    if dimension <= 0:
        raise ValueError("max_dimension must be greater than zero")
    quality_value = int(quality)
    if not 1 <= quality_value <= 100:
        raise ValueError("quality must be within 1..100")
    format_name = str(output_format).strip().upper()
    if format_name == "JPG":
        format_name = "JPEG"
    if format_name not in {"PNG", "JPEG", "WEBP"}:
        raise ValueError("output_format must be PNG, JPEG or WEBP")

    with Image.open(BytesIO(payload)) as opened:
        image = ImageOps.exif_transpose(opened)
        image.load()
        input_size = tuple(int(value) for value in image.size)
        output = image.copy()

    if max(output.size) > dimension:
        output.thumbnail((dimension, dimension), Image.Resampling.LANCZOS)

    if format_name == "JPEG" and output.mode not in {"L", "RGB"}:
        background = Image.new("RGB", output.size, (0, 0, 0))
        if "A" in output.getbands():
            background.paste(output, mask=output.getchannel("A"))
        else:
            background.paste(output.convert("RGB"))
        output = background

    encoded = BytesIO()
    save_options: dict[str, object] = {"optimize": True}
    if format_name == "JPEG":
        save_options.update(quality=quality_value, progressive=True)
    elif format_name == "WEBP":
        save_options.update(quality=quality_value, method=6)
    output.save(encoded, format=format_name, **save_options)
    optimized = encoded.getvalue()

    return TextureOptimizationResult(
        data=optimized,
        input_size=input_size,
        output_size=tuple(int(value) for value in output.size),
        input_bytes=len(payload),
        output_bytes=len(optimized),
        output_format=format_name,
    )


def register_texture_optimizer(
    pipeline: AssetPipeline,
    *,
    name: str = "texture-optimizer",
    max_dimension: int = 2048,
    output_format: str = "PNG",
    quality: int = 90,
) -> str:
    """Register an opt-in background image optimization processor."""

    def loader(path):
        return optimize_texture_bytes(
            path.read_bytes(),
            max_dimension=max_dimension,
            output_format=output_format,
            quality=quality,
        )

    pipeline.register_processor(
        name,
        suffixes=(".png", ".jpg", ".jpeg", ".webp"),
        loader=loader,
    )
    return name
