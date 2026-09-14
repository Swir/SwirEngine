from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass, field

import numpy as np

from ..math.types import Color, Transform, Vec3, perspective
from .camera3d import Camera3D
from .material import Material3D
from .mesh import MeshData

MAX_SKIN_JOINTS = 64
_ANIMATION_PATHS = {"translation", "rotation", "scale"}
_INTERPOLATIONS = {"LINEAR", "STEP", "CUBICSPLINE"}


def _vec(values: object, size: int, label: str) -> np.ndarray:
    value = np.asarray(values, dtype="f4")
    if value.shape != (size,):
        raise ValueError(f"{label} must contain {size} values")
    return value


def _normalized_quaternion(values: object) -> np.ndarray:
    value = _vec(values, 4, "rotation quaternion")
    length = float(np.linalg.norm(value))
    if length <= 1e-8:
        raise ValueError("rotation quaternion cannot be zero")
    return value / length


def quaternion_slerp(a: object, b: object, amount: float) -> np.ndarray:
    """Shortest-path normalized quaternion interpolation for glTF XYZW quaternions."""

    start = _normalized_quaternion(a)
    end = _normalized_quaternion(b)
    t = min(1.0, max(0.0, float(amount)))
    dot = float(np.dot(start, end))
    if dot < 0.0:
        end = -end
        dot = -dot
    if dot > 0.9995:
        result = start + t * (end - start)
        return result / np.linalg.norm(result)
    theta = math.acos(min(1.0, max(-1.0, dot)))
    sine = math.sin(theta)
    if abs(sine) <= 1e-8:
        return start.copy()
    return (
        math.sin((1.0 - t) * theta) / sine * start
        + math.sin(t * theta) / sine * end
    ).astype("f4")


