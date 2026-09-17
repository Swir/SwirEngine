# Dynamic Resolution & Quality Budget Controller — SwirEngine 1.8

SwirEngine 1.8 adds an opt-in, renderer-independent quality controller for games that need to trade
rendering quality for stable frame delivery without changing simulation truth. The controller consumes
frame/GPU timing evidence and returns one creator-authored quality tier for the renderer to apply at a
safe frame boundary.

It does **not** resize a window, recreate render targets, modify physics, alter fixed-step simulation,
change gameplay time, or issue GPU commands. Renderer2 integration is deliberately deferred to the
1.8 compatibility bridge milestone.

## Core model

```python
from swirengine.render_quality18 import (
    DynamicQualityController,
    RenderQualityPolicy,
    RenderQualityStep,
)

controller = DynamicQualityController(
    (
        RenderQualityStep("ultra", resolution_scale=1.0, quality_scale=1.0),
        RenderQualityStep("high", resolution_scale=0.9, quality_scale=0.9),
        RenderQualityStep("medium", resolution_scale=0.75, quality_scale=0.75),
        RenderQualityStep("low", resolution_scale=0.6, quality_scale=0.55),
    ),
    policy=RenderQualityPolicy(
        target_frame_ms=16.6667,
        degrade_ratio=1.08,
        recover_ratio=0.82,
        degrade_frames=4,
        recover_frames=45,
        cooldown_frames=30,
        sample_window=6,
    ),
)

# Run once per presented/rendered frame. The game simulation remains untouched.
decision = controller.observe(frame_ms=19.4, gpu_ms=18.8)
if decision.changed:
    renderer_backend.apply_quality(
        resolution_scale=decision.step.resolution_scale,
        quality_scale=decision.step.quality_scale,
    )
```

Quality steps are authored from highest quality to lowest quality. Resolution and generic quality
scales may stay equal between adjacent tiers, but they may not increase as the tier moves downward.
This makes every automatic degradation deterministic and monotonic.

## Timing policy

`RenderQualityPolicy` separates the target frame budget from the adaptation thresholds:

- `degrade_ratio` defines sustained pressure above the target before dropping one tier;
- `recover_ratio` defines sustained headroom below the target before recovering one tier;
- `degrade_frames` and `recover_frames` are independent hysteresis streaks;
- `sample_window` is a bounded rolling-average window (maximum 240 samples);
- `cooldown_frames` requires fresh timing evidence after a quality transition;
- `max_steps` bounds creator-authored quality tiers (maximum 64).

The recovery threshold must remain below the target and the degrade threshold cannot be below the
target. That dead band plus independent streak lengths prevents single-frame spikes from causing
quality oscillation.

`metric_source` chooses the timing evidence:

- `"frame"` uses total frame time;
- `"gpu"` uses GPU frame time when available and falls back to total frame time when it is not;
- `"max"` (default) uses the slower of total frame time and explicit GPU frame time.

No policy path waits for GPU queries. GPU evidence should come from already resolved data such as the
SwirEngine 1.8 GPU Timing Capture system.

## PerformanceDiagnostics2 integration

GPU Timing Capture 1.8 records a `gpu.frame_ms` counter into `PerformanceDiagnostics2`. The quality
controller can consume that portable frame directly:

```python
performance.begin_frame()
# update / physics / render instrumentation ...
frame = performance.end_frame(frame_seconds=measured_frame_seconds)
decision = controller.observe_performance_frame(frame)
```

The helper reads `frame.frame_ms` and, when present, the explicit `gpu.frame_ms` counter. It never sums
per-pass GPU timings because overlapping GPU work would make that an unsafe approximation.

The controller can also expose its own numeric state to `PerformanceDiagnostics2`:

```python
controller.bind_diagnostics(performance)
```

The `render_quality.*` counters then include current step, resolution/quality scales, transition counts,
hysteresis streaks, cooldown, timing evidence, override state and bounded sample count.

## Creator override

Games often need deterministic capture modes, accessibility settings, menus, photo modes, benchmark
passes or platform-specific presets. A creator can pin a tier explicitly:

```python
controller.set_override("high")
# Automatic changes are suspended, but timing observations remain visible in diagnostics.
...
controller.clear_override()
```

`set_step()` changes the adaptive baseline without creating a persistent override. Clearing an override
starts the normal transition cooldown so stale timing evidence cannot immediately undo a creator choice.

## Portable diagnostics and reproducibility

`diagnostics()` exposes bounded numeric state suitable for runtime overlays and captures.
`portable_state()` contains policy, authored steps and deterministic logical controller state without
renderer/backend objects. `fingerprint` is a SHA-256 digest of that canonical state, which is useful in
CI, replay metadata and workload comparisons.

Invalid or non-finite timing samples fail before controller state is mutated. An adaptive transition is
always one authored step at a time. At the highest/lowest tier, additional recovery/degradation pressure
is observable but cannot move outside creator-authored bounds.

## Performance contract

`tools/benchmark_dynamic_quality_1_8.py` drives 200,000 deterministic timing observations across
pressure, neutral and recovery phases. The Python 3.13 CI gate uses a deliberately generous 5-second
ceiling. This is a controller-overhead regression contract only; it is **not** an FPS, GPU-performance,
or hardware-throughput claim.
