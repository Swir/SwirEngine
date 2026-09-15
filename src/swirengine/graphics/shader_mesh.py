from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from ..math.types import Color, Transform, Vec3, perspective
from .camera3d import Camera3D
from .lights import DirectionalLight3D, select_lights
from .mesh import MeshData
from .shader_pipeline import (
    DefineValue,
    ShaderDiagnostics,
    ShaderHookPoint,
    ShaderMaterial3D,
    ShaderPipelineError,
    ShaderProgramCache,
    ShaderTemplate,
    UniformValue,
    prepare_shader_variant,
)


SURFACE_3D_TEMPLATE = ShaderTemplate(
    "swir_surface_3d",
    """#version 330
in vec3 in_pos;
in vec3 in_normal;
in vec2 in_uv;
uniform mat4 mvp;
uniform mat4 model;
out vec3 v_world_position;
out vec3 v_normal;
out vec2 v_uv;
/* SWIR_HOOK:vertex_globals */
void main() {
    vec3 local_position = in_pos;
    vec3 local_normal = in_normal;
    /* SWIR_HOOK:vertex_surface */
    vec4 world = model * vec4(local_position, 1.0);
    v_world_position = world.xyz;
    v_normal = normalize(mat3(transpose(inverse(model))) * local_normal);
    v_uv = in_uv;
    gl_Position = mvp * vec4(local_position, 1.0);
}
""",
    """#version 330
uniform vec4 color;
uniform int directional_enabled;
uniform vec3 directional_direction;
uniform vec3 directional_color;
uniform float directional_intensity;
in vec3 v_world_position;
in vec3 v_normal;
in vec2 v_uv;
out vec4 fragColor;
/* SWIR_HOOK:fragment_globals */
void main() {
    vec4 surface_rgba = color;
    vec3 surface_normal = normalize(v_normal);
    /* SWIR_HOOK:fragment_surface */

    vec3 lighting = surface_rgba.rgb * 0.18;
    if (directional_enabled != 0) {
        float ndotl = max(dot(surface_normal, normalize(-directional_direction)), 0.0);
        lighting += surface_rgba.rgb * directional_color * directional_intensity * ndotl;
    } else {
        lighting += surface_rgba.rgb * 0.82;
    }
    /* SWIR_HOOK:fragment_lighting */
    fragColor = vec4(lighting, surface_rgba.a);
}
""",
    hook_points=(
        ShaderHookPoint("vertex_globals", "vertex"),
        ShaderHookPoint("vertex_surface", "vertex"),
        ShaderHookPoint("fragment_globals", "fragment"),
        ShaderHookPoint("fragment_surface", "fragment"),
        ShaderHookPoint("fragment_lighting", "fragment"),
    ),
)


@dataclass(slots=True)
class ShaderMesh3D:
    """3D mesh rendered through a validated SwirEngine shader material variant."""

    mesh: MeshData
    shader_material: ShaderMaterial3D
    position: Vec3 = field(default_factory=Vec3)
    rotation: Vec3 = field(default_factory=Vec3)
    scale: Vec3 = field(default_factory=lambda: Vec3(1.0, 1.0, 1.0))
    color: Color = field(default_factory=Color)
    enabled: bool = True
    visible: bool = True
    name: str = ""
    tags: set[str] = field(default_factory=set)

    @property
    def transform(self) -> Transform:
        return Transform(self.position, self.rotation, self.scale)

    def update(self, dt: float) -> None:
        pass


def shader_material_3d(
    *,
    defines: dict[str, DefineValue] | None = None,
    hooks: dict[str, str] | None = None,
    uniforms: dict[str, UniformValue] | None = None,
    strict_uniforms: bool = True,
) -> ShaderMaterial3D:
    """Create a context-free material for the engine-owned ShaderMesh3D template."""

    variant = prepare_shader_variant(
        SURFACE_3D_TEMPLATE,
        defines=defines,
        hooks=hooks,
    )
    return ShaderMaterial3D(
        variant,
        uniforms=dict(uniforms or {}),
        strict_uniforms=strict_uniforms,
    )


class _RendererHost(Protocol):
    ctx: object
    width: int
    height: int
    stats: object

    @staticmethod
    def _write_mat4(uniform: object, matrix: object) -> None: ...


