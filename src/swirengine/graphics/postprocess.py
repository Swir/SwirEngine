from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import numpy as np

from .renderer import Renderer

ToneMapping = Literal["none", "reinhard", "aces"]


@dataclass(slots=True)
class PostProcessSettings:
    """Creator-facing full-screen color grading and anti-aliasing settings."""

    enabled: bool = False
    tone_mapping: ToneMapping = "aces"
    exposure: float = 1.0
    gamma: float = 2.2
    contrast: float = 1.0
    saturation: float = 1.0
    vignette: float = 0.0
    fxaa: bool = True

    def __post_init__(self) -> None:
        if self.tone_mapping not in {"none", "reinhard", "aces"}:
            raise ValueError("tone_mapping must be 'none', 'reinhard', or 'aces'")
        if self.exposure <= 0.0:
            raise ValueError("exposure must be greater than zero")
        if self.gamma <= 0.0:
            raise ValueError("gamma must be greater than zero")
        if self.contrast < 0.0:
            raise ValueError("contrast must be non-negative")
        if self.saturation < 0.0:
            raise ValueError("saturation must be non-negative")
        if not 0.0 <= self.vignette <= 1.0:
            raise ValueError("vignette must be between 0 and 1")

    @property
    def tone_mapping_mode(self) -> int:
        return {"none": 0, "reinhard": 1, "aces": 2}[self.tone_mapping]

    def update(self, **changes: object) -> PostProcessSettings:
        """Update settings in place while preserving validation guarantees."""
        values = {
            "enabled": self.enabled,
            "tone_mapping": self.tone_mapping,
            "exposure": self.exposure,
            "gamma": self.gamma,
            "contrast": self.contrast,
            "saturation": self.saturation,
            "vignette": self.vignette,
            "fxaa": self.fxaa,
        }
        unknown = sorted(set(changes) - set(values))
        if unknown:
            raise TypeError(f"unknown post-process setting: {unknown[0]}")
        values.update(changes)
        candidate = PostProcessSettings(**values)
        for name, value in values.items():
            setattr(self, name, getattr(candidate, name))
        return self


