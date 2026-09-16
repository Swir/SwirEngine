from __future__ import annotations

import json
import tracemalloc
from dataclasses import dataclass

import pytest

from swirengine.performance15 import (
    PerformanceCapture,
    PerformanceDiagnostics2,
    PerformanceFrame,
    PerformanceMemory,
)


class _Clock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


@dataclass(frozen=True)
class _PhysicsDiagnostics:
    bodies: int
    contacts: int
    sleeping: int


class _StreamingDiagnostics:
    def portable(self) -> dict[str, object]:
        return {
            "active_cells": 7,
            "active_cost": 12,
            "blocked": 2,
            "focus": [1, 2, 3],
        }


def test_frame_sections_asset_timing_and_system_counters() -> None:
    clock = _Clock()
    profiler = PerformanceDiagnostics2(history=4, clock=clock)
    profiler.begin_frame()

    with profiler.measure("update"):
        clock.advance(0.002)
    with profiler.measure("physics"):
        clock.advance(0.001)
    with profiler.measure("render"):
        clock.advance(0.003)
    with profiler.measure_asset("textures/hero.png"):
        clock.advance(0.004)

    assert profiler.sample_diagnostics("physics", _PhysicsDiagnostics(20, 4, 8)) == 3
    assert profiler.sample_diagnostics("streaming", _StreamingDiagnostics()) == 3
    profiler.set_counter("navigation", "expanded_nodes", 17)
    profiler.record_resource("scene_objects", count=44, bytes_used=4096)
    clock.advance(0.010)

    frame = profiler.end_frame()

    assert frame.frame_ms == pytest.approx(20.0)
    assert frame.fps == pytest.approx(50.0)
    assert frame.update_ms == pytest.approx(2.0)
    assert frame.physics_ms == pytest.approx(1.0)
    assert frame.render_ms == pytest.approx(3.0)
    assert len(frame.timings) == 1
    assert frame.timings[0].domain == "asset"
    assert frame.timings[0].name == "textures/hero.png"
    assert frame.timings[0].value == pytest.approx(4.0)
    counters = {(item.domain, item.name): item.value for item in frame.counters}
    assert counters[("physics", "bodies")] == 20
    assert counters[("physics", "contacts")] == 4
    assert counters[("navigation", "expanded_nodes")] == 17
    assert counters[("streaming", "active_cells")] == 7
    assert ("streaming", "focus") not in counters
    assert frame.resources[0].name == "scene_objects"
    assert frame.resources[0].count == 44
    assert frame.resources[0].bytes_used == 4096


def test_bound_diagnostics_are_sampled_and_provider_failures_are_contained() -> None:
    profiler = PerformanceDiagnostics2()
    profiler.bind_provider("streaming", lambda: {"active_cells": 5})

    def broken_provider() -> object:
        raise RuntimeError("telemetry unavailable")

    profiler.bind_provider("navigation", broken_provider)
    profiler.begin_frame()
    frame = profiler.end_frame(0.016)

    counters = {(item.domain, item.name): item.value for item in frame.counters}
    assert counters[("streaming", "active_cells")] == 5
    assert counters[("diagnostics", "provider_errors")] == 1
    assert profiler.provider_errors == 1


def test_strict_provider_failure_closes_frame_for_recovery() -> None:
    profiler = PerformanceDiagnostics2(strict_providers=True)
    profiler.bind_provider("physics", lambda: 42)
    profiler.begin_frame()

    with pytest.raises(TypeError, match="diagnostics must be"):
        profiler.end_frame(0.016)

    assert not profiler.active
    profiler.unbind_provider("physics")
    profiler.begin_frame()
    assert profiler.end_frame(0.016).index == 0


def test_history_is_bounded_without_renumbering_frames() -> None:
    profiler = PerformanceDiagnostics2(history=2)
    for seconds in (0.010, 0.020, 0.030):
        profiler.begin_frame()
        profiler.end_frame(seconds)

    assert [frame.index for frame in profiler.frames] == [1, 2]
    assert profiler.latest is not None
    assert profiler.latest.frame_ms == pytest.approx(30.0)


