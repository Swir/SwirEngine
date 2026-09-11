from __future__ import annotations

import math
from collections import OrderedDict
from pathlib import Path

import numpy as np

from ..math.types import Color, orthographic, perspective
from .batching import SpriteBatch, build_render_runs
from .camera import Camera2D
from .camera3d import Camera3D
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
                out vec2 v_uv;
                void main() {
                    gl_Position = mvp * vec4(in_pos, 1.0);
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
                in vec3 v_normal;
                in vec2 v_uv;
                out vec4 fragColor;
                void main() {
                    vec3 n = normalize(v_normal);
                    float d = max(dot(n, normalize(vec3(0.4, 0.8, 0.6))), 0.0);
                    vec4 surface = color;
                    if (use_texture) {
                        surface *= texture(image, v_uv);
                    }
                    float light = ambient_strength + diffuse_strength * d;
                    fragColor = vec4(surface.rgb * light, surface.a);
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
        self.program3d["ambient_strength"].value = float(ambient)
        self.program3d["diffuse_strength"].value = float(diffuse)

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
