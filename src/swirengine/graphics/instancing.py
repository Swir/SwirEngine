from __future__ import annotations

import math
from collections.abc import Iterable
from dataclasses import dataclass, field

import numpy as np

from ..math.types import Color, Transform, Vec3, perspective
from .camera3d import Camera3D
from .lights import (
    MAX_DIRECTIONAL_LIGHTS,
    MAX_POINT_LIGHTS,
    MAX_SPOT_LIGHTS,
    DirectionalLight3D,
    PointLight3D,
    SpotLight3D,
    select_lights,
)
from .material import Material3D
from .mesh import MeshData, cube_mesh


@dataclass(slots=True)
class Instance3D:
    """One transform/color entry rendered as part of an instanced mesh batch."""

    position: Vec3 = field(default_factory=Vec3)
    rotation: Vec3 = field(default_factory=Vec3)
    scale: Vec3 = field(default_factory=lambda: Vec3(1.0, 1.0, 1.0))
    color: Color = field(default_factory=Color)
    enabled: bool = True
    visible: bool = True

    @property
    def transform(self) -> Transform:
        return Transform(self.position, self.rotation, self.scale)


@dataclass(frozen=True, slots=True)
class FrustumPlane:
    x: float
    y: float
    z: float
    w: float

    def distance(self, point: Vec3) -> float:
        return self.x * point.x + self.y * point.y + self.z * point.z + self.w


@dataclass(frozen=True, slots=True)
class Frustum3D:
    """Six normalized clip planes extracted from a view-projection matrix."""

    planes: tuple[FrustumPlane, ...]

    @classmethod
    def from_view_projection(cls, matrix: np.ndarray) -> Frustum3D:
        value = np.asarray(matrix, dtype="f4")
        if value.shape != (4, 4):
            raise ValueError("view_projection must have shape (4, 4)")
        rows = value
        raw = (
            rows[3] + rows[0],
            rows[3] - rows[0],
            rows[3] + rows[1],
            rows[3] - rows[1],
            rows[3] + rows[2],
            rows[3] - rows[2],
        )
        planes: list[FrustumPlane] = []
        for item in raw:
            length = float(np.linalg.norm(item[:3]))
            if length <= 1e-8:
                raise ValueError("view_projection contains a degenerate frustum plane")
            plane = item / length
            planes.append(
                FrustumPlane(
                    float(plane[0]),
                    float(plane[1]),
                    float(plane[2]),
                    float(plane[3]),
                )
            )
        return cls(tuple(planes))

    def sphere_visible(self, center: Vec3, radius: float = 0.0) -> bool:
        value = max(0.0, float(radius))
        return all(plane.distance(center) >= -value for plane in self.planes)


@dataclass(frozen=True, slots=True)
class InstancingDiagnostics:
    source_instances: int
    active_instances: int
    visible_instances: int
    culled_instances: int
    draw_calls_before: int
    draw_calls_after: int

    @property
    def draw_call_reduction(self) -> float:
        if self.draw_calls_before <= 0:
            return 0.0
        return 1.0 - self.draw_calls_after / self.draw_calls_before


@dataclass(frozen=True, slots=True)
class PreparedInstanceFrame:
    """CPU preparation result; ``data`` is a view into the supplied staging array."""

    data: np.ndarray
    diagnostics: InstancingDiagnostics


def _instance_radius(base_radius: float, instance: Instance3D) -> float:
    scale = instance.scale
    return base_radius * max(abs(float(scale.x)), abs(float(scale.y)), abs(float(scale.z)))


