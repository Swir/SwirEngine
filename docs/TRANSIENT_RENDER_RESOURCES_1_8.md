# Transient GPU Resource Pool & Attachment Reuse — SwirEngine 1.8

SwirEngine 1.8 Milestone 2 adds an opt-in backend-neutral resource-pool layer in
`swirengine.render_resources18`. It consumes the verified `RenderGraphPlan` lifetime contract from
Milestone 1 without changing stable 1.x `Renderer`/`Renderer2` behavior or root imports.

The pool owns backend objects supplied by creator/backend callbacks. It does **not** create OpenGL,
Vulkan, Metal or Direct3D objects by itself and does not claim that render-graph alias slots are
physical GPU allocations.

## Resource descriptors

`RenderResourceDescriptor` is an immutable compatibility key containing:

- resource `kind` and backend format;
- width, height, layers and sample count;
- usage class;
- declared byte size used by the pool's explicit memory budget.

Reuse is intentionally conservative: only an exact descriptor match can reuse an idle object.
That prevents an attachment from silently crossing incompatible texture/buffer formats, dimensions,
sample counts or usage classes.

```python
from swirengine.render_resources18 import (
    RenderResourceDescriptor,
    TransientRenderResourcePool,
)

pool = TransientRenderResourcePool(
    create=create_backend_resource,
    destroy=destroy_backend_resource,
    max_resources=128,
    max_bytes=512 * 1024 * 1024,
)

descriptor = RenderResourceDescriptor(
    "texture",
    "rgba16f",
    1920,
    1080,
    usage="color-attachment",
    size_bytes=1920 * 1080 * 8,
)
lease = pool.acquire(descriptor)
use_backend_resource(lease.resource)
pool.release(lease.handle)
```

## Bounded residency and deterministic reuse

The pool enforces independent hard limits for resident object count and declared resident bytes.
When a new incompatible object would exceed a limit, the oldest idle resource is evicted first using
a stable release-sequence/slot ordering. A resource that is still leased is never evicted.

If all reclaimable capacity is leased, acquisition fails explicitly instead of silently exceeding
the configured budget. Resource creation failures are isolated to the failed acquire and do not
partially mutate residency accounting.

Handles contain a slot plus a monotonically increasing generation. Reacquiring a previously idle
slot advances the generation, so an old lease cannot later release or resolve the new lease.

## Render-graph integration

`RenderPlanResourceSchedule.from_plan(...)` translates active transient lifetimes from a verified
`RenderGraphPlan` into deterministic pass-indexed acquire/release events. Every active transient
resource must have an explicit backend descriptor. External and persistent resources remain outside
this pool.

`RenderPlanPoolSession` then applies that schedule one pass at a time:

```python
schedule = RenderPlanResourceSchedule.from_plan(plan, descriptors)
session = RenderPlanPoolSession(pool, schedule)

for index in range(schedule.pass_count):
    active_resources = session.begin_pass(index)
    render_pass(plan.passes[index], active_resources)
    session.end_pass(index)
```

Pass order is strict. If a backend create fails partway through one pass's acquisitions, every
resource acquired for that pass is released before the error escapes, and the session remains at
the same pass index for an explicit retry or abort.

The scheduler follows graph lifetimes rather than blindly trusting alias-slot numbers. Alias slots
are planner metadata; backend compatibility is still decided by `RenderResourceDescriptor`.

## Trimming and backend failure containment

`trim(target_resources=..., target_bytes=...)` deterministically removes idle allocations until the
requested residency target is reached or no idle resource remains. The pool never trims a currently
leased object.

Backend destruction errors are surfaced with the stable `RenderResourcePoolError` contract and are
counted in diagnostics. Residency accounting is changed only after a successful backend destroy,
so a failed destruction cannot make the pool report memory as freed when it is still owned.

`close()` attempts destruction of every retained backend object before reporting an aggregate
failure. A second `close()` is safe and does not repeat already completed cleanup.

## Diagnostics

`diagnostics().portable()` contains bounded numeric data only:

- resident/free/leased resource counts and resident bytes;
- peak residency;
- create/reuse/release/eviction/trim counters;
- backend create/destroy failures;
- capacity failures and stale-handle failures.

Backend objects and creator payloads are never included in portable diagnostics.

## Verification contract

The dedicated `Transient Render Resources 1.8` workflow validates the layer on Python 3.10, 3.13
and 3.14. It runs focused resource-pool tests together with the verified Render Graph 3.0 and stable
1.4 accelerated-renderer regressions, strict Ruff and compile checks, the creator demo, and a
Python 3.13 deterministic workload.

The workload runs 100 logical frames over a 512-pass linear render graph (51,200 transient logical
acquisitions) and requires the compatible pool to stabilize at two physical resources while
remaining below a deliberately generous 5-second CI ceiling. This is a planner/pool regression
budget, not an FPS or GPU-performance claim.

Milestone completion also requires the repository-wide compatibility/regression workflows to remain
green on the exact final candidate head.

SwirEngine 1.8 remains a source-only checkpoint. **Release/PyPI: frozen until SwirEngine 2.0.**
