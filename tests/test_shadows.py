from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import pytest

from swirengine.graphics.lights import DirectionalLight3D
from swirengine.graphics.mesh import Mesh3D, cube_mesh
from swirengine.graphics.shadows import (
    DirectionalShadowMap,
    DirectionalShadowSettings,
    directional_shadow_frame,
)
from swirengine.math.types import Vec3


class _Uniform:
    def __init__(self) -> None:
        self.data = b""

    def write(self, data: bytes) -> None:
        self.data = data


class _Program:
    def __init__(self) -> None:
        self.uniform = _Uniform()
        self.released = False

    def __getitem__(self, name: str):
        assert name == "light_mvp"
        return self.uniform

    def release(self) -> None:
        self.released = True


class _Resource:
    def __init__(self) -> None:
        self.released = False
        self.used_locations: list[int] = []

    def release(self) -> None:
        self.released = True

    def use(self, location: int = 0) -> None:
        self.used_locations.append(location)


class _DepthTexture(_Resource):
    def __init__(self, size: tuple[int, int]) -> None:
        super().__init__()
        self.size = size
        self.repeat_x = True
        self.repeat_y = True


class _Framebuffer(_Resource):
    def __init__(self, depth_attachment: _DepthTexture) -> None:
        super().__init__()
        self.depth_attachment = depth_attachment
        self.clear_depths: list[float] = []
        self.use_count = 0

    def use(self) -> None:
        self.use_count += 1

    def clear(self, *, depth: float) -> None:
        self.clear_depths.append(depth)


class _Vao(_Resource):
    def __init__(self) -> None:
        super().__init__()
        self.render_counts: list[int] = []

    def render(self, *, vertices: int) -> None:
        self.render_counts.append(vertices)


class _Ctx:
    DEPTH_TEST = 1

    def __init__(self) -> None:
        self.viewport = (0, 0, 800, 600)
        self.program_obj = _Program()
        self.depth_textures: list[_DepthTexture] = []
        self.framebuffers: list[_Framebuffer] = []
        self.vaos: list[_Vao] = []
        self.buffers: list[_Resource] = []
        self.enabled: list[int] = []

    def program(self, **_kwargs):
        return self.program_obj

    def depth_texture(self, size: tuple[int, int]):
        texture = _DepthTexture(size)
        self.depth_textures.append(texture)
        return texture

    def framebuffer(self, *, depth_attachment):
        framebuffer = _Framebuffer(depth_attachment)
        self.framebuffers.append(framebuffer)
        return framebuffer

    def buffer(self, _data: bytes):
        buffer = _Resource()
        self.buffers.append(buffer)
        return buffer

    def vertex_array(self, _program, _bindings):
        vao = _Vao()
        self.vaos.append(vao)
        return vao

    def enable(self, flag: int) -> None:
        self.enabled.append(flag)


def test_shadow_settings_validate_ranges() -> None:
    with pytest.raises(ValueError):
        DirectionalShadowSettings(resolution=32)
    with pytest.raises(ValueError):
        DirectionalShadowSettings(near=2.0, far=1.0)
    with pytest.raises(ValueError):
        DirectionalShadowSettings(bias=-0.1)


def test_directional_shadow_frame_is_finite_and_tracks_light_direction() -> None:
    light = DirectionalLight3D(direction=Vec3(-1.0, -2.0, -1.0))
    frame = directional_shadow_frame(light, Vec3(3.0, 1.0, -2.0))

    assert frame.view.shape == (4, 4)
    assert frame.projection.shape == (4, 4)
    assert frame.view_projection.shape == (4, 4)
    assert np.isfinite(frame.view_projection).all()
    assert frame.light_direction == light.direction.normalized()


def test_shadow_frame_handles_vertical_light_without_degenerate_view() -> None:
    light = DirectionalLight3D(direction=Vec3(0.0, -1.0, 0.0))
    frame = directional_shadow_frame(light, Vec3())
    assert np.isfinite(frame.view).all()
    assert abs(float(np.linalg.det(frame.view))) > 0.5


def test_directional_shadow_map_renders_visible_meshes_and_restores_viewport() -> None:
    ctx = _Ctx()
    shadow = DirectionalShadowMap(ctx, DirectionalShadowSettings(resolution=512))
    visible = Mesh3D(cube_mesh())
    hidden = Mesh3D(cube_mesh(), visible=False)
    scene = SimpleNamespace(objects=[visible, hidden, object()])

    shadow.render(scene, DirectionalLight3D())

    assert ctx.viewport == (0, 0, 800, 600)
    assert ctx.depth_textures[0].size == (512, 512)
    assert ctx.depth_textures[0].repeat_x is False
    assert ctx.depth_textures[0].repeat_y is False
    assert ctx.framebuffers[0].clear_depths == [1.0]
    assert ctx.vaos[0].render_counts == [visible.mesh.vertex_count]
    assert len(ctx.program_obj.uniform.data) == 64

    shadow.use(7)
    assert ctx.depth_textures[0].used_locations == [7]


def test_directional_shadow_map_reuses_mesh_gpu_resources_and_releases() -> None:
    ctx = _Ctx()
    shadow = DirectionalShadowMap(ctx)
    mesh = Mesh3D(cube_mesh())
    scene = SimpleNamespace(objects=[mesh])
    light = DirectionalLight3D()

    shadow.render(scene, light)
    shadow.render(scene, light)

    assert len(ctx.buffers) == 1
    assert len(ctx.vaos) == 1
    assert ctx.vaos[0].render_counts == [mesh.mesh.vertex_count, mesh.mesh.vertex_count]

    shadow.release()
    shadow.release()
    assert ctx.buffers[0].released is True
    assert ctx.vaos[0].released is True
    assert ctx.depth_textures[0].released is True
    assert ctx.framebuffers[0].released is True
    assert ctx.program_obj.released is True

    with pytest.raises(RuntimeError):
        shadow.render(scene, light)
