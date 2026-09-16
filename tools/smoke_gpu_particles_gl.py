from __future__ import annotations

import os
import tempfile
from pathlib import Path
from types import SimpleNamespace

import moderngl
import numpy as np
from PIL import Image

os.environ.setdefault("LIBGL_ALWAYS_SOFTWARE", "1")
os.environ.setdefault("MESA_GL_VERSION_OVERRIDE", "3.3")

from swirengine import GPUParticleEmitter3D, GPUParticleRenderMode3D
from swirengine.graphics.camera3d import Camera3D
from swirengine.graphics.gpu_particles import GPUParticlePass3D
from swirengine.math.types import Color, Vec3


def live_count(particle_pass: GPUParticlePass3D, emitter: GPUParticleEmitter3D) -> int:
    resource = particle_pass._resources[id(emitter)]
    state_bytes = resource.buffers[resource.source_index].read()
    state = np.frombuffer(state_bytes, dtype=np.float32).reshape((-1, 12))
    return int(np.count_nonzero(state[:, 3] >= 0.0))


def main() -> None:
    ctx = moderngl.create_standalone_context(require=330, backend="egl")
    size = (128, 96)
    color = ctx.texture(size, 4, dtype="f2")
    depth = ctx.depth_texture(size)
    target = ctx.framebuffer(color_attachments=[color], depth_attachment=depth)
    target.clear(0.0, 0.0, 0.0, 0.0, depth=1.0)
    camera = Camera3D()
    particle_pass = GPUParticlePass3D(ctx)

    with tempfile.TemporaryDirectory() as directory:
        texture_path = Path(directory) / "particle.png"
        Image.new("RGBA", (4, 4), (255, 210, 80, 255)).save(texture_path)

        sprite = GPUParticleEmitter3D(
            position=Vec3(-0.35, 0.0, -3.0),
            capacity=64,
            rate=0.0,
            lifetime=(2.0, 2.0),
            velocity_min=Vec3(0.4, 0.0, 0.0),
            velocity_max=Vec3(0.4, 0.0, 0.0),
            gravity=Vec3(),
            drag=0.0,
            size_pixels=(20.0, 20.0),
            start_color=Color(1.0, 0.8, 0.2, 1.0),
            end_color=Color(1.0, 0.1, 0.0, 1.0),
            emissive_strength=4.0,
            texture=str(texture_path),
            trail_enabled=True,
            seed=1234,
        )
        mesh = GPUParticleEmitter3D(
            position=Vec3(0.55, 0.0, -3.0),
            capacity=32,
            rate=0.0,
            lifetime=(2.0, 2.0),
            velocity_min=Vec3(),
            velocity_max=Vec3(),
            gravity=Vec3(),
            drag=0.0,
            render_mode=GPUParticleRenderMode3D.MESH,
            mesh_scale=0.08,
            start_color=Color(0.2, 0.7, 1.0, 1.0),
            end_color=Color(0.05, 0.2, 1.0, 1.0),
            emissive_strength=2.0,
            seed=4321,
        )
        assert sprite.emit(16) == 16
        assert mesh.emit(8) == 8
        sprite.update(1.0 / 60.0)
        mesh.update(1.0 / 60.0)
        scene = SimpleNamespace(objects=[sprite, mesh])

        diagnostics = particle_pass.render(
            scene,
            camera,
            color_texture=color,
            depth_texture=depth,
            width=size[0],
            height=size[1],
        )
        assert diagnostics.emitters == 2
        assert diagnostics.simulated_particles == sprite.capacity + mesh.capacity
        assert diagnostics.submitted_particles == sprite.capacity + mesh.capacity
        assert diagnostics.draw_calls == 3
        assert diagnostics.sprite_draw_calls == 1
        assert diagnostics.mesh_draw_calls == 1
        assert diagnostics.trail_draw_calls == 1
        assert live_count(particle_pass, sprite) == 16
        assert live_count(particle_pass, mesh) == 8
        assert len(particle_pass._particle_textures) == 1

        sprite_resource = particle_pass._resources[id(sprite)]
        first_state = np.frombuffer(
            sprite_resource.buffers[sprite_resource.source_index].read(),
            dtype=np.float32,
        ).reshape((-1, 12))
        assert np.allclose(first_state[:16, 2], -3.0, atol=1e-5)

        pixels = np.frombuffer(color.read(), dtype=np.float16)
        assert float(np.max(pixels)) > 1.0, "emissive GPU VFX did not reach HDR intensity"

        sprite.update(0.25)
        mesh.update(0.25)
        second = particle_pass.render(
            scene,
            camera,
            color_texture=color,
            depth_texture=depth,
            width=size[0],
            height=size[1],
        )
        assert second.draw_calls == 3
        second_state = np.frombuffer(
            sprite_resource.buffers[sprite_resource.source_index].read(),
            dtype=np.float32,
        ).reshape((-1, 12))
        assert np.any(np.abs(second_state[:16, 0] - second_state[:16, 9]) > 1e-6)
        assert sprite.diagnostics.simulation_frames == 2
        assert mesh.diagnostics.simulation_frames == 2
        assert len(particle_pass._particle_textures) == 1

    particle_pass.release()
    target.release()
    depth.release()
    color.release()
    ctx.release()
    print("GPU VFX OpenGL 3.3 sprite/texture/trail/mesh smoke: OK")


if __name__ == "__main__":
    main()
