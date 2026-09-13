from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from ..math.types import Vec3
from .lights import DirectionalLight3D
from .mesh import Mesh3D


@dataclass(frozen=True, slots=True)
class DirectionalShadowSettings:
    """Configuration for one directional-light shadow map."""

    resolution: int = 2048
    extent: float = 24.0
    distance: float = 32.0
    near: float = 0.1
    far: float = 80.0
    bias: float = 0.0015
    normal_bias: float = 0.003

    def __post_init__(self) -> None:
        if int(self.resolution) < 64:
            raise ValueError("shadow resolution must be at least 64")
        if float(self.extent) <= 0.0:
            raise ValueError("shadow extent must be greater than 0")
        if float(self.distance) <= 0.0:
            raise ValueError("shadow distance must be greater than 0")
        if float(self.near) <= 0.0 or float(self.far) <= float(self.near):
            raise ValueError("shadow planes must satisfy 0 < near < far")
        if float(self.bias) < 0.0 or float(self.normal_bias) < 0.0:
            raise ValueError("shadow bias values cannot be negative")


@dataclass(frozen=True, slots=True)
class DirectionalShadowFrame:
    """Matrices and light direction used by a directional shadow pass."""

    view: np.ndarray
    projection: np.ndarray
    view_projection: np.ndarray
    light_direction: Vec3


def _normalize(value: np.ndarray) -> np.ndarray:
    length = float(np.linalg.norm(value))
    if length <= 1e-8:
        raise ValueError("cannot normalize a zero vector")
    return value / length


def _look_at(eye: np.ndarray, target: np.ndarray, up: np.ndarray) -> np.ndarray:
    forward = _normalize(target - eye)
    side = np.cross(forward, up)
    if float(np.linalg.norm(side)) <= 1e-8:
        fallback = np.array((0.0, 0.0, 1.0), dtype="f4")
        side = np.cross(forward, fallback)
    side = _normalize(side)
    corrected_up = np.cross(side, forward)

    matrix = np.eye(4, dtype="f4")
    matrix[0, :3] = side
    matrix[1, :3] = corrected_up
    matrix[2, :3] = -forward
    matrix[0, 3] = -float(np.dot(side, eye))
    matrix[1, 3] = -float(np.dot(corrected_up, eye))
    matrix[2, 3] = float(np.dot(forward, eye))
    return matrix


def _orthographic_shadow(extent: float, near: float, far: float) -> np.ndarray:
    size = float(extent)
    matrix = np.eye(4, dtype="f4")
    matrix[0, 0] = 1.0 / size
    matrix[1, 1] = 1.0 / size
    matrix[2, 2] = -2.0 / (far - near)
    matrix[2, 3] = -(far + near) / (far - near)
    return matrix


def directional_shadow_frame(
    light: DirectionalLight3D,
    focus: Vec3,
    settings: DirectionalShadowSettings | None = None,
) -> DirectionalShadowFrame:
    """Build a stable orthographic light camera around a world-space focus point."""

    config = settings or DirectionalShadowSettings()
    direction = light.direction.normalized()
    direction_array = np.array((direction.x, direction.y, direction.z), dtype="f4")
    focus_array = np.array((focus.x, focus.y, focus.z), dtype="f4")
    eye = focus_array - direction_array * float(config.distance)
    view = _look_at(eye, focus_array, np.array((0.0, 1.0, 0.0), dtype="f4"))
    projection = _orthographic_shadow(config.extent, config.near, config.far)
    return DirectionalShadowFrame(
        view=view,
        projection=projection,
        view_projection=projection @ view,
        light_direction=direction,
    )


class DirectionalShadowMap:
    """GPU depth-map pass for Mesh3D directional-light shadow casters.

    The class intentionally owns an isolated position-only mesh cache so the main renderer can
    integrate the generated depth texture without coupling shadow rendering to material shaders.
    """

    def __init__(self, ctx, settings: DirectionalShadowSettings | None = None) -> None:
        self.ctx = ctx
        self.settings = settings or DirectionalShadowSettings()
        self.depth_texture = None
        self.framebuffer = None
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

    def _ensure_target(self) -> None:
        if self.depth_texture is not None:
            return
        resolution = int(self.settings.resolution)
        self.depth_texture = self.ctx.depth_texture((resolution, resolution))
        self.depth_texture.repeat_x = False
        self.depth_texture.repeat_y = False
        if hasattr(self.depth_texture, "compare_func"):
            self.depth_texture.compare_func = ""
        self.framebuffer = self.ctx.framebuffer(depth_attachment=self.depth_texture)

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

    @staticmethod
    def _write_mat4(uniform, matrix: np.ndarray) -> None:
        uniform.write(np.asarray(matrix, dtype="f4").T.tobytes())

    def render(
        self,
        scene,
        light: DirectionalLight3D,
        *,
        focus: Vec3 | None = None,
    ) -> DirectionalShadowFrame:
        """Render visible Mesh3D objects into the depth map and return the light frame."""

        if self._released:
            raise RuntimeError("shadow map has been released")
        self._ensure_target()
        frame = directional_shadow_frame(light, focus or Vec3(), self.settings)
        previous_viewport = self.ctx.viewport
        self.framebuffer.use()
        resolution = int(self.settings.resolution)
        self.ctx.viewport = (0, 0, resolution, resolution)
        self.framebuffer.clear(depth=1.0)
        self.ctx.enable(self.ctx.DEPTH_TEST)
        try:
            for obj in scene.objects:
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
        return frame

    def use(self, location: int = 5) -> None:
        """Bind the generated depth texture for sampling by a lighting shader."""

        if self.depth_texture is None:
            raise RuntimeError("shadow map has not been rendered yet")
        self.depth_texture.use(location=int(location))

    def release(self) -> None:
        if self._released:
            return
        for vbo, vao, _ in self._mesh_gpu.values():
            vao.release()
            vbo.release()
        self._mesh_gpu.clear()
        if self.framebuffer is not None:
            self.framebuffer.release()
            self.framebuffer = None
        if self.depth_texture is not None:
            self.depth_texture.release()
            self.depth_texture = None
        self.program.release()
        self._released = True
