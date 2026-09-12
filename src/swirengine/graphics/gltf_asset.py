from __future__ import annotations

import hashlib
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from ..math.types import Color
from .gltf import (
    _accessor_array,
    _decode_data_uri,
    _generate_normals,
    _load_buffers,
    _load_document,
    _normalized_normals,
)
from .material import Material3D
from .mesh import MeshData

_IMAGE_EXTENSIONS = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/webp": ".webp",
}


@dataclass(frozen=True, slots=True)
class GltfPrimitiveAsset:
    """One glTF primitive with its material kept intact."""

    mesh: MeshData
    material: Material3D
    primitive_index: int
    material_index: int | None = None
    metallic_factor: float = 1.0
    roughness_factor: float = 1.0


def _source(path: str | Path) -> Path:
    source = Path(path).expanduser().resolve()
    if not source.is_file():
        raise FileNotFoundError(f"glTF file not found: {source}")
    return source


def _cache_embedded_image(payload: bytes, mime_type: str) -> Path:
    suffix = _IMAGE_EXTENSIONS.get(mime_type)
    if suffix is None:
        raise ValueError(f"unsupported glTF image MIME type {mime_type!r}")
    digest = hashlib.sha256(payload).hexdigest()
    cache = Path(tempfile.gettempdir()) / "swirengine" / "gltf-images"
    cache.mkdir(parents=True, exist_ok=True)
    target = cache / f"{digest}{suffix}"
    if not target.exists():
        temporary = target.with_suffix(target.suffix + ".tmp")
        temporary.write_bytes(payload)
        temporary.replace(target)
    return target


def _image_path(
    document: dict[str, Any],
    buffers: list[bytes],
    source: Path,
    image_index: int,
) -> Path:
    images = document.get("images", [])
    views = document.get("bufferViews", [])
    try:
        image = images[image_index]
    except (IndexError, TypeError) as exc:
        raise ValueError(f"invalid glTF image index {image_index}") from exc

    uri = image.get("uri")
    if isinstance(uri, str):
        if uri.startswith("data:"):
            header = uri.partition(",")[0]
            mime_type = header[5:].split(";", 1)[0]
            return _cache_embedded_image(_decode_data_uri(uri), mime_type)
        target = (source.parent / uri).resolve()
        if not target.is_file():
            raise FileNotFoundError(f"glTF image not found: {target}")
        return target

    if "bufferView" not in image:
        raise ValueError(f"glTF image {image_index} has neither URI nor bufferView")
    mime_type = str(image.get("mimeType", ""))
    try:
        view = views[int(image["bufferView"])]
        payload = buffers[int(view["buffer"])]
    except (IndexError, KeyError, TypeError, ValueError) as exc:
        raise ValueError(f"glTF image {image_index} references an invalid bufferView") from exc
    offset = int(view.get("byteOffset", 0))
    length = int(view.get("byteLength", 0))
    if offset < 0 or length <= 0 or offset + length > len(payload):
        raise ValueError(f"glTF image {image_index} exceeds its buffer bounds")
    return _cache_embedded_image(payload[offset : offset + length], mime_type)


def _texture_path(
    document: dict[str, Any],
    buffers: list[bytes],
    source: Path,
    texture_info: dict[str, Any],
    *,
    material_index: int,
    label: str,
) -> Path:
    if int(texture_info.get("texCoord", 0)) != 0:
        raise ValueError(f"glTF material {material_index}: only TEXCOORD_0 is supported")
    if texture_info.get("extensions"):
        raise ValueError(
            f"glTF material {material_index}: texture transform extensions are not supported"
        )
    textures = document.get("textures", [])
    try:
        texture = textures[int(texture_info["index"])]
        image_index = int(texture["source"])
    except (IndexError, KeyError, TypeError, ValueError) as exc:
        raise ValueError(f"glTF material {material_index}: invalid {label}") from exc
    return _image_path(document, buffers, source, image_index)


def _material(
    document: dict[str, Any],
    buffers: list[bytes],
    source: Path,
    material_index: int | None,
) -> tuple[Material3D, float, float]:
    if material_index is None:
        return Material3D(), 1.0, 1.0
    materials = document.get("materials", [])
    try:
        spec = materials[material_index]
    except (IndexError, TypeError) as exc:
        raise ValueError(f"invalid glTF material index {material_index}") from exc

    alpha_mode = str(spec.get("alphaMode", "OPAQUE"))
    if alpha_mode != "OPAQUE":
        raise ValueError(
            f"glTF material {material_index}: alphaMode {alpha_mode!r} is not supported yet"
        )
    emissive = np.asarray(spec.get("emissiveFactor", (0.0, 0.0, 0.0)), dtype="f4")
    if emissive.shape != (3,) or np.any(np.abs(emissive) > 1e-8):
        raise ValueError(f"glTF material {material_index}: emissive materials are not supported yet")

    pbr = spec.get("pbrMetallicRoughness", {})
    factor = np.asarray(pbr.get("baseColorFactor", (1.0, 1.0, 1.0, 1.0)), dtype="f4")
    if factor.shape != (4,):
        raise ValueError(f"glTF material {material_index}: baseColorFactor must have 4 values")
    if np.any(factor < 0.0) or np.any(factor > 1.0):
        raise ValueError(f"glTF material {material_index}: baseColorFactor must be within 0..1")

    texture_path: Path | None = None
    texture_info = pbr.get("baseColorTexture")
    if texture_info is not None:
        texture_path = _texture_path(
            document,
            buffers,
            source,
            texture_info,
            material_index=material_index,
            label="baseColorTexture",
        )

    metallic = float(pbr.get("metallicFactor", 1.0))
    roughness = float(pbr.get("roughnessFactor", 1.0))
    if not 0.0 <= metallic <= 1.0 or not 0.0 <= roughness <= 1.0:
        raise ValueError(f"glTF material {material_index}: metallic/roughness factors must be 0..1")

    metallic_roughness_path: Path | None = None
    metallic_roughness_info = pbr.get("metallicRoughnessTexture")
    if metallic_roughness_info is not None:
        metallic_roughness_path = _texture_path(
            document,
            buffers,
            source,
            metallic_roughness_info,
            material_index=material_index,
            label="metallicRoughnessTexture",
        )

    material = Material3D(
        texture=texture_path,
        tint=Color(*(float(value) for value in factor)),
        metallic=metallic,
        roughness=roughness,
        metallic_roughness_texture=metallic_roughness_path,
    )
    return material, metallic, roughness


