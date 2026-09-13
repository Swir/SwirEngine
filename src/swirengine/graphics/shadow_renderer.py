from __future__ import annotations

from typing import Any

import numpy as np

from .camera3d import Camera3D
from .ibl_renderer import ImageBasedPostProcessRenderer, _read_context_state
from .lights import DirectionalLight3D, select_lights
from .mesh import Mesh3D
from .renderer import Renderer
from .shadows import DirectionalShadowFrame, DirectionalShadowMap, DirectionalShadowSettings


class ShadowedImageBasedPostProcessRenderer(ImageBasedPostProcessRenderer):
    """Full 3D renderer with optional directional shadow mapping.

    Shadows are opt-in to preserve the 0.4 rendering contract. When enabled, the first
    selected directional light owns one reusable depth map. A 3x3 PCF resolve is multiplied
    over direct scene lighting before the additive IBL pass, so image-based environment light
    remains available inside shadows.
    """

    def __init__(
        self,
        *args: Any,
        shadows_enabled: bool = False,
        shadow_settings: DirectionalShadowSettings | None = None,
        **kwargs: Any,
    ) -> None:
        self.shadows_enabled = bool(shadows_enabled)
        self.shadow_settings = shadow_settings or DirectionalShadowSettings()
        self._directional_shadow: DirectionalShadowMap | None = None
        self._shadow_overlay_gpu: dict[int, tuple[object, object, int]] = {}
        super().__init__(*args, **kwargs)
        self._init_shadow_overlay()

    def _init_shadow_overlay(self) -> None:
        self.shadow_overlay_program = self.ctx.program(
            vertex_shader="""
                #version 330
                in vec3 in_pos;
                in vec3 in_normal;
                uniform mat4 mvp;
                uniform mat4 model;
                uniform mat4 light_view_projection;
                uniform float normal_bias;
                out vec4 v_light_position;

                void main() {
                    vec4 world = model * vec4(in_pos, 1.0);
                    vec3 normal = normalize(mat3(transpose(inverse(model))) * in_normal);
                    vec3 biased_world = world.xyz + normal * normal_bias;
                    v_light_position = light_view_projection * vec4(biased_world, 1.0);
                    gl_Position = mvp * vec4(in_pos, 1.0);
                }
            """,
            fragment_shader="""
                #version 330
                uniform sampler2D shadow_map;
                uniform float shadow_bias;
                uniform float shadow_floor;
                in vec4 v_light_position;
                out vec4 fragColor;

                float visibility() {
                    if (abs(v_light_position.w) <= 0.000001) {
                        return 1.0;
                    }
                    vec3 projected = v_light_position.xyz / v_light_position.w;
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
                            float blocker_depth = texture(
                                shadow_map,
                                sample_position.xy + vec2(float(x), float(y)) * texel
                            ).r;
                            visible_samples += receiver_depth <= blocker_depth ? 1.0 : 0.0;
                        }
                    }
                    return visible_samples / 9.0;
                }

                void main() {
                    float factor = mix(shadow_floor, 1.0, visibility());
                    fragColor = vec4(vec3(factor), 1.0);
                }
            """,
        )
        self.shadow_overlay_program["shadow_map"].value = 5

    def _shadow_resource(self) -> DirectionalShadowMap:
        if self._directional_shadow is None:
            self._directional_shadow = DirectionalShadowMap(self.ctx, self.shadow_settings)
        return self._directional_shadow

    @staticmethod
    def _shadow_light(scene: object) -> DirectionalLight3D | None:
        selection = select_lights(getattr(scene, "objects", ()))
        return selection.directional[0] if selection.directional else None

    def _restore_scene_target(self) -> None:
        if self.postprocess.enabled and self._post_framebuffer is not None:
            self._post_framebuffer.use()
        else:
            self.ctx.screen.use()
        self.ctx.viewport = (0, 0, self.width, self.height)

    def _shadow_overlay_vao(self, obj: Mesh3D) -> tuple[object, int]:
        key = id(obj.mesh)
        cached = self._shadow_overlay_gpu.get(key)
        if cached is None:
            interleaved = obj.mesh.interleaved(include_uvs=True).reshape((-1, 8))
            position_normal = np.ascontiguousarray(interleaved[:, :6], dtype="f4")
            vbo = self.ctx.buffer(position_normal.tobytes())
            vao = self.ctx.vertex_array(
                self.shadow_overlay_program,
                [(vbo, "3f 3f", "in_pos", "in_normal")],
            )
            cached = (vbo, vao, obj.mesh.vertex_count)
            self._shadow_overlay_gpu[key] = cached
        return cached[1], cached[2]

    def _render_shadow_overlay(
        self,
        scene: object,
        camera: Camera3D,
        frame: DirectionalShadowFrame,
    ) -> None:
        resource = self._directional_shadow
        if resource is None:
            return
        resource.use(location=5)
        self._write_mat4(
            self.shadow_overlay_program["light_view_projection"],
            frame.view_projection,
        )
        self.shadow_overlay_program["shadow_bias"].value = float(self.shadow_settings.bias)
        self.shadow_overlay_program["normal_bias"].value = float(
            self.shadow_settings.normal_bias
        )
        # Keep a small ambient floor because this resolve intentionally shadows direct light
        # while the additive IBL pass is evaluated afterwards.
        self.shadow_overlay_program["shadow_floor"].value = 0.18

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
                vao, count = self._shadow_overlay_vao(obj)
                model = obj.transform.matrix()
                self._write_mat4(self.shadow_overlay_program["model"], model)
                self._write_mat4(
                    self.shadow_overlay_program["mvp"],
                    view_projection @ model,
                )
                vao.render(vertices=count)
                self.stats.draw_calls += 1
                self.stats.triangles += count // 3
        finally:
            self.ctx.depth_mask = previous_depth_mask
            self.ctx.depth_func = previous_depth_func
            self.ctx.disable(self.ctx.BLEND)
            self.ctx.disable(self.ctx.DEPTH_TEST)

    def _shadow_projection(self, camera: Camera3D) -> np.ndarray:
        from ..math.types import perspective

        return perspective(
            float(camera.fov),
            self.width / max(1, self.height),
            float(camera.near),
            float(camera.far),
        )

    def _render_3d(self, scene: object, camera: Camera3D) -> None:
        if not self.shadows_enabled:
            super()._render_3d(scene, camera)
            return

        light = self._shadow_light(scene)
        if light is None:
            super()._render_3d(scene, camera)
            return

        resource = self._shadow_resource()
        frame = resource.render(scene, light, focus=camera.position)
        self._restore_scene_target()

        # Call the base direct-light pass explicitly so IBL can remain unshadowed and additive.
        Renderer._render_3d(self, scene, camera)
        self._render_shadow_overlay(scene, camera, frame)
        self._render_ibl(scene, camera)

    def release(self) -> None:
        if self._directional_shadow is not None:
            self._directional_shadow.release()
            self._directional_shadow = None
        for vbo, vao, _ in self._shadow_overlay_gpu.values():
            vao.release()
            vbo.release()
        self._shadow_overlay_gpu.clear()
        self.shadow_overlay_program.release()
        super().release()
