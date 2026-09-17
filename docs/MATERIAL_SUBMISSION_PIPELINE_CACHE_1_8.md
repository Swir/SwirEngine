# SwirEngine 1.8 Material Submission & Pipeline State Cache

SwirEngine 1.8 Milestone 4 adds an **opt-in, renderer-independent material submission planner** and a
**bounded pipeline/program state cache**. The goal is to reduce avoidable render-state churn without
changing stable 1.x renderer behavior or silently reordering work that creators mark as order-sensitive.

This milestone does **not** replace `Renderer2`, force a backend migration, or claim a physical GPU
throughput improvement by itself. It provides deterministic planning/cache contracts that the 1.8
renderer compatibility bridge can integrate later.

## Why this exists

Real games regularly submit thousands of draws that reuse a much smaller set of shader/pipeline and
material states. Submitting those draws in arbitrary gameplay order can create unnecessary pipeline,
program, blend, depth, texture-binding, and material-state changes. SwirEngine now has a portable layer
that can:

- describe backend-neutral pipeline state with stable immutable keys;
- describe material identity separately from pipeline/program state;
- sort reorderable draw runs deterministically to reduce state changes;
- preserve explicit ordering barriers for transparent/UI/post-process/creator-sensitive work;
- prepare a compiled submission plan against a bounded backend pipeline cache;
- invalidate pipelines deterministically after shader changes;
- expose portable diagnostics and fingerprints for regression testing and creator tooling.

## Public module

```python
from swirengine.render_submission18 import (
    MaterialKey,
    MaterialSubmissionQueue,
    PipelineStateCache,
    PipelineStateKey,
)
```

The module is additive. Existing renderers do not instantiate it unless a creator/backend explicitly
opts in.

## Pipeline state keys

`PipelineStateKey` captures state that must be compatible before two draws may reuse one backend
pipeline/program object:

- shader identity;
- vertex layout;
- blend mode;
- depth mode;
- cull mode;
- primitive topology;
- render-target signature;
- sample count;
- sorted compile-time variant pairs.

Keys are immutable and normalized. Their SHA-256 fingerprint is precomputed once, so draw sorting and
cache lookup do not repeatedly serialize the same key.

```python
opaque = PipelineStateKey(
    "lit",
    vertex_layout="static-pnt",
    blend_mode="opaque",
    depth_mode="less-write",
    cull_mode="back",
    render_target="hdr-main",
)

alpha = PipelineStateKey(
    "lit",
    vertex_layout="static-pnt",
    blend_mode="alpha",
    depth_mode="less-read",
    cull_mode="back",
    render_target="hdr-main",
)
```

Two keys only compare equal when every state field and normalized variant pair matches.

## Material keys

`MaterialKey` separates material identity from the pipeline state. It contains:

- a stable material id;
- ordered texture/resource ids;
- a uniform-layout identity.

The material key also has a precomputed deterministic fingerprint. Runtime uniform values are not
embedded in the key because rapidly-changing gameplay data should not create a new material identity
for every frame.

## Submission queue

Create a bounded queue and author draws in gameplay order:

```python
queue = MaterialSubmissionQueue(max_draws=20000)
queue.submit("crate-7", opaque, crate_material, "crate-mesh", layer=0)
queue.submit("pipe-2", opaque, pipe_material, "pipe-mesh", layer=0)
```

`compile()` creates a portable `MaterialSubmissionPlan`.

### Reorderable draws

By default, a draw is reorderable inside its current contiguous run. SwirEngine sorts that run by:

1. layer;
2. pipeline fingerprint;
3. material fingerprint;
4. creator-provided integer `sort_depth`;
5. mesh id;
6. original sequence as the final stable tie-breaker.

This makes the plan deterministic while clustering compatible state.

### Order barriers

Set `preserve_order=True` for work that cannot safely move relative to surrounding draws:

```python
queue.submit(
    "glass-window",
    alpha,
    glass_material,
    "window-mesh",
    layer=1,
    sort_depth=120,
    preserve_order=True,
)
```

