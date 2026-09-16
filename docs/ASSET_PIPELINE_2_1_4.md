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
- make glTF imports dependency-aware, including external buffers and images;
- provide opt-in mesh and texture optimization without destructive source rewrites.

## Core API

`AssetPipeline` is layered on top of `AssetManager`:

```python
from swirengine import AssetManager, AssetPipeline

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

## Dependency graph and hot reload

`AssetDependencyGraph` stores source-to-dependency edges and reverse edges. `affected_by()` walks reverse edges transitively and is cycle-safe.

When `AssetPipeline.bind()` is active, existing `AssetManager.invalidate()` notifications propagate into the pipeline. `AssetManager.poll_changes()` already invalidates changed watched files and calls registered invalidators, so filesystem-driven hot reload uses the same dependency-aware eviction path. Invalidating a texture can therefore evict a material import, a glTF import or another higher-level derived asset that depends on it.

## glTF / GLB integration

`register_gltf_asset_processor()` registers `.gltf` and `.glb` with the pipeline. CPU primitive/material parsing runs in workers.

`gltf_asset_dependencies()` discovers external glTF resources such as:

- external buffer URIs;
- external image URIs.

Data URIs and embedded GLB chunks are part of the source container and do not create external dependency edges.

Changing an external `.bin` file or texture invalidates the derived glTF import on the next dependency notification or fingerprint check.

The 1.4 importer also preserves more glTF PBR material intent:

- `OPAQUE`, `MASK` and `BLEND` alpha modes;
- `alphaCutoff`;
- `doubleSided`;
- base color, metallic/roughness, normal, occlusion and emissive channels already supported by the existing importer.

Preserving material metadata does not imply that every renderer backend already renders every alpha mode differently. The CPU asset keeps the intent so renderer support can evolve without destructive re-import. `KHR_texture_transform` is still rejected explicitly and is not claimed as supported.

## Mesh optimization

`optimize_mesh_data()` performs a conservative optimization compatible with the current expanded-triangle `MeshData` representation. It removes degenerate triangles while preserving the order, normals and UVs of surviving vertices.

`register_gltf_asset_processor(..., optimize_meshes=True)` enables that cleanup for imported glTF primitives. The option defaults to `False` so existing 1.x behavior does not silently change.

The optimizer reports input/output triangle counts and the number of removed degenerates. It raises instead of producing an empty mesh when every triangle is degenerate.

## Texture optimization

`optimize_texture_bytes()` is an opt-in CPU preprocessing utility. It:

- never enlarges the source texture;
- preserves aspect ratio when applying a maximum dimension;
- supports PNG, JPEG and WebP output;
- applies EXIF orientation before encoding;
- reports input/output dimensions and byte counts;
- returns bytes instead of overwriting the source asset.

`register_texture_optimizer()` exposes the operation as an Asset Pipeline processor for PNG/JPEG/WebP files. Because processor suffix ownership is exclusive, projects explicitly choose whether the optimizer owns those suffixes.

JPEG cannot preserve alpha. When JPEG output is selected, alpha is flattened onto a black RGB background before encoding. PNG/WebP should be used when alpha preservation is required.

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

This cache is intentionally separate from the in-memory object cache: arbitrary runtime Python objects are not persisted automatically. Texture-optimization output can be stored in this cache explicitly by creator/export tooling.

## Diagnostics

`AssetImportDiagnostics` exposes:

- configured worker count;
- queued and running jobs;
- completed, failed, stale and cancelled totals;
- cache hits and misses;
- current cached entries;
- invalidated entries;
- dependency graph node count.

`DerivedAssetCacheDiagnostics` reports disk-cache entries, bytes used, hits, misses, writes and evictions. Mesh and texture optimization result objects expose their own before/after statistics for creator tooling.

## Compatibility

The existing `AssetManager` and `AssetPreloader` remain available. Asset Pipeline 2.0 is additive and does not change the stable package version during 1.4 development. Mesh optimization remains opt-in, texture optimization never rewrites source files and persistent derived caching does not serialize arbitrary runtime objects.

## Validation contract

The milestone validation covers:

- legacy asset/preloader regressions;
- Asset Pipeline 2.0 unit and race tests;
- public API exports;
- glTF dependency discovery, stronger PBR metadata preservation and processor integration;
- texture/mesh optimization behavior and diagnostics;
- persistent derived-cache behavior and eviction;
- deterministic cold/warm/invalidate/refill workload gate;
- integration demo;
- strict Ruff;
- compileall.

The workload benchmark prints host timings for diagnostics only. Milestone completion is based on deterministic behavioral contracts, not synthetic FPS claims or fragile machine-specific timing thresholds.
