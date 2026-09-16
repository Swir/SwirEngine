from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np

from .camera3d import Camera3D
from .ibl_renderer import _read_context_state
from .lights import DirectionalLight3D, select_lights
from .mesh import Mesh3D
from .renderer import Renderer
from .renderer2 import (
    CascadedShadowPlan3D,
    Renderer2FramePlan,
    Renderer2Planner,
    Renderer2Settings,
    build_cascaded_shadow_plan,
)
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

    def _gpu_mesh(self, obj: Mesh3D) -> tuple[object, int]:
        key = id(obj.mesh)
        cached = self._mesh_gpu.get(key)
        if cached is None:
            vertices = np.ascontiguousarray(obj.mesh.vertices, dtype="f4")
            vbo = self.ctx.buffer(vertices.tobytes())
            vao = self.ctx.vertex_array(self.program, [(vbo, "3f", "in_pos")])
            cached = (vbo, vao, obj.mesh.vertex_count)
            self._mesh_gpu[key] = cached
        return cached[1], cached[2]

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
                    if not isinstance(obj, Mesh3D):
                        continue
                    if not getattr(obj, "enabled", True) or not getattr(obj, "visible", True):
                        continue
                    vao, count = self._gpu_mesh(obj)
                    matrix = frame.view_projection @ obj.transform.matrix()
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
    """Additive SwirEngine 1.4 renderer path with real cascaded directional shadow execution.

    Existing renderer classes remain untouched and keep their 1.x behavior. Renderer2 starts from the
    proven 1.3 renderer stack and layers new production passes behind explicit quality settings.
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
        kwargs["shadows_enabled"] = False
        super().__init__(*args, **kwargs)
        self._init_csm_overlay()

    @property
    def renderer2_frame(self) -> Renderer2FramePlan | None:
        return self._renderer2_frame

    @property
    def renderer2_diagnostics(self):
        return None if self._renderer2_frame is None else self._renderer2_frame.diagnostics

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

    def _csm_resource(self) -> CascadedDirectionalShadowMap:
        if self._csm is None:
            self._csm = CascadedDirectionalShadowMap(self.ctx, self.renderer2)
        return self._csm

    @staticmethod
    def _renderer2_light(scene: object) -> DirectionalLight3D | None:
        selection = select_lights(getattr(scene, "objects", ()))
        return selection.directional[0] if selection.directional else None

    def _csm_overlay_vao(self, obj: Mesh3D) -> tuple[object, int]:
        key = id(obj.mesh)
        cached = self._csm_overlay_gpu.get(key)
        if cached is None:
            interleaved = obj.mesh.interleaved(include_uvs=True).reshape((-1, 8))
            position_normal = np.ascontiguousarray(interleaved[:, :6], dtype="f4")
            vbo = self.ctx.buffer(position_normal.tobytes())
            vao = self.ctx.vertex_array(
                self.csm_overlay_program,
                [(vbo, "3f 3f", "in_pos", "in_normal")],
            )
            cached = (vbo, vao, obj.mesh.vertex_count)
            self._csm_overlay_gpu[key] = cached
        return cached[1], cached[2]

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
        # Fill unused sampler slots with the last valid cascade so every sampler is complete.
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
        self._write_mat4(self.csm_overlay_program["view_matrix"], camera.view_matrix())

        projection = self._shadow_projection(camera)
        view_projection = projection @ camera.view_matrix()
        previous_depth_func = _read_context_state(self.ctx, "depth_func", "<")
        previous_depth_mask = _read_context_state(self.ctx, "depth_mask", True)
        self.ctx.enable(self.ctx.DEPTH_TEST)
        self.ctx.enable(self.ctx.BLEND)
        self.ctx.blend_func = self.ctx.DST_COLOR, self.ctx.ZERO
        self.ctx.depth_func = "<="
        self.ctx.depth_mask = False
        try:
            for obj in getattr(scene, "objects", ()):
                if not isinstance(obj, Mesh3D) or not obj.enabled or not obj.visible:
                    continue
                vao, vertices = self._csm_overlay_vao(obj)
                model = obj.transform.matrix()
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

    def _render_3d(self, scene: object, camera: Camera3D) -> None:
        self._renderer2_frame = self._renderer2_planner.plan(
            scene,
            camera,
            width=self.width,
            height=self.height,
        )
        if not self.renderer2.cascaded_shadows:
            super()._render_3d(scene, camera)
            return

        light = self._renderer2_light(scene)
        if light is None:
            super()._render_3d(scene, camera)
            return

        csm_frame = self._csm_resource().render(
            scene,
            light,
            camera,
            width=self.width,
            height=self.height,
        )
        self._restore_scene_target()
        Renderer._render_3d(self, scene, camera)
        self._render_dynamic_13(scene, camera)
        self._render_csm_overlay(scene, camera, csm_frame)
        self._render_ibl(scene, camera)

    def release(self) -> None:
        if self._csm is not None:
            self._csm.release()
            self._csm = None
        for vbo, vao, _ in self._csm_overlay_gpu.values():
            vao.release()
            vbo.release()
        self._csm_overlay_gpu.clear()
        self.csm_overlay_program.release()
        super().release()
