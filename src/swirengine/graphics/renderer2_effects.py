from __future__ import annotations

import math
from collections.abc import Callable

import numpy as np

from ..math.types import perspective
from .camera3d import Camera3D
from .ibl_renderer import _read_context_state
from .mesh import Mesh3D, MeshData, cube_mesh
from .primitives import Cube3D
from .renderer2 import Decal3D, Renderer2Settings

_FULLSCREEN_VERTICES = np.asarray((-1.0, -1.0, 3.0, -1.0, -1.0, 3.0), dtype="f4")


def _write_mat4(uniform, matrix: np.ndarray) -> None:
    uniform.write(np.asarray(matrix, dtype="f4").T.tobytes())


class DepthNormalPrepass3D:
    """Depth + view-normal prepass sharing Renderer2's sampleable scene depth texture."""

    def __init__(self, ctx) -> None:
        self.ctx = ctx
        self._size = (0, 0)
        self._depth_identity = 0
        self.normal_texture = None
        self.framebuffer = None
        self._mesh_gpu: dict[int, tuple[object, object, int]] = {}
        self._cube_mesh = cube_mesh()
        self.program = self.ctx.program(
            vertex_shader="""
                #version 330
                in vec3 in_pos;
                in vec3 in_normal;
                uniform mat4 mvp;
                uniform mat4 view_model;
                out vec3 v_view_normal;
                void main() {
                    v_view_normal = normalize(
                        mat3(transpose(inverse(view_model))) * in_normal
                    );
                    gl_Position = mvp * vec4(in_pos, 1.0);
                }
            """,
            fragment_shader="""
                #version 330
                in vec3 v_view_normal;
                out vec4 fragColor;
                void main() {
                    vec3 encoded = normalize(v_view_normal) * 0.5 + 0.5;
                    fragColor = vec4(encoded, 1.0);
                }
            """,
        )

    def _release_target(self) -> None:
        if self.framebuffer is not None:
            self.framebuffer.release()
        if self.normal_texture is not None:
            self.normal_texture.release()
        self.framebuffer = None
        self.normal_texture = None
        self._size = (0, 0)
        self._depth_identity = 0

    def _ensure_target(self, size: tuple[int, int], depth_texture: object) -> None:
        identity = id(depth_texture)
        if (
            self.framebuffer is not None
            and self._size == size
            and self._depth_identity == identity
        ):
            return
        self._release_target()
        self.normal_texture = self.ctx.texture(size, 4, dtype="f2")
        self.normal_texture.filter = (self.ctx.NEAREST, self.ctx.NEAREST)
        self.normal_texture.repeat_x = False
        self.normal_texture.repeat_y = False
        self.framebuffer = self.ctx.framebuffer(
            color_attachments=[self.normal_texture],
            depth_attachment=depth_texture,
        )
        self._size = size
        self._depth_identity = identity

    def _gpu_mesh(self, mesh: MeshData) -> tuple[object, int]:
        key = id(mesh)
        cached = self._mesh_gpu.get(key)
        if cached is None:
            interleaved = mesh.interleaved(include_uvs=True).reshape((-1, 8))
            position_normal = np.ascontiguousarray(interleaved[:, :6], dtype="f4")
            vbo = self.ctx.buffer(position_normal.tobytes())
            vao = self.ctx.vertex_array(
                self.program,
                [(vbo, "3f 3f", "in_pos", "in_normal")],
            )
            cached = (vbo, vao, mesh.vertex_count)
            self._mesh_gpu[key] = cached
        return cached[1], cached[2]

    def _geometry(self, obj: object) -> tuple[MeshData, np.ndarray] | None:
        if isinstance(obj, Mesh3D):
            return obj.mesh, obj.transform.matrix()
        if isinstance(obj, Cube3D):
            return self._cube_mesh, obj.transform.matrix()
        return None

    def render(
        self,
        scene: object,
        camera: Camera3D,
        *,
        width: int,
        height: int,
        depth_texture: object,
    ) -> int:
        size = (int(width), int(height))
        self._ensure_target(size, depth_texture)
        assert self.framebuffer is not None
        self.framebuffer.use()
        self.ctx.viewport = (0, 0, size[0], size[1])
        self.framebuffer.clear(0.5, 0.5, 1.0, 0.0, depth=1.0)
        previous_depth_func = _read_context_state(self.ctx, "depth_func", "<")
        previous_depth_mask = _read_context_state(self.ctx, "depth_mask", True)
        self.ctx.enable(self.ctx.DEPTH_TEST)
        self.ctx.depth_func = "<"
        self.ctx.depth_mask = True
        projection = perspective(
            float(camera.fov),
            float(width) / max(1.0, float(height)),
            float(camera.near),
            float(camera.far),
        )
        view = camera.view_matrix()
        view_projection = projection @ view
        draws = 0
        try:
            for obj in getattr(scene, "objects", ()):
                if not getattr(obj, "enabled", True) or not getattr(obj, "visible", True):
                    continue
                geometry = self._geometry(obj)
                if geometry is None:
                    continue
                mesh, model = geometry
                vao, count = self._gpu_mesh(mesh)
                _write_mat4(self.program["mvp"], view_projection @ model)
                _write_mat4(self.program["view_model"], view @ model)
                vao.render(vertices=count)
                draws += 1
        finally:
            self.ctx.depth_mask = previous_depth_mask
            self.ctx.depth_func = previous_depth_func
            self.ctx.disable(self.ctx.DEPTH_TEST)
        return draws

    def release(self) -> None:
        self._release_target()
        for vbo, vao, _ in self._mesh_gpu.values():
            vao.release()
            vbo.release()
        self._mesh_gpu.clear()
        self.program.release()


