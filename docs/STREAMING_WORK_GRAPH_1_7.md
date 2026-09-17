# Streaming Work Graph 3.0 — SwirEngine 1.7

`swirengine.work_graph17` is an additive, opt-in orchestration layer for staged world/content work. It does not replace the stable 1.x `Scene`, asset, renderer, ECS or world-streaming APIs and does not change the published 1.5.0 package surface.

## What it solves

Large content transitions commonly mix work that is safe in background threads with work that must stay on the owning game/render thread. `StreamingWorkGraph` makes that boundary explicit and deterministic:

- `PREFETCH` and `DECODE` phases execute through the bounded 1.7 `JobScheduler` worker pool;
- `INSTANTIATE` and `UNLOAD` phases execute only from creator-controlled `poll(...)` calls;
- dependencies are explicit and graph construction requires dependencies to be added first, so cycles cannot be authored accidentally;
- graph size, scheduler pending work, background submissions per poll and main-thread callback execution are all bounded;
- one failed/cancelled branch blocks only its dependents while independent branches continue;
- diagnostics report progress/state/counters without exposing work-result payloads.

## Basic pipeline

```python
from swirengine.work_graph17 import StreamingWorkGraph, WorkPhase

graph = StreamingWorkGraph(max_workers=4, max_nodes=1024)

graph.add("prefetch", WorkPhase.PREFETCH, lambda _ctx: read_bytes())
graph.add(
    "decode",
    WorkPhase.DECODE,
    lambda ctx: decode(ctx.dependency_values["prefetch"]),
    dependencies=["prefetch"],
)
graph.add(
    "instantiate",
    WorkPhase.INSTANTIATE,
    lambda ctx: mount_scene(ctx.dependency_values["decode"]),
    dependencies=["decode"],
)

graph.start()

# Call from the owning game thread. This hard-bounds handoff/callback work per call.
while not graph.complete:
    graph.poll(max_items=8)
```

`run_until_complete(...)` exists for tests, command-line tooling and deterministic offline workloads. Real-time games should normally call `poll(...)` from their update loop instead of blocking.

## Thread-affinity contract

The phase-to-affinity mapping is fixed:

| Phase | Affinity | Intended use |
| --- | --- | --- |
| `PREFETCH` | background | file/network/cache read preparation that does not mutate engine-owned UI/GPU/window state |
| `DECODE` | background | CPU-only parsing, decoding, decompression and immutable preparation |
| `INSTANTIATE` | main thread | scene/ECS/object creation, renderer/audio upload, owning-thread mutation |
| `UNLOAD` | main thread | scene/resource detachment and owning-thread cleanup |

Background functions receive a `WorkContext` whose `affinity` is `BACKGROUND`; instantiate/unload callbacks receive `MAIN_THREAD`. SwirEngine deliberately does not attempt to monkey-patch or intercept arbitrary creator code. The safety boundary is structural: engine-owned thread-affine work is represented only by main-thread phases and those callbacks are never submitted to workers.

## Dependencies and data flow

Each node can depend on previously added nodes. Successful dependency results are exposed through the read-only `context.dependency_values` mapping. Failed, cancelled or blocked dependencies never execute dependent callbacks.

Requiring dependencies to exist at `add(...)` time provides three useful guarantees:

1. cycles cannot be created;
2. dependency order is deterministic;
3. malformed graph construction fails before execution begins.

## Bounded work

`StreamingWorkGraph` exposes multiple independent safety bounds:

- `max_nodes` limits authored graph size;
- `max_workers` limits concurrent background execution;
- `max_pending_background` is delegated to the verified bounded `JobScheduler`;
- `max_background_submissions_per_poll` limits newly scheduled worker work from one graph advancement;
- `poll(max_items=...)` limits completed-worker handoffs plus main-thread callbacks handled in one owning-thread call.

These are work contracts, not FPS claims. The dedicated 1.7 validation gate also runs a deterministic 2,048-node workload (512 four-stage chains) against a generous 5.0-second CI budget.

## Fault isolation

Worker exceptions and main-thread callback exceptions become node-level `FAILED` results. Dependents become `BLOCKED` with a stable dependency diagnostic while unrelated graph branches continue normally.

`cancel(node_id, cascade=True)` explicitly cancels a node and its dependent subgraph. With `cascade=False`, only the selected node is cancelled and normal dependency propagation blocks its dependents. Cancellation never silently marks unrelated work as cancelled.

## Diagnostics

`graph.diagnostics()` returns `WorkGraphDiagnostics` with:

- state counts (`waiting`, `scheduled`, `ready_main`, `succeeded`, `failed`, `cancelled`, `blocked`);
- total/terminal node counts and deterministic progress;
- background submission and main-thread execution totals;
- failure/cancellation/block counters;
- last-poll handoff/callback counts;
- phase counts.

`portable()` intentionally contains no work payloads. Actual node values remain available only through `graph.result(node_id)` after the node is terminal.

## Compatibility and release policy

Streaming Work Graph 3.0 is a source-development feature on the SwirEngine 1.7 path toward 2.0. It keeps published SwirEngine 1.5.0 metadata unchanged and does not add root-level imports that could alter established 1.x projects.

**Release/PyPI remain frozen until SwirEngine 2.0.**
