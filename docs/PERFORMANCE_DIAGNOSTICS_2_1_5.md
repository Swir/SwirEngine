# Performance & Diagnostics 2.0 — SwirEngine 1.5

Performance & Diagnostics 2.0 is an additive, opt-in runtime instrumentation layer for SwirEngine 1.5. It lives in `swirengine.performance15` and does not replace or change the released 1.x `swirengine.Profiler` contract.

The goal is to give creators and CI jobs a small, headless-safe way to answer five questions consistently:

1. Where is frame time spent?
2. What are the important runtime systems doing?
3. Which asset/cache operations are expensive?
4. How many resources and bytes are currently accounted for?
5. Can the same captured metrics be exported and compared reproducibly?

## Quick start

```python
from swirengine.performance15 import PerformanceDiagnostics2

perf = PerformanceDiagnostics2(history=300)
perf.bind_provider("navigation", lambda: navigation.diagnostics)
perf.bind_provider("streaming", lambda: world_stream.diagnostics)

perf.begin_frame()
with perf.measure("update"):
    update_game()
with perf.measure("physics"):
    physics.step(dt)
with perf.measure("render"):
    render_frame()
perf.record_resource("scene_objects", count=len(scene.objects))
frame = perf.end_frame()

print(frame.frame_ms, frame.fps)
```

`begin_frame()`/`end_frame()` define one captured frame. The built-in frame sections are `update`, `physics`, and `render`. Additional timings use `measure_timing(domain, name)` or `record_timing(domain, name, seconds)`.

## Stable 1.x compatibility

`PerformanceDiagnostics2` deliberately lives outside the stable root profiler API. Existing projects can continue to use `swirengine.Profiler` unchanged. A project adopts the 1.5 recorder only by importing `swirengine.performance15` and creating an instance.

The new recorder has no renderer requirement and can run in tests, tools, servers, export verification, and headless benchmarks.

## Frame and subsystem timing

Use `measure()` for the standard frame phases:

```python
perf.begin_frame()
with perf.measure("update"):
    update_world()
with perf.measure("physics"):
    physics.step(dt)
with perf.measure("render"):
    renderer.render(scene)
frame = perf.end_frame()
```

Use a named domain for creator-specific work:

```python
with perf.measure_timing("script", "enemy_ai"):
    update_enemies()
```

Repeated timings with the same `(domain, name)` inside one frame accumulate. Recorded values are stored in milliseconds in the resulting `PerformanceFrame`.

For asset work, `measure_asset(asset_name)` is a convenience wrapper:

```python
with perf.measure_asset("characters/hero.glb"):
    import_asset()
```

For deterministic tests or imported measurements, `record_timing(domain, name, seconds)` records an explicit duration without reading the clock.

## Physics, navigation, streaming, and cache counters

`sample_diagnostics(domain, value)` accepts:

- a mapping;
- a dataclass instance;
- an object exposing `portable()` that returns a mapping.

Numeric fields are flattened into counters. Nested mappings use dotted names. Non-numeric fields are ignored intentionally so creator-facing diagnostic records can contain labels, keys, paths, or focus descriptions without becoming invalid metrics.

```python
perf.begin_frame()
perf.sample_diagnostics("navigation", navigation.diagnostics)
perf.sample_diagnostics("streaming", world_stream.diagnostics)
perf.sample_diagnostics("asset_cache", derived_cache.diagnostics)
perf.end_frame(1.0 / 60.0)
```

For long-running sessions, bind providers once and let `end_frame()` sample them:

```python
perf.bind_provider("navigation", lambda: navigation.diagnostics)
perf.bind_provider("streaming", lambda: world_stream.diagnostics)
perf.bind_provider("asset_cache", lambda: cache.diagnostics)
```

Provider failures do not crash the game by default. They increment the cumulative `diagnostics.provider_errors` counter. Tests and tools that want hard failures can construct the recorder with `strict_providers=True`.

Manual counters are also supported:

```python
perf.set_counter("physics", "contacts", contact_count)
perf.add_counter("scripts", "callbacks")
```

Counter values must be finite integers or floats. Boolean values are exported as `0`/`1`.

## Resource accounting

Resource tracking is explicit rather than magical. This keeps the profiler portable and prevents hidden object traversal from becoming part of frame cost.

