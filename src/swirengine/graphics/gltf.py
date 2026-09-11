from __future__ import annotations

import base64
import json
import struct
from dataclasses import dataclass
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
_GLB_MAGIC = b"glTF"
_GLB_JSON_CHUNK = 0x4E4F534A
_GLB_BIN_CHUNK = 0x004E4942


@dataclass(frozen=True, slots=True)
class GltfSceneMesh:
    """One mesh instance resolved from a glTF scene graph.

    ``mesh`` is baked into world space so it can be handed directly to ``Mesh3D`` without
    exposing quaternion/node hierarchy concepts in the stable 0.4 instance API yet.
    """

    mesh: MeshData
    node_index: int
    mesh_index: int
    node_name: str = ""


def _decode_data_uri(uri: str) -> bytes:
    header, separator, payload = uri.partition(",")
    if not separator or ";base64" not in header:
        raise ValueError("only base64 data URIs are supported")
    try:
        return base64.b64decode(payload, validate=True)
    except ValueError as exc:
        raise ValueError("invalid base64 buffer data") from exc


def _parse_glb(source: Path) -> tuple[dict[str, Any], bytes | None]:
    payload = source.read_bytes()
    if len(payload) < 12:
        raise ValueError(f"{source}: GLB header is truncated")
    magic, version, declared_length = struct.unpack_from("<4sII", payload, 0)
    if magic != _GLB_MAGIC:
        raise ValueError(f"{source}: invalid GLB magic")
    if version != 2:
        raise ValueError(f"{source}: only GLB version 2 is supported")
    if declared_length != len(payload):
        raise ValueError(f"{source}: GLB length does not match header")

    offset = 12
    document: dict[str, Any] | None = None
    binary_chunk: bytes | None = None
    chunk_index = 0
    while offset < len(payload):
        if offset + 8 > len(payload):
            raise ValueError(f"{source}: GLB chunk header is truncated")
        chunk_length, chunk_type = struct.unpack_from("<II", payload, offset)
        offset += 8
        end = offset + chunk_length
        if end > len(payload):
            raise ValueError(f"{source}: GLB chunk exceeds container length")
        chunk = payload[offset:end]
        offset = end

        if chunk_index == 0 and chunk_type != _GLB_JSON_CHUNK:
            raise ValueError(f"{source}: first GLB chunk must be JSON")
        if chunk_type == _GLB_JSON_CHUNK:
            if document is not None:
                raise ValueError(f"{source}: GLB contains multiple JSON chunks")
            try:
                text = chunk.rstrip(b" \t\r\n\x00").decode("utf-8")
                document = json.loads(text)
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise ValueError(f"{source}: invalid GLB JSON chunk") from exc
        elif chunk_type == _GLB_BIN_CHUNK and binary_chunk is None:
            binary_chunk = bytes(chunk)
        chunk_index += 1

    if document is None:
        raise ValueError(f"{source}: GLB contains no JSON chunk")
    return document, binary_chunk


