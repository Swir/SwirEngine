from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from .gltf import (
    _accessor_array,
    _generate_normals,
    _load_buffers,
    _load_document,
    _node_matrix,
    _normalized_normals,
)
from .gltf_asset import _material
from .mesh import MeshData
from .skeletal import (
    MAX_SKIN_JOINTS,
    SkeletalAnimationChannel,
    SkeletalAnimationClip3D,
    Skeleton3D,
    SkeletonNode3D,
    Skin3D,
    SkinnedMesh3D,
    SkinnedMeshData,
)


@dataclass(frozen=True, slots=True)
class GltfSkeletalAsset:
    """Loaded glTF skinned scene objects plus shared skeletal animation clips."""

    objects: tuple[SkinnedMesh3D, ...]
    clips: tuple[SkeletalAnimationClip3D, ...]

    @property
    def clip_names(self) -> tuple[str, ...]:
        return tuple(clip.name for clip in self.clips)


def _source(path: str | Path) -> Path:
    source = Path(path).expanduser().resolve()
    if not source.is_file():
        raise FileNotFoundError(f"glTF file not found: {source}")
    return source


def _rotation_from_matrix(matrix: np.ndarray) -> tuple[float, float, float, float]:
    trace = float(np.trace(matrix))
    if trace > 0.0:
        root = np.sqrt(trace + 1.0) * 2.0
        w = 0.25 * root
        x = (matrix[2, 1] - matrix[1, 2]) / root
        y = (matrix[0, 2] - matrix[2, 0]) / root
        z = (matrix[1, 0] - matrix[0, 1]) / root
    else:
        index = int(np.argmax(np.diag(matrix)))
        if index == 0:
            root = np.sqrt(1.0 + matrix[0, 0] - matrix[1, 1] - matrix[2, 2]) * 2.0
            w = (matrix[2, 1] - matrix[1, 2]) / root
            x = 0.25 * root
            y = (matrix[0, 1] + matrix[1, 0]) / root
            z = (matrix[0, 2] + matrix[2, 0]) / root
        elif index == 1:
            root = np.sqrt(1.0 + matrix[1, 1] - matrix[0, 0] - matrix[2, 2]) * 2.0
            w = (matrix[0, 2] - matrix[2, 0]) / root
            x = (matrix[0, 1] + matrix[1, 0]) / root
            y = 0.25 * root
            z = (matrix[1, 2] + matrix[2, 1]) / root
        else:
            root = np.sqrt(1.0 + matrix[2, 2] - matrix[0, 0] - matrix[1, 1]) * 2.0
            w = (matrix[1, 0] - matrix[0, 1]) / root
            x = (matrix[0, 2] + matrix[2, 0]) / root
            y = (matrix[1, 2] + matrix[2, 1]) / root
            z = 0.25 * root
    value = np.asarray((x, y, z, w), dtype="f4")
    length = float(np.linalg.norm(value))
    if length <= 1e-8:
        raise ValueError("node matrix contains an invalid rotation")
    value /= length
    return tuple(float(item) for item in value)


def _decompose_node_matrix(
    matrix: np.ndarray, node_index: int
) -> tuple[tuple[float, ...], tuple[float, ...], tuple[float, ...]]:
    matrix = np.asarray(matrix, dtype="f8")
    translation = matrix[:3, 3]
    linear = matrix[:3, :3]
    scales = np.linalg.norm(linear, axis=0)
    if np.any(scales <= 1e-10):
        raise ValueError(f"node {node_index} matrix has a zero scale axis")
    rotation = linear / scales
    determinant = float(np.linalg.det(rotation))
    if determinant < 0.0:
        axis = int(np.argmax(scales))
        scales[axis] *= -1.0
        rotation[:, axis] *= -1.0
    if not np.allclose(rotation.T @ rotation, np.eye(3), atol=2e-4):
        raise ValueError(
            f"node {node_index} matrix contains shear unsupported by skeletal animation"
        )
    return (
        tuple(float(item) for item in translation),
        _rotation_from_matrix(rotation),
        tuple(float(item) for item in scales),
    )


