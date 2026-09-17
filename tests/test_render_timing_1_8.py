from __future__ import annotations

import json

import pytest

from swirengine.performance15 import PerformanceDiagnostics2
from swirengine.render_graph18 import RenderGraphBuilder
from swirengine.render_timing18 import (
    GpuTimingCapture,
    GpuTimingError,
    GpuTimingRecorder,
)


class FakeTimingProvider:
    def __init__(self, values: dict[str, float | None]) -> None:
        self.values = dict(values)
        self.started: list[tuple[int, str]] = []
        self.ended: list[str] = []

    def begin(self, frame_index: int, pass_name: str) -> object | None:
        self.started.append((frame_index, pass_name))
        return pass_name

    def end(self, token: object) -> None:
        self.ended.append(str(token))

    def poll(self, token: object) -> float | None:
        return self.values[str(token)]


def _plan():
    graph = RenderGraphBuilder()
    graph.add_resource("camera", external=True)
    graph.add_resource("hdr", transient=True, size_bytes=4096)
    graph.add_resource("backbuffer", external=True)
    graph.add_pass("geometry", reads=("camera",), writes=("hdr",))
    graph.add_pass(
        "present",
        reads=("hdr",),
        writes=("backbuffer",),
        side_effect=True,
    )
    return graph.compile()


def _record_two_passes(recorder: GpuTimingRecorder) -> None:
    recorder.begin_frame(_plan())
    recorder.begin_pass("geometry")
    recorder.end_pass()
    recorder.begin_pass("present")
    recorder.end_pass()
    recorder.end_frame()


def test_non_blocking_poll_keeps_unready_query_pending() -> None:
    provider = FakeTimingProvider({"geometry": None, "present": 0.002})
    recorder = GpuTimingRecorder(provider)

    _record_two_passes(recorder)

    assert recorder.poll_ready() == ()
    assert recorder.pending_queries == 1
    provider.values["geometry"] = 0.004
    committed = recorder.poll_ready()

    assert len(committed) == 1
    assert [sample.pass_name for sample in committed[0].samples] == [
        "geometry",
        "present",
    ]
    assert committed[0].gpu_ms == pytest.approx(6.0)
    assert recorder.diagnostics().resolved_queries == 2


def test_missing_provider_is_safe_and_observable() -> None:
    recorder = GpuTimingRecorder()
    _record_two_passes(recorder)

    frame = recorder.latest
    assert frame is not None
    assert [sample.status for sample in frame.samples] == ["unavailable", "unavailable"]
    assert frame.unavailable_queries == 2
    assert recorder.diagnostics().unavailable_queries == 2


def test_render_plan_order_and_membership_are_enforced() -> None:
    recorder = GpuTimingRecorder(FakeTimingProvider({"geometry": 0.001, "present": 0.001}))
    plan = _plan()
    recorder.begin_frame(plan)
    recorder.begin_pass("present")
    recorder.end_pass()

    with pytest.raises(GpuTimingError) as error:
        recorder.begin_pass("geometry")
    assert error.value.code == "plan-order"

    recorder.end_frame()
    recorder.poll_ready()

    other = GpuTimingRecorder(FakeTimingProvider({"shadow": 0.001}))
    other.begin_frame(plan)
    with pytest.raises(GpuTimingError) as error:
        other.begin_pass("shadow")
    assert error.value.code == "unknown-plan-pass"


def test_performance_diagnostics_integration_records_gpu_pass_timings() -> None:
    recorder = GpuTimingRecorder(
        FakeTimingProvider({"geometry": 0.004, "present": 0.001})
    )
    _record_two_passes(recorder)
    frame = recorder.poll_ready()[0]

    performance = PerformanceDiagnostics2()
    performance.begin_frame()
    assert recorder.record_into(performance, frame) == 2
    result = performance.end_frame(frame_seconds=0.016)

    timings = {(item.domain, item.name): item.value for item in result.timings}
    counters = {(item.domain, item.name): item.value for item in result.counters}
    assert timings[("gpu", "geometry")] == pytest.approx(4.0)
    assert timings[("gpu", "present")] == pytest.approx(1.0)
    assert counters[("gpu", "ready_passes")] == 2
    assert counters[("gpu", "frame_ms")] == pytest.approx(5.0)


def test_capture_is_portable_deterministic_and_reports_hotspots(tmp_path) -> None:
    provider = FakeTimingProvider({"geometry": 0.003, "present": 0.001})
    recorder = GpuTimingRecorder(provider)

    for _ in range(3):
        _record_two_passes(recorder)
        recorder.poll_ready()

    capture = recorder.capture({"renderer": "fake", "scene": "demo"})
    assert isinstance(capture, GpuTimingCapture)
    assert capture.hotspots()[0].pass_name == "geometry"
    assert capture.hotspots()[0].samples == 3
    assert capture.fingerprint == recorder.capture(
        {"scene": "demo", "renderer": "fake"}
    ).fingerprint

    path = capture.export_json(tmp_path / "capture.json")
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["format"] == "swirengine.gpu-timing.capture"
    assert payload["metadata"] == {"renderer": "fake", "scene": "demo"}
    assert payload["frames"][0]["plan_fingerprint"] == _plan().fingerprint


def test_history_is_bounded_and_reports_dropped_frames() -> None:
    provider = FakeTimingProvider({"geometry": 0.001, "present": 0.001})
    recorder = GpuTimingRecorder(provider, history=2)

    for _ in range(4):
        _record_two_passes(recorder)
        recorder.poll_ready()

    assert [frame.frame_index for frame in recorder.frames] == [2, 3]
    assert recorder.diagnostics().dropped_frames == 2
