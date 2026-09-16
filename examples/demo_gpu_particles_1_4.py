from __future__ import annotations

import math

from swirengine import Color, Game, GPUParticleBlendMode, GPUParticleEmissionShape3D, Vec3

game = Game("SwirEngine 1.4 — GPU VFX", 1280, 720, mode="3d")
game.configure_renderer2(
    True,
    bloom=True,
    bloom_threshold=0.7,
    bloom_intensity=1.0,
    ssao=True,
)
game.camera.position = Vec3(0.0, 1.5, 4.5)
game.camera.look_at(Vec3(0.0, 1.0, -3.0))

emitter = game.gpu_particles(
    position=Vec3(0.0, 1.0, -3.0),
    capacity=8192,
    rate=1800.0,
    lifetime=(0.8, 1.8),
    velocity_min=Vec3(-1.8, 1.0, -1.8),
    velocity_max=Vec3(1.8, 5.5, 1.8),
    gravity=Vec3(0.0, -4.0, 0.0),
    drag=0.2,
    size_pixels=(4.0, 14.0),
    end_size_scale=0.1,
    start_color=Color(1.0, 0.65, 0.12, 1.0),
    end_color=Color(1.0, 0.03, 0.01, 0.0),
    emission_shape=GPUParticleEmissionShape3D.SPHERE,
    emission_extent=Vec3(0.45, 0.45, 0.45),
    blend_mode=GPUParticleBlendMode.ADDITIVE,
    seed=1405,
)
emitter.burst(1500)

elapsed = 0.0


@game.update
def animate(dt: float) -> None:
    global elapsed
    elapsed += dt
    emitter.position.x = math.sin(elapsed * 0.9) * 1.25
    emitter.position.z = -3.0 + math.cos(elapsed * 0.7) * 0.4


game.run()
