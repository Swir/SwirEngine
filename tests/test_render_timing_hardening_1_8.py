from __future__ import annotations

import math

import pytest

from swirengine.render_graph18 import RenderGraphBuilder
from swirengine.render_timing18 import GpuTimingCapture, GpuTimingError, GpuTimingRecorder


class ScriptedProvider:
    def __init__(self) -> None:
        self.results: dict[str, object] = {}
        self.raise_begin: set[str] = set()
        self.raise_end: set[str] = set()
        self.raise_poll: set[str] = set()

    def begin(self, frame_index: int, pass_name: str) -> object | None:
        if pass_name in self.raise_begin:
            raise RuntimeError("begin unavailable")
        return f"{frame_index}:{pass_name}"

    def end(self, token: object) -> None:
        name = str(token).split(":", 1)[1]
        if name in self.raise_end:
            raise RuntimeError("end unavailable")

    def poll(self, token: object) -> float | None:
        name = str(token).split(":", 1)[1]
        if name in self.raise_poll:
            raise RuntimeError("poll unavailable")
        return self.results.get(name)


def _plan(*names: str):
    graph = RenderGraphBuilder()
    previous = None
    for index, name in enumerate(names):
        resource = f"r{index}"
        graph.add_resource(resource, transient=True)
        kwargs = {"writes": (resource,)}
        if previous is not None:
            kwargs["depends_on"] = (previous,)
        graph.add_pass(name, **kwargs)
        previous = name
    return graph.compile()


def _finish(recorder: GpuTimingRecorder, *names: str) -> None:
    recorder.begin_frame(_plan(*names))
    for name in names:
        recorder.begin_pass(name)
        recorder.end_pass()
    recorder.end_frame()


def test_provider_begin_end_and_poll_failures_are_contained() -> None:
    provider = ScriptedProvider()
    provider.raise_begin.add("begin")
    provider.raise_end.add("end")
    provider.raise_poll.add("poll")
    recorder = GpuTimingRecorder(provider)

    _finish(recorder, "begin", "end", "poll")
    frame = recorder.poll_ready()[0]

    assert [sample.status for sample in frame.samples] == ["failed", "failed", "failed"]
    assert frame.provider_failures == 3
    assert recorder.diagnostics().provider_failures == 3
    assert recorder.pending_queries == 0


def test_invalid_provider_results_become_failed_samples() -> None:
    provider = ScriptedProvider()
    provider.results["nan"] = math.nan
    provider.results["negative"] = -0.1
    provider.results["bool"] = True
    recorder = GpuTimingRecorder(provider)

    _finish(recorder, "nan", "negative", "bool")
    frame = recorder.poll_ready()[0]

    assert all(sample.status == "failed" for sample in frame.samples)
    assert recorder.diagnostics().provider_failures == 3


def test_strict_provider_failure_raises_stable_error_without_corrupting_frame() -> None:
    provider = ScriptedProvider()
    provider.raise_end.add("broken")
    recorder = GpuTimingRecorder(provider, strict_provider=True)
    recorder.begin_frame(_plan("broken"))
    recorder.begin_pass("broken")

    with pytest.raises(GpuTimingError) as error:
        recorder.end_pass()
    assert error.value.code == "provider-end-failed"

    recorder.end_pass()
    recorder.end_frame()
    frame = recorder.latest
    assert frame is not None
    assert frame.samples[0].status == "failed"


def test_pass_and_pending_frame_limits_are_hard() -> None:
    provider = ScriptedProvider()
    recorder = GpuTimingRecorder(
        provider,
        max_passes_per_frame=1,
        max_pending_frames=1,
        max_pending_queries=2,
    )
    recorder.begin_frame(_plan("one", "two"))
    recorder.begin_pass("one")
    recorder.end_pass()
    with pytest.raises(GpuTimingError) as error:
        recorder.begin_pass("two")
    assert error.value.code == "pass-limit"
    recorder.end_frame()

    with pytest.raises(GpuTimingError) as error:
        recorder.begin_frame(_plan("one"))
    assert error.value.code == "pending-frame-limit"


def test_poll_budget_does_not_force_unready_or_excess_queries() -> None:
    provider = ScriptedProvider()
    provider.results.update({"one": 0.001, "two": 0.002, "three": 0.003})
    recorder = GpuTimingRecorder(provider)
    _finish(recorder, "one", "two", "three")

    assert recorder.poll_ready(max_queries=1) == ()
    assert recorder.pending_queries == 2
    assert recorder.poll_ready(max_queries=1) == ()
    assert recorder.pending_queries == 1
    committed = recorder.poll_ready(max_queries=1)
    assert len(committed) == 1
    assert committed[0].gpu_ms == pytest.approx(6.0)


def test_clear_refuses_to_orphan_pending_backend_tokens() -> None:
    provider = ScriptedProvider()
    recorder = GpuTimingRecorder(provider)
    _finish(recorder, "pending")

    with pytest.raises(GpuTimingError) as error:
        recorder.clear()
    assert error.value.code == "pending-queries"

    provider.results["pending"] = 0.001
    recorder.poll_ready()
    recorder.clear()
    assert recorder.frames == ()


def test_capture_metadata_is_bounded_and_duplicate_keys_are_rejected() -> None:
    with pytest.raises(ValueError, match="64 metadata"):
        GpuTimingCapture((), tuple((f"k{i}", "v") for i in range(65)))

    with pytest.raises(ValueError, match="unique"):
        GpuTimingCapture((), (("same", "a"), ("same", "b")))

    with pytest.raises(ValueError, match="1024"):
        GpuTimingCapture((), (("key", "x" * 1025),))


def test_capture_hotspot_order_is_deterministic() -> None:
    provider = ScriptedProvider()
    provider.results.update({"a": 0.002, "b": 0.004})
    recorder = GpuTimingRecorder(provider)
    _finish(recorder, "a", "b")
    recorder.poll_ready()

    hotspots = recorder.capture().hotspots()
    assert [item.pass_name for item in hotspots] == ["b", "a"]


def test_frame_and_capture_fingerprints_exclude_provider_tokens() -> None:
    def run() -> tuple[str, str]:
        provider = ScriptedProvider()
        provider.results["draw"] = 0.0025
        recorder = GpuTimingRecorder(provider)
        _finish(recorder, "draw")
        recorder.poll_ready()
        assert recorder.latest is not None
        return recorder.latest.fingerprint, recorder.capture().fingerprint

    assert run() == run()