class SSAOPass3D:
    """Depth/normal SSAO with deterministic kernel and depth-aware 3x3 blur."""

    _TEXTURE_DEPTH = 0
    _TEXTURE_NORMAL = 1
    _TEXTURE_AO = 2

    def __init__(self, ctx) -> None:
        self.ctx = ctx
        self._size = (0, 0)
        self._ao_texture = None
        self._blur_texture = None
        self._ao_framebuffer = None
        self._blur_framebuffer = None
        self._released = False
        self.program = self.ctx.program(
            vertex_shader="""
                #version 330
                in vec2 in_pos;
                out vec2 v_uv;
                void main() {
                    v_uv = in_pos * 0.5 + 0.5;
                    gl_Position = vec4(in_pos, 0.0, 1.0);
                }
            """,
            fragment_shader="""
                #version 330
                uniform sampler2D depth_image;
                uniform sampler2D normal_image;
                uniform mat4 inverse_projection;
                uniform vec2 samples[64];
                uniform int sample_count;
                uniform float radius;
                uniform float power_value;
                uniform float bias;
                in vec2 v_uv;
                out float fragAO;

                vec3 view_position(vec2 uv, float depth) {
                    vec4 clip = vec4(uv * 2.0 - 1.0, depth * 2.0 - 1.0, 1.0);
                    vec4 view = inverse_projection * clip;
                    return view.xyz / max(abs(view.w), 0.000001);
                }

                void main() {
                    float center_depth = texture(depth_image, v_uv).r;
                    vec4 normal_sample = texture(normal_image, v_uv);
                    if (center_depth >= 0.999999 || normal_sample.a < 0.5) {
                        fragAO = 1.0;
                        return;
                    }
                    vec3 center = view_position(v_uv, center_depth);
                    vec3 normal = normalize(normal_sample.xyz * 2.0 - 1.0);
                    float depth_scale = radius / max(-center.z, 0.35);
                    float occlusion = 0.0;
                    for (int i = 0; i < 64; ++i) {
                        if (i >= sample_count) break;
                        vec2 sample_uv = v_uv + samples[i] * depth_scale * 0.12;
                        if (any(lessThan(sample_uv, vec2(0.0)))
                            || any(greaterThan(sample_uv, vec2(1.0)))) {
                            continue;
                        }
                        float sample_depth = texture(depth_image, sample_uv).r;
                        if (sample_depth >= 0.999999) continue;
                        vec3 sample_position = view_position(sample_uv, sample_depth);
                        vec3 delta = sample_position - center;
                        float distance_to_sample = length(delta);
                        if (distance_to_sample <= 0.00001 || distance_to_sample > radius) continue;
                        float facing = max(dot(normal, delta / distance_to_sample), 0.0);
                        float range_weight = 1.0 - smoothstep(radius * 0.25, radius, distance_to_sample);
                        float blocked = sample_position.z >= center.z + bias ? 1.0 : 0.0;
                        occlusion += blocked * facing * range_weight;
                    }
                    float normalized = occlusion / max(float(sample_count), 1.0);
                    fragAO = pow(clamp(1.0 - normalized * 2.0, 0.0, 1.0), power_value);
                }
            """,
        )
        self.blur_program = self.ctx.program(
            vertex_shader="""
                #version 330
                in vec2 in_pos;
                out vec2 v_uv;
                void main() {
                    v_uv = in_pos * 0.5 + 0.5;
                    gl_Position = vec4(in_pos, 0.0, 1.0);
                }
            """,
            fragment_shader="""
                #version 330
                uniform sampler2D ao_image;
                uniform sampler2D depth_image;
                uniform sampler2D normal_image;
                uniform vec2 inverse_resolution;
                in vec2 v_uv;
                out float fragAO;
                void main() {
                    float center_depth = texture(depth_image, v_uv).r;
                    float center_valid = texture(normal_image, v_uv).a;
                    if (center_depth >= 0.999999 || center_valid < 0.5) {
                        fragAO = 1.0;
                        return;
                    }
                    float total = 0.0;
                    float weight_sum = 0.0;
                    for (int x = -1; x <= 1; ++x) {
                        for (int y = -1; y <= 1; ++y) {
                            vec2 uv = v_uv + vec2(float(x), float(y)) * inverse_resolution;
                            if (texture(normal_image, uv).a < 0.5) continue;
                            float depth = texture(depth_image, uv).r;
                            float depth_weight = exp(-abs(depth - center_depth) * 180.0);
                            float spatial = (x == 0 && y == 0) ? 2.0 : 1.0;
                            float weight = depth_weight * spatial;
                            total += texture(ao_image, uv).r * weight;
                            weight_sum += weight;
                        }
                    }
                    fragAO = total / max(weight_sum, 0.000001);
                }
            """,
        )
        self.program["depth_image"].value = self._TEXTURE_DEPTH
        self.program["normal_image"].value = self._TEXTURE_NORMAL
        self.blur_program["ao_image"].value = self._TEXTURE_AO
        self.blur_program["depth_image"].value = self._TEXTURE_DEPTH
        self.blur_program["normal_image"].value = self._TEXTURE_NORMAL
        vertices = self.ctx.buffer(_FULLSCREEN_VERTICES.tobytes())
        self._vbo = vertices
        self._vao = self.ctx.simple_vertex_array(self.program, vertices, "in_pos")
        self._blur_vao = self.ctx.simple_vertex_array(self.blur_program, vertices, "in_pos")
        kernel = []
        golden_angle = math.pi * (3.0 - math.sqrt(5.0))
        for index in range(64):
            radius = math.sqrt((index + 0.5) / 64.0)
            angle = index * golden_angle
            kernel.extend((math.cos(angle) * radius, math.sin(angle) * radius))
        self.program["samples"].write(np.asarray(kernel, dtype="f4").tobytes())

    @property
    def texture(self):
        return self._blur_texture

    def _release_targets(self) -> None:
        for resource in (
            self._ao_framebuffer,
            self._blur_framebuffer,
            self._ao_texture,
            self._blur_texture,
        ):
            if resource is not None:
                resource.release()
        self._ao_framebuffer = None
        self._blur_framebuffer = None
        self._ao_texture = None
        self._blur_texture = None
        self._size = (0, 0)

    def _ensure_targets(self, size: tuple[int, int]) -> None:
        if self._ao_framebuffer is not None and self._size == size:
            return
        self._release_targets()
        self._ao_texture = self.ctx.texture(size, 1, dtype="f1")
        self._blur_texture = self.ctx.texture(size, 1, dtype="f1")
        for texture in (self._ao_texture, self._blur_texture):
            texture.filter = (self.ctx.LINEAR, self.ctx.LINEAR)
            texture.repeat_x = False
            texture.repeat_y = False
        self._ao_framebuffer = self.ctx.framebuffer(color_attachments=[self._ao_texture])
        self._blur_framebuffer = self.ctx.framebuffer(color_attachments=[self._blur_texture])
        self._size = size

    def render(
        self,
        *,
        depth_texture: object,
        normal_texture: object,
        camera: Camera3D,
        width: int,
        height: int,
        settings: Renderer2Settings,
    ):
        if self._released:
            raise RuntimeError("SSAO pass has been released")
        size = (int(width), int(height))
        self._ensure_targets(size)
        projection = perspective(
            float(camera.fov),
            float(width) / max(1.0, float(height)),
            float(camera.near),
            float(camera.far),
        )
        inverse_projection = np.linalg.inv(projection).astype("f4")
        depth_texture.use(location=self._TEXTURE_DEPTH)
        normal_texture.use(location=self._TEXTURE_NORMAL)
        _write_mat4(self.program["inverse_projection"], inverse_projection)
        self.program["sample_count"].value = int(settings.ssao_samples)
        self.program["radius"].value = float(settings.ssao_radius)
        self.program["power_value"].value = float(settings.ssao_power)
        self.program["bias"].value = 0.02
        assert self._ao_framebuffer is not None
        self._ao_framebuffer.use()
        self.ctx.viewport = (0, 0, size[0], size[1])
        self.ctx.disable(self.ctx.DEPTH_TEST)
        self._vao.render(vertices=3)

        assert self._ao_texture is not None
        assert self._blur_framebuffer is not None
        self._ao_texture.use(location=self._TEXTURE_AO)
        depth_texture.use(location=self._TEXTURE_DEPTH)
        normal_texture.use(location=self._TEXTURE_NORMAL)
        self.blur_program["inverse_resolution"].value = (
            1.0 / max(1, size[0]),
            1.0 / max(1, size[1]),
        )
        self._blur_framebuffer.use()
        self._blur_vao.render(vertices=3)
        return self._blur_texture

    def release(self) -> None:
        if self._released:
            return
        self._release_targets()
        self._vao.release()
        self._blur_vao.release()
        self._vbo.release()
        self.program.release()
        self.blur_program.release()
        self._released = True