class ShaderMaterialRenderPipeline:
    """Production direct-forward path for ShaderMesh3D objects.

    Vertex buffers are shared across shader variants. Only lightweight VAO bindings are
    cached per mesh/variant pair, while compiled programs live in the bounded LRU cache.
    """

    def __init__(self, host: _RendererHost, *, max_programs: int = 64) -> None:
        self.host = host
        self.ctx = host.ctx
        self.programs = ShaderProgramCache(self.ctx, max_programs=max_programs)
        self._mesh_buffers: dict[int, tuple[object, int]] = {}
        self._mesh_vaos: dict[tuple[int, str], object] = {}

    @property
    def diagnostics(self) -> ShaderDiagnostics:
        return self.programs.diagnostics

    def _validate_material(self, material: ShaderMaterial3D) -> None:
        variant = material.variant
        if (
            variant.template_name != SURFACE_3D_TEMPLATE.name
            or variant.template_fingerprint != SURFACE_3D_TEMPLATE.fingerprint
        ):
            raise ShaderPipelineError(
                "ShaderMesh3D only accepts variants prepared from the engine-owned "
                "SURFACE_3D_TEMPLATE"
            )

    def _gpu_mesh(self, obj: ShaderMesh3D, program: object) -> tuple[object, int]:
        mesh_key = id(obj.mesh)
        buffer_entry = self._mesh_buffers.get(mesh_key)
        if buffer_entry is None:
            packed = obj.mesh.interleaved(include_uvs=True)
            vbo = self.ctx.buffer(packed.tobytes())  # type: ignore[attr-defined]
            buffer_entry = (vbo, obj.mesh.vertex_count)
            self._mesh_buffers[mesh_key] = buffer_entry
            self.host.stats.mesh_uploads += 1  # type: ignore[attr-defined]

        vao_key = (mesh_key, obj.shader_material.variant.key.digest)
        vao = self._mesh_vaos.get(vao_key)
        if vao is None:
            vao = self.ctx.vertex_array(  # type: ignore[attr-defined]
                program,
                [(buffer_entry[0], "3f 3f 2f", "in_pos", "in_normal", "in_uv")],
                skip_errors=True,
            )
            self._mesh_vaos[vao_key] = vao
        return vao, buffer_entry[1]

    @staticmethod
    def _configure_frame_program(
        program: object,
        directional: DirectionalLight3D | None,
    ) -> None:
        program["directional_enabled"].value = int(directional is not None)  # type: ignore[index]
        if directional is None:
            program["directional_direction"].value = (0.0, -1.0, 0.0)  # type: ignore[index]
            program["directional_color"].value = (1.0, 1.0, 1.0)  # type: ignore[index]
            program["directional_intensity"].value = 0.0  # type: ignore[index]
            return
        direction = directional.direction
        light_color = directional.color
        program["directional_direction"].value = (  # type: ignore[index]
            float(direction.x),
            float(direction.y),
            float(direction.z),
        )
        program["directional_color"].value = (  # type: ignore[index]
            float(light_color.r),
            float(light_color.g),
            float(light_color.b),
        )
        program["directional_intensity"].value = float(directional.intensity)  # type: ignore[index]

    def render(self, scene: object, camera: Camera3D) -> None:
        objects = tuple(
            obj
            for obj in getattr(scene, "objects", ())
            if isinstance(obj, ShaderMesh3D) and obj.enabled and obj.visible
        )
        if not objects:
            return

        projection = perspective(
            float(camera.fov),
            self.host.width / max(1, self.host.height),
            float(camera.near),
            float(camera.far),
        )
        view_projection = projection @ camera.view_matrix()
        selection = select_lights(getattr(scene, "objects", ()), max_directional=1)
        directional = selection.directional[0] if selection.directional else None
        configured_programs: set[int] = set()
        self.ctx.enable(self.ctx.DEPTH_TEST)  # type: ignore[attr-defined]
        try:
            for obj in objects:
                material = obj.shader_material
                self._validate_material(material)
                program = self.programs.resolve(material.variant)
                program_id = id(program)
                if program_id not in configured_programs:
                    self._configure_frame_program(program, directional)
                    configured_programs.add(program_id)

                vao, vertex_count = self._gpu_mesh(obj, program)
                model = obj.transform.matrix()
                self.host._write_mat4(program["model"], model)  # type: ignore[index]
                self.host._write_mat4(program["mvp"], view_projection @ model)  # type: ignore[index]
                color = obj.color.clamped()
                program["color"].value = (  # type: ignore[index]
                    float(color.r),
                    float(color.g),
                    float(color.b),
                    float(color.a),
                )
                material.apply_uniforms(program)
                vao.render(vertices=vertex_count)
                self.host.stats.draw_calls += 1  # type: ignore[attr-defined]
                self.host.stats.shader_meshes += 1  # type: ignore[attr-defined]
                self.host.stats.triangles += vertex_count // 3  # type: ignore[attr-defined]
        finally:
            self.ctx.disable(self.ctx.DEPTH_TEST)  # type: ignore[attr-defined]

    def release(self) -> None:
        for vao in self._mesh_vaos.values():
            release = getattr(vao, "release", None)
            if callable(release):
                release()
        self._mesh_vaos.clear()
        for vbo, _ in self._mesh_buffers.values():
            release = getattr(vbo, "release", None)
            if callable(release):
                release()
        self._mesh_buffers.clear()
        self.programs.release()