def test_capture_json_and_fingerprint_are_reproducible(tmp_path) -> None:
    profiler = PerformanceDiagnostics2()
    profiler.begin_frame()
    profiler.set_counter("navigation", "visited_nodes", 9)
    profiler.record_timing("asset", "mesh.glb", 0.00125)
    profiler.record_resource("textures", count=3, bytes_used=1024)
    profiler.end_frame(0.02)

    left = profiler.capture({"scenario": "benchmark", "seed": 7})
    right = profiler.capture({"seed": 7, "scenario": "benchmark"})

    assert left.canonical_json() == right.canonical_json()
    assert left.fingerprint == right.fingerprint
    destination = left.export_json(tmp_path / "captures" / "frame.json")
    loaded = json.loads(destination.read_text(encoding="utf-8"))
    assert loaded["format"] == "swirengine.performance.capture"
    assert loaded["format_version"] == 1
    assert loaded["metadata"] == {"scenario": "benchmark", "seed": "7"}
    assert loaded["frames"][0]["counters"][0]["name"] == "visited_nodes"


def test_memory_tracking_is_explicit_and_records_snapshot() -> None:
    profiler = PerformanceDiagnostics2()
    profiler.enable_memory_tracking()
    allocation = bytearray(4096)
    profiler.begin_frame()
    frame = profiler.end_frame(0.016)
    profiler.disable_memory_tracking(stop_tracing=True)

    assert allocation
    assert frame.memory is not None
    assert frame.memory.current_bytes >= 0
    assert frame.memory.peak_bytes >= frame.memory.current_bytes
    assert not tracemalloc.is_tracing()


def test_memory_tracking_does_not_stop_external_tracemalloc_owner() -> None:
    if tracemalloc.is_tracing():
        tracemalloc.stop()
    tracemalloc.start()
    try:
        profiler = PerformanceDiagnostics2()
        profiler.enable_memory_tracking()
        profiler.begin_frame()
        assert profiler.end_frame(0.016).memory is not None
        profiler.disable_memory_tracking(stop_tracing=True)
        assert tracemalloc.is_tracing()
    finally:
        tracemalloc.stop()


def test_disabled_recorder_is_a_true_noop() -> None:
    profiler = PerformanceDiagnostics2(enabled=False)
    profiler.begin_frame()
    with profiler.measure("not-a-standard-section"):
        profiler.set_counter("", "", float("nan"))
        profiler.record_resource("", count=-1)
    frame = profiler.end_frame(float("nan"))

    assert not profiler.active
    assert profiler.frames == ()
    assert frame.frame_ms == 0.0


def test_public_capture_values_validate_invariants() -> None:
    with pytest.raises(ValueError, match="peak memory"):
        PerformanceMemory(current_bytes=20, peak_bytes=10)
    with pytest.raises(ValueError, match="frame index"):
        PerformanceFrame(-1, 1.0, 0.0, 0.0, 0.0)
    with pytest.raises(ValueError, match="frame_ms"):
        PerformanceFrame(0, float("nan"), 0.0, 0.0, 0.0)
    with pytest.raises(TypeError, match="PerformanceFrame"):
        PerformanceCapture(frames=(object(),))  # type: ignore[arg-type]


def test_invalid_metrics_and_frame_lifecycle_are_rejected() -> None:
    profiler = PerformanceDiagnostics2()
    with pytest.raises(RuntimeError, match="begin_frame"):
        profiler.set_counter("physics", "bodies", 1)

    profiler.begin_frame()
    with pytest.raises(RuntimeError, match="already active"):
        profiler.begin_frame()
    with pytest.raises(ValueError, match="finite"):
        profiler.set_counter("physics", "contacts", float("nan"))
    with pytest.raises(ValueError, match="unknown performance frame section"), profiler.measure(
        "network"
    ):
        pass
    with pytest.raises(ValueError, match="frame seconds"):
        profiler.end_frame(float("inf"))

    assert profiler.active
    assert profiler.end_frame(0.016).frame_ms == pytest.approx(16.0)
