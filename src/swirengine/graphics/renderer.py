from __future__ import annotations

import math
from pathlib import Path

import numpy as np

from ..math.types import orthographic, perspective
from .camera import Camera2D
from .primitives import Cube3D, Rectangle2D, Sprite2D, Text2D


class Renderer:
    def __init__(self, ctx, width: int, height: int, mode: str = "2d") -> None:
        self.ctx = ctx
        self.width = width
        self.height = height
        self.mode = mode
        self._textures: dict[str, tuple[object, int, int]] = {}
        self._text_textures: dict[tuple[str, str, int], tuple[object, int, int]] = {}
        self._init_2d()
        self._init_3d()

    def resize(self, width: int, height: int) -> None:
        self.width = max(1, width)
        self.height = max(1, height)
        self.ctx.viewport = (0, 0, self.width, self.height)

    def _init_2d(self) -> None:
        vertex_shader = """
            #version 330
            in vec2 in_pos;
            uniform mat4 projection;
            uniform vec2 center;
            uniform vec2 size;
            uniform float angle;
            void main() {
                float c = cos(angle);
                float s = sin(angle);
                vec2 p = in_pos * size;
                p = vec2(c*p.x - s*p.y, s*p.x + c*p.y) + center;
                gl_Position = projection * vec4(p, 0.0, 1.0);
            }
        """
        self.program2d = self.ctx.program(
            vertex_shader=vertex_shader,
            fragment_shader="""
                #version 330
                uniform vec4 color;
                out vec4 fragColor;
                void main() { fragColor = color; }
            """,
        )
        quad = np.array(
            [
                -0.5, -0.5,
                 0.5, -0.5,
                 0.5,  0.5,
                -0.5, -0.5,
                 0.5,  0.5,
                -0.5,  0.5,
            ],
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
                    float c = cos(angle);
                    float s = sin(angle);
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
                void main() {
                    fragColor = texture(image, v_uv) * tint;
                }
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

    def _init_3d(self) -> None:
        self.program3d = self.ctx.program(
            vertex_shader="""
                #version 330
                in vec3 in_pos;
                in vec3 in_normal;
                uniform mat4 mvp;
                uniform mat4 model;
                out vec3 v_normal;
                void main() {
                    gl_Position = mvp * vec4(in_pos, 1.0);
                    v_normal = mat3(model) * in_normal;
                }
            """,
            fragment_shader="""
                #version 330
                uniform vec4 color;
                in vec3 v_normal;
                out vec4 fragColor;
                void main() {
                    vec3 n = normalize(v_normal);
                    vec3 lightDir = normalize(vec3(0.4, 0.8, 0.6));
                    float diffuse = max(dot(n, lightDir), 0.0);
                    float light = 0.25 + 0.75 * diffuse;
                    fragColor = vec4(color.rgb * light, color.a);
                }
            """,
        )
        p = 0.5
        faces = [
            ((0, 0, 1), [(-p, -p, p), (p, -p, p), (p, p, p), (-p, -p, p), (p, p, p), (-p, p, p)]),
            (
                (0, 0, -1),
                [
                    (p, -p, -p),
                    (-p, -p, -p),
                    (-p, p, -p),
                    (p, -p, -p),
                    (-p, p, -p),
                    (p, p, -p),
                ],
            ),
            ((1, 0, 0), [(p, -p, p), (p, -p, -p), (p, p, -p), (p, -p, p), (p, p, -p), (p, p, p)]),
            (
                (-1, 0, 0),
                [
                    (-p, -p, -p),
                    (-p, -p, p),
                    (-p, p, p),
                    (-p, -p, -p),
                    (-p, p, p),
                    (-p, p, -p),
                ],
            ),
            ((0, 1, 0), [(-p, p, p), (p, p, p), (p, p, -p), (-p, p, p), (p, p, -p), (-p, p, -p)]),
            (
                (0, -1, 0),
                [
                    (-p, -p, -p),
                    (p, -p, -p),
                    (p, -p, p),
                    (-p, -p, -p),
                    (p, -p, p),
                    (-p, -p, p),
                ],
            ),
        ]
        vertices: list[float] = []
        for normal, positions in faces:
            for pos in positions:
                vertices.extend((*pos, *normal))
        cube = np.array(vertices, dtype="f4")
        self.vbo3d = self.ctx.buffer(cube.tobytes())
        self.vao3d = self.ctx.vertex_array(
            self.program3d, [(self.vbo3d, "3f 3f", "in_pos", "in_normal")]
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
        return cached

    def _text_texture(self, obj: Text2D) -> tuple[object, int, int]:
        font_key = str(obj.font) if obj.font is not None else ""
        key = (obj.text, font_key, max(1, int(obj.font_size)))
        cached = self._text_textures.get(key)
        if cached is not None:
            return cached

        from PIL import Image, ImageDraw, ImageFont

        size = key[2]
        try:
            font = ImageFont.truetype(font_key or "DejaVuSans.ttf", size)
        except OSError:
            font = ImageFont.load_default()
        sample = obj.text if obj.text else " "
        scratch = Image.new("RGBA", (1, 1), (0, 0, 0, 0))
        draw = ImageDraw.Draw(scratch)
        bbox = draw.textbbox((0, 0), sample, font=font)
        width = max(1, bbox[2] - bbox[0])
        height = max(1, bbox[3] - bbox[1])
        image = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        draw = ImageDraw.Draw(image)
        draw.text((-bbox[0], -bbox[1]), sample, font=font, fill=(255, 255, 255, 255))
        image = image.transpose(Image.Transpose.FLIP_TOP_BOTTOM)
        texture = self.ctx.texture((width, height), 4, image.tobytes())
        texture.filter = (self.ctx.LINEAR, self.ctx.LINEAR)
        cached = (texture, width, height)
        self._text_textures[key] = cached
        return cached

    @staticmethod
    def _center(
        obj: Rectangle2D | Sprite2D | Text2D,
        camera: Camera2D,
    ) -> tuple[float, float]:
        x = float(obj.x)
        y = float(obj.y)
        if obj.screen_space:
            return x, y
        return x - camera.x, y - camera.y

    def render(
        self,
        scene,
        *,
        camera: Camera2D | None = None,
        clear_color=(0.035, 0.045, 0.07, 1.0),
    ) -> None:
        self.ctx.clear(*clear_color)
        if self.mode == "3d":
            self._render_3d(scene)
        else:
            self._render_2d(scene, camera or Camera2D())

    def _render_2d(self, scene, camera: Camera2D) -> None:
        self.ctx.enable(self.ctx.BLEND)
        self.ctx.blend_func = self.ctx.SRC_ALPHA, self.ctx.ONE_MINUS_SRC_ALPHA

        projection = orthographic(
            self.width / camera.safe_zoom,
            self.height / camera.safe_zoom,
        )
        screen_projection = orthographic(self.width, self.height)

        objects = sorted(scene.objects, key=lambda item: getattr(item, "layer", 0))
        for obj in objects:
            if not getattr(obj, "enabled", True) or not getattr(obj, "visible", True):
                continue

            current_projection = screen_projection if getattr(obj, "screen_space", False) else projection
            if isinstance(obj, Rectangle2D):
                self._write_mat4(self.program2d["projection"], current_projection)
                self.program2d["center"].value = self._center(obj, camera)
                self.program2d["size"].value = (float(obj.width), float(obj.height))
                self.program2d["angle"].value = math.radians(float(obj.rotation))
                color = obj.color.clamped()
                self.program2d["color"].value = (color.r, color.g, color.b, color.a)
                self.vao2d.render()
                continue

            if isinstance(obj, Sprite2D):
                texture, image_width, image_height = self._texture(obj.texture)
                width = float(obj.width if obj.width is not None else image_width)
                height = float(obj.height if obj.height is not None else image_height)
                self._write_mat4(self.sprite_program["projection"], current_projection)
                self.sprite_program["center"].value = self._center(obj, camera)
                self.sprite_program["size"].value = (width, height)
                self.sprite_program["angle"].value = math.radians(float(obj.rotation))
                tint = obj.tint.clamped()
                self.sprite_program["tint"].value = (tint.r, tint.g, tint.b, tint.a)
                self.sprite_program["uv_rect"].value = tuple(float(value) for value in obj.uv_rect)
                texture.use(location=0)
                self.sprite_vao.render()
                continue

            if isinstance(obj, Text2D):
                texture, text_width, text_height = self._text_texture(obj)
                self._write_mat4(self.sprite_program["projection"], current_projection)
                self.sprite_program["center"].value = self._center(obj, camera)
                self.sprite_program["size"].value = (
                    float(text_width) * obj.scale,
                    float(text_height) * obj.scale,
                )
                self.sprite_program["angle"].value = 0.0
                color = obj.color.clamped()
                self.sprite_program["tint"].value = (color.r, color.g, color.b, color.a)
                self.sprite_program["uv_rect"].value = (0.0, 0.0, 1.0, 1.0)
                texture.use(location=0)
                self.sprite_vao.render()

        self.ctx.disable(self.ctx.BLEND)

    def _render_3d(self, scene) -> None:
        self.ctx.enable(self.ctx.DEPTH_TEST)
        projection = perspective(60.0, self.width / max(1, self.height), 0.1, 100.0)
        view = np.eye(4, dtype="f4")
        for obj in scene.objects:
            if not isinstance(obj, Cube3D) or not obj.enabled or not obj.visible:
                continue
            model = obj.transform.matrix()
            self._write_mat4(self.program3d["model"], model)
            self._write_mat4(self.program3d["mvp"], projection @ view @ model)
            color = obj.color.clamped()
            self.program3d["color"].value = (color.r, color.g, color.b, color.a)
            self.vao3d.render()
        self.ctx.disable(self.ctx.DEPTH_TEST)

    def release(self) -> None:
        for texture, _width, _height in self._textures.values():
            texture.release()
        self._textures.clear()
        for texture, _width, _height in self._text_textures.values():
            texture.release()
        self._text_textures.clear()
