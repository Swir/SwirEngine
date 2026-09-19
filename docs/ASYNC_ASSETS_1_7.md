# Async Asset Decode/Cook Pipeline — SwirEngine 1.7

`swirengine.assets17.AsyncAssetPipeline` is an additive creator-facing pipeline for moving file reads, content hashing, decode work and CPU-side cooking away from the game/render thread while keeping GPU, audio and other owning-thread resource creation explicit.

It is built on the bounded `swirengine.jobs17.JobScheduler`. It does **not** replace the stable `AssetManager`, `AssetPreloader` or `AssetPipeline` APIs and does not change published 1.x root imports.

## Ownership model

The pipeline has a strict split:

- `dependencies(path)`, content fingerprinting, `decode(path, context)` and `cook(value, context)` run on bounded worker threads.
- `finalizer(value)` runs only when the creator calls `pipeline.poll(...)`.
- `poll(max_items=N)` finalizes at most `N` worker outcomes, so a creator can bound owning-thread handoff work per frame instead of allowing an unbounded upload spike.
- diagnostics contain counters and budgets only; they do not expose decoded/cooked payloads.

Renderer, window, OpenGL/ModernGL, GPU texture/buffer creation and thread-affine audio/device calls belong in the finalizer, never in decode/cook callbacks.

## Basic use

```python
from pathlib import Path

from swirengine.assets import AssetManager
from swirengine.assets17 import AsyncAssetPipeline

assets = AssetManager("assets")
pipeline = AsyncAssetPipeline(assets, max_workers=4, max_pending=256)


def decode_mesh(path: Path, context):
    context.raise_if_cancelled()
    return parse_mesh_bytes(path.read_bytes())


def cook_mesh(mesh, context):
    context.raise_if_cancelled()
    return build_interleaved_vertices(mesh)


def upload_mesh(cooked):
    # Called by poll() on the owning thread.
    return renderer.create_mesh(cooked)


pipeline.register_processor(
    "mesh",
    suffixes=[".mesh"],
    decode=decode_mesh,
    cook=cook_mesh,
    finalizer=upload_mesh,
)

request = pipeline.submit("ship.mesh", priority=10)

# In the owning-thread update loop:
for result in pipeline.poll(max_items=4):
    if result.successful:
        loaded_assets[result.source] = result.value
    # Once the result is stored elsewhere and no retained request depends on it,
    # release the request bookkeeping explicitly.
    pipeline.forget(result.request_id)
```

`submit()` never waits for decode/cook work. `wait_workers()` exists for tests, command-line tools and controlled shutdown paths; a realtime game loop should normally submit and keep polling with a bounded budget.

## Derived request dependencies

A request can depend on earlier pipeline requests:

```python
base = pipeline.submit("base.mesh")
variant = pipeline.submit("variant.mesh", depends_on=[base.request_id])
```

The underlying job scheduler does not start the dependent worker until every referenced worker product succeeds. The dependent callback receives those background products through `context.dependency_values` keyed by request id. This dependency is intentionally between CPU-side products; it does not make a worker depend on a GPU/audio finalizer.

Failed or cancelled scheduler dependencies block dependent worker execution through the existing 1.7 job-system contract.

## File dependencies and stale-build protection

Processors can declare source-file dependencies without reading them on the game thread:

```python
def dependencies(path: Path):
    return [path.with_suffix(".inc")]
```

The resolver executes on the worker. SwirEngine captures SHA-256 `AssetFingerprint` records for the source and every declared dependency before decode/cook, then captures them again after the background build. If any input changed during the build, the product is returned as `AsyncAssetState.STALE` and is never finalized or cached.

Immediately before finalization, the pipeline also checks the captured existence/size/mtime metadata. This is a cheap owning-thread guard against a file changing in the worker-to-finalizer handoff window without re-hashing large assets on the game thread.

## Cache contract

The worker cache stores CPU-side cooked products only. GPU/audio finalizer outputs are not cached by this layer.