def _parents(document: dict[str, Any]) -> list[int | None]:
    nodes = document.get("nodes", [])
    parents: list[int | None] = [None] * len(nodes)
    for parent_index, node in enumerate(nodes):
        for raw_child in node.get("children", []):
            child = int(raw_child)
            if not 0 <= child < len(nodes):
                raise ValueError(f"node {parent_index} references invalid child {child}")
            if parents[child] is not None:
                raise ValueError(f"node {child} has multiple parents")
            parents[child] = parent_index
    return parents


def _skeleton(document: dict[str, Any]) -> Skeleton3D:
    raw_nodes = document.get("nodes", [])
    if not raw_nodes:
        raise ValueError("skeletal glTF contains no nodes")
    parents = _parents(document)
    nodes: list[SkeletonNode3D] = []
    for index, node in enumerate(raw_nodes):
        if "matrix" in node:
            translation, rotation, scale = _decompose_node_matrix(_node_matrix(node, index), index)
        else:
            translation = tuple(float(item) for item in node.get("translation", (0.0, 0.0, 0.0)))
            rotation = tuple(float(item) for item in node.get("rotation", (0.0, 0.0, 0.0, 1.0)))
            scale = tuple(float(item) for item in node.get("scale", (1.0, 1.0, 1.0)))
        nodes.append(
            SkeletonNode3D(
                index=index,
                parent=parents[index],
                name=str(node.get("name", "")),
                translation=translation,  # type: ignore[arg-type]
                rotation=rotation,  # type: ignore[arg-type]
                scale=scale,  # type: ignore[arg-type]
            )
        )
    return Skeleton3D(tuple(nodes))


def _normalized_weights(
    document: dict[str, Any], buffers: list[bytes], accessor_index: int
) -> np.ndarray:
    values = _accessor_array(document, buffers, accessor_index)
    accessor = document.get("accessors", [])[accessor_index]
    component_type = int(accessor.get("componentType", 0))
    if component_type == 5126:
        return np.asarray(values, dtype="f4")
    if not bool(accessor.get("normalized", False)) or component_type not in {5121, 5123}:
        raise ValueError("WEIGHTS_0 must use FLOAT or normalized unsigned byte/short components")
    denominator = 255.0 if component_type == 5121 else 65535.0
    return np.asarray(values, dtype="f4") / denominator


def _expanded_attribute(
    document: dict[str, Any],
    buffers: list[bytes],
    accessor_index: int,
    indices: np.ndarray | None,
) -> np.ndarray:
    values = _accessor_array(document, buffers, accessor_index)
    return values if indices is None else values[indices]


