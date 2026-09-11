from types import SimpleNamespace

import pytest

from swirengine import Profiler


def test_profiler_records_sections_and_renderer_stats():
    profiler = Profiler(history=4)
    profiler.begin_frame()
    profiler.record("update", 0.002)
    profiler.record("physics", 0.001)
    profiler.record("render", 0.003)
    stats = SimpleNamespace(
        draw_calls=4,
        sprites=12,
        sprite_batches=2,
        triangles=30,
        directional_lights=2,
        point_lights=3,
        spot_lights=1,
        lights_dropped=2,
    )

    frame = profiler.end_frame(0.02, stats)

    assert frame.fps == pytest.approx(50.0)
    assert frame.frame_ms == pytest.approx(20.0)
    assert frame.update_ms == pytest.approx(2.0)
    assert frame.physics_ms == pytest.approx(1.0)
    assert frame.render_ms == pytest.approx(3.0)
    assert frame.draw_calls == 4
    assert frame.sprites == 12
    assert frame.sprite_batches == 2
    assert frame.triangles == 30
    assert frame.directional_lights == 2
    assert frame.point_lights == 3
    assert frame.spot_lights == 1
    assert frame.active_lights == 6
    assert frame.lights_dropped == 2


def test_profiler_average_uses_recent_samples():
    profiler = Profiler(history=8)
    profiler.begin_frame()
    profiler.end_frame(0.01)
    profiler.begin_frame()
    profiler.end_frame(0.02)

    average = profiler.average(2)

    assert average.frame_ms == pytest.approx(15.0)
    assert average.fps == pytest.approx(75.0)


def test_profiler_rejects_unknown_sections():
    profiler = Profiler()
    with pytest.raises(ValueError, match="unknown profiler section"):
        profiler.record("network", 0.1)