- Cache identity is processor name + canonical source path.
- A cache entry is reusable only when the worker has recomputed exact source/dependency fingerprints and they match the stored entry.
- A cache hit still goes through the explicit `poll()` finalizer boundary.
- Stale, cancelled and failed requests never populate the cache.
- `invalidate(asset, processor=...)` and `clear_cache()` provide explicit creator invalidation.
- `cache_hits_total` and `cache_misses_total` count finalized/stale worker products rather than speculative lookups.

This keeps cache validation off the game thread while preserving deterministic accounting.

## Cancellation

`cancel(request_id)` forwards cancellation to `JobScheduler`. Decode/cook callbacks should call `context.raise_if_cancelled()` around expensive phases. If a worker has already succeeded but its result has not yet been handed off, cancellation marks that request for discard: `poll()` returns `CANCELLED`, skips the finalizer and does not populate the cache.

This makes the worker-to-main-thread boundary cancellable rather than forcing an obsolete GPU/audio upload.

## Failure isolation

Worker exceptions are converted to `FAILED` results by the job scheduler. Finalizer exceptions are also captured as one request's `FAILED` result. Neither path raises from `poll()` or stops unrelated finalized work.

Dependency-resolution errors, decode failures and cook failures stay on the worker side. Processor-registration and malformed-submit errors remain synchronous creator errors because no background request was accepted.

## Finalized-request reclamation

Long-running creator sessions can explicitly release finalized request bookkeeping instead of retaining every terminal request for the lifetime of the pipeline.

- `forget(request_id)` removes one finalized request and its delivered scheduler outcome and returns the finalized `AsyncAssetResult`.
- unfinished requests cannot be forgotten;
- a dependency cannot be forgotten while a retained dependent request still references it;
- `prune_finalized(max_items=N)` reclaims at most `N` dependency-safe finalized leaves, newest-first;
- `prune_finalized()` without a limit reclaims every finalized request that can be safely removed in the current retained dependency graph;
- cache entries are independent of request bookkeeping, so reclaiming a request does not discard valid CPU-side cooked cache entries.

For dependency chains, release dependents before their dependencies or use `prune_finalized()`:

```python
base = pipeline.submit("base.mesh")
variant = pipeline.submit("variant.mesh", depends_on=[base.request_id])

# ... poll until both are finalized ...
forgotten_ids = pipeline.prune_finalized()
```

The maintained post-release lifecycle audit stress-tests repeated success, worker failure and cancellation paths and requires zero retained request/scheduler records after explicit reclamation.

## Diagnostics

`pipeline.diagnostics()` exposes:

- configured worker and unfinished-job budgets;
- submitted/completed/failed/cancelled/stale totals;
- exact finalized cache hit/miss totals;
- number of finalizer calls;
- current pending request count and cached CPU-product count.

Use the existing job scheduler diagnostics when lower-level queue/running/back-pressure details are needed. Payload values are intentionally absent from diagnostics.

## Performance contract

`tools/benchmark_async_assets_1_7.py` creates 512 small assets, performs a cold decode/cook pass and a fingerprint-validated cached pass (1,024 requests total), drains finalization in bounded slices and requires completion within the deliberately generous 5.0-second CI budget on the Python 3.13 validation runner.

This is a regression/workload contract, not an FPS claim. Real asset throughput depends on storage, decoder complexity, content size and creator finalizers.

## Compatibility

The async asset pipeline originated during the 1.7 source-development checkpoint and remains additive in the published SwirEngine 2.0 line. Published 1.x asset APIs remain the compatibility floor; the new reclamation methods are additive lifecycle hardening and do not rewrite historical releases.

SwirEngine **2.0.0 is publicly released**. Active maintenance status is tracked in [`SWIRENGINE_2_0_POST_RELEASE_AUDIT.md`](SWIRENGINE_2_0_POST_RELEASE_AUDIT.md); runtime/resource lifecycle work belongs to Domain 5 of that audit.
