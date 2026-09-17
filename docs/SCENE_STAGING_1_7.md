# Scene Build & Activation Staging — SwirEngine 1.7

`swirengine.scene_staging17` is an additive, opt-in bridge between background preparation and
thread-affine scene mutation. It does not replace `Scene`, `Prefab`, ECS, `ChunkContent`, or the
1.5 world-streaming APIs.

## Why it exists

Large rooms, streamed cells, prefab batches and derived scene descriptions often contain CPU-side
work that can be prepared away from the render/game thread. The live `Scene`, renderer, window,
physics ownership and lifecycle hooks still need deterministic owning-thread mutation.

`SceneStager` separates those responsibilities:

1. a `ScenePlanBuilder` runs through the bounded 1.7 `JobScheduler`;
2. the builder receives `SceneBuildContext`, which deliberately has no live `Scene`;
3. the builder returns an immutable `PreparedScenePlan`;
4. `SceneStager.poll()` applies a bounded number of activation steps on the thread that created the
   stager;
5. if activation fails or is cancelled, already-applied steps roll back in reverse order, also
   under the same explicit per-poll budget.

Requests activate in submission order even when background preparation completes out of order.
That deterministic head-of-line rule favors reproducibility over opportunistic scene mutation.

## Creator example

```python
from swirengine.core.scene import Scene
from swirengine.scene_staging17 import (
    PreparedScenePlan,
    SceneStager,
    object_factory_step,
)

scene = Scene()

def build_room(context):
    context.raise_if_cancelled()
    return PreparedScenePlan(
        context.request_id,
        (
            object_factory_step("floor", lambda _scene: Floor()),
            object_factory_step("props", lambda _scene: [Crate(), Lamp()]),
        ),
    )

with SceneStager(scene, max_workers=2, max_activation_steps_per_poll=2) as staging:
    staging.submit("room-a", build_room)
    while staging.diagnostics().unfinished:
        staging.poll(max_steps=2)
```

The background builder should perform CPU-side preparation only. The object factories above execute
later from `poll()` on the owning thread.

## Stable integration adapters

The module ships adapters instead of changing stable APIs:

- `object_factory_step(...)` creates and owns ordinary Scene objects;
- `prefab_step(...)` clones the existing stable `Prefab` off the live Scene, then registers its
  objects transactionally;
- `entity_step(...)` composes an ECS entity from copied component templates;
- `chunk_content_step(...)` mounts stable `ChunkContent` and uses `SceneMount.unmount()` for
  rollback;
- `callback_step(...)` is the low-level escape hatch for creator-defined transactions.

The `ChunkContent` adapter rejects and cleans newly-created ECS entities that the factory forgot to
list in `ChunkContent.entities`, preventing a failed activation from silently stranding ECS state.

## Transaction rules

A successful step returns an opaque rollback token. If a later step fails, successful steps roll
back in reverse order. Built-in adapters clean their own partial mutations if their apply path
raises before returning a token.

For `callback_step`, the creator-owned apply callback must either be atomic or clean up its own
partial mutation before raising. The stager cannot compensate a mutation for which no token was
returned.

Cancellation during background preparation is cooperative through `SceneBuildContext`. Cancellation
during activation switches the request into bounded reverse rollback. Failures and cancellations
do not stop independent later requests.

## Budgets and diagnostics

Three independent bounds protect frame time and memory growth:

- `JobScheduler.max_workers` limits simultaneous background builders;
- `max_pending_preparations` bounds unfinished background preparation;
- `poll(max_steps=...)` / `max_activation_steps_per_poll` bounds owning-thread apply and rollback
  work.

`max_requests` separately bounds retained request state. Terminal requests can be explicitly
`forget()`-ten after their outcome is no longer needed.

`SceneStagingDiagnostics` contains states, limits and counters only. It never exposes scene objects,
activation tokens or prepared payloads.

## Thread ownership

The thread that creates `SceneStager` becomes its activation owner. `poll()`, `run_until_idle()`,
`forget()` and `shutdown()` reject calls from another thread. This makes accidental background
Scene mutation fail loudly rather than becoming a renderer/runtime race.

## Compatibility

This system is additive. Existing `Scene`, `Prefab`, ECS, `LargeWorldStreamer`,
`WorldStreamingRuntime` and stable 1.x root imports are unchanged. Projects that do not opt into
`swirengine.scene_staging17` keep their existing behavior.

SwirEngine 1.7 is a source-development checkpoint. No 1.7 tag, GitHub Release or PyPI publication
is created; public publication remains frozen until SwirEngine 2.0.
