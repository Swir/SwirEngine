from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np

from .camera3d import Camera3D
from .ibl_renderer import _read_context_state
from .lights import DirectionalLight3D, select_lights
from .mesh import Mesh3D, MeshData, cube_mesh
from .postprocess import PostProcessSettings
from .primitives import Cube3D
from .renderer import Renderer
from .renderer2 import (
    CascadedShadowPlan3D,
    Renderer2FramePlan,
    Renderer2Planner,
    Renderer2Settings,
    build_cascaded_shadow_plan,
)
from .renderer2_effects import BloomPass3D, DecalPass3D, DepthNormalPrepass3D, SSAOPass3D
from .shadow_renderer import ShadowedImageBasedPostProcessRenderer
from .shadows import DirectionalShadowFrame, DirectionalShadowSettings, directional_shadow_frame


@dataclass(frozen=True, slots=True)
class CascadedShadowFrame3D:
    plan: CascadedShadowPlan3D
    light_frames: tuple[DirectionalShadowFrame, ...]


class CascadedDirectionalShadowMap:
    """Up to four GPU depth maps driven by the deterministic Renderer 2.0 CSM plan."""

    def __init__(self, ctx, settings: Renderer2Settings | None = None) -> None:
        self.ctx = ctx
        self.settings = settings or Renderer2Settings()
        self._targets: list[tuple[object, object]] = []
        self._mesh_gpu: dict[int, tuple[object, object, int]] = {}
        self._cube_mesh = cube_mesh()
        self._released = False
        self.program = self.ctx.program(
            vertex_shader="""
                #version 330
                in vec3 in_pos;
                uniform mat4 light_mvp;
                void main() {
                    gl_Position = light_mvp * vec4(in_pos, 1.0);
                }
            """,
            fragment_shader="""
                #version 330
                void main() {}
            """,
        )

    @property
    def cascade_count(self) -> int:
        return int(self.settings.shadow_cascades)

    @staticmethod
    def _write_mat4(uniform, matrix: np.ndarray) -> None:
        uniform.write(np.asarray(matrix, dtype="f4").T.tobytes())

    def _ensure_targets(self) -> None:
        required = self.cascade_count
        resolution = int(self.settings.shadow_resolution)
        if len(self._targets) == required:
            return
        self._release_targets()
        for _ in range(required):
            depth = self.ctx.depth_texture((resolution, resolution))
            depth.repeat_x = False
            depth.repeat_y = False
            if hasattr(depth, "compare_func"):
                depth.compare_func = ""
            framebuffer = self.ctx.framebuffer(depth_attachment=depth)
            self._targets.append((depth, framebuffer))

    def _release_targets(self) -> None:
        for depth, framebuffer in self._targets:
            framebuffer.release()
            depth.release()
        self._targets.clear()

    def _gpu_mesh(self, mesh: MeshData) -> tuple[object, int]:
        key = id(mesh)
        cached = self._mesh_gpu.get(key)
        if cached is None:
            vertices = np.ascontiguousarray(mesh.vertices, dtype="f4")
            vbo = self.ctx.buffer(vertices.tobytes())
            vao = self.ctx.vertex_array(self.program, [(vbo, "3f", "in_pos")])
            cached = (vbo, vao, mesh.vertex_count)
            self._mesh_gpu[key] = cached
        return cached[1], cached[2]

    def _shadow_geometry(self, obj: object) -> tuple[MeshData, np.ndarray] | None:
        if isinstance(obj, Mesh3D):
            return obj.mesh, obj.transform.matrix()
        if isinstance(obj, Cube3D):
            return self._cube_mesh, obj.transform.matrix()
        return None

    def render(
        self,
        scene: object,
        light: DirectionalLight3D,
        camera: Camera3D,
        *,
        width: int,
        height: int,
    ) -> CascadedShadowFrame3D:
        if self._released:
            raise RuntimeError("cascaded shadow map has been released")
        self._ensure_targets()
        plan = build_cascaded_shadow_plan(
            camera,
            aspect=float(width) / max(1.0, float(height)),
            settings=self.settings,
        )
        previous_viewport = self.ctx.viewport
        resolution = int(self.settings.shadow_resolution)
        light_frames: list[DirectionalShadowFrame] = []
        try:
            for cascade, (_, framebuffer) in zip(plan.cascades, self._targets):
                light_distance = max(16.0, cascade.extent * 2.0)
                shadow_settings = DirectionalShadowSettings(
                    resolution=resolution,
                    extent=cascade.extent,
                    distance=light_distance,
                    near=0.1,
                    far=max(32.0, light_distance * 2.0 + cascade.extent * 2.0),
                )
                frame = directional_shadow_frame(light, cascade.focus, shadow_settings)
                light_frames.append(frame)
                framebuffer.use()
                self.ctx.viewport = (0, 0, resolution, resolution)
                framebuffer.clear(depth=1.0)
                self.ctx.enable(self.ctx.DEPTH_TEST)
                for obj in getattr(scene, "objects", ()):
                    if not getattr(obj, "enabled", True) or not getattr(obj, "visible", True):
                        continue
                    geometry = self._shadow_geometry(obj)
                    if geometry is None:
                        continue
                    mesh, model = geometry
                    vao, count = self._gpu_mesh(mesh)
                    matrix = frame.view_projection @ model
                    self._write_mat4(self.program["light_mvp"], matrix)
                    vao.render(vertices=count)
        finally:
            self.ctx.viewport = previous_viewport
        return CascadedShadowFrame3D(plan=plan, light_frames=tuple(light_frames))

    def use(self, cascade: int, *, location: int) -> None:
        if not self._targets:
            raise RuntimeError("cascaded shadow maps have not been rendered yet")
        self._targets[int(cascade)][0].use(location=int(location))

    def release(self) -> None:
        if self._released:
            return
        self._release_targets()
        for vbo, vao, _ in self._mesh_gpu.values():
            vao.release()
            vbo.release()
        self._mesh_gpu.clear()
        self.program.release()
        self._released = True