def _load_document(source: Path) -> tuple[dict[str, Any], bytes | None]:
    suffix = source.suffix.lower()
    if suffix == ".glb":
        document, binary_chunk = _parse_glb(source)
    elif suffix == ".gltf":
        try:
            document = json.loads(source.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ValueError(f"{source}: invalid glTF JSON: {exc.msg}") from exc
        binary_chunk = None
    else:
        raise ValueError("glTF assets must use .gltf or .glb")

    if document.get("asset", {}).get("version") != "2.0":
        raise ValueError(f"{source}: only glTF 2.0 is supported")
    return document, binary_chunk


def _load_buffers(
    document: dict[str, Any], source: Path, binary_chunk: bytes | None
) -> list[bytes]:
    buffers: list[bytes] = []
    for index, spec in enumerate(document.get("buffers", [])):
        uri = spec.get("uri")
        if isinstance(uri, str):
            if uri.startswith("data:"):
                payload = _decode_data_uri(uri)
            else:
                buffer_path = (source.parent / uri).resolve()
                if not buffer_path.is_file():
                    raise FileNotFoundError(f"glTF buffer not found: {buffer_path}")
                payload = buffer_path.read_bytes()
        else:
            if binary_chunk is None or index != 0:
                raise ValueError(f"buffer {index} has no URI or matching GLB BIN chunk")
            payload = binary_chunk

        declared = int(spec.get("byteLength", len(payload)))
        if len(payload) < declared:
            raise ValueError(f"buffer {index} is shorter than declared byteLength {declared}")
        buffers.append(payload)
    return buffers


def _accessor_array(
    document: dict[str, Any], buffers: list[bytes], accessor_index: int
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
        normal = (
            np.asarray((0.0, 1.0, 0.0), dtype="f4")
            if length <= 1e-12
            else normal / length
        )
        normals[index : index + 3] = normal
    return normals


def _normalized_normals(values: np.ndarray) -> np.ndarray:
    normals = np.asarray(values, dtype="f4").copy()
    lengths = np.linalg.norm(normals, axis=1)
    valid = lengths > 1e-12
    normals[valid] /= lengths[valid, None]
    normals[~valid] = (0.0, 1.0, 0.0)
    return normals


def _mesh_from_document(
    document: dict[str, Any], buffers: list[bytes], mesh_index: int
) -> MeshData:
    meshes = document.get("meshes", [])
    if not 0 <= mesh_index < len(meshes):
        raise ValueError(f"mesh_index {mesh_index} is out of range")

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
            raise ValueError(f"mesh {mesh_index} primitive {primitive_index}: POSITION is required")

        positions = np.asarray(
            _accessor_array(document, buffers, int(attributes["POSITION"])), dtype="f4"
        )
        if positions.ndim != 2 or positions.shape[1] != 3:
            raise ValueError(f"mesh {mesh_index} primitive {primitive_index}: POSITION must be VEC3")
        original_count = len(positions)

        indices = None
        if "indices" in primitive:
            indices = np.asarray(
                _accessor_array(document, buffers, int(primitive["indices"]))
            ).reshape(-1)
            if not np.issubdtype(indices.dtype, np.integer):
                raise ValueError(
                    f"mesh {mesh_index} primitive {primitive_index}: indices must be integer"
                )
            if len(indices) % 3 != 0:
                raise ValueError(
                    f"mesh {mesh_index} primitive {primitive_index}: index count must be divisible by 3"
                )
            if len(indices) and int(indices.max()) >= len(positions):
                raise ValueError(f"mesh {mesh_index} primitive {primitive_index}: index is out of range")
            positions = positions[indices]
        elif len(positions) % 3 != 0:
            raise ValueError(
                f"mesh {mesh_index} primitive {primitive_index}: vertex count must be divisible by 3"
            )

        normals = None
        if "NORMAL" in attributes:
            normals = np.asarray(
                _accessor_array(document, buffers, int(attributes["NORMAL"])), dtype="f4"
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
                _accessor_array(document, buffers, int(attributes["TEXCOORD_0"])), dtype="f4"
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
        raise ValueError(f"selected glTF mesh {mesh_index} contains no primitives")

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


def _node_matrix(node: dict[str, Any], node_index: int) -> np.ndarray:
    if "matrix" in node:
        if any(key in node for key in ("translation", "rotation", "scale")):
            raise ValueError(f"node {node_index} cannot define matrix together with TRS")
        values = np.asarray(node["matrix"], dtype="f8")
        if values.shape != (16,):
            raise ValueError(f"node {node_index} matrix must contain 16 values")
        return values.reshape(4, 4).T

    translation = np.asarray(node.get("translation", (0.0, 0.0, 0.0)), dtype="f8")
    rotation = np.asarray(node.get("rotation", (0.0, 0.0, 0.0, 1.0)), dtype="f8")
    scale = np.asarray(node.get("scale", (1.0, 1.0, 1.0)), dtype="f8")
    if translation.shape != (3,) or rotation.shape != (4,) or scale.shape != (3,):
        raise ValueError(f"node {node_index} has malformed TRS values")

    length = float(np.linalg.norm(rotation))
    if length <= 1e-12:
        raise ValueError(f"node {node_index} rotation quaternion has zero length")
    x, y, z, w = rotation / length
    rotation_matrix = np.array(
        [
            [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
            [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
            [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)],
        ],
        dtype="f8",
    )
    result = np.eye(4, dtype="f8")
    result[:3, :3] = rotation_matrix @ np.diag(scale)
    result[:3, 3] = translation
    return result


def _transform_mesh(mesh: MeshData, matrix: np.ndarray) -> MeshData:
    linear = matrix[:3, :3]
    try:
        normal_matrix = np.linalg.inv(linear).T
    except np.linalg.LinAlgError as exc:
        raise ValueError("glTF node transform has a singular scale") from exc

    homogeneous = np.concatenate(
        (mesh.vertices.astype("f8"), np.ones((mesh.vertex_count, 1), dtype="f8")), axis=1
    )
    vertices = (homogeneous @ matrix.T)[:, :3].astype("f4")
    normals = _normalized_normals(mesh.normals.astype("f8") @ normal_matrix.T)
    uvs = None if mesh.uvs is None else mesh.uvs.copy()

    if float(np.linalg.det(linear)) < 0.0:
        order = np.arange(mesh.vertex_count).reshape(-1, 3)[:, [0, 2, 1]].reshape(-1)
        vertices = vertices[order]
        normals = normals[order]
        if uvs is not None:
            uvs = uvs[order]
    return MeshData(vertices, normals, uvs)


def load_gltf(path: str | Path, *, mesh_index: int = 0) -> MeshData:
    """Load one static triangle mesh from a glTF 2.0 ``.gltf`` or ``.glb`` asset."""
    source = Path(path).expanduser().resolve()
    if not source.is_file():
        raise FileNotFoundError(f"glTF file not found: {source}")
    document, binary_chunk = _load_document(source)
    buffers = _load_buffers(document, source, binary_chunk)
    return _mesh_from_document(document, buffers, mesh_index)


def load_gltf_scene(path: str | Path, *, scene_index: int | None = None) -> list[GltfSceneMesh]:
    """Load a glTF scene graph and bake every mesh node into world-space ``MeshData``.

    Hierarchical node transforms support either a 4x4 glTF matrix or translation/rotation/
    scale TRS. Quaternion rotation is handled internally. This deliberately returns baked
    meshes so the existing ``Mesh3D`` transform API remains backward compatible.
    """
    source = Path(path).expanduser().resolve()
    if not source.is_file():
        raise FileNotFoundError(f"glTF file not found: {source}")
    document, binary_chunk = _load_document(source)
    buffers = _load_buffers(document, source, binary_chunk)
    nodes = document.get("nodes", [])
    scenes = document.get("scenes", [])

    if scenes:
        selected = int(document.get("scene", 0)) if scene_index is None else int(scene_index)
        if not 0 <= selected < len(scenes):
            raise ValueError(f"scene_index {selected} is out of range")
        roots = list(scenes[selected].get("nodes", []))
    else:
        if scene_index not in (None, 0):
            raise ValueError("scene_index is out of range because the asset has no scenes")
        children = {
            int(child)
            for node in nodes
            for child in node.get("children", [])
            if isinstance(child, int)
        }
        roots = [index for index in range(len(nodes)) if index not in children]

    results: list[GltfSceneMesh] = []

    def visit(node_index: int, parent: np.ndarray, active: frozenset[int]) -> None:
        if not 0 <= node_index < len(nodes):
            raise ValueError(f"invalid glTF node index {node_index}")
        if node_index in active:
            raise ValueError(f"glTF node hierarchy contains a cycle at node {node_index}")
        node = nodes[node_index]
        world = parent @ _node_matrix(node, node_index)
        mesh_index = node.get("mesh")
        if mesh_index is not None:
            resolved_index = int(mesh_index)
            mesh = _mesh_from_document(document, buffers, resolved_index)
            results.append(
                GltfSceneMesh(
                    _transform_mesh(mesh, world),
                    node_index=node_index,
                    mesh_index=resolved_index,
                    node_name=str(node.get("name", "")),
                )
            )
        next_active = active | {node_index}
        for child in node.get("children", []):
            visit(int(child), world, next_active)

    identity = np.eye(4, dtype="f8")
    for root in roots:
        visit(int(root), identity, frozenset())
    return results