class PostProcessRenderer(Renderer):
    """Renderer variant that resolves the scene through one GPU full-screen post-process pass."""

    def __init__(self, *args, postprocess: PostProcessSettings | None = None, **kwargs) -> None:
        self.postprocess = postprocess or PostProcessSettings()
        self._post_size = (0, 0)
        self._post_color = None
        self._post_depth = None
        self._post_framebuffer = None
        super().__init__(*args, **kwargs)
        self._init_postprocess()

    def _init_postprocess(self) -> None:
        self.post_program = self.ctx.program(
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
                uniform vec2 inverse_resolution;
                uniform int tone_mapping_mode;
                uniform float exposure;
                uniform float gamma_value;
                uniform float contrast;
                uniform float saturation;
                uniform float vignette;
                uniform bool fxaa_enabled;
                in vec2 v_uv;
                out vec4 fragColor;

                vec3 srgb_to_linear(vec3 value) {
                    vec3 low = value / 12.92;
                    vec3 high = pow((value + 0.055) / 1.055, vec3(2.4));
                    return mix(low, high, step(vec3(0.04045), value));
                }

                vec3 sample_scene(vec2 uv) {
                    if (!fxaa_enabled) {
                        return texture(scene_image, uv).rgb;
                    }
                    vec3 rgb_m = texture(scene_image, uv).rgb;
                    vec3 rgb_nw = texture(scene_image, uv + vec2(-1.0, 1.0) * inverse_resolution).rgb;
                    vec3 rgb_ne = texture(scene_image, uv + vec2(1.0, 1.0) * inverse_resolution).rgb;
                    vec3 rgb_sw = texture(scene_image, uv + vec2(-1.0, -1.0) * inverse_resolution).rgb;
                    vec3 rgb_se = texture(scene_image, uv + vec2(1.0, -1.0) * inverse_resolution).rgb;
                    vec3 luma = vec3(0.299, 0.587, 0.114);
                    float luma_m = dot(rgb_m, luma);
                    float luma_min = min(luma_m, min(min(dot(rgb_nw, luma), dot(rgb_ne, luma)), min(dot(rgb_sw, luma), dot(rgb_se, luma))));
                    float luma_max = max(luma_m, max(max(dot(rgb_nw, luma), dot(rgb_ne, luma)), max(dot(rgb_sw, luma), dot(rgb_se, luma))));
                    vec2 dir;
                    dir.x = -((dot(rgb_nw, luma) + dot(rgb_ne, luma)) - (dot(rgb_sw, luma) + dot(rgb_se, luma)));
                    dir.y = ((dot(rgb_nw, luma) + dot(rgb_sw, luma)) - (dot(rgb_ne, luma) + dot(rgb_se, luma)));
                    float reduce = max((dot(rgb_nw + rgb_ne + rgb_sw + rgb_se, luma) * 0.25) * 0.03125, 0.0078125);
                    float reciprocal = 1.0 / (min(abs(dir.x), abs(dir.y)) + reduce);
                    dir = clamp(dir * reciprocal, vec2(-8.0), vec2(8.0)) * inverse_resolution;
                    vec3 rgb_a = 0.5 * (
                        texture(scene_image, uv + dir * (1.0 / 3.0 - 0.5)).rgb +
                        texture(scene_image, uv + dir * (2.0 / 3.0 - 0.5)).rgb
                    );
                    vec3 rgb_b = rgb_a * 0.5 + 0.25 * (
                        texture(scene_image, uv + dir * -0.5).rgb +
                        texture(scene_image, uv + dir * 0.5).rgb
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
                    return clamp((color * (a * color + b)) / (color * (c * color + d) + e), 0.0, 1.0);
                }

                void main() {
                    vec3 color = srgb_to_linear(sample_scene(v_uv));
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
        self.post_program["scene_image"].value = 0
        vertices = np.asarray((-1.0, -1.0, 3.0, -1.0, -1.0, 3.0), dtype="f4")
        self.post_vbo = self.ctx.buffer(vertices.tobytes())
        self.post_vao = self.ctx.simple_vertex_array(self.post_program, self.post_vbo, "in_pos")
        self._ensure_post_target()

    def _release_post_target(self) -> None:
        for resource in (self._post_framebuffer, self._post_depth, self._post_color):
            if resource is not None:
                resource.release()
        self._post_framebuffer = None
        self._post_depth = None
        self._post_color = None
        self._post_size = (0, 0)

    def _ensure_post_target(self) -> None:
        size = (self.width, self.height)
        if self._post_framebuffer is not None and self._post_size == size:
            return
        self._release_post_target()
        self._post_color = self.ctx.texture(size, 4, dtype="f2")
        self._post_color.filter = (self.ctx.LINEAR, self.ctx.LINEAR)
        self._post_depth = self.ctx.depth_renderbuffer(size)
        self._post_framebuffer = self.ctx.framebuffer(
            color_attachments=[self._post_color], depth_attachment=self._post_depth
        )
        self._post_size = size

    def resize(self, width: int, height: int) -> None:
        super().resize(width, height)
        if hasattr(self, "post_program"):
            self._ensure_post_target()

    def render(self, scene, *, camera=None, clear_color=(0.035, 0.045, 0.07, 1.0)) -> None:
        if not self.postprocess.enabled:
            super().render(scene, camera=camera, clear_color=clear_color)
            return

        self._ensure_post_target()
        self._post_framebuffer.use()
        super().render(scene, camera=camera, clear_color=clear_color)
        self.ctx.screen.use()
        self.ctx.disable(self.ctx.DEPTH_TEST)
        self._post_color.use(location=0)
        settings = self.postprocess
        self.post_program["inverse_resolution"].value = (
            1.0 / max(1, self.width),
            1.0 / max(1, self.height),
        )
        self.post_program["tone_mapping_mode"].value = settings.tone_mapping_mode
        self.post_program["exposure"].value = float(settings.exposure)
        self.post_program["gamma_value"].value = float(settings.gamma)
        self.post_program["contrast"].value = float(settings.contrast)
        self.post_program["saturation"].value = float(settings.saturation)
        self.post_program["vignette"].value = float(settings.vignette)
        self.post_program["fxaa_enabled"].value = bool(settings.fxaa)
        self.post_vao.render(vertices=3)
        self.stats.draw_calls += 1
        self.stats.triangles += 1

    def release(self) -> None:
        self._release_post_target()
        self.post_vao.release()
        self.post_vbo.release()
        super().release()