def _skinned_primitive(
    document: dict[str, Any],
    buffers: list[bytes],
    mesh_index: int,
    primitive_index: int,
) -> SkinnedMeshData:
    meshes = document.get("meshes", [])
    try:
        primitive = meshes[mesh_index].get("primitives", [])[primitive_index]
    except (IndexError, TypeError) as exc:
        raise ValueError(f"invalid skinned primitive {mesh_index}:{primitive_index}") from exc
    if int(primitive.get("mode", 4)) != 4:
        raise ValueError("skinned glTF primitives must use TRIANGLES mode")
    attributes = primitive.get("attributes", {})
    for required in ("POSITION", "JOINTS_0", "WEIGHTS_0"):
        if required not in attributes:
            raise ValueError(f"skinned primitive requires {required}")

    positions = np.asarray(
        _accessor_array(document, buffers, int(attributes["POSITION"])), dtype="f4"
    )
    if positions.ndim != 2 or positions.shape[1] != 3:
        raise ValueError("skinned POSITION must be VEC3")
    source_count = len(positions)
    indices: np.ndarray | None = None
    if "indices" in primitive:
        indices = np.asarray(
            _accessor_array(document, buffers, int(primitive["indices"]))
        ).reshape(-1)
        if not np.issubdtype(indices.dtype, np.integer):
            raise ValueError("skinned indices must be integers")
        if len(indices) % 3 != 0 or (len(indices) and int(indices.max()) >= source_count):
            raise ValueError("skinned primitive contains invalid indices")
        positions = positions[indices]
    elif source_count % 3 != 0:
        raise ValueError("unindexed skinned primitive vertex count must be divisible by 3")

    normals: np.ndarray | None = None
    if "NORMAL" in attributes:
        normals = np.asarray(
            _expanded_attribute(document, buffers, int(attributes["NORMAL"]), indices), dtype="f4"
        )
        if normals.shape != positions.shape:
            raise ValueError("skinned NORMAL must match POSITION")
        normals = _normalized_normals(normals)
    if normals is None:
        normals = _generate_normals(positions)

    uvs: np.ndarray | None = None
    if "TEXCOORD_0" in attributes:
        uvs = np.asarray(
            _expanded_attribute(document, buffers, int(attributes["TEXCOORD_0"]), indices),
            dtype="f4",
        )
        if uvs.shape != (len(positions), 2):
            raise ValueError("skinned TEXCOORD_0 must be VEC2")

    joints = np.asarray(
        _expanded_attribute(document, buffers, int(attributes["JOINTS_0"]), indices)
    )
    if joints.shape != (len(positions), 4) or not np.issubdtype(joints.dtype, np.integer):
        raise ValueError("JOINTS_0 must be an integer VEC4 matching POSITION")
    source_weights = _normalized_weights(document, buffers, int(attributes["WEIGHTS_0"]))
    weights = source_weights if indices is None else source_weights[indices]
    if weights.shape != (len(positions), 4):
        raise ValueError("WEIGHTS_0 must be a VEC4 matching POSITION")

    return SkinnedMeshData(MeshData(positions, normals, uvs), joints, weights)


def _skin(
    document: dict[str, Any],
    buffers: list[bytes],
    skin_index: int,
    mesh_node_index: int,
) -> Skin3D:
    skins = document.get("skins", [])
    try:
        spec = skins[skin_index]
    except (IndexError, TypeError) as exc:
        raise ValueError(f"invalid glTF skin index {skin_index}") from exc
    joints = tuple(int(item) for item in spec.get("joints", ()))
    if not joints:
        raise ValueError(f"glTF skin {skin_index} has no joints")
    if len(joints) > MAX_SKIN_JOINTS:
        raise ValueError(f"glTF skin {skin_index} exceeds {MAX_SKIN_JOINTS} GPU joints")
    if "inverseBindMatrices" in spec:
        accessor_index = int(spec["inverseBindMatrices"])
        accessor = document.get("accessors", [])[accessor_index]
        if int(accessor.get("componentType", 0)) != 5126 or accessor.get("type") != "MAT4":
            raise ValueError("inverseBindMatrices must be FLOAT MAT4")
        raw = np.asarray(_accessor_array(document, buffers, accessor_index), dtype="f4")
        if len(raw) < len(joints) or raw.shape[1:] != (16,):
            raise ValueError("inverseBindMatrices does not cover the skin joint table")
        inverse_bind = raw[: len(joints)].reshape((-1, 4, 4)).transpose(0, 2, 1)
    else:
        inverse_bind = np.repeat(np.eye(4, dtype="f4")[None, :, :], len(joints), axis=0)
    raw_root = spec.get("skeleton")
    skeleton_root = None if raw_root is None else int(raw_root)
    return Skin3D(
        joints=joints,
        inverse_bind_matrices=inverse_bind,
        mesh_node_index=mesh_node_index,
        skeleton_root=skeleton_root,
        name=str(spec.get("name", "")),
    )