An order-preserved draw is a hard barrier. Work before it cannot cross to the right, and work after it
cannot cross to the left. The barrier itself remains at its authored position. This is the safe path for
transparent blending, UI composition, post-process ordering, stencil-sensitive work, or any creator-
defined draw dependency.

## Diagnostics

Every compiled plan reports:

- authored and compiled draw counts;
- reorderable versus strict ordered draws;
- number of sortable segments;
- pipeline switches before and after compilation;
- material switches before and after compilation;
- pipeline/material switches saved by planning.

The values describe CPU-side submission planning only. They are not FPS or physical GPU throughput
claims.

## Pipeline state cache

`PipelineStateCache` is generic over the backend pipeline/program object type. The backend supplies
`create` and `destroy` callbacks:

```python
cache = PipelineStateCache(
    create=backend_create_pipeline,
    destroy=backend_destroy_pipeline,
    max_entries=256,
)
```

### Deterministic LRU behavior

- cache hits update a monotonic touch sequence;
- a miss creates exactly one backend state;
- when full, the least-recently-used entry is selected;
- equal-age ties use the pipeline fingerprint for deterministic selection;
- resident cache count never exceeds `max_entries` after a successful operation.

### Failure containment

Backend creation and destruction failures are surfaced through `RenderSubmissionError` with stable
creator-facing codes.

Important behavior:

- a creation failure does not mutate cache residency;
- if eviction destruction fails, the old victim remains cached;
- the just-created untracked candidate is destroyed as rollback before the failure is returned;
- single-key invalidation keeps the entry resident when backend destruction fails;
- shader-wide invalidation continues deterministically through other variants and reports partial
  failure without deleting failed entries;
- `clear()` keeps failed entries live and is retryable;
- `close()` only marks the cache closed after every resident backend state was destroyed successfully.

These rules prevent diagnostics from claiming state was removed when the backend says otherwise.

## Preparing a plan

`cache.prepare(plan)` resolves backend pipeline/program objects in the exact compiled draw order and
returns `(draw, backend_pipeline)` pairs. Repeated compatible draws become cache hits.

The cache does not submit GPU commands. The renderer/backend remains responsible for binding the
prepared state, applying material data, and issuing the actual draw.

## Shader hot reload

`invalidate_shader("lit")` destroys every cached variant using that shader identity in deterministic
fingerprint order. A later `prepare()` or `get_or_create()` call rebuilds only states that are used again.

This is intended to support later editor/live-development integration without forcing cache-wide
rebuilds after a single shader change.

## Portable state and fingerprints

`PipelineStateKey`, `MaterialKey`, compiled submission diagnostics, and the cache's logical state can be
fingerprinted deterministically. Backend pipeline payloads/callbacks are intentionally excluded from
portable data.

This lets tests and future tooling compare plans/cache state without serializing driver objects.

## Workload regression gate

`tools/benchmark_render_submission_1_8.py` executes a deterministic workload of:

- 20 frames;
- 4,096 draws per frame;
- 81,920 total draws;
- 32 pipeline states;
- 96 materials;
- periodic explicit ordering barriers;
- compiled submission planning plus pipeline-cache preparation.

The Python 3.13 CI contract uses a generous **5.0 second** ceiling. The gate also requires substantial
pipeline-switch reduction and exact cache create/hit accounting. It is a regression ceiling, not a
published FPS benchmark.

## Creator demo

Run:

```bash
python examples/demo_render_submission_1_8.py
```

The demo shows opaque state clustering, an alpha-order barrier, compiled switch diagnostics, cache
reuse, and a portable plan fingerprint.

## Compatibility

- Existing root renderer imports and stable 1.x runtime paths are unchanged.
- This module does not require a GPU backend to import or test.
- No backend is silently selected.
- No draw is reordered across an explicit order barrier.
- SwirEngine 1.8 remains source-only; no 1.8 GitHub Release, tag, or PyPI publication is created.

The next public release remains SwirEngine 2.0 after the dedicated 2.0 roadmap and final release gate
are fully verified.