```python
perf.record_resource("textures", count=42, bytes_used=128_000_000)
perf.record_resource("scene_objects", count=len(scene.objects))
```

`PerformanceResource` requires non-negative counts and byte totals. The recorder reports what the engine or creator explicitly accounts for; it does not guess native GPU allocations.

## Python memory tracking

Python allocation tracking is opt-in because `tracemalloc` has measurable overhead:

```python
perf.enable_memory_tracking()
perf.begin_frame()
# ... work ...
frame = perf.end_frame()
print(frame.memory.current_bytes, frame.memory.peak_bytes)
perf.disable_memory_tracking(stop_tracing=True)
```

The snapshot reports Python-traced current and peak bytes only. It is not a GPU-memory or operating-system resident-set measurement. Do not enable it in a shipping hot path unless the diagnostic cost is acceptable.

`tracemalloc` is process-global. The recorder tracks ownership: if `enable_memory_tracking()` had to start tracing, `disable_memory_tracking(stop_tracing=True)` may stop it; if tracing was already active because another tool started it, the recorder leaves that external tracing session running. This prevents diagnostics teardown from silently breaking another profiler.

## Bounded history

The recorder keeps a bounded deque of frames. The default is 300 frames:

```python
perf = PerformanceDiagnostics2(history=120)
```

Older entries are discarded automatically. Frame indexes continue increasing, so a bounded history does not make retained frames look like a new session.

`clear()` resets retained history and the index and is rejected while a frame is active.

## Reproducible capture and export

`capture()` freezes the retained frame history into a `PerformanceCapture`:

```python
capture = perf.capture({"scenario": "city_stress", "seed": 7})
print(capture.fingerprint)
capture.export_json("artifacts/city_stress.json")
```

Capture JSON uses sorted keys, stable metric ordering, a versioned format marker, and no automatic wall-clock timestamp. Two captures containing the same metric values and metadata therefore produce the same canonical JSON and SHA-256 fingerprint regardless of metadata insertion order.

The exported structure starts with:

```json
{
  "format": "swirengine.performance.capture",
  "format_version": 1,
  "metadata": {},
  "frames": []
}
```

`export_json()` writes through a temporary sibling and replaces the destination only after serialization succeeds.

Reproducible capture does **not** mean real performance measurements are expected to be numerically identical across machines. It means the serialization and fingerprint of a given measurement set are deterministic. CI should compare explicitly chosen budgets or normalized scenario outputs rather than assuming timing equality between runners.

## Disabled recorder

`PerformanceDiagnostics2(enabled=False)` is available for creator code that wants one instrumentation wiring path but needs recording disabled. Recording calls and measurement scopes become no-ops without validating metric names or values, and `end_frame()` returns a zero-duration transient frame without retaining history. For the lowest possible shipping overhead, avoid entering diagnostic scopes entirely when the feature is disabled at the application level.

## Error and lifecycle rules

- `begin_frame()` cannot be nested.
- Recording counters/resources/timings requires an active frame when the recorder is enabled.
- Invalid `frame_seconds` does not consume the active frame, so a caller can correct the explicit duration and retry `end_frame()`.
- A strict bound-provider failure closes the active frame but does not append a partial capture.
- Non-strict provider failures are counted and the frame is still captured.
- Timing and counter floats must be finite.
- Resource counts and byte totals must be non-negative integers.
- Public frame/capture value objects validate non-negative frame times, frame indexes, resource types, memory peak/current invariants, and capture frame types.

## Milestone 9 verification contract

Milestone 9 is not considered complete merely because the API exists. The milestone gate requires all of the following on the exact candidate head:

- focused Performance & Diagnostics 2.0 tests on Python 3.10, 3.13, and 3.14;
- stable `tests/test_profiler.py` regression coverage unchanged and green;
- strict Ruff and compile checks for the 1.5 implementation, tests, benchmark, and example;
- a runnable headless example;
- a 10,000-frame instrumentation workload inside the documented generous CI budget, with bounded retained history and deterministic capture validation;
- the repository's normal compatibility/regression workflows remaining green.

The benchmark is an instrumentation-overhead guard and **not** an FPS claim. Renderer/GPU performance remains platform- and backend-dependent and belongs in the final 1.5 showcase/release validation.
