from __future__ import annotations

from pathlib import Path
from typing import Any

from ..math.types import Color, perspective
from .camera3d import Camera3D
from .cubemap import CubemapGPUTexture, ImageBasedEnvironment3D
from .material import Material3D
from .mesh import Mesh3D
from .postprocess import PostProcessRenderer


class ImageBasedPostProcessRenderer(PostProcessRenderer):
    """Post-process renderer with an additive cubemap IBL pass for PBR meshes.

    Direct lights remain handled by :class:`Renderer`; this pass adds image-based diffuse
    and roughness-dependent specular lighting sourced from the first enabled
    :class:`ImageBasedEnvironment3D` in the scene. Keeping the pass additive preserves the
    existing 0.4 rendering contract while enabling real ``samplerCube`` lighting.
    """

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        self._ibl_cubemaps: dict[tuple[str, ...], CubemapGPUTexture] = {}
        self._ibl_vaos: dict[int, object] = {}
        super().__init__(*args, **kwargs)
        self._init_ibl_pass()

    def _init_ibl_pass(self) -> None:
        self.ibl_program = self.ctx.program(
            vertex_shader="""
                #version 330
                in vec3 in_pos;
                in vec3 in_normal;
                in vec2 in_uv;
                uniform mat4 mvp;
                uniform mat4 model;
                out vec3 v_normal;
                out vec3 v_world_pos;
                out vec2 v_uv;
                void main() {
                    vec4 world = model * vec4(in_pos, 1.0);
                    gl_Position = mvp * vec4(in_pos, 1.0);
                    v_world_pos = world.xyz;
                    v_normal = mat3(transpose(inverse(model))) * in_normal;
                    v_uv = in_uv;
                }
            """,
            fragment_shader="""
                #version 330
                uniform samplerCube environment_map;
                uniform sampler2D base_image;
                uniform sampler2D metallic_roughness_image;
                uniform sampler2D normal_image;
                uniform sampler2D occlusion_image;
                uniform bool use_base_texture;
                uniform bool use_metallic_roughness_texture;
                uniform bool use_normal_texture;
                uniform bool use_occlusion_texture;
                uniform vec4 base_color;
                uniform float metallic_factor;
                uniform float roughness_factor;
                uniform float normal_scale;
                uniform float occlusion_strength;
                uniform vec3 view_position;
                uniform float environment_intensity;
                uniform float diffuse_strength;
                uniform float specular_strength;
                uniform float max_specular_lod;
                in vec3 v_normal;
                in vec3 v_world_pos;
                in vec2 v_uv;
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
                    if (!use_normal_texture) return base;
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
                    tangent = normalize(tangent / tangent_length - base * dot(base, tangent / tangent_length));
                    vec3 bitangent = normalize(cross(base, tangent));
                    if (determinant < 0.0) bitangent = -bitangent;
                    return normalize(mat3(tangent, bitangent, base) * tangent_normal);
                }

                vec3 fresnel_schlick_roughness(float cos_theta, vec3 f0, float roughness) {
                    return f0 + (max(vec3(1.0 - roughness), f0) - f0)
                        * pow(clamp(1.0 - cos_theta, 0.0, 1.0), 5.0);
                }

                void main() {
                    vec3 albedo = base_color.rgb;
                    if (use_base_texture) {
                        albedo *= srgb_to_linear(texture(base_image, v_uv).rgb);
                    }
                    float metallic = clamp(metallic_factor, 0.0, 1.0);
                    float roughness = clamp(roughness_factor, 0.04, 1.0);
                    if (use_metallic_roughness_texture) {
                        vec4 material_sample = texture(metallic_roughness_image, v_uv);
                        roughness = clamp(roughness * material_sample.g, 0.04, 1.0);
                        metallic = clamp(metallic * material_sample.b, 0.0, 1.0);
                    }
                    float occlusion = 1.0;
                    if (use_occlusion_texture) {
                        float sampled = texture(occlusion_image, v_uv).r;
                        occlusion = mix(1.0, sampled, clamp(occlusion_strength, 0.0, 1.0));
                    }

                    vec3 normal = mapped_normal(v_normal);
                    vec3 view_dir = normalize(view_position - v_world_pos);
                    vec3 reflection = reflect(-view_dir, normal);
                    vec3 f0 = mix(vec3(0.04), albedo, metallic);
                    vec3 fresnel = fresnel_schlick_roughness(
                        max(dot(normal, view_dir), 0.0), f0, roughness
                    );
                    vec3 k_d = (vec3(1.0) - fresnel) * (1.0 - metallic);

                    // The coarsest generated cubemap mip is a stable low-frequency diffuse probe.
                    vec3 irradiance = srgb_to_linear(textureLod(
                        environment_map, normal, max(max_specular_lod, 0.0)
                    ).rgb);
                    vec3 diffuse = irradiance * albedo * k_d * diffuse_strength;

                    float lod = roughness * max(max_specular_lod, 0.0);
                    vec3 prefiltered = srgb_to_linear(textureLod(environment_map, reflection, lod).rgb);
                    vec3 specular = prefiltered * fresnel * specular_strength;
                    vec3 result = (diffuse + specular) * environment_intensity * occlusion;
                    fragColor = vec4(linear_to_srgb(result), base_color.a);
                }
            """,
        )
        self.ibl_program["environment_map"].value = 5
        self.ibl_program["base_image"].value = 0
        self.ibl_program["metallic_roughness_image"].value = 1
        self.ibl_program["normal_image"].value = 2
        self.ibl_program["occlusion_image"].value = 3

    @staticmethod
    def _environment(scene: object) -> ImageBasedEnvironment3D | None:
        for obj in getattr(scene, "objects", ()):
            if isinstance(obj, ImageBasedEnvironment3D) and obj.enabled:
                return obj
        return None

    @staticmethod
    def _environment_key(environment: ImageBasedEnvironment3D) -> tuple[str, ...]:
        return tuple(str(path.resolve()) for path in environment.cubemap.paths())

    def _cubemap(self, environment: ImageBasedEnvironment3D) -> CubemapGPUTexture:
        key = self._environment_key(environment)
        cached = self._ibl_cubemaps.get(key)
        if cached is not None and not cached.released:
            return cached
        resource = environment.upload(self.ctx, build_mipmaps=True)
        if hasattr(resource.texture, "filter"):
            resource.texture.filter = (self.ctx.LINEAR_MIPMAP_LINEAR, self.ctx.LINEAR)
        self._ibl_cubemaps[key] = resource
        self.stats.texture_uploads += 1
        return resource

    def invalidate_cubemap(self, path: str | Path) -> bool:
        """Release every cached environment containing ``path`` for live reload."""
        resolved = str(Path(path).expanduser().resolve())
        keys = [key for key in self._ibl_cubemaps if resolved in key]
        for key in keys:
            self._ibl_cubemaps.pop(key).release()
        return bool(keys)

    def _ibl_vao(self, obj: Mesh3D) -> tuple[object, int]:
        key = id(obj.mesh)
        _base_vao, count = self._gpu_mesh(obj)
        cached = self._ibl_vaos.get(key)
        if cached is None:
            vbo, _vao, _count = self._mesh_gpu[key]
            cached = self.ctx.vertex_array(
                self.ibl_program,
                [(vbo, "3f 3f 2f", "in_pos", "in_normal", "in_uv")],
            )
            self._ibl_vaos[key] = cached
        return cached, count

    def _configure_ibl_material(self, material: Material3D, color: Color) -> None:
        tint = material.tint.clamped()
        instance = color.clamped()
        self.ibl_program["base_color"].value = (
            float(tint.r * instance.r),
            float(tint.g * instance.g),
            float(tint.b * instance.b),
            float(tint.a * instance.a),
        )
        self.ibl_program["metallic_factor"].value = float(material.metallic or 0.0)
        self.ibl_program["roughness_factor"].value = float(
            0.5 if material.roughness is None else material.roughness
        )
        self.ibl_program["normal_scale"].value = float(material.normal_scale)
        self.ibl_program["occlusion_strength"].value = float(material.occlusion_strength)

        channels = (
            ("use_base_texture", material.texture, 0),
            ("use_metallic_roughness_texture", material.metallic_roughness_texture, 1),
            ("use_normal_texture", material.normal_texture, 2),
            ("use_occlusion_texture", material.occlusion_texture, 3),
        )
        for uniform, path, location in channels:
            self.ibl_program[uniform].value = path is not None
            if path is not None:
                texture, _, _ = self._texture(path)
                texture.use(location=location)

    def _render_ibl(self, scene: object, camera: Camera3D) -> None:
        environment = self._environment(scene)
        if environment is None or environment.intensity <= 0.0:
            return
        meshes = [
            obj
            for obj in getattr(scene, "objects", ())
            if isinstance(obj, Mesh3D)
            and obj.enabled
            and obj.visible
            and obj.material is not None
            and obj.material.pbr_enabled
        ]
        if not meshes:
            return

        cubemap = self._cubemap(environment)
        cubemap.use(location=5)
        self.ibl_program["view_position"].value = (
            float(camera.position.x),
            float(camera.position.y),
            float(camera.position.z),
        )
        self.ibl_program["environment_intensity"].value = float(environment.intensity)
        self.ibl_program["diffuse_strength"].value = float(environment.diffuse_strength)
        self.ibl_program["specular_strength"].value = float(environment.specular_strength)
        self.ibl_program["max_specular_lod"].value = float(environment.max_specular_lod)

        projection = perspective(
            float(camera.fov),
            self.width / max(1, self.height),
            float(camera.near),
            float(camera.far),
        )
        view_projection = projection @ camera.view_matrix()
        previous_depth_func = getattr(self.ctx, "depth_func", None)
        previous_depth_mask = getattr(self.ctx, "depth_mask", None)
        self.ctx.enable(self.ctx.DEPTH_TEST)
        self.ctx.enable(self.ctx.BLEND)
        self.ctx.blend_func = self.ctx.ONE, self.ctx.ONE
        if previous_depth_func is not None:
            self.ctx.depth_func = "<="
        if previous_depth_mask is not None:
            self.ctx.depth_mask = False
        try:
            for obj in meshes:
                material = obj.material
                assert material is not None
                vao, count = self._ibl_vao(obj)
                model = obj.transform.matrix()
                self._write_mat4(self.ibl_program["model"], model)
                self._write_mat4(self.ibl_program["mvp"], view_projection @ model)
                self._configure_ibl_material(material, obj.color)
                vao.render(vertices=count)
                self.stats.draw_calls += 1
                self.stats.triangles += count // 3
        finally:
            if previous_depth_mask is not None:
                self.ctx.depth_mask = previous_depth_mask
            if previous_depth_func is not None:
                self.ctx.depth_func = previous_depth_func
            self.ctx.disable(self.ctx.BLEND)
            self.ctx.disable(self.ctx.DEPTH_TEST)

    def _render_3d(self, scene: object, camera: Camera3D) -> None:
        super()._render_3d(scene, camera)
        self._render_ibl(scene, camera)

    def release(self) -> None:
        for resource in self._ibl_cubemaps.values():
            resource.release()
        self._ibl_cubemaps.clear()
        for vao in self._ibl_vaos.values():
            vao.release()
        self._ibl_vaos.clear()
        self.ibl_program.release()
        super().release()
