from __future__ import annotations

import math
import numpy as np

from ..math.types import orthographic, perspective
from .primitives import Rectangle2D, Cube3D


class Renderer:
    def __init__(self, ctx, width: int, height: int, mode: str = "2d") -> None:
        self.ctx = ctx
        self.width = width
        self.height = height
        self.mode = mode
        self._init_2d()
        self._init_3d()

    def resize(self, width: int, height: int) -> None:
        self.width = max(1, width)
        self.height = max(1, height)
        self.ctx.viewport = (0, 0, self.width, self.height)

    def _init_2d(self) -> None:
        self.program2d = self.ctx.program(vertex_shader='''#version 330
in vec2 in_pos;
uniform mat4 projection;
uniform vec2 center;
uniform vec2 size;
uniform float angle;
void main(){float c=cos(angle);float s=sin(angle);vec2 p=in_pos*size;p=vec2(c*p.x-s*p.y,s*p.x+c*p.y);p+=center;gl_Position=projection*vec4(p,0.0,1.0);}''', fragment_shader='''#version 330
uniform vec4 color;
out vec4 fragColor;
void main(){fragColor=color;}''')
        quad = np.array([-0.5,-0.5, 0.5,-0.5, 0.5,0.5, -0.5,-0.5, 0.5,0.5, -0.5,0.5], dtype="f4")
        self.vbo2d = self.ctx.buffer(quad.tobytes())
        self.vao2d = self.ctx.simple_vertex_array(self.program2d, self.vbo2d, "in_pos")

    def _init_3d(self) -> None:
        self.program3d = self.ctx.program(vertex_shader='''#version 330
in vec3 in_pos; in vec3 in_normal; uniform mat4 mvp; uniform mat4 model; out vec3 v_normal;
void main(){gl_Position=mvp*vec4(in_pos,1.0);v_normal=mat3(model)*in_normal;}''', fragment_shader='''#version 330
uniform vec4 color; in vec3 v_normal; out vec4 fragColor;
void main(){vec3 n=normalize(v_normal);vec3 l=normalize(vec3(0.4,0.8,0.6));float d=max(dot(n,l),0.0);float k=0.25+0.75*d;fragColor=vec4(color.rgb*k,color.a);}''')
        p = 0.5
        faces = [
            ((0,0,1),[(-p,-p,p),(p,-p,p),(p,p,p),(-p,-p,p),(p,p,p),(-p,p,p)]),
            ((0,0,-1),[(p,-p,-p),(-p,-p,-p),(-p,p,-p),(p,-p,-p),(-p,p,-p),(p,p,-p)]),
            ((1,0,0),[(p,-p,p),(p,-p,-p),(p,p,-p),(p,-p,p),(p,p,-p),(p,p,p)]),
            ((-1,0,0),[(-p,-p,-p),(-p,-p,p),(-p,p,p),(-p,-p,-p),(-p,p,p),(-p,p,-p)]),
            ((0,1,0),[(-p,p,p),(p,p,p),(p,p,-p),(-p,p,p),(p,p,-p),(-p,p,-p)]),
            ((0,-1,0),[(-p,-p,-p),(p,-p,-p),(p,-p,p),(-p,-p,-p),(p,-p,p),(-p,-p,p)]),
        ]
        verts = []
        for normal, positions in faces:
            for pos in positions:
                verts.extend((*pos, *normal))
        cube = np.array(verts, dtype="f4")
        self.vbo3d = self.ctx.buffer(cube.tobytes())
        self.vao3d = self.ctx.vertex_array(self.program3d, [(self.vbo3d, "3f 3f", "in_pos", "in_normal")])

    @staticmethod
    def _write_mat4(uniform, matrix: np.ndarray) -> None:
        uniform.write(np.asarray(matrix, dtype="f4").T.tobytes())

    def render(self, scene, clear_color=(0.035, 0.045, 0.07, 1.0)) -> None:
        self.ctx.clear(*clear_color)
        self._render_3d(scene) if self.mode == "3d" else self._render_2d(scene)

    def _render_2d(self, scene) -> None:
        self._write_mat4(self.program2d["projection"], orthographic(self.width, self.height))
        for obj in scene.objects:
            if not isinstance(obj, Rectangle2D) or not obj.enabled:
                continue
            self.program2d["center"].value = (float(obj.x), float(obj.y))
            self.program2d["size"].value = (float(obj.width), float(obj.height))
            self.program2d["angle"].value = math.radians(float(obj.rotation))
            c = obj.color.clamped()
            self.program2d["color"].value = (c.r, c.g, c.b, c.a)
            self.vao2d.render()

    def _render_3d(self, scene) -> None:
        self.ctx.enable(self.ctx.DEPTH_TEST)
        proj = perspective(60.0, self.width / max(1, self.height), 0.1, 100.0)
        view = np.eye(4, dtype="f4")
        for obj in scene.objects:
            if not isinstance(obj, Cube3D) or not obj.enabled:
                continue
            model = obj.transform.matrix()
            self._write_mat4(self.program3d["model"], model)
            self._write_mat4(self.program3d["mvp"], proj @ view @ model)
            c = obj.color.clamped()
            self.program3d["color"].value = (c.r, c.g, c.b, c.a)
            self.vao3d.render()
        self.ctx.disable(self.ctx.DEPTH_TEST)
