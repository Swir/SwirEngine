# SwirEngine 1.4 — Asset Pipeline 2.0

Asset Pipeline 2.0 is the sixth milestone of the SwirEngine 1.4 roadmap. It extends the existing `AssetManager` and `AssetPreloader` without removing their 1.x-compatible behavior.

## Goals

- move CPU-heavy parsing and preprocessing away from the gameplay/render thread;
- keep renderer/GPU finalization on the caller thread;
- track source and external-file dependencies explicitly;
- invalidate derived imports transitively when a dependency changes;
- reject stale results when a source or dependency changes while an import is running;
- provide deterministic diagnostics for scheduling, cache use and invalidation;
- support persistent, content-addressed derived artifacts without executable serialization;
- make glTF imports dependency-aware, including external buffers and images.

## Core API

`AssetPipeline` is layered on top of `AssetManager`:

```python
from swirengine.asset_pipeline import AssetPipeline
from swirengine.assets import AssetManager

assets = AssetManager("assets")
with AssetPipeline(assets, max_workers=4) as pipeline:
    pipeline.register_processor(
        "text",
        suffixes=(".txt",),
        loader=lambda path: path.read_text(encoding="utf-8"),
    )
    result = pipeline.wait(pipeline.submit("story.txt"), timeout=2)
```

Processors may define four pieces of behavior:

1. a name;
2. one or more owned file suffixes;
3. a worker-side loader;
4. optional dependency discovery and caller-thread finalization.

Suffix ownership is deterministic. Two processors cannot silently claim the same suffix.

## Background work and caller-thread finalization

CPU parsing runs in a bounded `ThreadPoolExecutor`. Optional finalizers execute only while the caller runs `poll()` or `wait()`. This split is deliberate: a renderer can decode/prepare CPU data in workers and create context-owned GPU resources later on the render thread.

`AssetPipeline` uses a reentrant lock so a finalizer can safely query pipeline diagnostics or other read-only pipeline state without deadlocking the caller.

## Content-aware fingerprints

`AssetFingerprint` combines:

- canonical path;
- existence state;
- file size;
- nanosecond modification time;
- SHA-256 content digest.

The digest prevents same-size content changes from being mistaken for unchanged assets.

## Transactional imports

The source fingerprint is captured when the request is submitted. Dependency paths are resolved and fingerprinted before the heavy loader runs. Before a result is committed, the pipeline rechecks the source and every dependency.

If anything changed during the import, the result becomes `STALE`, the optional finalizer is not called and no derived cache entry is committed.

Terminal states are:

- `COMPLETED`
- `FAILED`
- `STALE`
- `CANCELLED`

## Dependency graph

`AssetDependencyGraph` stores source-to-dependency edges and reverse edges. `affected_by()` walks reverse edges transitively and is cycle-safe.

When `AssetPipeline.bind()` is active, existing `AssetManager.invalidate()` notifications propagate into the pipeline. Invalidating a texture can therefore evict a material import, a glTF import or another higher-level derived asset that depends on it.

## glTF / GLB integration

`register_gltf_asset_processor()` registers `.gltf` and `.glb` with the pipeline. CPU primitive/material parsing runs in workers.

`gltf_asset_dependencies()` discovers external glTF resources such as:

- external buffer URIs;
- external image URIs.

Data URIs and embedded GLB chunks are part of the source container and do not create external dependency edges.

Changing an external `.bin` file or texture invalidates the derived glTF import on the next dependency notification or fingerprint check.

## Persistent derived-asset cache

`DerivedAssetCache` provides an opt-in disk cache for bytes and JSON artifacts.

Properties:

- SHA-256 content-addressed file names;
- namespace + logical-key isolation;
- atomic sibling-temp-file writes followed by `os.replace()`;
- `flush()` + `fsync()` before replacement;
- configurable entry and byte budgets;
- least-recently-touched pruning behavior;
- no `pickle` and no executable deserialization format.

This cache is intentionally separate from the in-memory object cache: arbitrary runtime Python objects are not persisted automatically.

## Diagnostics

`AssetImportDiagnostics` exposes:

- configured worker count;
- queued and running jobs;
- completed, failed, stale and cancelled totals;
- cache hits and misses;
- current cached entries;
- invalidated entries;
- dependency graph node count.

`DerivedAssetCacheDiagnostics` reports disk-cache entries, bytes used, hits, misses, writes and evictions.

## Compatibility

The existing `AssetManager` and `AssetPreloader` remain available. Asset Pipeline 2.0 is additive and does not change the stable package version during 1.4 development.

## Validation contract

The milestone validation covers:

- legacy asset/preloader regressions;
- Asset Pipeline 2.0 unit and race tests;
- glTF dependency discovery and processor integration;
- persistent derived-cache behavior and eviction;
- deterministic cold/warm/invalidate/refill workload gate;
- integration demo;
- strict Ruff;
- compileall.

The workload benchmark prints host timings for diagnostics only. Milestone completion is based on deterministic behavioral contracts, not synthetic FPS claims or fragile machine-specific timing thresholds.