class BloomPass3D:
    """HDR bright extraction with deterministic downsample/upsample mip chain."""

    def __init__(self, ctx) -> None:
        self.ctx = ctx
        self._size = (0, 0)
        self._levels = 0
        self._textures: list[object] = []
        self._framebuffers: list[object] = []
        self._released = False
        vertex = """
            #version 330
            in vec2 in_pos;
            out vec2 v_uv;
            void main() {
                v_uv = in_pos * 0.5 + 0.5;
                gl_Position = vec4(in_pos, 0.0, 1.0);
            }
        """
        self.extract_program = self.ctx.program(
            vertex_shader=vertex,
            fragment_shader="""
                #version 330
                uniform sampler2D source_image;
                uniform float threshold;
                in vec2 v_uv;
                out vec4 fragColor;
                void main() {
                    vec3 color = texture(source_image, v_uv).rgb;
                    float brightness = max(max(color.r, color.g), color.b);
                    float contribution = max(brightness - threshold, 0.0) / max(brightness, 0.00001);
                    fragColor = vec4(color * contribution, 1.0);
                }
            """,
        )
        self.down_program = self.ctx.program(
            vertex_shader=vertex,
            fragment_shader="""
                #version 330
                uniform sampler2D source_image;
                in vec2 v_uv;
                out vec4 fragColor;
                void main() {
                    vec2 texel = 1.0 / vec2(textureSize(source_image, 0));
                    vec3 color = vec3(0.0);
                    color += texture(source_image, v_uv + texel * vec2(-0.5, -0.5)).rgb;
                    color += texture(source_image, v_uv + texel * vec2( 0.5, -0.5)).rgb;
                    color += texture(source_image, v_uv + texel * vec2(-0.5,  0.5)).rgb;
                    color += texture(source_image, v_uv + texel * vec2( 0.5,  0.5)).rgb;
                    fragColor = vec4(color * 0.25, 1.0);
                }
            """,
        )
        self.up_program = self.ctx.program(
            vertex_shader=vertex,
            fragment_shader="""
                #version 330
                uniform sampler2D source_image;
                in vec2 v_uv;
                out vec4 fragColor;
                void main() {
                    vec2 texel = 1.0 / vec2(textureSize(source_image, 0));
                    vec3 color = texture(source_image, v_uv).rgb * 4.0;
                    color += texture(source_image, v_uv + texel * vec2(1.0, 0.0)).rgb;
                    color += texture(source_image, v_uv + texel * vec2(-1.0, 0.0)).rgb;
                    color += texture(source_image, v_uv + texel * vec2(0.0, 1.0)).rgb;
                    color += texture(source_image, v_uv + texel * vec2(0.0, -1.0)).rgb;
                    fragColor = vec4(color * 0.125, 1.0);
                }
            """,
        )
        for program in (self.extract_program, self.down_program, self.up_program):
            program["source_image"].value = 0
        self._vbo = self.ctx.buffer(_FULLSCREEN_VERTICES.tobytes())
        self._extract_vao = self.ctx.simple_vertex_array(
            self.extract_program, self._vbo, "in_pos"
        )
        self._down_vao = self.ctx.simple_vertex_array(self.down_program, self._vbo, "in_pos")
        self._up_vao = self.ctx.simple_vertex_array(self.up_program, self._vbo, "in_pos")

    @property
    def texture(self):
        return self._textures[0] if self._textures else None

    def _release_targets(self) -> None:
        for framebuffer in self._framebuffers:
            framebuffer.release()
        for texture in self._textures:
            texture.release()
        self._framebuffers.clear()
        self._textures.clear()
        self._size = (0, 0)
        self._levels = 0

    def _ensure_targets(self, size: tuple[int, int], levels: int) -> None:
        if self._textures and self._size == size and self._levels == levels:
            return
        self._release_targets()
        width, height = size
        for index in range(levels):
            divisor = 2 ** (index + 1)
            level_size = (max(1, width // divisor), max(1, height // divisor))
            texture = self.ctx.texture(level_size, 4, dtype="f2")
            texture.filter = (self.ctx.LINEAR, self.ctx.LINEAR)
            texture.repeat_x = False
            texture.repeat_y = False
            framebuffer = self.ctx.framebuffer(color_attachments=[texture])
            self._textures.append(texture)
            self._framebuffers.append(framebuffer)
        self._size = size
        self._levels = levels

    def render(
        self,
        source_texture: object,
        *,
        width: int,
        height: int,
        settings: Renderer2Settings,
    ):
        if self._released:
            raise RuntimeError("bloom pass has been released")
        levels = int(settings.bloom_levels)
        self._ensure_targets((int(width), int(height)), levels)
        self.ctx.disable(self.ctx.DEPTH_TEST)
        source_texture.use(location=0)
        self.extract_program["threshold"].value = float(settings.bloom_threshold)
        self._framebuffers[0].use()
        self.ctx.viewport = (0, 0, *self._textures[0].size)
        self._extract_vao.render(vertices=3)

        for index in range(1, levels):
            self._textures[index - 1].use(location=0)
            self._framebuffers[index].use()
            self.ctx.viewport = (0, 0, *self._textures[index].size)
            self._down_vao.render(vertices=3)

        self.ctx.enable(self.ctx.BLEND)
        self.ctx.blend_func = self.ctx.ONE, self.ctx.ONE
        try:
            for index in range(levels - 1, 0, -1):
                self._textures[index].use(location=0)
                self._framebuffers[index - 1].use()
                self.ctx.viewport = (0, 0, *self._textures[index - 1].size)
                self._up_vao.render(vertices=3)
        finally:
            self.ctx.disable(self.ctx.BLEND)
        return self._textures[0]

    def release(self) -> None:
        if self._released:
            return
        self._release_targets()
        self._extract_vao.release()
        self._down_vao.release()
        self._up_vao.release()
        self._vbo.release()
        self.extract_program.release()
        self.down_program.release()
        self.up_program.release()
        self._released = True


class DecalPass3D:
    """Screen-space decal projection into the HDR scene color using reconstructed world depth."""

    def __init__(self, ctx) -> None:
        self.ctx = ctx
        self._color_identity = 0
        self.framebuffer = None
        self.program = self.ctx.program(
            vertex_shader="""
                #version 330
                in vec2 in_pos;
                out vec2 v_uv;
                void main() {
                    v_uv = in_pos * 0.5 + 0.5;
                    gl_Position = vec4(in_pos, 0.0, 1.0);
                }
            """,
            fragment_shader="""
                #version 330
                uniform sampler2D depth_image;
                uniform sampler2D decal_image;
                uniform bool use_texture;
                uniform mat4 inverse_view_projection;
                uniform vec3 decal_position;
                uniform vec3 decal_size;
                uniform vec4 decal_color;
                uniform float opacity_value;
                in vec2 v_uv;
                out vec4 fragColor;

                void main() {
                    float depth = texture(depth_image, v_uv).r;
                    if (depth >= 0.999999) discard;
                    vec4 clip = vec4(v_uv * 2.0 - 1.0, depth * 2.0 - 1.0, 1.0);
                    vec4 world = inverse_view_projection * clip;
                    world /= max(abs(world.w), 0.000001);
                    vec3 local = (world.xyz - decal_position) / decal_size;
                    vec3 absolute_local = abs(local);
                    if (any(greaterThan(absolute_local, vec3(0.5)))) discard;
                    vec2 decal_uv = local.xz + 0.5;
                    vec4 sampled = use_texture ? texture(decal_image, decal_uv) : vec4(1.0);
                    float edge = max(max(absolute_local.x, absolute_local.y), absolute_local.z);
                    float edge_fade = 1.0 - smoothstep(0.42, 0.5, edge);
                    vec4 color = sampled * decal_color;
                    color.a *= opacity_value * edge_fade;
                    if (color.a <= 0.0001) discard;
                    fragColor = color;
                }
            """,
        )
        self.program["depth_image"].value = 0
        self.program["decal_image"].value = 1
        self._vbo = self.ctx.buffer(_FULLSCREEN_VERTICES.tobytes())
        self._vao = self.ctx.simple_vertex_array(self.program, self._vbo, "in_pos")

    def _ensure_framebuffer(self, color_texture: object) -> None:
        identity = id(color_texture)
        if self.framebuffer is not None and self._color_identity == identity:
            return
        if self.framebuffer is not None:
            self.framebuffer.release()
        self.framebuffer = self.ctx.framebuffer(color_attachments=[color_texture])
        self._color_identity = identity

    def render(
        self,
        decals: tuple[Decal3D, ...],
        *,
        color_texture: object,
        depth_texture: object,
        camera: Camera3D,
        width: int,
        height: int,
        texture_loader: Callable[[str], object],
    ) -> int:
        if not decals:
            return 0
        self._ensure_framebuffer(color_texture)
        assert self.framebuffer is not None
        projection = perspective(
            float(camera.fov),
            float(width) / max(1.0, float(height)),
            float(camera.near),
            float(camera.far),
        )
        inverse_view_projection = np.linalg.inv(projection @ camera.view_matrix()).astype("f4")
        _write_mat4(self.program["inverse_view_projection"], inverse_view_projection)
        depth_texture.use(location=0)
        self.framebuffer.use()
        self.ctx.viewport = (0, 0, int(width), int(height))
        self.ctx.disable(self.ctx.DEPTH_TEST)
        self.ctx.enable(self.ctx.BLEND)
        self.ctx.blend_func = self.ctx.SRC_ALPHA, self.ctx.ONE_MINUS_SRC_ALPHA
        draws = 0
        try:
            for decal in decals:
                color = decal.color.clamped()
                self.program["decal_position"].value = (
                    float(decal.position.x),
                    float(decal.position.y),
                    float(decal.position.z),
                )
                self.program["decal_size"].value = (
                    float(decal.size.x),
                    float(decal.size.y),
                    float(decal.size.z),
                )
                self.program["decal_color"].value = (
                    float(color.r),
                    float(color.g),
                    float(color.b),
                    float(color.a),
                )
                self.program["opacity_value"].value = float(decal.opacity)
                self.program["use_texture"].value = decal.texture is not None
                if decal.texture is not None:
                    texture_loader(decal.texture).use(location=1)
                self._vao.render(vertices=3)
                draws += 1
        finally:
            self.ctx.disable(self.ctx.BLEND)
        return draws

    def release(self) -> None:
        if self.framebuffer is not None:
            self.framebuffer.release()
            self.framebuffer = None
        self._vao.release()
        self._vbo.release()
        self.program.release()
