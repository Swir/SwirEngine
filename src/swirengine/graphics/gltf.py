from __future__ import annotations

import base64
import json
from pathlib import Path
from typing import Any

import numpy as np

from .mesh import MeshData

_COMPONENT_DTYPES = {
    5120: np.dtype("i1"),
    5121: np.dtype("u1"),
    5122: np.dtype("<i2"),
    5123: np.dtype("<u2"),
    5125: np.dtype("<u4"),
    5126: np.dtype("<f4"),
}
_TYPE_COMPONENTS = {
    "SCALAR": 1,
    "VEC2": 2,
    "VEC3": 3,
    "VEC4": 4,
    "MAT2": 4,
    "MAT3": 9,
    "MAT4": 16,
}


def _decode_data_uri(uri: str) -> bytes:
    header, separator, payload = uri.partition(",")
    if not separator or ";base64" not in header:
        raise ValueError("only base64 data URIs are supported")
    try:
        return base64.b64decode(payload, validate=True)
    except ValueError as exc:
        raise ValueError("invalid base64 buffer data") from exc


def _load_buffers(document: dict[str, Any], source: Path) -> list[bytes]:
    buffers: list[bytes] = []
    for index, spec in enumerate(document.get("buffers", [])):
        uri = spec.get("uri")
        if not isinstance(uri, str):
            raise TypeError(
                f"buffer {index} has no URI; GLB binary chunks are not supported by load_gltf()"
            )
        if uri.startswith("data:"):
            payload = _decode_data_uri(uri)
        else:
            buffer_path = (source.parent / uri).resolve()
            if not buffer_path.is_file():
                raise FileNotFoundError(f"glTF buffer not found: {buffer_path}")
            payload = buffer_path.read_bytes()
        declared = int(spec.get("byteLength", len(payload)))
        if len(payload) < declared:
            raise ValueError(
                f"buffer {index} is shorter than declared byteLength {declared}"
            )
        buffers.append(payload)
    return buffers


def _accessor_array(
    document: dict[str, Any],
    buffers: list[bytes],
    accessor_index: int,
) -> np.ndarray:
    accessors = document.get("accessors", [])
    views = document.get("bufferViews", [])
    try:
        accessor = accessors[accessor_index]
    except (IndexError, TypeError) as exc:
        raise ValueError(f"invalid accessor index {accessor_index}") from exc
    if accessor.get("sparse") is not None:
        raise ValueError("sparse glTF accessors are not supported yet")
    if "bufferView" not in accessor:
        raise ValueError(f"accessor {accessor_index} has no bufferView")

    try:
        view = views[int(accessor["bufferView"])]
        payload = buffers[int(view["buffer"])]
    except (IndexError, KeyError, TypeError, ValueError) as exc:
        raise ValueError(f"accessor {accessor_index} references an invalid buffer view") from exc

    component_type = int(accessor.get("componentType", 0))
    dtype = _COMPONENT_DTYPES.get(component_type)
    if dtype is None:
        raise ValueError(f"unsupported glTF componentType {component_type}")
    type_name = str(accessor.get("type", ""))
    components = _TYPE_COMPONENTS.get(type_name)
    if components is None:
        raise ValueError(f"unsupported glTF accessor type {type_name!r}")

    count = int(accessor.get("count", 0))
    if count < 0:
        raise ValueError(f"accessor {accessor_index} has a negative count")
    offset = int(view.get("byteOffset", 0)) + int(accessor.get("byteOffset", 0))
    element_size = dtype.itemsize * components
    stride = int(view.get("byteStride", element_size))
    if stride < element_size:
        raise ValueError(f"accessor {accessor_index} has an invalid byteStride")

    if count == 0:
        shape = (0,) if components == 1 else (0, components)
        return np.empty(shape, dtype=dtype)

    end = offset + (count - 1) * stride + element_size
    if offset < 0 or end > len(payload):
        raise ValueError(f"accessor {accessor_index} exceeds its buffer bounds")

    if stride == element_size:
        array = np.frombuffer(payload, dtype=dtype, count=count * components, offset=offset)
        if components > 1:
            array = array.reshape(count, components)
        return np.array(array, copy=True)

    array = np.ndarray(
        shape=(count, components),
        dtype=dtype,
        buffer=payload,
        offset=offset,
        strides=(stride, dtype.itemsize),
    )
    copied = np.array(array, copy=True)
    return copied[:, 0] if components == 1 else copied


def _generate_normals(vertices: np.ndarray) -> np.ndarray:
    normals = np.zeros_like(vertices, dtype="f4")
    for index in range(0, len(vertices), 3):
        edge_a = vertices[index + 1] - vertices[index]
        edge_b = vertices[index + 2] - vertices[index]
        normal = np.cross(edge_a, edge_b)
        length = float(np.linalg.norm(normal))
        if length <= 1e-12:
            normal = np.asarray((0.0, 1.0, 0.0), dtype="f4")
        else:
            normal = normal / length
        normals[index:index + 3] = normal
    return normals