def _clips(document: dict[str, Any], buffers: list[bytes]) -> tuple[SkeletalAnimationClip3D, ...]:
    clips: list[SkeletalAnimationClip3D] = []
    for animation_index, animation in enumerate(document.get("animations", [])):
        samplers = animation.get("samplers", [])
        channels: list[SkeletalAnimationChannel] = []
        for channel_index, channel in enumerate(animation.get("channels", [])):
            target = channel.get("target", {})
            path = str(target.get("path", ""))
            if path == "weights":
                continue
            if path not in {"translation", "rotation", "scale"}:
                raise ValueError(
                    f"animation {animation_index} channel {channel_index}: bad path {path!r}"
                )
            if "node" not in target:
                raise ValueError(
                    f"animation {animation_index} channel {channel_index} has no target node"
                )
            try:
                sampler = samplers[int(channel["sampler"])]
            except (IndexError, KeyError, TypeError, ValueError) as exc:
                raise ValueError(
                    f"animation {animation_index} channel {channel_index}: invalid sampler"
                ) from exc
            times = np.asarray(
                _accessor_array(document, buffers, int(sampler["input"])), dtype="f4"
            ).reshape(-1)
            output = np.asarray(
                _accessor_array(document, buffers, int(sampler["output"])), dtype="f4"
            )
            interpolation = str(sampler.get("interpolation", "LINEAR")).upper()
            components = 4 if path == "rotation" else 3
            if interpolation == "CUBICSPLINE":
                if output.shape != (len(times) * 3, components):
                    raise ValueError("CUBICSPLINE output must contain in/value/out triplets")
                output = output.reshape((len(times), 3, components))
            elif output.shape != (len(times), components):
                raise ValueError("animation sampler output shape does not match its target")
            channels.append(
                SkeletalAnimationChannel(
                    node_index=int(target["node"]),
                    path=path,
                    times=times,
                    values=output,
                    interpolation=interpolation,
                )
            )
        name = str(animation.get("name") or f"animation_{animation_index}")
        clips.append(SkeletalAnimationClip3D(name, tuple(channels)))
    return tuple(clips)


def _scene_nodes(document: dict[str, Any], scene_index: int | None) -> set[int]:
    nodes = document.get("nodes", [])
    scenes = document.get("scenes", [])
    if not scenes:
        return set(range(len(nodes)))
    selected = int(document.get("scene", 0)) if scene_index is None else int(scene_index)
    if not 0 <= selected < len(scenes):
        raise ValueError(f"scene_index {selected} is out of range")
    reachable: set[int] = set()
    stack = [int(item) for item in scenes[selected].get("nodes", [])]
    while stack:
        node_index = stack.pop()
        if not 0 <= node_index < len(nodes):
            raise ValueError(f"scene references invalid node {node_index}")
        if node_index in reachable:
            continue
        reachable.add(node_index)
        stack.extend(int(item) for item in nodes[node_index].get("children", []))
    return reachable


def load_gltf_skeletal(path: str | Path, *, scene_index: int | None = None) -> GltfSkeletalAsset:
    """Load glTF/GLB skins and skeletal animation without changing the static loaders."""

    source = _source(path)
    document, binary_chunk = _load_document(source)
    buffers = _load_buffers(document, source, binary_chunk)
    skeleton = _skeleton(document)
    clips = _clips(document, buffers)
    clip_map = {clip.name: clip for clip in clips}
    reachable = _scene_nodes(document, scene_index)
    meshes = document.get("meshes", [])
    objects: list[SkinnedMesh3D] = []

    for node_index in sorted(reachable):
        node = document.get("nodes", [])[node_index]
        if "mesh" not in node or "skin" not in node:
            continue
        mesh_index = int(node["mesh"])
        skin = _skin(document, buffers, int(node["skin"]), node_index)
        try:
            primitives = meshes[mesh_index].get("primitives", [])
        except (IndexError, TypeError) as exc:
            raise ValueError(f"node {node_index} references invalid mesh {mesh_index}") from exc
        for primitive_index, primitive in enumerate(primitives):
            raw_material = primitive.get("material")
            material_index = None if raw_material is None else int(raw_material)
            material, _, _ = _material(document, buffers, source, material_index)
            obj = SkinnedMesh3D(
                data=_skinned_primitive(document, buffers, mesh_index, primitive_index),
                skeleton=skeleton,
                skin=skin,
                clips=clip_map,
                material=material,
                name=str(node.get("name", "")) or f"skinned_mesh_{node_index}_{primitive_index}",
            )
            objects.append(obj)

    if not objects:
        raise ValueError("selected glTF scene contains no nodes with both mesh and skin")
    return GltfSkeletalAsset(tuple(objects), clips)
