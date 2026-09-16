from __future__ import annotations

import pytest

from swirengine import (
    Color,
    Game,
    GPUParticleBlendMode,
    GPUParticleEmissionShape3D,
    GPUParticleEmitter3D,
    GPUParticleRenderMode3D,
    Vec3,
)


def test_gpu_particle_emitter_validates_configuration() -> None:
    with pytest.raises(ValueError, match="capacity"):
        GPUParticleEmitter3D(capacity=0)
    with pytest.raises(ValueError, match="rate"):
        GPUParticleEmitter3D(rate=-1.0)
    with pytest.raises(ValueError, match="lifetime"):
        GPUParticleEmitter3D(lifetime=(0.0, 1.0))
    with pytest.raises(ValueError, match="size_pixels"):
        GPUParticleEmitter3D(size_pixels=(-1.0, 2.0))
    with pytest.raises(ValueError, match="emissive_strength"):
        GPUParticleEmitter3D(emissive_strength=-0.1)
    with pytest.raises(ValueError, match="mesh_scale"):
        GPUParticleEmitter3D(mesh_scale=-0.1)
    with pytest.raises(ValueError, match="trail_alpha_scale"):
        GPUParticleEmitter3D(trail_alpha_scale=1.1)
    with pytest.raises(ValueError, match="emission_extent"):
        GPUParticleEmitter3D(emission_extent=Vec3(-1.0, 0.0, 0.0))


def test_gpu_particle_emitter_normalizes_public_values() -> None:
    emitter = GPUParticleEmitter3D(
        capacity=64,
        emission_shape="sphere",
        blend_mode="alpha",
        render_mode="mesh",
        texture="assets/fx/spark.png",
        emissive_strength=4.0,
        start_color=Color(2.0, -1.0, 0.5, 1.5),
    )
    assert emitter.emission_shape is GPUParticleEmissionShape3D.SPHERE
    assert emitter.blend_mode is GPUParticleBlendMode.ALPHA
    assert emitter.render_mode is GPUParticleRenderMode3D.MESH
    assert emitter.texture == "assets/fx/spark.png"
    assert emitter.emissive_strength == 4.0
    assert emitter.start_color == Color(1.0, 0.0, 0.5, 1.0)


def test_game_gpu_particles_is_creator_facing_and_3d_only() -> None:
    game = Game(mode="3d")
    emitter = game.gpu_particles(capacity=256, rate=0.0, trail_enabled=True)
    assert isinstance(emitter, GPUParticleEmitter3D)
    assert emitter.trail_enabled is True
    assert emitter in game.scene

    with pytest.raises(RuntimeError, match="mode='3d'"):
        Game(mode="2d").gpu_particles()


def test_gpu_particle_update_only_schedules_gpu_work() -> None:
    emitter = GPUParticleEmitter3D(capacity=64, rate=100.0)
    emitter.update(0.1)
    diagnostics = emitter.diagnostics
    assert diagnostics.queued == 10
    assert diagnostics.emitted_total == 10
    assert not hasattr(emitter, "children")

    frame = emitter._consume_gpu_frame()
    assert frame.dt == pytest.approx(0.1)
    assert frame.spawn_cursor == 0
    assert frame.spawn_count == 10
    assert emitter.diagnostics.queued == 0
    assert emitter.diagnostics.submitted_total == 10
    assert emitter.diagnostics.spawn_cursor == 10


def test_gpu_particle_burst_is_bounded_by_capacity() -> None:
    emitter = GPUParticleEmitter3D(capacity=8, rate=0.0)
    assert emitter.emit(12) == 8
    assert emitter.diagnostics.queued == 8
    assert emitter.diagnostics.emitted_total == 12
    assert emitter.diagnostics.recycled_total == 4

    frame = emitter._consume_gpu_frame()
    assert frame.spawn_count == 8
    assert emitter.diagnostics.spawn_cursor == 0
    assert emitter.diagnostics.submitted_total == 8


def test_gpu_particle_ring_cursor_wraps_deterministically() -> None:
    emitter = GPUParticleEmitter3D(capacity=10, rate=0.0)
    emitter.emit(7)
    first = emitter._consume_gpu_frame()
    assert first.spawn_cursor == 0
    assert first.spawn_count == 7
    assert emitter.diagnostics.spawn_cursor == 7

    emitter.emit(6)
    second = emitter._consume_gpu_frame()
    assert second.spawn_cursor == 7
    assert second.spawn_count == 6
    assert emitter.diagnostics.spawn_cursor == 3
    assert emitter.diagnostics.recycled_total == 3


def test_gpu_particle_clear_requests_gpu_reset() -> None:
    emitter = GPUParticleEmitter3D(capacity=16, rate=0.0)
    emitter.emit(5)
    emitter.update(0.05)
    emitter._consume_gpu_frame()
    emitter.clear()
    assert emitter._gpu_reset_requested is True
    assert emitter.diagnostics.queued == 0
    assert emitter.diagnostics.spawn_cursor == 0
    assert emitter.diagnostics.simulation_frames == 0


def test_gpu_particle_update_clamps_accumulated_simulation_step() -> None:
    emitter = GPUParticleEmitter3D(capacity=128, rate=20.0)
    emitter.update(1.0)
    frame = emitter._consume_gpu_frame()
    assert frame.dt == pytest.approx(0.25)
    assert frame.spawn_count == 5
