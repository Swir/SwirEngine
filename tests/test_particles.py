from swirengine import Color
from swirengine.particles import ParticleEmitter2D


def test_emitter_uses_fixed_pool():
    emitter = ParticleEmitter2D(max_particles=4, seed=1)
    children = emitter.children
    emitter.burst(10)
    assert len(emitter.children) == 4
    assert emitter.children == children
    assert emitter.alive_count == 4


def test_particles_expire_and_fade():
    emitter = ParticleEmitter2D(
        max_particles=2,
        rate=0,
        lifetime=(1, 1),
        speed=(0, 0),
        gravity=(0, 0),
        color=Color(1, 0, 0, 1),
        seed=1,
    )
    emitter.burst(1)
    emitter.update(0.5)
    assert emitter.alive_count == 1
    assert emitter.children[0].color.a == 0.5
    emitter.update(0.5)
    assert emitter.alive_count == 0


def test_rate_emission_accumulates_fractional_time():
    emitter = ParticleEmitter2D(max_particles=10, rate=4, speed=(0, 0), seed=1)
    emitter.update(0.24)
    assert emitter.alive_count == 0
    emitter.update(0.01)
    assert emitter.alive_count == 1