def _pack_instance(target: np.ndarray, instance: Instance3D) -> None:
    """Pack one model matrix in OpenGL column order plus RGBA without a matrix allocation."""

    rotation = instance.rotation
    scale = instance.scale
    px, py, pz = float(instance.position.x), float(instance.position.y), float(instance.position.z)
    scale_x, scale_y, scale_z = float(scale.x), float(scale.y), float(scale.z)

    if rotation.x == 0.0 and rotation.y == 0.0 and rotation.z == 0.0:
        target[0:4] = (scale_x, 0.0, 0.0, 0.0)
        target[4:8] = (0.0, scale_y, 0.0, 0.0)
        target[8:12] = (0.0, 0.0, scale_z, 0.0)
    else:
        rx = math.radians(float(rotation.x))
        ry = math.radians(float(rotation.y))
        rz = math.radians(float(rotation.z))
        sxn, cx = math.sin(rx), math.cos(rx)
        syn, cy = math.sin(ry), math.cos(ry)
        szn, cz = math.sin(rz), math.cos(rz)

        r00 = cz * cy
        r01 = cz * syn * sxn - szn * cx
        r02 = cz * syn * cx + szn * sxn
        r10 = szn * cy
        r11 = szn * syn * sxn + cz * cx
        r12 = szn * syn * cx - cz * sxn
        r20 = -syn
        r21 = cy * sxn
        r22 = cy * cx

        target[0:4] = (r00 * scale_x, r10 * scale_x, r20 * scale_x, 0.0)
        target[4:8] = (r01 * scale_y, r11 * scale_y, r21 * scale_y, 0.0)
        target[8:12] = (r02 * scale_z, r12 * scale_z, r22 * scale_z, 0.0)
    target[12:16] = (px, py, pz, 1.0)

    color = instance.color.clamped()
    target[16:20] = (color.r, color.g, color.b, color.a)


@dataclass(slots=True)
class InstancedMesh3D:
    """One mesh/material plus many dynamic transforms rendered with GPU instancing."""

    mesh: MeshData
    instances: list[Instance3D] = field(default_factory=list)
    color: Color = field(default_factory=Color)
    material: Material3D | None = None
    cull: bool = True
    enabled: bool = True
    visible: bool = True
    name: str = ""
    tags: set[str] = field(default_factory=set)
    bounds_radius: float | None = None

    def __post_init__(self) -> None:
        if self.bounds_radius is None:
            lengths = np.linalg.norm(self.mesh.vertices, axis=1)
            self.bounds_radius = float(lengths.max(initial=0.0))
        else:
            self.bounds_radius = max(0.0, float(self.bounds_radius))

    def update(self, dt: float) -> None:
        pass

    @property
    def instance_count(self) -> int:
        return len(self.instances)

    def add_instance(
        self,
        *,
        position: Vec3 | None = None,
        rotation: Vec3 | None = None,
        scale: Vec3 | None = None,
        color: Color | None = None,
        enabled: bool = True,
        visible: bool = True,
    ) -> Instance3D:
        instance = Instance3D(
            position=position or Vec3(),
            rotation=rotation or Vec3(),
            scale=scale or Vec3(1.0, 1.0, 1.0),
            color=color or Color(),
            enabled=enabled,
            visible=visible,
        )
        self.instances.append(instance)
        return instance

    def extend(self, instances: Iterable[Instance3D]) -> InstancedMesh3D:
        self.instances.extend(instances)
        return self

    def remove_instance(self, instance: Instance3D) -> bool:
        try:
            self.instances.remove(instance)
        except ValueError:
            return False
        return True

    def clear_instances(self) -> None:
        self.instances.clear()

    def prepare(
        self,
        view_projection: np.ndarray,
        *,
        staging: np.ndarray | None = None,
        frustum: Frustum3D | None = None,
    ) -> PreparedInstanceFrame:
        """Cull and pack active instances into a reusable float32 staging buffer."""

        source = len(self.instances)
        if staging is None:
            staging = np.empty((max(1, source), 20), dtype="f4")
        if staging.dtype != np.dtype("f4") or staging.ndim != 2 or staging.shape[1] != 20:
            raise ValueError("staging must be a float32 array with shape (N, 20)")
        if staging.shape[0] < source:
            raise ValueError("staging does not have enough rows for this batch")

        frustum = (frustum or Frustum3D.from_view_projection(view_projection)) if self.cull else None
        radius = float(self.bounds_radius or 0.0)
        active = 0
        visible = 0
        culled = 0

        for instance in self.instances:
            if not instance.enabled or not instance.visible:
                continue
            active += 1
            if frustum is not None and not frustum.sphere_visible(
                instance.position,
                _instance_radius(radius, instance),
            ):
                culled += 1
                continue
            _pack_instance(staging[visible], instance)
            visible += 1

        diagnostics = InstancingDiagnostics(
            source_instances=source,
            active_instances=active,
            visible_instances=visible,
            culled_instances=culled,
            draw_calls_before=active,
            draw_calls_after=1 if visible else 0,
        )
        return PreparedInstanceFrame(staging[:visible], diagnostics)