def compose_trs(translation: object, rotation: object, scale: object) -> np.ndarray:
    """Compose glTF-style translation, XYZW quaternion rotation and scale."""

    translation_value = _vec(translation, 3, "translation")
    x, y, z, w = _normalized_quaternion(rotation)
    scale_value = _vec(scale, 3, "scale")
    rotation_matrix = np.asarray(
        [
            [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
            [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
            [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)],
        ],
        dtype="f4",
    )
    result = np.eye(4, dtype="f4")
    result[:3, :3] = rotation_matrix @ np.diag(scale_value)
    result[:3, 3] = translation_value
    return result


@dataclass(frozen=True, slots=True)
class SkeletonNode3D:
    index: int
    parent: int | None = None
    name: str = ""
    translation: tuple[float, float, float] = (0.0, 0.0, 0.0)
    rotation: tuple[float, float, float, float] = (0.0, 0.0, 0.0, 1.0)
    scale: tuple[float, float, float] = (1.0, 1.0, 1.0)

    def __post_init__(self) -> None:
        if self.index < 0:
            raise ValueError("node index cannot be negative")
        _vec(self.translation, 3, "translation")
        _normalized_quaternion(self.rotation)
        _vec(self.scale, 3, "scale")


@dataclass(frozen=True, slots=True)
class Skeleton3D:
    nodes: tuple[SkeletonNode3D, ...]

    def __post_init__(self) -> None:
        if not self.nodes:
            raise ValueError("skeleton must contain at least one node")
        for expected, node in enumerate(self.nodes):
            if node.index != expected:
                raise ValueError("skeleton nodes must be stored in index order")
            if node.parent is not None and not 0 <= node.parent < len(self.nodes):
                raise ValueError(f"node {node.index} has invalid parent {node.parent}")
        for node in self.nodes:
            seen: set[int] = set()
            parent = node.parent
            while parent is not None:
                if parent in seen or parent == node.index:
                    raise ValueError("skeleton node hierarchy contains a cycle")
                seen.add(parent)
                parent = self.nodes[parent].parent

    @property
    def node_count(self) -> int:
        return len(self.nodes)

    def bind_pose(self) -> SkeletalPose:
        return SkeletalPose(
            tuple(np.asarray(node.translation, dtype="f4") for node in self.nodes),
            tuple(_normalized_quaternion(node.rotation) for node in self.nodes),
            tuple(np.asarray(node.scale, dtype="f4") for node in self.nodes),
        )


@dataclass(frozen=True, slots=True)
class Skin3D:
    joints: tuple[int, ...]
    inverse_bind_matrices: np.ndarray
    mesh_node_index: int
    skeleton_root: int | None = None
    name: str = ""

    def __post_init__(self) -> None:
        if not self.joints:
            raise ValueError("skin must contain at least one joint")
        if any(joint < 0 for joint in self.joints):
            raise ValueError("skin joint node indices cannot be negative")
        if len(self.joints) > MAX_SKIN_JOINTS:
            raise ValueError(f"skin exceeds GPU joint budget of {MAX_SKIN_JOINTS}")
        matrices = np.asarray(self.inverse_bind_matrices, dtype="f4")
        if matrices.shape != (len(self.joints), 4, 4):
            raise ValueError("inverse_bind_matrices must have shape (joint_count, 4, 4)")
        if self.mesh_node_index < 0:
            raise ValueError("mesh_node_index cannot be negative")
        object.__setattr__(self, "inverse_bind_matrices", np.ascontiguousarray(matrices))


@dataclass(frozen=True, slots=True)
class SkeletalPose:
    translations: tuple[np.ndarray, ...]
    rotations: tuple[np.ndarray, ...]
    scales: tuple[np.ndarray, ...]

    def __post_init__(self) -> None:
        count = len(self.translations)
        if len(self.rotations) != count or len(self.scales) != count:
            raise ValueError("pose TRS arrays must have matching node counts")

    @property
    def node_count(self) -> int:
        return len(self.translations)


@dataclass(frozen=True, slots=True)
class SkeletalAnimationChannel:
    node_index: int
    path: str
    times: np.ndarray
    values: np.ndarray
    interpolation: str = "LINEAR"

    def __post_init__(self) -> None:
        path = str(self.path)
        interpolation = str(self.interpolation).upper()
        if self.node_index < 0:
            raise ValueError("animation node index cannot be negative")
        if path not in _ANIMATION_PATHS:
            raise ValueError(f"unsupported skeletal animation path {path!r}")
        if interpolation not in _INTERPOLATIONS:
            raise ValueError(f"unsupported glTF interpolation {interpolation!r}")
        times = np.asarray(self.times, dtype="f4").reshape(-1)
        if len(times) == 0 or not np.all(np.isfinite(times)):
            raise ValueError("animation channel must contain finite keyframe times")
        if np.any(np.diff(times) <= 0.0):
            raise ValueError("animation keyframe times must be strictly increasing")
        components = 4 if path == "rotation" else 3
        values = np.asarray(self.values, dtype="f4")
        expected = (
            (len(times), 3, components)
            if interpolation == "CUBICSPLINE"
            else (len(times), components)
        )
        if values.shape != expected:
            raise ValueError(f"animation values must have shape {expected}")
        object.__setattr__(self, "path", path)
        object.__setattr__(self, "interpolation", interpolation)
        object.__setattr__(self, "times", np.ascontiguousarray(times))
        object.__setattr__(self, "values", np.ascontiguousarray(values))

    @property
    def end_time(self) -> float:
        return float(self.times[-1])

    def sample(self, time: float) -> np.ndarray:
        t = float(time)
        if t <= float(self.times[0]):
            value = self.values[0, 1] if self.interpolation == "CUBICSPLINE" else self.values[0]
            return _normalized_quaternion(value) if self.path == "rotation" else value.copy()
        if t >= float(self.times[-1]):
            value = self.values[-1, 1] if self.interpolation == "CUBICSPLINE" else self.values[-1]
            return _normalized_quaternion(value) if self.path == "rotation" else value.copy()

        right = int(np.searchsorted(self.times, t, side="right"))
        left = right - 1
        start_time = float(self.times[left])
        end_time = float(self.times[right])
        span = end_time - start_time
        amount = (t - start_time) / span

        if self.interpolation == "STEP":
            value = self.values[left]
        elif self.interpolation == "CUBICSPLINE":
            p0 = self.values[left, 1]
            m0 = self.values[left, 2] * span
            p1 = self.values[right, 1]
            m1 = self.values[right, 0] * span
            a2 = amount * amount
            a3 = a2 * amount
            value = (
                (2 * a3 - 3 * a2 + 1) * p0
                + (a3 - 2 * a2 + amount) * m0
                + (-2 * a3 + 3 * a2) * p1
                + (a3 - a2) * m1
            )
        elif self.path == "rotation":
            return quaternion_slerp(self.values[left], self.values[right], amount)
        else:
            value = self.values[left] + amount * (self.values[right] - self.values[left])
        return (
            _normalized_quaternion(value)
            if self.path == "rotation"
            else np.asarray(value, dtype="f4")
        )


@dataclass(frozen=True, slots=True)
class SkeletalAnimationClip3D:
    name: str
    channels: tuple[SkeletalAnimationChannel, ...]
    duration: float = 0.0

    def __post_init__(self) -> None:
        duration = max((channel.end_time for channel in self.channels), default=0.0)
        requested = float(self.duration)
        object.__setattr__(self, "duration", max(requested, duration))


def sample_skeletal_clip(
    skeleton: Skeleton3D,
    clip: SkeletalAnimationClip3D | None,
    time: float,
    *,
    loop: bool = True,
) -> SkeletalPose:
    bind = skeleton.bind_pose()
    if clip is None or not clip.channels:
        return bind
    duration = float(clip.duration)
    sample_time = float(time)
    if duration > 0.0:
        sample_time = sample_time % duration if loop else min(max(sample_time, 0.0), duration)

    translations = [value.copy() for value in bind.translations]
    rotations = [value.copy() for value in bind.rotations]
    scales = [value.copy() for value in bind.scales]
    for channel in clip.channels:
        if channel.node_index >= skeleton.node_count:
            raise ValueError(f"animation channel targets unknown node {channel.node_index}")
        sampled = channel.sample(sample_time)
        if channel.path == "translation":
            translations[channel.node_index] = sampled
        elif channel.path == "rotation":
            rotations[channel.node_index] = sampled
        else:
            scales[channel.node_index] = sampled
    return SkeletalPose(tuple(translations), tuple(rotations), tuple(scales))


def blend_skeletal_poses(a: SkeletalPose, b: SkeletalPose, amount: float) -> SkeletalPose:
    if a.node_count != b.node_count:
        raise ValueError("cannot blend skeletal poses with different node counts")
    weight = min(1.0, max(0.0, float(amount)))
    translations = tuple(
        left + (right - left) * weight
        for left, right in zip(a.translations, b.translations, strict=True)
    )
    rotations = tuple(
        quaternion_slerp(left, right, weight)
        for left, right in zip(a.rotations, b.rotations, strict=True)
    )
    scales = tuple(
        left + (right - left) * weight
        for left, right in zip(a.scales, b.scales, strict=True)
    )
    return SkeletalPose(translations, rotations, scales)


def global_pose_matrices(skeleton: Skeleton3D, pose: SkeletalPose) -> np.ndarray:
    if pose.node_count != skeleton.node_count:
        raise ValueError("pose does not match skeleton node count")
    result = np.empty((skeleton.node_count, 4, 4), dtype="f4")
    resolved = np.zeros(skeleton.node_count, dtype=bool)

    def resolve(index: int) -> np.ndarray:
        if resolved[index]:
            return result[index]
        node = skeleton.nodes[index]
        local = compose_trs(pose.translations[index], pose.rotations[index], pose.scales[index])
        result[index] = local if node.parent is None else resolve(node.parent) @ local
        resolved[index] = True
        return result[index]

    for index in range(skeleton.node_count):
        resolve(index)
    return result


def skin_joint_palette(skeleton: Skeleton3D, skin: Skin3D, pose: SkeletalPose) -> np.ndarray:
    globals_ = global_pose_matrices(skeleton, pose)
    if skin.mesh_node_index >= skeleton.node_count:
        raise ValueError("skin mesh node is outside the skeleton node table")
    for joint in skin.joints:
        if not 0 <= joint < skeleton.node_count:
            raise ValueError(f"skin references unknown joint node {joint}")
    try:
        inverse_mesh = np.linalg.inv(globals_[skin.mesh_node_index]).astype("f4")
    except np.linalg.LinAlgError as exc:
        raise ValueError("skinned mesh node transform is singular") from exc
    palette = np.empty((len(skin.joints), 4, 4), dtype="f4")
    for index, joint in enumerate(skin.joints):
        palette[index] = inverse_mesh @ globals_[joint] @ skin.inverse_bind_matrices[index]
    return palette


@dataclass(slots=True)
class SkeletalAnimationController:
    skeleton: Skeleton3D
    clips: Mapping[str, SkeletalAnimationClip3D]
    loop: bool = True
    speed: float = 1.0
    current: str | None = None
    time: float = 0.0
    _previous: str | None = None
    _previous_time: float = 0.0
    _fade_duration: float = 0.0
    _fade_elapsed: float = 0.0

    def __post_init__(self) -> None:
        self.clips = dict(self.clips)
        if self.current is not None and self.current not in self.clips:
            raise KeyError(f"unknown animation clip {self.current!r}")

    @property
    def names(self) -> tuple[str, ...]:
        return tuple(self.clips)

    @property
    def blending(self) -> bool:
        return self._previous is not None and self._fade_duration > 0.0

    def play(self, name: str, *, fade: float = 0.0, restart: bool = True) -> None:
        if name not in self.clips:
            raise KeyError(f"unknown animation clip {name!r}")
        same_clip = name == self.current
        if same_clip and not restart:
            return
        fade_value = max(0.0, float(fade))
        if fade_value > 0.0 and self.current is not None and self.current != name:
            self._previous = self.current
            self._previous_time = self.time
            self._fade_duration = fade_value
            self._fade_elapsed = 0.0
        else:
            self._previous = None
            self._fade_duration = 0.0
            self._fade_elapsed = 0.0
        self.current = name
        if restart or not same_clip:
            self.time = 0.0

    def stop(self) -> None:
        self.current = None
        self.time = 0.0
        self._previous = None
        self._previous_time = 0.0
        self._fade_duration = 0.0
        self._fade_elapsed = 0.0

    def update(self, dt: float) -> None:
        advance = max(0.0, float(dt)) * float(self.speed)
        self.time += advance
        if self._previous is not None:
            self._previous_time += advance
            self._fade_elapsed += max(0.0, float(dt))
            if self._fade_elapsed >= self._fade_duration:
                self._previous = None
                self._fade_duration = 0.0
                self._fade_elapsed = 0.0

    def pose(self) -> SkeletalPose:
        current_clip = self.clips.get(self.current) if self.current is not None else None
        current_pose = sample_skeletal_clip(self.skeleton, current_clip, self.time, loop=self.loop)
        if not self.blending or self._previous is None:
            return current_pose
        previous_pose = sample_skeletal_clip(
            self.skeleton,
            self.clips[self._previous],
            self._previous_time,
            loop=self.loop,
        )
        amount = self._fade_elapsed / max(self._fade_duration, 1e-8)
        return blend_skeletal_poses(previous_pose, current_pose, amount)


@dataclass(frozen=True, slots=True)
class SkinnedMeshData:
    mesh: MeshData
    joints: np.ndarray
    weights: np.ndarray

    def __post_init__(self) -> None:
        count = self.mesh.vertex_count
        joints = np.asarray(self.joints)
        weights = np.asarray(self.weights, dtype="f4")
        if joints.shape != (count, 4):
            raise ValueError("joints must have shape (vertex_count, 4)")
        if weights.shape != (count, 4):
            raise ValueError("weights must have shape (vertex_count, 4)")
        if not np.issubdtype(joints.dtype, np.integer):
            raise ValueError("joint indices must be integers")
        if np.any(joints < 0):
            raise ValueError("joint indices cannot be negative")
        if np.any(weights < 0.0) or not np.all(np.isfinite(weights)):
            raise ValueError("skin weights must be finite and non-negative")
        totals = weights.sum(axis=1)
        if np.any(totals <= 1e-8):
            raise ValueError("each skinned vertex must have a non-zero total weight")
        weights = weights / totals[:, None]
        object.__setattr__(self, "joints", np.ascontiguousarray(joints, dtype="i4"))
        object.__setattr__(self, "weights", np.ascontiguousarray(weights, dtype="f4"))

    def gpu_interleaved(self) -> np.ndarray:
        base = self.mesh.interleaved(include_uvs=True)
        return np.ascontiguousarray(
            np.concatenate((base, self.joints.astype("f4"), self.weights), axis=1),
            dtype="f4",
        )


@dataclass(slots=True)
class SkinnedMesh3D:
    data: SkinnedMeshData
    skeleton: Skeleton3D
    skin: Skin3D
    clips: Mapping[str, SkeletalAnimationClip3D] = field(default_factory=dict)
    position: Vec3 = field(default_factory=Vec3)
    rotation: Vec3 = field(default_factory=Vec3)
    scale: Vec3 = field(default_factory=lambda: Vec3(1.0, 1.0, 1.0))
    color: Color = field(default_factory=Color)
    material: Material3D | None = None
    enabled: bool = True
    visible: bool = True
    name: str = ""
    tags: set[str] = field(default_factory=set)
    controller: SkeletalAnimationController = field(init=False)

    def __post_init__(self) -> None:
        if self.skin.mesh_node_index >= self.skeleton.node_count:
            raise ValueError("skin mesh node is outside skeleton")
        if self.skin.joints and int(self.data.joints.max(initial=0)) >= len(self.skin.joints):
            raise ValueError("vertex joint index exceeds the skin joint table")
        self.clips = dict(self.clips)
        self.controller = SkeletalAnimationController(self.skeleton, self.clips)

    @property
    def transform(self) -> Transform:
        return Transform(self.position, self.rotation, self.scale)

    @property
    def vertex_count(self) -> int:
        return self.data.mesh.vertex_count

    def play(self, name: str, *, fade: float = 0.0, restart: bool = True) -> None:
        self.controller.play(name, fade=fade, restart=restart)

    def update(self, dt: float) -> None:
        self.controller.update(dt)

    def joint_palette(self) -> np.ndarray:
        return skin_joint_palette(self.skeleton, self.skin, self.controller.pose())


@dataclass(slots=True)
class _GPUSkinnedResource:
    source_vbo: object
    transform_vao: object
    skinned_vbo: object
    draw_vao: object
    vertex_count: int


class SkinnedRenderPipeline:
    """GPU skinning pre-pass feeding SwirEngine's existing forward/PBR renderer."""

    def __init__(self, owner: object) -> None:
        self.owner = owner
        self.ctx = owner.ctx
        self._resources: dict[int, _GPUSkinnedResource] = {}
        self.program = self.ctx.program(
            vertex_shader="""
                #version 330
                in vec3 in_pos;
                in vec3 in_normal;
                in vec2 in_uv;
                in vec4 in_joints;
                in vec4 in_weights;
                uniform sampler2D joint_palette;
                out vec3 skinned_pos;
                out vec3 skinned_normal;
                out vec2 skinned_uv;

                mat4 palette(int joint) {
                    return mat4(
                        texelFetch(joint_palette, ivec2(0, joint), 0),
                        texelFetch(joint_palette, ivec2(1, joint), 0),
                        texelFetch(joint_palette, ivec2(2, joint), 0),
                        texelFetch(joint_palette, ivec2(3, joint), 0)
                    );
                }

                void main() {
                    ivec4 joints = ivec4(in_joints + vec4(0.5));
                    mat4 skin =
                        in_weights.x * palette(joints.x)
                        + in_weights.y * palette(joints.y)
                        + in_weights.z * palette(joints.z)
                        + in_weights.w * palette(joints.w);
                    skinned_pos = (skin * vec4(in_pos, 1.0)).xyz;
                    skinned_normal = normalize(mat3(skin) * in_normal);
                    skinned_uv = in_uv;
                }
            """,
            varyings=["skinned_pos", "skinned_normal", "skinned_uv"],
        )
        self.program["joint_palette"].value = 7
        self._palette_texture = self.ctx.texture((4, MAX_SKIN_JOINTS), 4, dtype="f4")
        self._palette_texture.filter = (self.ctx.NEAREST, self.ctx.NEAREST)

    def _resource(self, obj: SkinnedMesh3D) -> _GPUSkinnedResource:
        key = id(obj.data)
        cached = self._resources.get(key)
        if cached is not None:
            return cached
        data = obj.data.gpu_interleaved()
        source_vbo = self.ctx.buffer(data.tobytes())
        transform_vao = self.ctx.vertex_array(
            self.program,
            [
                (
                    source_vbo,
                    "3f 3f 2f 4f 4f",
                    "in_pos",
                    "in_normal",
                    "in_uv",
                    "in_joints",
                    "in_weights",
                )
            ],
        )
        skinned_vbo = self.ctx.buffer(reserve=obj.vertex_count * 8 * np.dtype("f4").itemsize)
        draw_vao = self.ctx.vertex_array(
            self.owner.program3d,
            [(skinned_vbo, "3f 3f 2f", "in_pos", "in_normal", "in_uv")],
        )
        cached = _GPUSkinnedResource(
            source_vbo,
            transform_vao,
            skinned_vbo,
            draw_vao,
            obj.vertex_count,
        )
        self._resources[key] = cached
        self.owner.stats.mesh_uploads += 1
        return cached

    def _upload_palette(self, palette: np.ndarray) -> None:
        if len(palette) > MAX_SKIN_JOINTS:
            raise ValueError(f"skin exceeds GPU joint budget of {MAX_SKIN_JOINTS}")
        packed = np.zeros((MAX_SKIN_JOINTS, 4, 4), dtype="f4")
        packed[:, :, :] = np.eye(4, dtype="f4").T
        packed[: len(palette)] = np.asarray(palette, dtype="f4").transpose(0, 2, 1)
        self._palette_texture.write(np.ascontiguousarray(packed).tobytes())
        self._palette_texture.use(location=7)

    def render(self, scene: object, camera: Camera3D) -> None:
        objects = [
            obj
            for obj in getattr(scene, "objects", ())
            if isinstance(obj, SkinnedMesh3D) and obj.enabled and obj.visible
        ]
        if not objects:
            return
        projection = perspective(
            float(camera.fov),
            self.owner.width / max(1, self.owner.height),
            float(camera.near),
            float(camera.far),
        )
        view_projection = projection @ camera.view_matrix()
        for obj in objects:
            resource = self._resource(obj)
            self._upload_palette(obj.joint_palette())
            resource.transform_vao.transform(resource.skinned_vbo, vertices=resource.vertex_count)
            barrier = getattr(self.ctx, "memory_barrier", None)
            if barrier is not None:
                barrier(getattr(self.ctx, "VERTEX_ATTRIB_ARRAY_BARRIER_BIT", 0x00000001))
            self.owner._render_model(
                resource.draw_vao,
                obj.transform.matrix(),
                view_projection,
                obj.color,
                vertices=resource.vertex_count,
                material=obj.material,
            )
            self.owner.stats.meshes += 1
            if hasattr(self.owner.stats, "skinned_meshes"):
                self.owner.stats.skinned_meshes += 1
                self.owner.stats.skin_vertices += resource.vertex_count
                self.owner.stats.skin_joints += len(obj.skin.joints)

    def release(self) -> None:
        for resource in self._resources.values():
            resource.draw_vao.release()
            resource.skinned_vbo.release()
            resource.transform_vao.release()
            resource.source_vbo.release()
        self._resources.clear()
        self._palette_texture.release()
        self.program.release()
