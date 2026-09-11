from __future__ import annotations

import math
from collections import OrderedDict
from pathlib import Path

import numpy as np

from ..math.types import Color, orthographic, perspective
from .batching import SpriteBatch, build_render_runs
from .camera import Camera2D
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
from .mesh import Mesh3D
from .primitives import Cube3D, Rectangle2D, Sprite2D, Text2D
from .stats import RendererStats


class Renderer:
    def __init__(
        self,
        ctx,
        width: int,
        height: int,
        mode: str = "2d",
        *,
        text_cache_limit: int = 128,
    ) -> None:
        self.ctx = ctx
        self.width = width
        self.height = height
        self.mode = mode
        self.text_cache_limit = max(8, int(text_cache_limit))
        self.stats = RendererStats()
        self._textures: dict[str, tuple[object, int, int]] = {}
        self._text_textures: OrderedDict[
            tuple[str, str, int], tuple[object, int, int]
        ] = OrderedDict()
        self._mesh_gpu: dict[int, tuple[object, object, int]] = {}
        self._sprite_batch_capacity = 0
        self._init_2d()
        self._init_3d()

    def resize(self, width: int, height: int) -> None:
        self.width = max(1, width)
        self.height = max(1, height)
        self.ctx.viewport = (0, 0, self.width, self.height)

    def _init_2d(self) -> None:
        self.program2d = self.ctx.program(
            vertex_shader="""
                #version 330
                in vec2 in_pos;
                uniform mat4 projection;
                uniform vec2 center;
                uniform vec2 size;
                uniform float angle;
                void main() {
                    float c = cos(angle), s = sin(angle);
                    vec2 p = in_pos * size;
                    p = vec2(c*p.x - s*p.y, s*p.x + c*p.y) + center;
                    gl_Position = projection * vec4(p, 0.0, 1.0);
                }
            """,
            fragment_shader="""
                #version 330
                uniform vec4 color;
                out vec4 fragColor;
                void main() { fragColor = color; }
            """,
        )
        quad = np.array(
            [-0.5, -0.5, 0.5, -0.5, 0.5, 0.5, -0.5, -0.5, 0.5, 0.5, -0.5, 0.5],
            dtype="f4",
        )
        self.vbo2d = self.ctx.buffer(quad.tobytes())
        self.vao2d = self.ctx.simple_vertex_array(self.program2d, self.vbo2d, "in_pos")

        self.sprite_program = self.ctx.program(
            vertex_shader="""
                #version 330
                in vec2 in_pos;
                in vec2 in_uv;
                uniform mat4 projection;
                uniform vec2 center;
                uniform vec2 size;
                uniform float angle;
                uniform vec4 uv_rect;
                out vec2 v_uv;
                void main() {
                    float c = cos(angle), s = sin(angle);
                    vec2 p = in_pos * size;
                    p = vec2(c*p.x - s*p.y, s*p.x + c*p.y) + center;
                    gl_Position = projection * vec4(p, 0.0, 1.0);
                    v_uv = mix(uv_rect.xy, uv_rect.zw, in_uv);
                }
            """,
            fragment_shader="""
                #version 330
                uniform sampler2D image;
                uniform vec4 tint;
                in vec2 v_uv;
                out vec4 fragColor;
                void main() { fragColor = texture(image, v_uv) * tint; }
            """,
        )
        sprite_quad = np.array(
            [
                -0.5, -0.5, 0.0, 0.0,
                 0.5, -0.5, 1.0, 0.0,
                 0.5,  0.5, 1.0, 1.0,
                -0.5, -0.5, 0.0, 0.0,
                 0.5,  0.5, 1.0, 1.0,
                -0.5,  0.5, 0.0, 1.0,
            ],
            dtype="f4",
        )
        self.sprite_vbo = self.ctx.buffer(sprite_quad.tobytes())
        self.sprite_vao = self.ctx.vertex_array(
            self.sprite_program,
            [(self.sprite_vbo, "2f 2f", "in_pos", "in_uv")],
        )
        self.sprite_program["image"].value = 0

        self.sprite_batch_program = self.ctx.program(
            vertex_shader="""
                #version 330
                in vec2 in_pos;
                in vec2 in_uv;
                in vec4 in_tint;
                uniform mat4 projection;
                out vec2 v_uv;
                out vec4 v_tint;
                void main() {
                    gl_Position = projection * vec4(in_pos, 0.0, 1.0);
                    v_uv = in_uv;
                    v_tint = in_tint;
                }
            """,
            fragment_shader="""
                #version 330
                uniform sampler2D image;
                in vec2 v_uv;
                in vec4 v_tint;
                out vec4 fragColor;
                void main() { fragColor = texture(image, v_uv) * v_tint; }
            """,
        )
        self.sprite_batch_program["image"].value = 0
        self._create_sprite_batch_buffer(256)

    def _create_sprite_batch_buffer(self, capacity: int) -> None:
        if self._sprite_batch_capacity:
            self.sprite_batch_vao.release()
            self.sprite_batch_vbo.release()
        self._sprite_batch_capacity = max(1, int(capacity))
        bytes_per_sprite = 6 * 8 * np.dtype("f4").itemsize
        self.sprite_batch_vbo = self.ctx.buffer(
            reserve=self._sprite_batch_capacity * bytes_per_sprite
        )
        self.sprite_batch_vao = self.ctx.vertex_array(
            self.sprite_batch_program,
            [(self.sprite_batch_vbo, "2f 2f 4f", "in_pos", "in_uv", "in_tint")],
        )

    def _ensure_sprite_batch_capacity(self, count: int) -> None:
        if count <= self._sprite_batch_capacity:
            return
        capacity = self._sprite_batch_capacity
        while capacity < count:
            capacity *= 2
        self._create_sprite_batch_buffer(capacity)

    def _init_3d(self) -> None:
        self.program3d = self.ctx.program(
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
                uniform vec4 color;
                uniform sampler2D image;
                uniform bool use_texture;
                uniform float ambient_strength;
                uniform float diffuse_strength;
                uniform float specular_strength;
                uniform float shininess;
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
                out vec4 fragColor;

                vec3 illuminate(
                    vec3 normal,
                    vec3 view_dir,
                    vec3 light_dir,
                    vec3 light_color,
                    float power,
                    vec3 surface
                ) {
                    float diffuse_term = max(dot(normal, light_dir), 0.0);
                    vec3 reflected = reflect(-light_dir, normal);
                    float specular_term = 0.0;
                    if (diffuse_term > 0.0 && specular_strength > 0.0) {
                        specular_term = pow(max(dot(view_dir, reflected), 0.0), shininess);
                    }
                    vec3 diffuse_light = surface * diffuse_strength * diffuse_term;
                    vec3 specular_light = vec3(specular_strength * specular_term);
                    return (diffuse_light + specular_light) * light_color * power;
                }

                float attenuation(float distance_to_light, float light_range) {
                    float ratio = clamp(distance_to_light / max(light_range, 0.0001), 0.0, 1.0);
                    float falloff = 1.0 - ratio * ratio;
                    return falloff * falloff;
                }

                vec3 directional_light(
                    vec3 normal,
                    vec3 view_dir,
                    vec3 surface,
                    vec3 direction,
                    vec3 light_color,
                    float intensity
                ) {
                    return illuminate(
                        normal, view_dir, normalize(-direction), light_color, intensity, surface
                    );
                }

                vec3 point_light(
                    vec3 normal,
                    vec3 view_dir,
                    vec3 surface,
                    vec3 position,
                    vec3 light_color,
                    float intensity,
                    float light_range
                ) {
                    vec3 delta = position - v_world_pos;
                    float distance_to_light = length(delta);
                    if (distance_to_light <= 0.0001) {
                        return vec3(0.0);
                    }
                    float power = intensity * attenuation(distance_to_light, light_range);
                    return illuminate(
                        normal, view_dir, delta / distance_to_light, light_color, power, surface
                    );
                }

                vec3 spot_light(
                    vec3 normal,
                    vec3 view_dir,
                    vec3 surface,
                    vec3 position,
                    vec3 direction,
                    vec3 light_color,
                    float intensity,
                    float light_range,
                    float inner_cos,
                    float outer_cos
                ) {
                    vec3 delta = position - v_world_pos;
                    float distance_to_light = length(delta);
                    if (distance_to_light <= 0.0001) {
                        return vec3(0.0);
                    }
                    vec3 light_dir = delta / distance_to_light;
                    float theta = dot(-light_dir, normalize(direction));
                    float cone = smoothstep(outer_cos, inner_cos, theta);
                    float power = intensity * cone * attenuation(distance_to_light, light_range);
                    return illuminate(
                        normal, view_dir, light_dir, light_color, power, surface
                    );
                }

                void main() {
                    vec4 surface_rgba = color;
                    if (use_texture) {
                        surface_rgba *= texture(image, v_uv);
                    }
                    vec3 surface = surface_rgba.rgb;
                    vec3 normal = normalize(v_normal);
                    vec3 view_dir = normalize(view_position - v_world_pos);
                    vec3 lighting = surface * ambient_strength;

                    if (dir0_enabled) lighting += directional_light(normal, view_dir, surface, dir0_direction, dir0_color, dir0_intensity);
                    if (dir1_enabled) lighting += directional_light(normal, view_dir, surface, dir1_direction, dir1_color, dir1_intensity);
                    if (dir2_enabled) lighting += directional_light(normal, view_dir, surface, dir2_direction, dir2_color, dir2_intensity);
                    if (dir3_enabled) lighting += directional_light(normal, view_dir, surface, dir3_direction, dir3_color, dir3_intensity);

                    if (point0_enabled) lighting += point_light(normal, view_dir, surface, point0_position, point0_color, point0_intensity, point0_range);
                    if (point1_enabled) lighting += point_light(normal, view_dir, surface, point1_position, point1_color, point1_intensity, point1_range);
                    if (point2_enabled) lighting += point_light(normal, view_dir, surface, point2_position, point2_color, point2_intensity, point2_range);
                    if (point3_enabled) lighting += point_light(normal, view_dir, surface, point3_position, point3_color, point3_intensity, point3_range);

                    if (spot0_enabled) lighting += spot_light(normal, view_dir, surface, spot0_position, spot0_direction, spot0_color, spot0_intensity, spot0_range, spot0_inner_cos, spot0_outer_cos);
                    if (spot1_enabled) lighting += spot_light(normal, view_dir, surface, spot1_position, spot1_direction, spot1_color, spot1_intensity, spot1_range, spot1_inner_cos, spot1_outer_cos);
                    if (spot2_enabled) lighting += spot_light(normal, view_dir, surface, spot2_position, spot2_direction, spot2_color, spot2_intensity, spot2_range, spot2_inner_cos, spot2_outer_cos);
                    if (spot3_enabled) lighting += spot_light(normal, view_dir, surface, spot3_position, spot3_direction, spot3_color, spot3_intensity, spot3_range, spot3_inner_cos, spot3_outer_cos);

                    fragColor = vec4(lighting, surface_rgba.a);
                }
            """,
        )
        self.program3d["image"].value = 0

        p = 0.5
        faces = (
            ((0, 0, 1), ((-p, -p, p), (p, -p, p), (p, p, p), (-p, p, p))),
            ((0, 0, -1), ((p, -p, -p), (-p, -p, -p), (-p, p, -p), (p, p, -p))),
            ((1, 0, 0), ((p, -p, p), (p, -p, -p), (p, p, -p), (p, p, p))),
            ((-1, 0, 0), ((-p, -p, -p), (-p, -p, p), (-p, p, p), (-p, p, -p))),
            ((0, 1, 0), ((-p, p, p), (p, p, p), (p, p, -p), (-p, p, -p))),
            ((0, -1, 0), ((-p, -p, -p), (p, -p, -p), (p, -p, p), (-p, -p, p))),
        )
        quad_uvs = ((0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0))
        indices = (0, 1, 2, 0, 2, 3)
        vertices: list[float] = []
        for normal, positions in faces:
            for index in indices:
                vertices.extend((*positions[index], *normal, *quad_uvs[index]))
        self.vbo3d = self.ctx.buffer(np.asarray(vertices, dtype="f4").tobytes())
        self.vao3d = self.ctx.vertex_array(
            self.program3d,
            [(self.vbo3d, "3f 3f 2f", "in_pos", "in_normal", "in_uv")],
        )

    @staticmethod
    def _write_mat4(uniform, matrix: np.ndarray) -> None:
        uniform.write(np.asarray(matrix, dtype="f4").T.tobytes())

    def _texture(self, path: str | Path) -> tuple[object, int, int]:
        key = str(Path(path).expanduser().resolve())
        cached = self._textures.get(key)
        if cached is not None:
            return cached
        from PIL import Image

        with Image.open(key) as source:
            image = source.convert("RGBA").transpose(Image.Transpose.FLIP_TOP_BOTTOM)
            width, height = image.size
            texture = self.ctx.texture((width, height), 4, image.tobytes())
        texture.build_mipmaps()
        texture.filter = (self.ctx.LINEAR_MIPMAP_LINEAR, self.ctx.LINEAR)
        cached = (texture, width, height)
        self._textures[key] = cached
        self.stats.texture_uploads += 1
        return cached

    def _text_texture(self, obj: Text2D) -> tuple[object, int, int]:
        font_key = str(obj.font) if obj.font is not None else ""
        key = (obj.text, font_key, max(1, int(obj.font_size)))
        cached = self._text_textures.get(key)
        if cached is not None:
            self._text_textures.move_to_end(key)
            return cached
        from PIL import Image, ImageDraw, ImageFont

        size = key[2]
        try:
            font = ImageFont.truetype(font_key or "DejaVuSans.ttf", size)
        except OSError:
            font = ImageFont.load_default()
        sample = obj.text or " "
        scratch = Image.new("RGBA", (1, 1), (0, 0, 0, 0))
        bbox = ImageDraw.Draw(scratch).textbbox((0, 0), sample, font=font)
        width = max(1, bbox[2] - bbox[0])
        height = max(1, bbox[3] - bbox[1])
        image = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        ImageDraw.Draw(image).text(
            (-bbox[0], -bbox[1]), sample, font=font, fill=(255, 255, 255, 255)
        )
        image = image.transpose(Image.Transpose.FLIP_TOP_BOTTOM)
        texture = self.ctx.texture((width, height), 4, image.tobytes())
        texture.filter = (self.ctx.LINEAR, self.ctx.LINEAR)
        cached = (texture, width, height)
        self._text_textures[key] = cached
        self.stats.text_uploads += 1
        while len(self._text_textures) > self.text_cache_limit:
            _, (old_texture, _, _) = self._text_textures.popitem(last=False)
            old_texture.release()
        return cached

    @staticmethod
    def _center(
        obj: Rectangle2D | Sprite2D | Text2D,
        camera: Camera2D,
    ) -> tuple[float, float]:
        x, y = float(obj.x), float(obj.y)
        return (x, y) if obj.screen_space else (x - camera.x, y - camera.y)

    @staticmethod
    def _sprite_vertices(
        batch: SpriteBatch,
        image_width: int,
        image_height: int,
        camera: Camera2D,
    ) -> np.ndarray:
        values: list[float] = []
        for sprite in batch.sprites:
            width = float(sprite.width if sprite.width is not None else image_width)
            height = float(sprite.height if sprite.height is not None else image_height)
            center_x, center_y = Renderer._center(sprite, camera)
            angle = math.radians(float(sprite.rotation))
            cos_angle, sin_angle = math.cos(angle), math.sin(angle)
            u0, v0, u1, v1 = map(float, sprite.uv_rect)
            tint = sprite.tint.clamped()
            vertices = (
                (-0.5, -0.5, u0, v0),
                (0.5, -0.5, u1, v0),
                (0.5, 0.5, u1, v1),
                (-0.5, -0.5, u0, v0),
                (0.5, 0.5, u1, v1),
                (-0.5, 0.5, u0, v1),
            )
            for local_x, local_y, u, v in vertices:
                scaled_x, scaled_y = local_x * width, local_y * height
                world_x = cos_angle * scaled_x - sin_angle * scaled_y + center_x
                world_y = sin_angle * scaled_x + cos_angle * scaled_y + center_y
                values.extend((world_x, world_y, u, v, tint.r, tint.g, tint.b, tint.a))
        return np.asarray(values, dtype="f4")

    def render(
        self,
        scene,
        *,
        camera: Camera2D | Camera3D | None = None,
        clear_color=(0.035, 0.045, 0.07, 1.0),
    ) -> None:
        self.stats.reset()
        self.ctx.clear(*clear_color)
        if self.mode == "3d":
            active = camera if isinstance(camera, Camera3D) else Camera3D()
            self._render_3d(scene, active)
        else:
            active_2d = camera if isinstance(camera, Camera2D) else Camera2D()
            self._render_2d(scene, active_2d)
        self.stats.texture_cache_entries = len(self._textures)
        self.stats.text_cache_entries = len(self._text_textures)

    def _render_sprite_batch(
        self,
        batch: SpriteBatch,
        camera: Camera2D,
        projection: np.ndarray,
        screen_projection: np.ndarray,
    ) -> None:
        texture, image_width, image_height = self._texture(batch.key.texture)
        current = screen_projection if batch.key.screen_space else projection
        vertices = self._sprite_vertices(batch, image_width, image_height, camera)
        count = len(batch.sprites)
        self._ensure_sprite_batch_capacity(count)
        self.sprite_batch_vbo.write(vertices.tobytes())
        self._write_mat4(self.sprite_batch_program["projection"], current)
        texture.use(location=0)
        self.sprite_batch_vao.render(vertices=count * 6)
        self.stats.draw_calls += 1
        self.stats.sprites += count
        self.stats.sprite_batches += 1
        self.stats.triangles += count * 2

    def _render_2d(self, scene, camera: Camera2D) -> None:
        self.ctx.enable(self.ctx.BLEND)
        self.ctx.blend_func = self.ctx.SRC_ALPHA, self.ctx.ONE_MINUS_SRC_ALPHA
        projection = orthographic(
            self.width / camera.safe_zoom,
            self.height / camera.safe_zoom,
        )
        screen_projection = orthographic(self.width, self.height)
        objects = sorted(scene.objects, key=lambda item: getattr(item, "layer", 0))

        for item in build_render_runs(objects):
            if isinstance(item, SpriteBatch):
                self._render_sprite_batch(item, camera, projection, screen_projection)
                continue
            obj = item
            current = screen_projection if obj.screen_space else projection
            if isinstance(obj, Rectangle2D):
                self._write_mat4(self.program2d["projection"], current)
                self.program2d["center"].value = self._center(obj, camera)
                self.program2d["size"].value = (float(obj.width), float(obj.height))
                self.program2d["angle"].value = math.radians(float(obj.rotation))
                color = obj.color.clamped()
                self.program2d["color"].value = (color.r, color.g, color.b, color.a)
                self.vao2d.render()
                self.stats.draw_calls += 1
                self.stats.rectangles += 1
                self.stats.triangles += 2
            elif isinstance(obj, Text2D):
                texture, width, height = self._text_texture(obj)
                self._write_mat4(self.sprite_program["projection"], current)
                self.sprite_program["center"].value = self._center(obj, camera)
                self.sprite_program["size"].value = (width * obj.scale, height * obj.scale)
                self.sprite_program["angle"].value = 0.0
                color = obj.color.clamped()
                self.sprite_program["tint"].value = (color.r, color.g, color.b, color.a)
                self.sprite_program["uv_rect"].value = (0.0, 0.0, 1.0, 1.0)
                texture.use(location=0)
                self.sprite_vao.render()
                self.stats.draw_calls += 1
                self.stats.texts += 1
                self.stats.triangles += 2
        self.ctx.disable(self.ctx.BLEND)

    def _gpu_mesh(self, obj: Mesh3D) -> tuple[object, int]:
        key = id(obj.mesh)
        cached = self._mesh_gpu.get(key)
        if cached is None:
            data = obj.mesh.interleaved(include_uvs=True)
            vbo = self.ctx.buffer(data.tobytes())
            vao = self.ctx.vertex_array(
                self.program3d,
                [(vbo, "3f 3f 2f", "in_pos", "in_normal", "in_uv")],
            )
            cached = (vbo, vao, obj.mesh.vertex_count)
            self._mesh_gpu[key] = cached
            self.stats.mesh_uploads += 1
        return cached[1], cached[2]

    @staticmethod
    def _combined_color(instance: Color, material: Material3D | None) -> Color:
        if material is None:
            return instance.clamped()
        tint = material.tint.clamped()
        color = instance.clamped()
        return Color(
            color.r * tint.r,
            color.g * tint.g,
            color.b * tint.b,
            color.a * tint.a,
        )

    def _set_directional_light(self, slot: int, light: DirectionalLight3D | None) -> None:
        prefix = f"dir{slot}"
        self.program3d[f"{prefix}_enabled"].value = light is not None
        if light is None:
            return
        direction = light.direction.normalized()
        color = light.color.clamped()
        self.program3d[f"{prefix}_direction"].value = (
            direction.x,
            direction.y,
            direction.z,
        )
        self.program3d[f"{prefix}_color"].value = (color.r, color.g, color.b)
        self.program3d[f"{prefix}_intensity"].value = float(light.intensity)

    def _set_point_light(self, slot: int, light: PointLight3D | None) -> None:
        prefix = f"point{slot}"
        self.program3d[f"{prefix}_enabled"].value = light is not None
        if light is None:
            return
        color = light.color.clamped()
        self.program3d[f"{prefix}_position"].value = (
            light.position.x,
            light.position.y,
            light.position.z,
        )
        self.program3d[f"{prefix}_color"].value = (color.r, color.g, color.b)
        self.program3d[f"{prefix}_intensity"].value = float(light.intensity)
        self.program3d[f"{prefix}_range"].value = float(light.range)

    def _set_spot_light(self, slot: int, light: SpotLight3D | None) -> None:
        prefix = f"spot{slot}"
        self.program3d[f"{prefix}_enabled"].value = light is not None
        if light is None:
            return
        direction = light.direction.normalized()
        color = light.color.clamped()
        self.program3d[f"{prefix}_position"].value = (
            light.position.x,
            light.position.y,
            light.position.z,
        )
        self.program3d[f"{prefix}_direction"].value = (
            direction.x,
            direction.y,
            direction.z,
        )
        self.program3d[f"{prefix}_color"].value = (color.r, color.g, color.b)
        self.program3d[f"{prefix}_intensity"].value = float(light.intensity)
        self.program3d[f"{prefix}_range"].value = float(light.range)
        self.program3d[f"{prefix}_inner_cos"].value = math.cos(math.radians(light.inner_angle))
        self.program3d[f"{prefix}_outer_cos"].value = math.cos(math.radians(light.outer_angle))

    def _configure_lights(self, scene, camera: Camera3D) -> None:
        selection = select_lights(scene.objects)
        self.stats.directional_lights = len(selection.directional)
        self.stats.point_lights = len(selection.point)
        self.stats.spot_lights = len(selection.spot)
        self.stats.lights_dropped = selection.dropped

        self.program3d["view_position"].value = (
            float(camera.position.x),
            float(camera.position.y),
            float(camera.position.z),
        )

        for slot in range(MAX_DIRECTIONAL_LIGHTS):
            light = selection.directional[slot] if slot < len(selection.directional) else None
            self._set_directional_light(slot, light)
        for slot in range(MAX_POINT_LIGHTS):
            light = selection.point[slot] if slot < len(selection.point) else None
            self._set_point_light(slot, light)
        for slot in range(MAX_SPOT_LIGHTS):
            light = selection.spot[slot] if slot < len(selection.spot) else None
            self._set_spot_light(slot, light)

    def _render_model(
        self,
        vao,
        model: np.ndarray,
        view_projection: np.ndarray,
        color: Color,
        *,
        vertices: int,
        material: Material3D | None = None,
    ) -> None:
        self._write_mat4(self.program3d["model"], model)
        self._write_mat4(self.program3d["mvp"], view_projection @ model)
        combined = self._combined_color(color, material)
        self.program3d["color"].value = (combined.r, combined.g, combined.b, combined.a)

        ambient = material.ambient if material is not None else 0.25
        diffuse = material.diffuse if material is not None else 0.75
        specular = material.specular if material is not None else 0.0
        shininess = material.shininess if material is not None else 32.0
        self.program3d["ambient_strength"].value = float(ambient)
        self.program3d["diffuse_strength"].value = float(diffuse)
        self.program3d["specular_strength"].value = float(specular)
        self.program3d["shininess"].value = float(shininess)

        texture_path = material.texture if material is not None else None
        self.program3d["use_texture"].value = texture_path is not None
        if texture_path is not None:
            texture, _, _ = self._texture(texture_path)
            texture.use(location=0)

        vao.render(vertices=vertices)
        self.stats.draw_calls += 1
        self.stats.triangles += vertices // 3

    def _render_3d(self, scene, camera: Camera3D) -> None:
        self.ctx.enable(self.ctx.DEPTH_TEST)
        projection = perspective(
            float(camera.fov),
            self.width / max(1, self.height),
            float(camera.near),
            float(camera.far),
        )
        view_projection = projection @ camera.view_matrix()
        self._configure_lights(scene, camera)
        for obj in scene.objects:
            if not getattr(obj, "enabled", True) or not getattr(obj, "visible", True):
                continue
            if isinstance(obj, Cube3D):
                self._render_model(
                    self.vao3d,
                    obj.transform.matrix(),
                    view_projection,
                    obj.color,
                    vertices=36,
                )
                self.stats.cubes += 1
            elif isinstance(obj, Mesh3D):
                vao, vertex_count = self._gpu_mesh(obj)
                self._render_model(
                    vao,
                    obj.transform.matrix(),
                    view_projection,
                    obj.color,
                    vertices=vertex_count,
                    material=obj.material,
                )
                self.stats.meshes += 1
        self.ctx.disable(self.ctx.DEPTH_TEST)

    def release(self) -> None:
        for texture, _, _ in self._textures.values():
            texture.release()
        self._textures.clear()
        for texture, _, _ in self._text_textures.values():
            texture.release()
        self._text_textures.clear()
        for vbo, vao, _ in self._mesh_gpu.values():
            vao.release()
            vbo.release()
        self._mesh_gpu.clear()
        self.sprite_batch_vao.release()
        self.sprite_batch_vbo.release()
        self.vao3d.release()
        self.vbo3d.release()
        self.sprite_vao.release()
        self.sprite_vbo.release()
        self.vao2d.release()
        self.vbo2d.release()