class Renderer2(ShadowedImageBasedPostProcessRenderer):
    """Additive SwirEngine 1.4 production renderer path.

    Renderer2 keeps the stable 1.x renderer hierarchy untouched while composing cascaded shadows,
    a depth/normal prepass, SSAO, screen-space decals, HDR bloom and the existing color-grading/FXAA
    controls in one opt-in renderer.
    """

    _CSM_TEXTURE_BASE = 5

    def __init__(
        self,
        *args: Any,
        renderer2: Renderer2Settings | None = None,
        **kwargs: Any,
    ) -> None:
        self.renderer2 = renderer2 or Renderer2Settings()
        self._renderer2_planner = Renderer2Planner(self.renderer2)
        self._renderer2_frame: Renderer2FramePlan | None = None
        self._csm: CascadedDirectionalShadowMap | None = None
        self._csm_overlay_gpu: dict[int, tuple[object, object, int]] = {}
        self._csm_cube_mesh = cube_mesh()
        if kwargs.get("postprocess") is None:
            kwargs["postprocess"] = PostProcessSettings(enabled=True)
        kwargs["shadows_enabled"] = False
        super().__init__(*args, **kwargs)
        self.postprocess.enabled = True
        self._prepass = DepthNormalPrepass3D(self.ctx)
        self._ssao_pass = SSAOPass3D(self.ctx)
        self._bloom_pass = BloomPass3D(self.ctx)
        self._decal_pass = DecalPass3D(self.ctx)
        self._init_csm_overlay()
        self._init_renderer2_resolve()

    @property
    def renderer2_frame(self) -> Renderer2FramePlan | None:
        return self._renderer2_frame

    @property
    def renderer2_diagnostics(self):
        return None if self._renderer2_frame is None else self._renderer2_frame.diagnostics

    def _ensure_post_target(self) -> None:
        size = (self.width, self.height)
        if self._post_framebuffer is not None and self._post_size == size:
            return
        self._release_post_target()
        self._post_color = self.ctx.texture(size, 4, dtype="f2")
        self._post_color.filter = (self.ctx.LINEAR, self.ctx.LINEAR)
        self._post_color.repeat_x = False
        self._post_color.repeat_y = False
        self._post_depth = self.ctx.depth_texture(size)
        self._post_depth.filter = (self.ctx.NEAREST, self.ctx.NEAREST)
        self._post_depth.repeat_x = False
        self._post_depth.repeat_y = False
        if hasattr(self._post_depth, "compare_func"):
            self._post_depth.compare_func = ""
        self._post_framebuffer = self.ctx.framebuffer(
            color_attachments=[self._post_color],
            depth_attachment=self._post_depth,
        )
        self._post_size = size

    def _init_csm_overlay(self) -> None:
        self.csm_overlay_program = self.ctx.program(
            vertex_shader="""
                #version 330
                in vec3 in_pos;
                in vec3 in_normal;
                uniform mat4 mvp;
                uniform mat4 model;
                uniform mat4 view_matrix;
                uniform mat4 light_vp0;
                uniform mat4 light_vp1;
                uniform mat4 light_vp2;
                uniform mat4 light_vp3;
                uniform float normal_bias;
                out vec4 v_light0;
                out vec4 v_light1;
                out vec4 v_light2;
                out vec4 v_light3;
                out float v_view_depth;

                void main() {
                    vec4 world = model * vec4(in_pos, 1.0);
                    vec3 normal = normalize(mat3(transpose(inverse(model))) * in_normal);
                    vec4 biased = vec4(world.xyz + normal * normal_bias, 1.0);
                    v_light0 = light_vp0 * biased;
                    v_light1 = light_vp1 * biased;
                    v_light2 = light_vp2 * biased;
                    v_light3 = light_vp3 * biased;
                    v_view_depth = max(0.0, -(view_matrix * world).z);
                    gl_Position = mvp * vec4(in_pos, 1.0);
                }
            """,
            fragment_shader="""
                #version 330
                uniform sampler2D shadow_map0;
                uniform sampler2D shadow_map1;
                uniform sampler2D shadow_map2;
                uniform sampler2D shadow_map3;
                uniform int cascade_count;
                uniform vec4 cascade_splits;
                uniform float shadow_bias;
                uniform float shadow_floor;
                in vec4 v_light0;
                in vec4 v_light1;
                in vec4 v_light2;
                in vec4 v_light3;
                in float v_view_depth;
                out vec4 fragColor;

                float sample_visibility(sampler2D shadow_map, vec4 light_position) {
                    if (abs(light_position.w) <= 0.000001) {
                        return 1.0;
                    }
                    vec3 projected = light_position.xyz / light_position.w;
                    vec3 sample_position = projected * 0.5 + 0.5;
                    if (
                        sample_position.x <= 0.0 || sample_position.x >= 1.0
                        || sample_position.y <= 0.0 || sample_position.y >= 1.0
                        || sample_position.z <= 0.0 || sample_position.z >= 1.0
                    ) {
                        return 1.0;
                    }
                    vec2 texel = 1.0 / vec2(textureSize(shadow_map, 0));
                    float receiver_depth = sample_position.z - shadow_bias;
                    float visible_samples = 0.0;
                    for (int x = -1; x <= 1; ++x) {
                        for (int y = -1; y <= 1; ++y) {
                            float blocker = texture(
                                shadow_map,
                                sample_position.xy + vec2(float(x), float(y)) * texel
                            ).r;
                            visible_samples += receiver_depth <= blocker ? 1.0 : 0.0;
                        }
                    }
                    return visible_samples / 9.0;
                }

                void main() {
                    float visibility;
                    if (cascade_count <= 1 || v_view_depth <= cascade_splits.x) {
                        visibility = sample_visibility(shadow_map0, v_light0);
                    } else if (cascade_count <= 2 || v_view_depth <= cascade_splits.y) {
                        visibility = sample_visibility(shadow_map1, v_light1);
                    } else if (cascade_count <= 3 || v_view_depth <= cascade_splits.z) {
                        visibility = sample_visibility(shadow_map2, v_light2);
                    } else {
                        visibility = sample_visibility(shadow_map3, v_light3);
                    }
                    float factor = mix(shadow_floor, 1.0, visibility);
                    fragColor = vec4(vec3(factor), 1.0);
                }
            """,
        )
        for index in range(4):
            self.csm_overlay_program[f"shadow_map{index}"].value = self._CSM_TEXTURE_BASE + index

    def _init_renderer2_resolve(self) -> None:
        self.renderer2_resolve_program = self.ctx.program(
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
                uniform sampler2D scene_image;
                uniform sampler2D ao_image;
                uniform sampler2D bloom_image;
                uniform vec2 inverse_resolution;
                uniform int tone_mapping_mode;
                uniform float exposure;
                uniform float gamma_value;
                uniform float contrast;
                uniform float saturation;
                uniform float vignette;
                uniform bool fxaa_enabled;
                uniform bool ao_enabled;
                uniform bool bloom_enabled;
                uniform float bloom_intensity;
                in vec2 v_uv;
                out vec4 fragColor;

                vec3 srgb_to_linear(vec3 value) {
                    vec3 low = value / 12.92;
                    vec3 high = pow((value + 0.055) / 1.055, vec3(2.4));
                    return mix(low, high, step(vec3(0.04045), value));
                }

                vec3 sample_scene(vec2 uv) {
                    if (!fxaa_enabled) return texture(scene_image, uv).rgb;
                    vec3 rgb_m = texture(scene_image, uv).rgb;
                    vec3 rgb_nw = texture(scene_image, uv + vec2(-1.0, 1.0) * inverse_resolution).rgb;
                    vec3 rgb_ne = texture(scene_image, uv + vec2(1.0, 1.0) * inverse_resolution).rgb;
                    vec3 rgb_sw = texture(scene_image, uv + vec2(-1.0, -1.0) * inverse_resolution).rgb;
                    vec3 rgb_se = texture(scene_image, uv + vec2(1.0, -1.0) * inverse_resolution).rgb;
                    vec3 luma = vec3(0.299, 0.587, 0.114);
                    float luma_m = dot(rgb_m, luma);
                    float luma_min = min(
                        luma_m,
                        min(
                            min(dot(rgb_nw, luma), dot(rgb_ne, luma)),
                            min(dot(rgb_sw, luma), dot(rgb_se, luma))
                        )
                    );
                    float luma_max = max(
                        luma_m,
                        max(
                            max(dot(rgb_nw, luma), dot(rgb_ne, luma)),
                            max(dot(rgb_sw, luma), dot(rgb_se, luma))
                        )
                    );
                    vec2 dir;
                    dir.x = -(
                        (dot(rgb_nw, luma) + dot(rgb_ne, luma))
                        - (dot(rgb_sw, luma) + dot(rgb_se, luma))
                    );
                    dir.y = (
                        (dot(rgb_nw, luma) + dot(rgb_sw, luma))
                        - (dot(rgb_ne, luma) + dot(rgb_se, luma))
                    );
                    float reduce = max(
                        (dot(rgb_nw + rgb_ne + rgb_sw + rgb_se, luma) * 0.25) * 0.03125,
                        0.0078125
                    );
                    float reciprocal = 1.0 / (min(abs(dir.x), abs(dir.y)) + reduce);
                    dir = clamp(dir * reciprocal, vec2(-8.0), vec2(8.0)) * inverse_resolution;
                    vec3 rgb_a = 0.5 * (
                        texture(scene_image, uv + dir * (1.0 / 3.0 - 0.5)).rgb
                        + texture(scene_image, uv + dir * (2.0 / 3.0 - 0.5)).rgb
                    );
                    vec3 rgb_b = rgb_a * 0.5 + 0.25 * (
                        texture(scene_image, uv + dir * -0.5).rgb
                        + texture(scene_image, uv + dir * 0.5).rgb
                    );
                    float luma_b = dot(rgb_b, luma);
                    return (luma_b < luma_min || luma_b > luma_max) ? rgb_a : rgb_b;
                }

                vec3 aces(vec3 color) {
                    const float a = 2.51;
                    const float b = 0.03;
                    const float c = 2.43;
                    const float d = 0.59;
                    const float e = 0.14;
                    return clamp(
                        (color * (a * color + b)) / (color * (c * color + d) + e),
                        0.0,
                        1.0
                    );
                }

                void main() {
                    vec3 color = srgb_to_linear(sample_scene(v_uv));
                    if (ao_enabled) {
                        color *= texture(ao_image, v_uv).r;
                    }
                    if (bloom_enabled) {
                        color += srgb_to_linear(texture(bloom_image, v_uv).rgb) * bloom_intensity;
                    }
                    color *= exposure;
                    if (tone_mapping_mode == 1) {
                        color = color / (vec3(1.0) + color);
                    } else if (tone_mapping_mode == 2) {
                        color = aces(color);
                    }
                    float luma = dot(color, vec3(0.2126, 0.7152, 0.0722));
                    color = mix(vec3(luma), color, saturation);
                    color = (color - 0.5) * contrast + 0.5;
                    vec2 centered = v_uv * 2.0 - 1.0;
                    float edge = smoothstep(0.25, 1.35, dot(centered, centered));
                    color *= 1.0 - edge * vignette;
                    color = pow(max(color, vec3(0.0)), vec3(1.0 / gamma_value));
                    fragColor = vec4(color, 1.0);
                }
            """,
        )
        self.renderer2_resolve_program["scene_image"].value = 0
        self.renderer2_resolve_program["ao_image"].value = 1
        self.renderer2_resolve_program["bloom_image"].value = 2
        self.renderer2_resolve_vao = self.ctx.simple_vertex_array(
            self.renderer2_resolve_program,
            self.post_vbo,
            "in_pos",
        )

    def _csm_resource(self) -> CascadedDirectionalShadowMap:
        if self._csm is None:
            self._csm = CascadedDirectionalShadowMap(self.ctx, self.renderer2)
        return self._csm

    @staticmethod
    def _renderer2_light(scene: object) -> DirectionalLight3D | None:
        selection = select_lights(getattr(scene, "objects", ()))
        return selection.directional[0] if selection.directional else None

    def _csm_overlay_vao(self, mesh: MeshData) -> tuple[object, int]:
        key = id(mesh)
        cached = self._csm_overlay_gpu.get(key)
        if cached is None:
            interleaved = mesh.interleaved(include_uvs=True).reshape((-1, 8))
            position_normal = np.ascontiguousarray(interleaved[:, :6], dtype="f4")
            vbo = self.ctx.buffer(position_normal.tobytes())
            vao = self.ctx.vertex_array(
                self.csm_overlay_program,
                [(vbo, "3f 3f", "in_pos", "in_normal")],
            )
            cached = (vbo, vao, mesh.vertex_count)
            self._csm_overlay_gpu[key] = cached
        return cached[1], cached[2]

    def _receiver_geometry(self, obj: object) -> tuple[MeshData, np.ndarray] | None:
        if isinstance(obj, Mesh3D):
            return obj.mesh, obj.transform.matrix()
        if isinstance(obj, Cube3D):
            return self._csm_cube_mesh, obj.transform.matrix()
        return None

    def _render_csm_overlay(
        self,
        scene: object,
        camera: Camera3D,
        frame: CascadedShadowFrame3D,
    ) -> None:
        resource = self._csm
        if resource is None or not frame.light_frames:
            return
        count = len(frame.light_frames)
        for index in range(count):
            resource.use(index, location=self._CSM_TEXTURE_BASE + index)
        for index in range(count, 4):
            resource.use(count - 1, location=self._CSM_TEXTURE_BASE + index)

        frames = list(frame.light_frames)
        while len(frames) < 4:
            frames.append(frames[-1])
        for index, light_frame in enumerate(frames[:4]):
            self._write_mat4(
                self.csm_overlay_program[f"light_vp{index}"],
                light_frame.view_projection,
            )
        splits = list(frame.plan.split_depths)
        while len(splits) < 4:
            splits.append(splits[-1])
        self.csm_overlay_program["cascade_count"].value = count
        self.csm_overlay_program["cascade_splits"].value = tuple(float(v) for v in splits[:4])
        self.csm_overlay_program["shadow_bias"].value = 0.0015
        self.csm_overlay_program["normal_bias"].value = 0.003
        self.csm_overlay_program["shadow_floor"].value = 0.18
        view_matrix = camera.view_matrix()
        self._write_mat4(self.csm_overlay_program["view_matrix"], view_matrix)

        projection = self._shadow_projection(camera)
        view_projection = projection @ view_matrix
        previous_depth_func = _read_context_state(self.ctx, "depth_func", "<")
        previous_depth_mask = _read_context_state(self.ctx, "depth_mask", True)
        self.ctx.enable(self.ctx.DEPTH_TEST)
        self.ctx.enable(self.ctx.BLEND)
        self.ctx.blend_func = self.ctx.DST_COLOR, self.ctx.ZERO
        self.ctx.depth_func = "<="
        self.ctx.depth_mask = False
        try:
            for obj in getattr(scene, "objects", ()):
                if not getattr(obj, "enabled", True) or not getattr(obj, "visible", True):
                    continue
                geometry = self._receiver_geometry(obj)
                if geometry is None:
                    continue
                mesh, model = geometry
                vao, vertices = self._csm_overlay_vao(mesh)
                self._write_mat4(self.csm_overlay_program["model"], model)
                self._write_mat4(
                    self.csm_overlay_program["mvp"],
                    view_projection @ model,
                )
                vao.render(vertices=vertices)
                self.stats.draw_calls += 1
                self.stats.triangles += vertices // 3
        finally:
            self.ctx.depth_mask = previous_depth_mask
            self.ctx.depth_func = previous_depth_func
            self.ctx.disable(self.ctx.BLEND)
            self.ctx.disable(self.ctx.DEPTH_TEST)

    def _render_base_color(self, scene: object, camera: Camera3D, *, prepassed: bool) -> None:
        if not prepassed:
            Renderer._render_3d(self, scene, camera)
            return
        previous_depth_func = _read_context_state(self.ctx, "depth_func", "<")
        previous_depth_mask = _read_context_state(self.ctx, "depth_mask", True)
        self.ctx.depth_func = "<="
        self.ctx.depth_mask = False
        try:
            Renderer._render_3d(self, scene, camera)
        finally:
            self.ctx.depth_mask = previous_depth_mask
            self.ctx.depth_func = previous_depth_func

    def _render_3d(self, scene: object, camera: Camera3D) -> None:
        self._renderer2_frame = self._renderer2_planner.plan(
            scene,
            camera,
            width=self.width,
            height=self.height,
        )
        prepassed = False
        if self.renderer2.depth_prepass and self._post_depth is not None:
            self._prepass.render(
                scene,
                camera,
                width=self.width,
                height=self.height,
                depth_texture=self._post_depth,
            )
            prepassed = True

        light = self._renderer2_light(scene)
        csm_frame = None
        if self.renderer2.cascaded_shadows and light is not None:
            csm_frame = self._csm_resource().render(
                scene,
                light,
                camera,
                width=self.width,
                height=self.height,
            )

        self._restore_scene_target()
        self._render_base_color(scene, camera, prepassed=prepassed)
        self._render_dynamic_13(scene, camera)
        if csm_frame is not None:
            self._render_csm_overlay(scene, camera, csm_frame)
        self._render_ibl(scene, camera)

    def _texture_for_decal(self, path: str):
        return self._texture(path)[0]

    def _resolve_renderer2(self, *, ao_texture: object | None, bloom_texture: object | None) -> None:
        assert self._post_color is not None
        self.ctx.screen.use()
        self.ctx.viewport = (0, 0, self.width, self.height)
        self.ctx.disable(self.ctx.DEPTH_TEST)
        self._post_color.use(location=0)
        (ao_texture or self._post_color).use(location=1)
        (bloom_texture or self._post_color).use(location=2)
        settings = self.postprocess
        program = self.renderer2_resolve_program
        program["inverse_resolution"].value = (
            1.0 / max(1, self.width),
            1.0 / max(1, self.height),
        )
        program["tone_mapping_mode"].value = (
            settings.tone_mapping_mode if self.renderer2.hdr else 0
        )
        program["exposure"].value = float(settings.exposure if self.renderer2.hdr else 1.0)
        program["gamma_value"].value = float(settings.gamma)
        program["contrast"].value = float(settings.contrast)
        program["saturation"].value = float(settings.saturation)
        program["vignette"].value = float(settings.vignette)
        program["fxaa_enabled"].value = bool(settings.fxaa)
        program["ao_enabled"].value = ao_texture is not None
        program["bloom_enabled"].value = bloom_texture is not None
        program["bloom_intensity"].value = float(self.renderer2.bloom_intensity)
        self.renderer2_resolve_vao.render(vertices=3)
        self.stats.draw_calls += 1
        self.stats.triangles += 1

    def render(
        self,
        scene,
        *,
        camera=None,
        clear_color=(0.035, 0.045, 0.07, 1.0),
    ) -> None:
        if self.mode != "3d":
            super().render(scene, camera=camera, clear_color=clear_color)
            return

        active = camera if isinstance(camera, Camera3D) else Camera3D()
        self._ensure_post_target()
        assert self._post_framebuffer is not None
        assert self._post_color is not None
        assert self._post_depth is not None
        self._post_framebuffer.use()
        Renderer.render(self, scene, camera=active, clear_color=clear_color)

        ao_texture = None
        normal_texture = self._prepass.normal_texture
        if self.renderer2.ssao and normal_texture is not None:
            ao_texture = self._ssao_pass.render(
                depth_texture=self._post_depth,
                normal_texture=normal_texture,
                camera=active,
                width=self.width,
                height=self.height,
                settings=self.renderer2,
            )

        if self.renderer2.decals and self._renderer2_frame is not None:
            self._decal_pass.render(
                self._renderer2_frame.decals,
                color_texture=self._post_color,
                depth_texture=self._post_depth,
                camera=active,
                width=self.width,
                height=self.height,
                texture_loader=self._texture_for_decal,
            )

        bloom_texture = None
        if self.renderer2.bloom:
            bloom_texture = self._bloom_pass.render(
                self._post_color,
                width=self.width,
                height=self.height,
                settings=self.renderer2,
            )

        self._resolve_renderer2(ao_texture=ao_texture, bloom_texture=bloom_texture)

    def release(self) -> None:
        if self._csm is not None:
            self._csm.release()
            self._csm = None
        self._prepass.release()
        self._ssao_pass.release()
        self._bloom_pass.release()
        self._decal_pass.release()
        for vbo, vao, _ in self._csm_overlay_gpu.values():
            vao.release()
            vbo.release()
        self._csm_overlay_gpu.clear()
        self.renderer2_resolve_vao.release()
        self.renderer2_resolve_program.release()
        self.csm_overlay_program.release()
        super().release()
