from __future__ import annotations

import math

import pytest

from swirengine.math.types import Color
from swirengine.particles import ParticleEmissionShape2D, ParticleEmitter2D


def test_children_tuple_is_stable_and_alive_count_is_constant_time_state() -> None:
    emitter = ParticleEmitter2D(max_particles=4096, emitting=False, seed=1)

    first = emitter.children
    second = emitter.children

    assert first is second
    assert emitter.alive_count == 0
    emitter.emit(3)
    assert emitter.alive_count == 3


def test_active_update_visits_only_live_particles_not_full_capacity() -> None:
    emitter = ParticleEmitter2D(
        max_particles=10_000,
        emitting=False,
        lifetime=(10.0, 10.0),
        speed=(0.0, 0.0),
        gravity=(0.0, 0.0),
        seed=2,
    )
    emitter.emit(8)

    emitter.update(0.1)

    diagnostics = emitter.diagnostics
    assert diagnostics.alive == 8
    assert diagnostics.update_visits == 8
    assert diagnostics.capacity == 10_000
    assert diagnostics.update_visits < diagnostics.capacity // 100

    emitter.update(0.1)
    assert emitter.diagnostics.update_visits == 8


def test_pool_recycling_does_not_duplicate_active_entries() -> None:
    emitter = ParticleEmitter2D(
        max_particles=2,
        emitting=False,
        lifetime=(10.0, 10.0),
        seed=3,
    )

    emitter.emit(5)

    assert emitter.alive_count == 2
    assert emitter.diagnostics.emitted_total == 5
    assert emitter.diagnostics.recycled_total == 3
    emitter.update(0.1)
    assert emitter.diagnostics.update_visits == 2


def test_box_emission_stays_inside_requested_region() -> None:
    emitter = ParticleEmitter2D(
        100.0,
        50.0,
        max_particles=64,
        emitting=False,
        emission_shape=ParticleEmissionShape2D.BOX,
        emission_size=(20.0, 10.0),
        speed=(0.0, 0.0),
        seed=4,
    )
    emitter.emit(64)

    for visual in emitter.children:
        assert 90.0 <= visual.x <= 110.0
        assert 45.0 <= visual.y <= 55.0


def test_ring_emission_uses_ellipse_boundary() -> None:
    emitter = ParticleEmitter2D(
        max_particles=16,
        emitting=False,
        emission_shape="ring",
        emission_size=(20.0, 10.0),
        speed=(0.0, 0.0),
        seed=5,
    )
    emitter.emit(16)

    for visual in emitter.children:
        normalized = (visual.x / 10.0) ** 2 + (visual.y / 5.0) ** 2
        assert normalized == pytest.approx(1.0)


def test_color_size_rotation_drag_and_gravity_evolve_over_lifetime() -> None:
    emitter = ParticleEmitter2D(
        max_particles=1,
        emitting=False,
        lifetime=(2.0, 2.0),
        speed=(10.0, 10.0),
        angle=(0.0, 0.0),
        size=(10.0, 10.0),
        gravity=(0.0, 4.0),
        color=Color(1.0, 0.0, 0.0, 1.0),
        end_color=Color(0.0, 0.0, 1.0, 0.0),
        end_size_scale=0.5,
        drag=0.5,
        rotation=(10.0, 10.0),
        angular_velocity=(20.0, 20.0),
        seed=6,
    )
    emitter.emit()

    emitter.update(1.0)
    visual = emitter.children[0]

    assert visual.x == pytest.approx(5.0)
    assert visual.y == pytest.approx(2.0)
    assert visual.rotation == pytest.approx(30.0)
    assert visual.width == pytest.approx(7.5)
    assert visual.height == pytest.approx(7.5)
    assert visual.color.r == pytest.approx(0.5)
    assert visual.color.b == pytest.approx(0.5)
    assert visual.color.a == pytest.approx(0.5)


def test_legacy_defaults_still_fade_to_transparent_same_rgb() -> None:
    emitter = ParticleEmitter2D(
        max_particles=1,
        emitting=False,
        lifetime=(1.0, 1.0),
        speed=(0.0, 0.0),
        gravity=(0.0, 0.0),
        color=Color(0.2, 0.4, 0.6, 0.8),
        seed=7,
    )
    emitter.emit()
    emitter.update(0.5)

    color = emitter.children[0].color
    assert color.r == pytest.approx(0.2)
    assert color.g == pytest.approx(0.4)
    assert color.b == pytest.approx(0.6)
    assert color.a == pytest.approx(0.4)


def test_circle_emission_fills_inside_ellipse() -> None:
    emitter = ParticleEmitter2D(
        max_particles=128,
        emitting=False,
        emission_shape="circle",
        emission_size=(20.0, 20.0),
        speed=(0.0, 0.0),
        seed=8,
    )
    emitter.emit(128)

    radii = [math.hypot(v.x, v.y) for v in emitter.children]
    assert max(radii) <= 10.0
    assert min(radii) < 5.0


def test_validation_rejects_invalid_extended_parameters() -> None:
    with pytest.raises(ValueError):
        ParticleEmitter2D(emission_size=(-1.0, 0.0))
    with pytest.raises(ValueError):
        ParticleEmitter2D(end_size_scale=-0.1)
    with pytest.raises(ValueError):
        ParticleEmitter2D(drag=-0.1)