def _normalized_normals(values: np.ndarray) -> np.ndarray:
    normals = np.asarray(values, dtype="f4").copy()
    lengths = np.linalg.norm(normals, axis=1)
    valid = lengths > 1e-12
    normals[valid] /= lengths[valid, None]
    normals[~valid] = (0.0, 1.0, 0.0)
    return normals


def load_gltf(path: str | Path, *, mesh_index: int = 0) -> MeshData:
    """Load one static triangle mesh from a JSON ``.gltf`` asset.

    The loader intentionally focuses on the runtime-friendly static subset first: JSON glTF
    2.0, external or base64 buffers, indexed/non-indexed triangle primitives, POSITION,
    NORMAL and TEXCOORD_0. All primitives in the selected mesh are combined into one
    ``MeshData``. Missing normals are generated per triangle. Node transforms, skins,
    morph targets, animation, materials and GLB containers remain future 0.4 work.
    """

    source = Path(path).expanduser().resolve()
    if not source.is_file():
        raise FileNotFoundError(f"glTF file not found: {source}")
    if source.suffix.lower() != ".gltf":
        raise ValueError("load_gltf() currently supports JSON .gltf files; GLB is not supported yet")

    try:
        document = json.loads(source.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"{source}: invalid glTF JSON: {exc.msg}") from exc
    if document.get("asset", {}).get("version") != "2.0":
        raise ValueError(f"{source}: only glTF 2.0 is supported")

    meshes = document.get("meshes", [])
    if not 0 <= mesh_index < len(meshes):
        raise ValueError(f"mesh_index {mesh_index} is out of range")
    buffers = _load_buffers(document, source)

    positions_parts: list[np.ndarray] = []
    normals_parts: list[np.ndarray | None] = []
    uv_parts: list[np.ndarray | None] = []
    any_uvs = False

    for primitive_index, primitive in enumerate(meshes[mesh_index].get("primitives", [])):
        mode = int(primitive.get("mode", 4))
        if mode != 4:
            raise ValueError(
                f"mesh {mesh_index} primitive {primitive_index}: only TRIANGLES mode is supported"
            )
        attributes = primitive.get("attributes", {})
        if "POSITION" not in attributes:
            raise ValueError(
                f"mesh {mesh_index} primitive {primitive_index}: POSITION is required"
            )

        position_source = _accessor_array(document, buffers, int(attributes["POSITION"]))
        positions = np.asarray(position_source, dtype="f4")
        if positions.ndim != 2 or positions.shape[1] != 3:
            raise ValueError(
                f"mesh {mesh_index} primitive {primitive_index}: POSITION must be VEC3"
            )
        original_count = len(positions)

        indices = None
        if "indices" in primitive:
            indices = np.asarray(
                _accessor_array(document, buffers, int(primitive["indices"])),
            ).reshape(-1)
            if not np.issubdtype(indices.dtype, np.integer):
                raise ValueError(
                    f"mesh {mesh_index} primitive {primitive_index}: indices must be integer"
                )
            if len(indices) % 3 != 0:
                raise ValueError(
                    f"mesh {mesh_index} primitive {primitive_index}: index count must be divisible by 3"
                )
            if len(indices) and (int(indices.min()) < 0 or int(indices.max()) >= len(positions)):
                raise ValueError(
                    f"mesh {mesh_index} primitive {primitive_index}: index is out of range"
                )
            positions = positions[indices]
        elif len(positions) % 3 != 0:
            raise ValueError(
                f"mesh {mesh_index} primitive {primitive_index}: vertex count must be divisible by 3"
            )

        normals = None
        if "NORMAL" in attributes:
            normals = np.asarray(
                _accessor_array(document, buffers, int(attributes["NORMAL"])),
                dtype="f4",
            )
            if normals.shape != (original_count, 3):
                raise ValueError(
                    f"mesh {mesh_index} primitive {primitive_index}: NORMAL must match POSITION"
                )
            if indices is not None:
                normals = normals[indices]
            normals = _normalized_normals(normals)

        uvs = None
        if "TEXCOORD_0" in attributes:
            uvs = np.asarray(
                _accessor_array(document, buffers, int(attributes["TEXCOORD_0"])),
                dtype="f4",
            )
            if uvs.shape != (original_count, 2):
                raise ValueError(
                    f"mesh {mesh_index} primitive {primitive_index}: TEXCOORD_0 must be VEC2"
                )
            if indices is not None:
                uvs = uvs[indices]
            any_uvs = True

        positions_parts.append(np.ascontiguousarray(positions, dtype="f4"))
        normals_parts.append(normals)
        uv_parts.append(uvs)

    if not positions_parts:
        raise ValueError(f"{source}: selected glTF mesh contains no primitives")

    resolved_normals = [
        _generate_normals(vertices) if normals is None else normals
        for vertices, normals in zip(positions_parts, normals_parts, strict=True)
    ]
    vertices = np.concatenate(positions_parts, axis=0)
    normals = np.concatenate(resolved_normals, axis=0)

    uvs = None
    if any_uvs:
        uvs = np.concatenate(
            [
                np.zeros((len(vertices_part), 2), dtype="f4") if part is None else part
                for vertices_part, part in zip(positions_parts, uv_parts, strict=True)
            ],
            axis=0,
        )

    return MeshData(vertices, normals, uvs)
