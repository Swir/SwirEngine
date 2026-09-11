from __future__ import annotations

import math
from pathlib import Path

import numpy as np

from ..math.types import orthographic, perspective
from .camera import Camera2D
from .primitives import Cube3D, Rectangle2D, Sprite2D


class Renderer:
    def __init__(self, ctx, width: int, height: int, mode: str = "2d") -> None:
        self.ctx = ctx
        self.width = width
        self.height = height
        self.mode = mode
        self._textures: dict[str, tuple[object, int, int]] = {}
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
                out vec2 v_uv;
                void main() {
                    float c = cos(angle);
                    float s = sin(angle);
                    vec2 p = in_pos * size;
                    p = vec2(c*p.x - s*p.y, s*p.x + c*p.y) + center;
                    gl_Position = projection * vec4(p, 0.0, 1.0);
                    v_uv = in_uv;
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
            ((0, 0, -1), [(p, -p, -p), (-p, -p, -p), (-p, p, -p), (p, -p, -p), (-p, p, -p), (p, p, -p)]),
            ((1, 0, 0), [(p, -p, p), (p, -p, -p), (p, p, -p), (p, -p, p), (p, p, -p), (p, p, p)]),
            ((-1, 0, 0), [(-p, -p, -p), (-p, -p, p), (-p, p, p), (-p, -p, -p), (-p, p, p), (-p, p, -p)]),
            ((0, 1, 0), [(-p, p, p), (p, p, p), (p, p, -p), (-p, p, p), (p, p, -p), (-p, p, -p)]),
            ((0, -1, 0), [(-p, -p, -p), (p, -p, -p), (p, -p, p), (-p, -p, -p), (p, -p, p), (-p, -p, p)]),
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
        self._write_mat4(self.program2d["projection"], projection)
        self._write_mat4(self.sprite_program["projection"], projection)

        for obj in scene.objects:
            if not getattr(obj, "enabled", True) or not getattr(obj, "visible", True):
                continue

            if isinstance(obj, Rectangle2D):
                self.program2d["center"].value = (
                    float(obj.x - camera.x),
                    float(obj.y - camera.y),
                )
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
                self.sprite_program["center"].value = (
                    float(obj.x - camera.x),
                    float(obj.y - camera.y),
                )
                self.sprite_program["size"].value = (width, height)
                self.sprite_program["angle"].value = math.radians(float(obj.rotation))
                tint = obj.tint.clamped()
                self.sprite_program["tint"].value = (tint.r, tint.g, tint.b, tint.a)
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
