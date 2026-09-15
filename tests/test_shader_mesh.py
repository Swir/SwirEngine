from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pytest

from swirengine.graphics.camera3d import Camera3D
from swirengine.graphics.mesh import cube_mesh
from swirengine.graphics.shader_mesh import (
    ShaderMaterialRenderPipeline,
    ShaderMesh3D,
    shader_material_3d,
)
from swirengine.graphics.shader_pipeline import (
    ShaderMaterial3D,
    ShaderPipelineError,
    ShaderTemplate,
    prepare_shader_variant,
)
from swirengine.graphics.stats import RendererStats
from swirengine.math.types import Color, Vec3


class _Uniform:
    def __init__(self) -> None:
        self.value = None

    def write(self, value: bytes) -> None:
        self.value = value


class _Program:
    def __init__(self) -> None:
        names = (
            "mvp",
            "model",
            "color",
            "directional_enabled",
            "directional_direction",
            "directional_color",
            "directional_intensity",
            "pulse",
        )
        self.uniforms = {name: _Uniform() for name in names}
        self.released = False

    def __getitem__(self, name: str) -> _Uniform:
        return self.uniforms[name]

    def release(self) -> None:
        self.released = True


class _Buffer:
    def __init__(self, data: bytes) -> None:
        self.data = data
        self.released = False

    def release(self) -> None:
        self.released = True


class _VAO:
    def __init__(self) -> None:
        self.render_calls = 0
        self.released = False

    def render(self, *, vertices: int) -> None:
        assert vertices == 36
        self.render_calls += 1

    def release(self) -> None:
        self.released = True


class _Context:
    DEPTH_TEST = 1

    def __init__(self) -> None:
        self.program_calls = 0
        self.buffer_calls = 0
        self.vao_calls = 0
        self.enabled: set[int] = set()
        self.programs: list[_Program] = []
        self.buffers: list[_Buffer] = []
        self.vaos: list[_VAO] = []

    def program(self, *, vertex_shader: str, fragment_shader: str) -> _Program:
        assert "SWIR_HOOK" not in vertex_shader
        assert "SWIR_HOOK" not in fragment_shader
        self.program_calls += 1
        program = _Program()
        self.programs.append(program)
        return program

    def buffer(self, data: bytes) -> _Buffer:
        self.buffer_calls += 1
        buffer = _Buffer(data)
        self.buffers.append(buffer)
        return buffer

    def vertex_array(self, program, content, *, skip_errors=False) -> _VAO:
        assert program in self.programs
        assert content
        assert skip_errors is True
        self.vao_calls += 1
        vao = _VAO()
        self.vaos.append(vao)
        return vao

    def enable(self, flag: int) -> None:
        self.enabled.add(flag)

    def disable(self, flag: int) -> None:
        self.enabled.discard(flag)


@dataclass
class _Host:
    ctx: _Context
    width: int = 1280
    height: int = 720

    def __post_init__(self) -> None:
        self.stats = RendererStats()

    @staticmethod
    def _write_mat4(uniform: _Uniform, matrix: object) -> None:
        uniform.write(np.asarray(matrix, dtype="f4").tobytes())


class _Scene:
    def __init__(self, objects) -> None:
        self.objects = list(objects)


def test_two_shader_meshes_share_program_vertex_buffer_and_vao():
    ctx = _Context()
    host = _Host(ctx)
    pipeline = ShaderMaterialRenderPipeline(host)
    mesh = cube_mesh()
    material = shader_material_3d(
        hooks={
            "fragment_globals": "uniform float pulse;",
            "fragment_surface": "surface_rgba.rgb *= vec3(pulse, 1.0, 0.5);",
        },
        uniforms={"pulse": 0.75},
    )
    scene = _Scene(
        (
            ShaderMesh3D(mesh, material, position=Vec3(-1.0, 0.0, -4.0)),
            ShaderMesh3D(mesh, material, position=Vec3(1.0, 0.0, -4.0)),
        )
    )

    pipeline.render(scene, Camera3D())

    assert ctx.program_calls == 1
    assert ctx.buffer_calls == 1
    assert ctx.vao_calls == 1
    assert pipeline.diagnostics.cache_misses == 1
    assert pipeline.diagnostics.cache_hits == 1
    assert host.stats.mesh_uploads == 1
    assert host.stats.shader_meshes == 2
    assert host.stats.draw_calls == 2
    assert ctx.programs[0]["pulse"].value == pytest.approx(0.75)

    pipeline.render(scene, Camera3D())
    assert ctx.program_calls == 1
    assert ctx.buffer_calls == 1
    assert ctx.vao_calls == 1
    assert pipeline.diagnostics.cache_hits == 3


def test_shader_mesh_color_reaches_variant_program():
    ctx = _Context()
    host = _Host(ctx)
    pipeline = ShaderMaterialRenderPipeline(host)
    material = shader_material_3d()
    obj = ShaderMesh3D(
        cube_mesh(),
        material,
        position=Vec3(0.0, 0.0, -4.0),
        color=Color(0.25, 0.5, 0.75, 1.0),
    )

    pipeline.render(_Scene((obj,)), Camera3D())
    assert ctx.programs[0]["color"].value == pytest.approx((0.25, 0.5, 0.75, 1.0))


def test_shader_mesh_rejects_foreign_whole_shader_template():
    foreign = ShaderTemplate(
        "foreign",
        "#version 330\nvoid main(){gl_Position=vec4(0.0);}",
        "#version 330\nout vec4 fragColor; void main(){fragColor=vec4(1.0);}",
    )
    material = ShaderMaterial3D(prepare_shader_variant(foreign))
    pipeline = ShaderMaterialRenderPipeline(_Host(_Context()))
    obj = ShaderMesh3D(cube_mesh(), material, position=Vec3(0.0, 0.0, -4.0))

    with pytest.raises(ShaderPipelineError, match="engine-owned"):
        pipeline.render(_Scene((obj,)), Camera3D())


def test_pipeline_release_releases_gpu_resources_and_programs():
    ctx = _Context()
    host = _Host(ctx)
    pipeline = ShaderMaterialRenderPipeline(host)
    material = shader_material_3d()
    pipeline.render(
        _Scene((ShaderMesh3D(cube_mesh(), material, position=Vec3(0.0, 0.0, -4.0)),)),
        Camera3D(),
    )

    pipeline.release()
    assert all(buffer.released for buffer in ctx.buffers)
    assert all(vao.released for vao in ctx.vaos)
    assert all(program.released for program in ctx.programs)
    assert pipeline.diagnostics.live_programs == 0
