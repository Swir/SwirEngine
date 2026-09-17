# GPU Timing & Frame Capture — SwirEngine 1.8

SwirEngine 1.8 adds an **opt-in, renderer-independent GPU timing contract** in
`swirengine.render_timing18`. It is designed for backend timestamp-query adapters and creator-facing
performance diagnostics without forcing GPU synchronization into the default runtime path.

## Design goals

- keep stable 1.x renderer behavior unchanged when GPU timing is not enabled;
- let OpenGL or future backends expose opaque timestamp-query tokens behind one small provider API;
- never call a blocking `wait`, `finish`, or synchronization operation from the recorder;
- keep unresolved queries pending and poll them with an explicit per-call work budget;
- associate pass timings with a verified `RenderGraphPlan` and preserve execution order;
- contain unavailable providers and backend failures instead of destabilizing gameplay;
- feed resolved pass timings into the existing `PerformanceDiagnostics2` capture path;
- retain bounded history/pending state and export deterministic portable captures/hotspots.

## Provider contract

A backend adapter implements three methods:

```python
class MyGpuTimingProvider:
    def begin(self, frame_index: int, pass_name: str) -> object | None:
        ...

    def end(self, token: object) -> None:
        ...

    def poll(self, token: object) -> float | None:
        ...
```

`begin()` returns an opaque backend query token, or `None` when timing is unavailable. `end()` closes
that query around the backend's submitted pass commands. `poll()` returns elapsed **seconds** only
when the result is already available; otherwise it returns `None` immediately. A provider must not
turn `poll()` into a forced GPU wait.

The recorder deliberately does not know OpenGL/Vulkan/Direct3D query objects and never serializes
provider tokens or callbacks.

## Render Graph integration

Pass timing can be attached to an existing `RenderGraphPlan`:

```python
recorder.begin_frame(plan)
for pass_name in plan.passes:
    recorder.begin_pass(pass_name)
    submit_backend_commands(pass_name)
    recorder.end_pass()
recorder.end_frame()

ready_frames = recorder.poll_ready()
```

When a plan is supplied, only active plan passes are accepted and timing scopes must follow compiled
execution order. The plan fingerprint is stored in the portable timing frame so captures can be tied
to the logical render schedule that produced them.

## Non-blocking polling and bounds

`GpuTimingRecorder` has independent bounds for:

- retained frame history;
- pending frames;
- passes per frame;
- pending timestamp queries;
- query results polled per `poll_ready()` call.

An unresolved query remains pending for a later frame/update. Reaching a hard bound returns a stable
`GpuTimingError` rather than silently allocating unbounded state. `clear()` refuses to orphan live
backend query tokens.

## Failure and unavailable modes

Provider begin/end/poll failures become `failed` pass samples by default. Missing providers and
backend-unavailable queries become `unavailable` samples. Diagnostics count both cases. Creators who
need fail-fast backend development can opt into `strict_provider=True`.

Invalid provider results (negative, non-finite, Boolean, or non-numeric values) are contained as
provider failures instead of entering performance data.

## PerformanceDiagnostics2 integration

A resolved GPU timing frame can be recorded into the existing 1.5 diagnostics recorder:

```python
performance.begin_frame()
recorder.record_into(performance, gpu_frame)
frame = performance.end_frame(frame_seconds=1.0 / 60.0)
```

Resolved passes appear as `gpu.<pass-name>` timing metrics. GPU-ready pass count, failure count,
unavailable-query count, and summed GPU pass milliseconds are added as counters. This integration is
explicit so GPU query polling remains decoupled from the normal CPU frame recorder.

## Portable capture and hotspots

`recorder.capture(metadata)` produces `GpuTimingCapture`, which contains only logical timing data,
plan fingerprints, bounded metadata, and creator-readable hotspots. It supports deterministic JSON,
SHA-256 fingerprints, and atomic JSON export.

Hotspots aggregate resolved samples by pass and sort primarily by total GPU time, making expensive
render passes visible without exposing backend objects. Capture metadata is limited to 64 entries,
keys to 128 characters, and values to 1024 characters.

## What this milestone does not claim

The 1.8 module defines and validates the timing/capture contract. It does **not** claim every backend
already exposes hardware timestamps, does not translate synthetic test timings into FPS claims, and
does not introduce forced GPU synchronization. Backend-specific adapters can be integrated behind the
provider contract while retaining the same creator-facing diagnostics surface.

## Validation

The dedicated 1.8 gate covers Python 3.10, 3.13, and 3.14, focused/hardening tests, Render Graph and
performance-diagnostics regressions, Ruff, compile validation, the creator demo, and a deterministic
64,000-query workload with a deliberately generous CI ceiling.
