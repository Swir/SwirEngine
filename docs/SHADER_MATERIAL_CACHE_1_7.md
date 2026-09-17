# Shader & Material Preparation Cache — SwirEngine 1.7

SwirEngine 1.7 adds an opt-in shader/material preparation layer in
`swirengine.shader_cache17`. It is deliberately additive: stable 1.x rendering and
material APIs keep their existing behavior, while creators and future renderer integrations
can move deterministic CPU-side shader preparation away from the owning thread.

## Contract

`ShaderMaterialPreparationCache` separates work into two explicit phases:

1. **Background-safe preparation** — canonical source capture, deterministic fingerprinting,
   optional creator preprocessing and cache lookup run through the bounded 1.7 job scheduler.
2. **Owning-thread finalization** — creator-provided compile/material creation callbacks run
   only when `poll()` is called on the thread that created the cache.

The cache stores only `PreparedShaderMaterial` CPU-side data. It never stores a GL/Vulkan/
Metal object and never calls a creator finalizer from a worker thread. This keeps the new
system transportable across render backends and prevents the additive 1.7 layer from
silently changing the stable renderer contract.

## Deterministic source keys

A request fingerprint is SHA-256 over canonical JSON containing:

- the normalized shader stage mapping;
- creator `defines` metadata;
- creator `material` metadata.

Mapping order does not change the fingerprint. Changing shader text, a define, or material
metadata does. Floating-point metadata must be finite and mapping keys must be strings.
Combined shader source size is bounded by `max_source_bytes` before worker admission.

```python
from swirengine.shader_cache17 import ShaderMaterialPreparationCache

cache = ShaderMaterialPreparationCache(max_workers=2, max_cache_entries=128)

request = cache.submit(
    {
        "vertex": vertex_source,
        "fragment": fragment_source,
    },
    defines={"QUALITY": 2},
    material={"roughness": 0.4},
    preprocess=preprocess_shader,
    finalize=compile_on_render_thread,
)

cache.wait_workers(timeout=2.0)  # waits for CPU work only
for outcome in cache.poll(max_items=8):  # owning-thread boundary
    if outcome.successful:
        use_program(outcome.value)
```

`preprocess_shader(source, context)` runs on a background worker and must return a mapping
with exactly the same normalized stage set as the submitted source. It can transform source
text, inject generated declarations, expand creator macros or perform other CPU-only work.
It receives a cooperative cancellation context.

`compile_on_render_thread(prepared)` runs only inside owner-thread `poll()`. Integrations can
compile a backend shader, create a material/program object, resolve GPU handles, or perform
another operation that must stay on the renderer-owning thread.

## Bounded work and back-pressure

The cache exposes independent limits:

- `max_workers` — worker concurrency;
- `max_pending` — unfinished scheduler jobs;
- `max_requests` — submitted requests that have not yet been finalized by `poll()`;
- `max_cache_entries` — retained CPU-side prepared artifacts;
- `max_source_bytes` — combined source bytes captured by one request.

`poll(max_items=N)` finalizes at most `N` completed jobs. Cache retention uses deterministic
FIFO eviction: inserting a new prepared fingerprint into a full cache evicts the oldest
retained fingerprint. Cache hits do not reorder entries, so eviction does not depend on
worker timing.

## Invalidation and stale work

`invalidate(fingerprint)` removes one cached prepared artifact and advances a generation for
that source. If matching background work was already running, its result becomes `stale`
and is refused before owner-thread finalization.

`clear_cache()` invalidates the entire cache and advances the global generation, so every
in-flight product submitted before that boundary is also refused. This is intended for
renderer reloads, include/dependency changes that are not represented in submitted metadata,
or project-wide material rebuilds.

Creators can also call `invalidate_source(...)` with the same stages/defines/material values
used for submission instead of manually computing a fingerprint.

## Cancellation and failure isolation

Cancellation remains valid after CPU work finishes but before `poll()` finalizes the request.
That makes it possible to discard a no-longer-needed shader without accidentally compiling it
on the next frame.

Preprocessor failures and finalizer failures are isolated to their request and are returned as
`ShaderMaterialOutcome` failures. A failed finalizer does not poison the reusable CPU-side
prepared artifact: a later request for the same fingerprint can reuse preparation and retry a
different or repaired finalizer.

## Diagnostics

`diagnostics().portable()` exposes only bounded numeric counters and limits:

- submitted/completed/failed/cancelled/stale totals;
- preparation cache hits/misses and deterministic evictions;
- preprocess and owner-thread finalizer call counts;
- invalidation count;
- pending requests and cached entries.

Shader source, material metadata, prepared payloads and finalizer return objects are never
included in portable diagnostics.

## Verification

The dedicated `Shader Material Cache 1.7` workflow runs on Python 3.10, 3.13 and 3.14 and
covers focused tests, stable 1.7 background-job and async-asset regressions, Ruff, compile
checks and a creator demo. Python 3.13 additionally runs the deterministic workload gate:
512 unique prepared variants followed by 512 exact cache reuses must complete below the
repository's generous 5-second CI budget. The workload is a regression contract, not an FPS
claim.

SwirEngine 1.7 remains a source-only development checkpoint. GitHub Release and PyPI
publication remain frozen until SwirEngine 2.0.