def _primitive_mesh(
    document: dict[str, Any],
    buffers: list[bytes],
    mesh_index: int,
    primitive_index: int,
) -> MeshData:
    meshes = document.get("meshes", [])
    if not 0 <= mesh_index < len(meshes):
        raise ValueError(f"mesh_index {mesh_index} is out of range")
    primitives = meshes[mesh_index].get("primitives", [])
    if not 0 <= primitive_index < len(primitives):
        raise ValueError(f"primitive_index {primitive_index} is out of range")
    primitive = primitives[primitive_index]
    if int(primitive.get("mode", 4)) != 4:
        raise ValueError(f"mesh {mesh_index} primitive {primitive_index}: only TRIANGLES is supported")

    attributes = primitive.get("attributes", {})
    if "POSITION" not in attributes:
        raise ValueError(f"mesh {mesh_index} primitive {primitive_index}: POSITION is required")
    positions = np.asarray(
        _accessor_array(document, buffers, int(attributes["POSITION"])), dtype="f4"
    )
    if positions.ndim != 2 or positions.shape[1] != 3:
        raise ValueError(f"mesh {mesh_index} primitive {primitive_index}: POSITION must be VEC3")
    original_count = len(positions)

    indices = None
    if "indices" in primitive:
        indices = np.asarray(_accessor_array(document, buffers, int(primitive["indices"]))).reshape(-1)
        if not np.issubdtype(indices.dtype, np.integer):
            raise ValueError(f"mesh {mesh_index} primitive {primitive_index}: indices must be integer")
        if len(indices) % 3 != 0:
            raise ValueError(f"mesh {mesh_index} primitive {primitive_index}: bad index count")
        if len(indices) and (int(indices.min()) < 0 or int(indices.max()) >= original_count):
            raise ValueError(f"mesh {mesh_index} primitive {primitive_index}: index is out of range")
        positions = positions[indices]
    elif len(positions) % 3 != 0:
        raise ValueError(f"mesh {mesh_index} primitive {primitive_index}: bad vertex count")

    normals = None
    if "NORMAL" in attributes:
        normals = np.asarray(_accessor_array(document, buffers, int(attributes["NORMAL"])), dtype="f4")
        if normals.shape != (original_count, 3):
            raise ValueError(f"mesh {mesh_index} primitive {primitive_index}: NORMAL must match POSITION")
        if indices is not None:
            normals = normals[indices]
        normals = _normalized_normals(normals)
    if normals is None:
        normals = _generate_normals(positions)

    uvs = None
    if "TEXCOORD_0" in attributes:
        uvs = np.asarray(_accessor_array(document, buffers, int(attributes["TEXCOORD_0"])), dtype="f4")
        if uvs.shape != (original_count, 2):
            raise ValueError(f"mesh {mesh_index} primitive {primitive_index}: TEXCOORD_0 must be VEC2")
        if indices is not None:
            uvs = uvs[indices]

    return MeshData(positions, normals, uvs)


def load_gltf_material(path: str | Path, material_index: int = 0) -> Material3D:
    """Load one glTF PBR material, including embedded GLB/data-URI images."""
    source = _source(path)
    document, binary_chunk = _load_document(source)
    buffers = _load_buffers(document, source, binary_chunk)
    material, _, _ = _material(document, buffers, source, int(material_index))
    return material


def load_gltf_primitives(path: str | Path, *, mesh_index: int = 0) -> list[GltfPrimitiveAsset]:
    """Load one glTF mesh without merging primitives, preserving per-primitive materials."""
    source = _source(path)
    document, binary_chunk = _load_document(source)
    buffers = _load_buffers(document, source, binary_chunk)
    meshes = document.get("meshes", [])
    if not 0 <= mesh_index < len(meshes):
        raise ValueError(f"mesh_index {mesh_index} is out of range")

    results: list[GltfPrimitiveAsset] = []
    for primitive_index, primitive in enumerate(meshes[mesh_index].get("primitives", [])):
        raw_index = primitive.get("material")
        material_index = None if raw_index is None else int(raw_index)
        material, metallic, roughness = _material(document, buffers, source, material_index)
        results.append(
            GltfPrimitiveAsset(
                mesh=_primitive_mesh(document, buffers, mesh_index, primitive_index),
                material=material,
                primitive_index=primitive_index,
                material_index=material_index,
                metallic_factor=metallic,
                roughness_factor=roughness,
            )
        )
    if not results:
        raise ValueError(f"selected glTF mesh {mesh_index} contains no primitives")
    return results