class InstancedCube3D(InstancedMesh3D):
    """Ergonomic instanced unit-cube batch."""

    def __init__(
        self,
        instances: Iterable[Instance3D] = (),
        *,
        color: Color | None = None,
        material: Material3D | None = None,
        cull: bool = True,
        name: str = "",
        tags: set[str] | None = None,
    ) -> None:
        super().__init__(
            cube_mesh(),
            list(instances),
            color=color or Color(),
            material=material,
            cull=cull,
            name=name,
            tags=set(tags or ()),
        )

    def add_cube(
        self,
        *,
        position: Vec3 | None = None,
        rotation: Vec3 | None = None,
        size: float = 1.0,
        color: Color | None = None,
        enabled: bool = True,
        visible: bool = True,
    ) -> Instance3D:
        value = float(size)
        return self.add_instance(
            position=position,
            rotation=rotation,
            scale=Vec3(value, value, value),
            color=color,
            enabled=enabled,
            visible=visible,
        )


@dataclass(slots=True)
class _GPUInstanceResource:
    mesh_vbo: object
    instance_vbo: object
    vao: object
    capacity: int
    vertex_count: int


class InstancedRenderPipeline:
    """Internal ModernGL instancing backend shared by the production renderer."""

    def __init__(self, owner: object) -> None:
        self.owner = owner
        self.ctx = owner.ctx
        self._resources: dict[int, _GPUInstanceResource] = {}
        self._staging = np.empty((256, 20), dtype="f4")
        self.program = self.ctx.program(
            vertex_shader="""
                #version 330
                in vec3 in_pos;
                in vec3 in_normal;
                in vec2 in_uv;
                in vec4 in_model_0;
                in vec4 in_model_1;
                in vec4 in_model_2;
                in vec4 in_model_3;
                in vec4 in_instance_color;
                uniform mat4 view_projection;
                out vec3 v_normal;
                out vec3 v_world_pos;
                out vec2 v_uv;
                out vec4 v_instance_color;

                void main() {
                    mat4 model = mat4(in_model_0, in_model_1, in_model_2, in_model_3);
                    vec4 world = model * vec4(in_pos, 1.0);
                    gl_Position = view_projection * world;
                    v_world_pos = world.xyz;
                    v_normal = mat3(transpose(inverse(model))) * in_normal;
                    v_uv = in_uv;
                    v_instance_color = in_instance_color;
                }
            """,
            fragment_shader="""
                #version 330
                const float PI = 3.14159265359;
                uniform vec4 base_color;
                uniform sampler2D image;
                uniform bool use_texture;
                uniform float ambient_strength;
                uniform float diffuse_strength;
                uniform float specular_strength;
                uniform float shininess;
                uniform bool pbr_enabled;
                uniform float metallic_factor;
                uniform float roughness_factor;
                uniform sampler2D metallic_roughness_image;
                uniform bool use_metallic_roughness_texture;
                uniform sampler2D normal_image;
                uniform bool use_normal_texture;
                uniform float normal_scale;
                uniform sampler2D occlusion_image;
                uniform bool use_occlusion_texture;
                uniform float occlusion_strength;
                uniform sampler2D emissive_image;
                uniform bool use_emissive_texture;
                uniform vec3 emissive_factor;
                uniform vec3 view_position;

                uniform bool dir0_enabled;
                uniform vec3 dir0_direction;
                uniform vec3 dir0_color;
                uniform float dir0_intensity;
                uniform bool dir1_enabled;
                uniform vec3 dir1_direction;
                uniform vec3 dir1_color;
                uniform float dir1_intensity;
                uniform bool dir2_enabled;
                uniform vec3 dir2_direction;
                uniform vec3 dir2_color;
                uniform float dir2_intensity;
                uniform bool dir3_enabled;
                uniform vec3 dir3_direction;
                uniform vec3 dir3_color;
                uniform float dir3_intensity;

                uniform bool point0_enabled;
                uniform vec3 point0_position;
                uniform vec3 point0_color;
                uniform float point0_intensity;
                uniform float point0_range;
                uniform bool point1_enabled;
                uniform vec3 point1_position;
                uniform vec3 point1_color;
                uniform float point1_intensity;
                uniform float point1_range;
                uniform bool point2_enabled;
                uniform vec3 point2_position;
                uniform vec3 point2_color;
                uniform float point2_intensity;
                uniform float point2_range;
                uniform bool point3_enabled;
                uniform vec3 point3_position;
                uniform vec3 point3_color;
                uniform float point3_intensity;
                uniform float point3_range;

                uniform bool spot0_enabled;
                uniform vec3 spot0_position;
                uniform vec3 spot0_direction;
                uniform vec3 spot0_color;
                uniform float spot0_intensity;
                uniform float spot0_range;
                uniform float spot0_inner_cos;
                uniform float spot0_outer_cos;
                uniform bool spot1_enabled;
                uniform vec3 spot1_position;
                uniform vec3 spot1_direction;
                uniform vec3 spot1_color;
                uniform float spot1_intensity;
                uniform float spot1_range;
                uniform float spot1_inner_cos;
                uniform float spot1_outer_cos;
                uniform bool spot2_enabled;
                uniform vec3 spot2_position;
                uniform vec3 spot2_direction;
                uniform vec3 spot2_color;
                uniform float spot2_intensity;
                uniform float spot2_range;
                uniform float spot2_inner_cos;
                uniform float spot2_outer_cos;
                uniform bool spot3_enabled;
                uniform vec3 spot3_position;
                uniform vec3 spot3_direction;
                uniform vec3 spot3_color;
                uniform float spot3_intensity;
                uniform float spot3_range;
                uniform float spot3_inner_cos;
                uniform float spot3_outer_cos;

                in vec3 v_normal;
                in vec3 v_world_pos;
                in vec2 v_uv;
                in vec4 v_instance_color;
                out vec4 fragColor;

                vec3 srgb_to_linear(vec3 value) {
                    vec3 low = value / 12.92;
                    vec3 high = pow((value + 0.055) / 1.055, vec3(2.4));
                    return mix(low, high, step(vec3(0.04045), value));
                }

                vec3 linear_to_srgb(vec3 value) {
                    value = max(value, vec3(0.0));
                    vec3 low = value * 12.92;
                    vec3 high = 1.055 * pow(value, vec3(1.0 / 2.4)) - 0.055;
                    return mix(low, high, step(vec3(0.0031308), value));
                }

                vec3 mapped_normal(vec3 base_normal) {
                    vec3 base = normalize(base_normal);
                    if (!pbr_enabled || !use_normal_texture) return base;
                    vec3 tangent_normal = texture(normal_image, v_uv).xyz * 2.0 - 1.0;
                    tangent_normal.xy *= normal_scale;
                    tangent_normal = normalize(tangent_normal);
                    vec3 dp1 = dFdx(v_world_pos);
                    vec3 dp2 = dFdy(v_world_pos);
                    vec2 duv1 = dFdx(v_uv);
                    vec2 duv2 = dFdy(v_uv);
                    vec3 tangent = dp1 * duv2.y - dp2 * duv1.y;
                    float tangent_length = length(tangent);
                    float determinant = duv1.x * duv2.y - duv1.y * duv2.x;
                    if (tangent_length <= 0.000001 || abs(determinant) <= 0.000001) return base;
                    tangent = tangent / tangent_length;
                    tangent = normalize(tangent - base * dot(base, tangent));
                    vec3 bitangent = normalize(cross(base, tangent));
                    if (determinant < 0.0) bitangent = -bitangent;
                    return normalize(mat3(tangent, bitangent, base) * tangent_normal);
                }

                float distribution_ggx(vec3 n, vec3 h, float roughness) {
                    float a = roughness * roughness;
                    float a2 = a * a;
                    float nh = max(dot(n, h), 0.0);
                    float d = nh * nh * (a2 - 1.0) + 1.0;
                    return a2 / max(PI * d * d, 0.000001);
                }

                float geometry_schlick(float nv, float roughness) {
                    float r = roughness + 1.0;
                    float k = (r * r) / 8.0;
                    return nv / max(nv * (1.0 - k) + k, 0.000001);
                }

                vec3 fresnel(float cos_theta, vec3 f0) {
                    return f0 + (1.0 - f0) * pow(clamp(1.0 - cos_theta, 0.0, 1.0), 5.0);
                }

                vec3 illuminate(
                    vec3 n,
                    vec3 view_dir,
                    vec3 light_dir,
                    vec3 light_color,
                    float power,
                    vec3 albedo,
                    float metallic,
                    float roughness
                ) {
                    float nl = max(dot(n, light_dir), 0.0);
                    if (nl <= 0.0) return vec3(0.0);
                    if (!pbr_enabled) {
                        vec3 reflected = reflect(-light_dir, n);
                        float spec = pow(max(dot(view_dir, reflected), 0.0), shininess);
                        return (
                            albedo * diffuse_strength * nl + vec3(specular_strength * spec)
                        ) * light_color * power;
                    }
                    float nv = max(dot(n, view_dir), 0.0);
                    if (nv <= 0.0) return vec3(0.0);
                    vec3 h = normalize(view_dir + light_dir);
                    vec3 f0 = mix(vec3(0.04), albedo, metallic);
                    vec3 f = fresnel(max(dot(h, view_dir), 0.0), f0);
                    float d = distribution_ggx(n, h, roughness);
                    float g = geometry_schlick(nv, roughness) * geometry_schlick(nl, roughness);
                    vec3 specular = d * g * f / max(4.0 * nv * nl, 0.001);
                    vec3 kd = (vec3(1.0) - f) * (1.0 - metallic);
                    return (kd * albedo / PI + specular) * light_color * power * nl;
                }

                float attenuation(float distance_to_light, float light_range) {
                    float ratio = clamp(distance_to_light / max(light_range, 0.0001), 0.0, 1.0);
                    float falloff = 1.0 - ratio * ratio;
                    return falloff * falloff;
                }

                vec3 directional(
                    vec3 n, vec3 v, vec3 a, float m, float r,
                    vec3 direction, vec3 color, float intensity
                ) {
                    return illuminate(n, v, normalize(-direction), color, intensity, a, m, r);
                }

                vec3 point(
                    vec3 n, vec3 v, vec3 a, float m, float r,
                    vec3 position, vec3 color, float intensity, float light_range
                ) {
                    vec3 delta = position - v_world_pos;
                    float distance_to_light = length(delta);
                    if (distance_to_light <= 0.0001) return vec3(0.0);
                    float power = intensity * attenuation(distance_to_light, light_range);
                    return illuminate(n, v, delta / distance_to_light, color, power, a, m, r);
                }

                vec3 spot(
                    vec3 n, vec3 v, vec3 a, float m, float r,
                    vec3 position, vec3 direction, vec3 color, float intensity,
                    float light_range, float inner_cos, float outer_cos
                ) {
                    vec3 delta = position - v_world_pos;
                    float distance_to_light = length(delta);
                    if (distance_to_light <= 0.0001) return vec3(0.0);
                    vec3 light_dir = delta / distance_to_light;
                    float theta = dot(-light_dir, normalize(direction));
                    float cone = smoothstep(outer_cos, inner_cos, theta);
                    float power = intensity * cone * attenuation(distance_to_light, light_range);
                    return illuminate(n, v, light_dir, color, power, a, m, r);
                }

                void main() {
                    vec4 surface_rgba = base_color * v_instance_color;
                    if (use_texture) {
                        vec4 sample_value = texture(image, v_uv);
                        if (pbr_enabled) sample_value.rgb = srgb_to_linear(sample_value.rgb);
                        surface_rgba *= sample_value;
                    }
                    float metallic = clamp(metallic_factor, 0.0, 1.0);
                    float roughness = clamp(roughness_factor, 0.04, 1.0);
                    if (pbr_enabled && use_metallic_roughness_texture) {
                        vec4 mr = texture(metallic_roughness_image, v_uv);
                        roughness = clamp(roughness * mr.g, 0.04, 1.0);
                        metallic = clamp(metallic * mr.b, 0.0, 1.0);
                    }
                    vec3 n = mapped_normal(v_normal);
                    vec3 v = normalize(view_position - v_world_pos);
                    float occlusion = 1.0;
                    if (pbr_enabled && use_occlusion_texture) {
                        float sampled = texture(occlusion_image, v_uv).r;
                        occlusion = mix(1.0, sampled, clamp(occlusion_strength, 0.0, 1.0));
                    }
                    vec3 albedo = surface_rgba.rgb;
                    vec3 lighting = albedo * ambient_strength * occlusion;

                    if (dir0_enabled) lighting += directional(n, v, albedo, metallic, roughness, dir0_direction, dir0_color, dir0_intensity);
                    if (dir1_enabled) lighting += directional(n, v, albedo, metallic, roughness, dir1_direction, dir1_color, dir1_intensity);
                    if (dir2_enabled) lighting += directional(n, v, albedo, metallic, roughness, dir2_direction, dir2_color, dir2_intensity);
                    if (dir3_enabled) lighting += directional(n, v, albedo, metallic, roughness, dir3_direction, dir3_color, dir3_intensity);

                    if (point0_enabled) lighting += point(n, v, albedo, metallic, roughness, point0_position, point0_color, point0_intensity, point0_range);
                    if (point1_enabled) lighting += point(n, v, albedo, metallic, roughness, point1_position, point1_color, point1_intensity, point1_range);
                    if (point2_enabled) lighting += point(n, v, albedo, metallic, roughness, point2_position, point2_color, point2_intensity, point2_range);
                    if (point3_enabled) lighting += point(n, v, albedo, metallic, roughness, point3_position, point3_color, point3_intensity, point3_range);

                    if (spot0_enabled) lighting += spot(n, v, albedo, metallic, roughness, spot0_position, spot0_direction, spot0_color, spot0_intensity, spot0_range, spot0_inner_cos, spot0_outer_cos);
                    if (spot1_enabled) lighting += spot(n, v, albedo, metallic, roughness, spot1_position, spot1_direction, spot1_color, spot1_intensity, spot1_range, spot1_inner_cos, spot1_outer_cos);
                    if (spot2_enabled) lighting += spot(n, v, albedo, metallic, roughness, spot2_position, spot2_direction, spot2_color, spot2_intensity, spot2_range, spot2_inner_cos, spot2_outer_cos);
                    if (spot3_enabled) lighting += spot(n, v, albedo, metallic, roughness, spot3_position, spot3_direction, spot3_color, spot3_intensity, spot3_range, spot3_inner_cos, spot3_outer_cos);

                    if (pbr_enabled) {
                        vec3 emissive = emissive_factor;
                        if (use_emissive_texture) {
                            emissive *= srgb_to_linear(texture(emissive_image, v_uv).rgb);
                        }
                        lighting += emissive;
                        lighting = linear_to_srgb(lighting);
                    }
                    fragColor = vec4(lighting, surface_rgba.a);
                }
            """,
        )
        self.program["image"].value = 0
        self.program["metallic_roughness_image"].value = 1
        self.program["normal_image"].value = 2
        self.program["occlusion_image"].value = 3
        self.program["emissive_image"].value = 4

    def _ensure_staging(self, count: int) -> None:
        if count <= len(self._staging):
            return
        capacity = len(self._staging)
        while capacity < count:
            capacity *= 2
        self._staging = np.empty((capacity, 20), dtype="f4")

    def _resource(self, batch: InstancedMesh3D, count: int) -> _GPUInstanceResource:
        key = id(batch.mesh)
        cached = self._resources.get(key)
        needed = max(1, count)
        if cached is not None and cached.capacity >= needed:
            return cached
        capacity = 1 if cached is None else cached.capacity
        while capacity < needed:
            capacity *= 2
        if cached is not None:
            cached.vao.release()
            cached.instance_vbo.release()
            mesh_vbo = cached.mesh_vbo
        else:
            mesh_data = batch.mesh.interleaved(include_uvs=True)
            mesh_vbo = self.ctx.buffer(mesh_data.tobytes())

        instance_vbo = self.ctx.buffer(reserve=capacity * 20 * np.dtype("f4").itemsize)
        vao = self.ctx.vertex_array(
            self.program,
            [
                (mesh_vbo, "3f 3f 2f", "in_pos", "in_normal", "in_uv"),
                (
                    instance_vbo,
                    "4f 4f 4f 4f 4f /i",
                    "in_model_0",
                    "in_model_1",
                    "in_model_2",
                    "in_model_3",
                    "in_instance_color",
                ),
            ],
        )
        resource = _GPUInstanceResource(
            mesh_vbo=mesh_vbo,
            instance_vbo=instance_vbo,
            vao=vao,
            capacity=capacity,
            vertex_count=batch.mesh.vertex_count,
        )
        self._resources[key] = resource
        if cached is None:
            self.owner.stats.mesh_uploads += 1
        return resource

    def _configure_material(self, batch: InstancedMesh3D) -> None:
        material = batch.material
        tint = material.tint.clamped() if material is not None else Color()
        color = batch.color.clamped()
        combined = Color(
            tint.r * color.r,
            tint.g * color.g,
            tint.b * color.b,
            tint.a * color.a,
        )
        self.program["base_color"].value = (combined.r, combined.g, combined.b, combined.a)
        self.program["ambient_strength"].value = float(material.ambient if material else 0.25)
        self.program["diffuse_strength"].value = float(material.diffuse if material else 0.75)
        self.program["specular_strength"].value = float(material.specular if material else 0.0)
        self.program["shininess"].value = float(material.shininess if material else 32.0)

        pbr = material is not None and material.pbr_enabled
        self.program["pbr_enabled"].value = pbr
        self.program["metallic_factor"].value = float(
            0.0 if material is None or material.metallic is None else material.metallic
        )
        self.program["roughness_factor"].value = float(
            0.5 if material is None or material.roughness is None else material.roughness
        )

        channels = (
            ("use_texture", None if material is None else material.texture, 0),
            (
                "use_metallic_roughness_texture",
                None if material is None else material.metallic_roughness_texture,
                1,
            ),
            ("use_normal_texture", None if material is None else material.normal_texture, 2),
            ("use_occlusion_texture", None if material is None else material.occlusion_texture, 3),
            ("use_emissive_texture", None if material is None else material.emissive_texture, 4),
        )
        for uniform, path, location in channels:
            enabled = path is not None and (uniform == "use_texture" or pbr)
            self.program[uniform].value = enabled
            if enabled and path is not None:
                texture, _, _ = self.owner._texture(path)
                texture.use(location=location)

        self.program["normal_scale"].value = float(material.normal_scale if material else 1.0)
        self.program["occlusion_strength"].value = float(
            material.occlusion_strength if material else 1.0
        )
        emissive = material.emissive_factor if material else Color(0.0, 0.0, 0.0, 1.0)
        self.program["emissive_factor"].value = (
            float(emissive.r),
            float(emissive.g),
            float(emissive.b),
        )

    def _configure_lights(self, scene: object, camera: Camera3D) -> None:
        selection = select_lights(getattr(scene, "objects", ()))
        self.program["view_position"].value = (
            float(camera.position.x),
            float(camera.position.y),
            float(camera.position.z),
        )
        for slot in range(MAX_DIRECTIONAL_LIGHTS):
            light = selection.directional[slot] if slot < len(selection.directional) else None
            self._set_directional(slot, light)
        for slot in range(MAX_POINT_LIGHTS):
            light = selection.point[slot] if slot < len(selection.point) else None
            self._set_point(slot, light)
        for slot in range(MAX_SPOT_LIGHTS):
            light = selection.spot[slot] if slot < len(selection.spot) else None
            self._set_spot(slot, light)

    def _set_directional(self, slot: int, light: DirectionalLight3D | None) -> None:
        prefix = f"dir{slot}"
        self.program[f"{prefix}_enabled"].value = light is not None
        if light is None:
            return
        direction = light.direction.normalized()
        color = light.color.clamped()
        self.program[f"{prefix}_direction"].value = (direction.x, direction.y, direction.z)
        self.program[f"{prefix}_color"].value = (color.r, color.g, color.b)
        self.program[f"{prefix}_intensity"].value = float(light.intensity)

    def _set_point(self, slot: int, light: PointLight3D | None) -> None:
        prefix = f"point{slot}"
        self.program[f"{prefix}_enabled"].value = light is not None
        if light is None:
            return
        color = light.color.clamped()
        self.program[f"{prefix}_position"].value = (
            light.position.x,
            light.position.y,
            light.position.z,
        )
        self.program[f"{prefix}_color"].value = (color.r, color.g, color.b)
        self.program[f"{prefix}_intensity"].value = float(light.intensity)
        self.program[f"{prefix}_range"].value = float(light.range)

    def _set_spot(self, slot: int, light: SpotLight3D | None) -> None:
        prefix = f"spot{slot}"
        self.program[f"{prefix}_enabled"].value = light is not None
        if light is None:
            return
        direction = light.direction.normalized()
        color = light.color.clamped()
        self.program[f"{prefix}_position"].value = (
            light.position.x,
            light.position.y,
            light.position.z,
        )
        self.program[f"{prefix}_direction"].value = (direction.x, direction.y, direction.z)
        self.program[f"{prefix}_color"].value = (color.r, color.g, color.b)
        self.program[f"{prefix}_intensity"].value = float(light.intensity)
        self.program[f"{prefix}_range"].value = float(light.range)
        self.program[f"{prefix}_inner_cos"].value = math.cos(math.radians(light.inner_angle))
        self.program[f"{prefix}_outer_cos"].value = math.cos(math.radians(light.outer_angle))

    def render(self, scene: object, camera: Camera3D) -> None:
        batches = [
            obj
            for obj in getattr(scene, "objects", ())
            if isinstance(obj, InstancedMesh3D) and obj.enabled and obj.visible
        ]
        if not batches:
            return
        projection = perspective(
            float(camera.fov),
            self.owner.width / max(1, self.owner.height),
            float(camera.near),
            float(camera.far),
        )
        view_projection = projection @ camera.view_matrix()
        self.owner._write_mat4(self.program["view_projection"], view_projection)
        self._configure_lights(scene, camera)
        frame_frustum = Frustum3D.from_view_projection(view_projection)

        self.ctx.enable(self.ctx.DEPTH_TEST)
        try:
            for batch in batches:
                self._ensure_staging(batch.instance_count)
                prepared = batch.prepare(view_projection, staging=self._staging, frustum=frame_frustum)
                diagnostics = prepared.diagnostics
                self.owner.stats.instance_candidates += diagnostics.active_instances
                self.owner.stats.instances_culled += diagnostics.culled_instances
                visible = diagnostics.visible_instances
                if visible == 0:
                    continue
                resource = self._resource(batch, visible)
                resource.instance_vbo.write(prepared.data)
                self._configure_material(batch)
                resource.vao.render(vertices=resource.vertex_count, instances=visible)
                self.owner.stats.draw_calls += 1
                self.owner.stats.instance_batches += 1
                self.owner.stats.instances += visible
                self.owner.stats.triangles += (resource.vertex_count // 3) * visible
        finally:
            self.ctx.disable(self.ctx.DEPTH_TEST)

    def release(self) -> None:
        for resource in self._resources.values():
            resource.vao.release()
            resource.instance_vbo.release()
            resource.mesh_vbo.release()
        self._resources.clear()
        self.program.release()
