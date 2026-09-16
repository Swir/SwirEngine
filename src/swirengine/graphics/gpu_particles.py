from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from ..gpu_particles import (
    GPUParticleBlendMode,
    GPUParticleEmissionShape3D,
    GPUParticleEmitter3D,
)
from ..math.types import perspective
from .camera3d import Camera3D
from .ibl_renderer import _read_context_state


@dataclass(frozen=True, slots=True)
class GPUParticlePassDiagnostics:
    emitters: int = 0
    simulated_particles: int = 0
    submitted_particles: int = 0
    draw_calls: int = 0


@dataclass(slots=True)
class _EmitterGPU:
    buffers: tuple[object, object]
    sim_vaos: tuple[object, object]
    render_vaos: tuple[object, object]
    source_index: int = 0

    def release(self) -> None:
        for vao in self.sim_vaos + self.render_vaos:
            vao.release()
        for buffer in self.buffers:
            buffer.release()


class GPUParticlePass3D:
    """OpenGL 3.3 transform-feedback simulation + one point-batch draw per emitter."""

    _STRIDE_FLOATS = 12

    def __init__(self, ctx) -> None:
        self.ctx = ctx
        self._resources: dict[int, _EmitterGPU] = {}
        self._framebuffer = None
        self._target_identity = (0, 0)
        self._released = False
        self.diagnostics = GPUParticlePassDiagnostics()
        self.sim_program = self.ctx.program(
            vertex_shader="""
                #version 330
                in vec4 in_position_age;
                in vec4 in_velocity_life;
                in vec4 in_misc;

                uniform float dt;
                uniform int capacity;
                uniform int spawn_cursor;
                uniform int spawn_count;
                uniform int spawn_serial;
                uniform int seed_value;
                uniform int emission_shape;
                uniform vec3 emitter_position;
                uniform vec3 emission_extent;
                uniform vec3 velocity_min;
                uniform vec3 velocity_max;
                uniform vec3 gravity;
                uniform vec2 lifetime_range;
                uniform vec2 size_range;
                uniform float drag;

                out vec4 out_position_age;
                out vec4 out_velocity_life;
                out vec4 out_misc;

                uint hash_u32(uint value) {
                    value ^= value >> 16;
                    value *= 0x7feb352du;
                    value ^= value >> 15;
                    value *= 0x846ca68bu;
                    value ^= value >> 16;
                    return value;
                }

                float random01(uint value) {
                    return float(hash_u32(value)) / 4294967295.0;
                }

                vec3 random3(uint base) {
                    return vec3(
                        random01(base ^ 0x68bc21ebu),
                        random01(base ^ 0x02e5be93u),
                        random01(base ^ 0x967a889bu)
                    );
                }

                vec3 spawn_offset(uint base) {
                    if (emission_shape == 0) return vec3(0.0);
                    vec3 r = random3(base) * 2.0 - 1.0;
                    if (emission_shape == 1) return r * emission_extent * 0.5;
                    float u = random01(base ^ 0x9e3779b9u);
                    float v = random01(base ^ 0x243f6a88u);
                    float w = random01(base ^ 0xb7e15162u);
                    float theta = 6.28318530718 * u;
                    float z = v * 2.0 - 1.0;
                    float xy = sqrt(max(0.0, 1.0 - z * z));
                    vec3 direction = vec3(cos(theta) * xy, z, sin(theta) * xy);
                    return direction * emission_extent * 0.5 * pow(w, 1.0 / 3.0);
                }

                void main() {
                    vec3 position = in_position_age.xyz;
                    float age = in_position_age.w;
                    vec3 velocity = in_velocity_life.xyz;
                    float lifetime = in_velocity_life.w;
                    vec4 misc = in_misc;
                    int relative = (gl_VertexID - spawn_cursor + capacity) % capacity;
                    bool respawn = spawn_count > 0 && relative >= 0 && relative < spawn_count;

                    if (respawn) {
                        uint base = uint(seed_value)
                            ^ (uint(gl_VertexID) * 747796405u)
                            ^ (uint(spawn_serial + relative) * 2891336453u);
                        vec3 random_velocity = random3(base ^ 0xa511e9b3u);
                        position = emitter_position + spawn_offset(base ^ 0x63d83595u);
                        velocity = mix(velocity_min, velocity_max, random_velocity);
                        age = 0.0;
                        lifetime = mix(
                            lifetime_range.x,
                            lifetime_range.y,
                            random01(base ^ 0xc2b2ae35u)
                        );
                        misc.x = mix(size_range.x, size_range.y, random01(base ^ 0x27d4eb2fu));
                    } else if (age >= 0.0 && dt > 0.0) {
                        age += dt;
                        if (age >= lifetime) {
                            age = -1.0;
                        } else {
                            velocity += gravity * dt;
                            velocity *= max(0.0, 1.0 - drag * dt);
                            position += velocity * dt;
                        }
                    }

                    out_position_age = vec4(position, age);
                    out_velocity_life = vec4(velocity, lifetime);
                    out_misc = misc;
                }
            """,
            varyings=["out_position_age", "out_velocity_life", "out_misc"],
        )
        self.render_program = self.ctx.program(
            vertex_shader="""
                #version 330
                in vec4 in_position_age;
                in vec4 in_velocity_life;
                in vec4 in_misc;
                uniform mat4 view_projection;
                uniform vec4 start_color;
                uniform vec4 end_color;
                uniform float end_size_scale;
                out vec4 v_color;
                void main() {
                    float age = in_position_age.w;
                    float lifetime = max(in_velocity_life.w, 0.000001);
                    if (age < 0.0) {
                        gl_Position = vec4(2.0, 2.0, 2.0, 1.0);
                        gl_PointSize = 0.0;
                        v_color = vec4(0.0);
                        return;
                    }
                    float t = clamp(age / lifetime, 0.0, 1.0);
                    gl_Position = view_projection * vec4(in_position_age.xyz, 1.0);
                    gl_PointSize = max(0.0, in_misc.x * mix(1.0, end_size_scale, t));
                    v_color = mix(start_color, end_color, t);
                }
            """,
            fragment_shader="""
                #version 330
                in vec4 v_color;
                out vec4 fragColor;
                void main() {
                    vec2 centered = gl_PointCoord * 2.0 - 1.0;
                    float radius2 = dot(centered, centered);
                    if (radius2 > 1.0) discard;
                    float feather = 1.0 - smoothstep(0.55, 1.0, radius2);
                    fragColor = vec4(v_color.rgb, v_color.a * feather);
                }
            """,
        )

    @staticmethod
    def _write_mat4(uniform, matrix: np.ndarray) -> None:
        uniform.write(np.asarray(matrix, dtype="f4").T.tobytes())

    def _initial_state(self, capacity: int) -> bytes:
        state = np.zeros((capacity, self._STRIDE_FLOATS), dtype="f4")
        state[:, 3] = -1.0
        state[:, 7] = 1.0
        return state.tobytes()

    def _make_resource(self, emitter: GPUParticleEmitter3D) -> _EmitterGPU:
        initial = self._initial_state(emitter.capacity)
        buffers = (self.ctx.buffer(initial), self.ctx.buffer(initial))
        sim_vaos = tuple(
            self.ctx.vertex_array(
                self.sim_program,
                [(buffer, "4f 4f 4f", "in_position_age", "in_velocity_life", "in_misc")],
            )
            for buffer in buffers
        )
        render_vaos = tuple(
            self.ctx.vertex_array(
                self.render_program,
                [(buffer, "4f 4f 4f", "in_position_age", "in_velocity_life", "in_misc")],
            )
            for buffer in buffers
        )
        return _EmitterGPU(buffers=buffers, sim_vaos=sim_vaos, render_vaos=render_vaos)

    def _resource(self, emitter: GPUParticleEmitter3D) -> _EmitterGPU:
        key = id(emitter)
        resource = self._resources.get(key)
        if resource is None:
            resource = self._make_resource(emitter)
            self._resources[key] = resource
        if emitter._gpu_reset_requested:
            initial = self._initial_state(emitter.capacity)
            for buffer in resource.buffers:
                buffer.write(initial)
            resource.source_index = 0
            emitter._gpu_reset_requested = False
        return resource

    def _ensure_target(self, color_texture: object, depth_texture: object) -> None:
        identity = (id(color_texture), id(depth_texture))
        if self._framebuffer is not None and self._target_identity == identity:
            return
        if self._framebuffer is not None:
            self._framebuffer.release()
        self._framebuffer = self.ctx.framebuffer(
            color_attachments=[color_texture],
            depth_attachment=depth_texture,
        )
        self._target_identity = identity

    def _simulate(self, emitter: GPUParticleEmitter3D, resource: _EmitterGPU) -> int:
        frame = emitter._consume_gpu_frame()
        if frame.dt <= 0.0 and frame.spawn_count == 0:
            return 0
        program = self.sim_program
        program["dt"].value = float(frame.dt)
        program["capacity"].value = int(emitter.capacity)
        program["spawn_cursor"].value = int(frame.spawn_cursor)
        program["spawn_count"].value = int(frame.spawn_count)
        program["spawn_serial"].value = int(frame.spawn_serial & 0x7FFFFFFF)
        program["seed_value"].value = int(emitter.seed & 0x7FFFFFFF)
        program["emission_shape"].value = {
            GPUParticleEmissionShape3D.POINT: 0,
            GPUParticleEmissionShape3D.BOX: 1,
            GPUParticleEmissionShape3D.SPHERE: 2,
        }[emitter.emission_shape]
        program["emitter_position"].value = (
            float(emitter.position.x),
            float(emitter.position.y),
            float(emitter.position.z),
        )
        program["emission_extent"].value = (
            float(emitter.emission_extent.x),
            float(emitter.emission_extent.y),
            float(emitter.emission_extent.z),
        )
        program["velocity_min"].value = (
            float(emitter.velocity_min.x),
            float(emitter.velocity_min.y),
            float(emitter.velocity_min.z),
        )
        program["velocity_max"].value = (
            float(emitter.velocity_max.x),
            float(emitter.velocity_max.y),
            float(emitter.velocity_max.z),
        )
        program["gravity"].value = (
            float(emitter.gravity.x),
            float(emitter.gravity.y),
            float(emitter.gravity.z),
        )
        program["lifetime_range"].value = tuple(sorted(map(float, emitter.lifetime)))
        program["size_range"].value = tuple(sorted(map(float, emitter.size_pixels)))
        program["drag"].value = float(emitter.drag)
        source = resource.source_index
        target = 1 - source
        discard = getattr(self.ctx, "RASTERIZER_DISCARD", None)
        if discard is not None:
            self.ctx.enable(discard)
        try:
            resource.sim_vaos[source].transform(
                resource.buffers[target],
                mode=self.ctx.POINTS,
                vertices=emitter.capacity,
            )
        finally:
            if discard is not None:
                self.ctx.disable(discard)
        resource.source_index = target
        return emitter.capacity

    def _draw(
        self,
        emitter: GPUParticleEmitter3D,
        resource: _EmitterGPU,
        camera: Camera3D,
        *,
        aspect: float,
    ) -> None:
        projection = perspective(
            float(camera.fov),
            float(aspect),
            float(camera.near),
            float(camera.far),
        )
        self._write_mat4(self.render_program["view_projection"], projection @ camera.view_matrix())
        start = emitter.start_color
        end = emitter.end_color
        self.render_program["start_color"].value = (start.r, start.g, start.b, start.a)
        self.render_program["end_color"].value = (end.r, end.g, end.b, end.a)
        self.render_program["end_size_scale"].value = float(emitter.end_size_scale)
        if emitter.blend_mode is GPUParticleBlendMode.ADDITIVE:
            self.ctx.blend_func = self.ctx.SRC_ALPHA, self.ctx.ONE
        else:
            self.ctx.blend_func = self.ctx.SRC_ALPHA, self.ctx.ONE_MINUS_SRC_ALPHA
        resource.render_vaos[resource.source_index].render(
            mode=self.ctx.POINTS,
            vertices=emitter.capacity,
        )

    def render(
        self,
        scene: object,
        camera: Camera3D,
        *,
        color_texture: object,
        depth_texture: object,
        width: int,
        height: int,
    ) -> GPUParticlePassDiagnostics:
        if self._released:
            raise RuntimeError("GPU particle pass has been released")
        emitters = tuple(
            obj
            for obj in getattr(scene, "objects", ())
            if isinstance(obj, GPUParticleEmitter3D) and obj.enabled and obj.visible
        )
        active_ids = {id(emitter) for emitter in emitters}
        for key in tuple(self._resources):
            if key not in active_ids:
                self._resources.pop(key).release()
        if not emitters:
            self.diagnostics = GPUParticlePassDiagnostics()
            return self.diagnostics

        self._ensure_target(color_texture, depth_texture)
        assert self._framebuffer is not None
        self._framebuffer.use()
        self.ctx.viewport = (0, 0, int(width), int(height))
        previous_depth_mask = _read_context_state(self.ctx, "depth_mask", True)
        self.ctx.enable(self.ctx.DEPTH_TEST)
        self.ctx.enable(self.ctx.BLEND)
        self.ctx.depth_mask = False
        point_size = getattr(self.ctx, "PROGRAM_POINT_SIZE", None)
        if point_size is not None:
            self.ctx.enable(point_size)
        simulated = 0
        submitted = 0
        draws = 0
        try:
            aspect = float(width) / max(1.0, float(height))
            for emitter in emitters:
                resource = self._resource(emitter)
                simulated += self._simulate(emitter, resource)
                self._draw(emitter, resource, camera, aspect=aspect)
                submitted += emitter.capacity
                draws += 1
        finally:
            if point_size is not None:
                self.ctx.disable(point_size)
            self.ctx.depth_mask = previous_depth_mask
            self.ctx.disable(self.ctx.BLEND)
            self.ctx.disable(self.ctx.DEPTH_TEST)
        self.diagnostics = GPUParticlePassDiagnostics(
            emitters=len(emitters),
            simulated_particles=simulated,
            submitted_particles=submitted,
            draw_calls=draws,
        )
        return self.diagnostics

    def release(self) -> None:
        if self._released:
            return
        for resource in self._resources.values():
            resource.release()
        self._resources.clear()
        if self._framebuffer is not None:
            self._framebuffer.release()
            self._framebuffer = None
        self.sim_program.release()
        self.render_program.release()
        self._released = True
