from __future__ import annotations

import os
from types import SimpleNamespace

import numpy as np

os.environ.setdefault("LIBGL_ALWAYS_SOFTWARE", "1")
os.environ.setdefault("MESA_GL_VERSION_OVERRIDE", "3.3")

import moderngl

from swirengine.gpu_particles import GPUParticleEmitter3D
from swirengine.graphics.camera3d import Camera3D
from swirengine.graphics.gpu_particles import GPUParticlePass3D
from swirengine.math.types import Color, Vec3


def main() -> None:
    ctx = moderngl.create_standalone_context(require=330, backend="egl")
    size = (128, 96)
    color = ctx.texture(size, 4, dtype="f2")
    depth = ctx.depth_texture(size)
    target = ctx.framebuffer(color_attachments=[color], depth_attachment=depth)
    target.clear(0.0, 0.0, 0.0, 0.0, depth=1.0)

    emitter = GPUParticleEmitter3D(
        position=Vec3(0.0, 0.0, -3.0),
        capacity=128,
        rate=0.0,
        lifetime=(2.0, 2.0),
        velocity_min=Vec3(),
        velocity_max=Vec3(),
        gravity=Vec3(),
        drag=0.0,
        size_pixels=(18.0, 18.0),
        start_color=Color(4.0, 1.0, 0.2, 1.0),
        end_color=Color(1.0, 0.1, 0.0, 1.0),
        seed=1234,
    )
    assert emitter.emit(32) == 32
    emitter.update(1.0 / 60.0)
    scene = SimpleNamespace(objects=[emitter])
    camera = Camera3D()
    particle_pass = GPUParticlePass3D(ctx)

    diagnostics = particle_pass.render(
        scene,
        camera,
        color_texture=color,
        depth_texture=depth,
        width=size[0],
        height=size[1],
    )
    assert diagnostics.emitters == 1
    assert diagnostics.simulated_particles == emitter.capacity
    assert diagnostics.submitted_particles == emitter.capacity
    assert diagnostics.draw_calls == 1

    resource = particle_pass._resources[id(emitter)]
    state_bytes = resource.buffers[resource.source_index].read()
    state = np.frombuffer(state_bytes, dtype=np.float32).reshape((-1, 12))
    alive = int(np.count_nonzero(state[:, 3] >= 0.0))
    assert alive == 32, f"expected exactly 32 live GPU particles, got {alive}"
    assert np.allclose(state[:32, 2], -3.0, atol=1e-5)

    pixels = np.frombuffer(color.read(), dtype=np.float16)
    assert float(np.max(pixels)) > 0.0, "GPU particle draw did not touch the HDR target"

    emitter.update(0.25)
    second = particle_pass.render(
        scene,
        camera,
        color_texture=color,
        depth_texture=depth,
        width=size[0],
        height=size[1],
    )
    assert second.draw_calls == 1
    assert emitter.diagnostics.simulation_frames == 2

    particle_pass.release()
    target.release()
    depth.release()
    color.release()
    ctx.release()
    print("GPU particle OpenGL 3.3 transform-feedback smoke: OK")


if __name__ == "__main__":
    main()
