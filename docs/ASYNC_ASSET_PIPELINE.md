# Async / preload asset pipeline

SwirEngine 1.1 adds a bounded background-loading layer on top of `AssetManager` for creator code
that needs to prepare larger levels without serially decoding every file on the gameplay thread.

## Basic preload

```python
from swirengine.asset_pipeline import AssetPreloader
from swirengine.assets import AssetManager

assets = AssetManager("assets")
assets.register_loader("txt", lambda path: path.read_text(encoding="utf-8"))

with AssetPreloader(assets, max_workers=4) as preloader:
    report = preloader.preload([
        "levels/city.txt",
        "dialog/intro.txt",
        "config/vehicles.txt",
    ])

print(report.loaded, report.failed, report.cache_hits)
print(f"preload wall time: {report.wall_time_ms:.2f} ms")
```

`preload(...)` blocks only while waiting for the batch, but individual loader work runs concurrently
inside a bounded worker pool. Results are always returned in the same order as the requested assets,
which keeps loading screens, logs and tests deterministic.

## Fully asynchronous batch

```python
future = preloader.preload_async(["map.txt", "cars.txt", "missions.txt"])

# Keep running menu/loading-screen work here.
# ...

report = future.result()
```

For one resource use `load_async(...)`, which returns a standard `concurrent.futures.Future`.
Duplicate requests resolving to the same canonical file path share one in-flight operation, avoiding
accidental duplicate decoding during scene transitions.

## Diagnostics

Every `AssetLoadResult` records:

- canonical path
- loaded value
- loader duration in nanoseconds / milliseconds
- whether the value was already cached
- an isolated error string if that resource failed

Every `AssetPreloadReport` records the full batch wall time, successful/failed counts, cache hits,
summed worker time and `stall_reduction_ratio`. The ratio compares observed concurrent batch wait
against the same loader durations serialized; it is a loading-wait metric, **not** an FPS claim.

A failed resource does not abort the remaining batch. Use `report.errors()` to surface failures in a
loading screen or diagnostics panel.

## Threading rule for render/audio resources

Background threads are appropriate for filesystem reads, parsing, decompression and CPU-side image
or model decoding when the chosen loader library is thread-safe. OpenGL and other context-owned GPU
uploads generally must stay on the render thread. A recommended split is:

1. background preload/parse/decode,
2. wait or poll for completion,
3. finalize renderer/GPU objects on the owning render thread.

The pipeline deliberately does not hide this rule; it avoids creating context-dependent behavior
that works on one platform and fails on another.

## Lifetime

Prefer the context-manager form or call `shutdown()` explicitly. Worker count is bounded and must be
at least one. `pending_paths()` provides a deterministic snapshot for loading UI/debug tooling.
