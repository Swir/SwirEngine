# Frame-time Budget Controller — SwirEngine 1.7

SwirEngine 1.7 adds the opt-in `swirengine.frame_budget17` controller for bounding
owning-thread handoff/finalization work by explicit per-frame time, item and callback limits.
The feature is additive and does not change stable 1.x game-loop or profiler behavior.

## Why this exists

The 1.7 parallel runtime can move decode, serialization, graph work and shader preparation to
workers, but some work still must return to the owning/render thread. Unbounded completion
bursts can turn successful background work into a main-thread frame spike. `FrameTimeBudgetController`
provides one deterministic place to meter those drains.

The controller does **not** create worker threads. It owns only small creator-provided drain
callbacks. Each callback receives a hard item limit and must return the number of items it
actually consumed. Time is measured between callbacks, so each callback must keep its own
single-call work bounded.

## Basic use

```python
from swirengine.frame_budget17 import FrameTimeBudgetController

budget = FrameTimeBudgetController(
    frame_budget_ms=2.0,
    max_items_per_frame=64,
    max_drain_calls_per_frame=12,
)

budget.register(
    "shader_finalize",
    drain_shader_results,
    priority=20,
    max_items_per_frame=16,
    reserved_items=1,
)
budget.register(
    "scene_activation",
    activate_ready_scenes,
    priority=10,
    max_items_per_frame=8,
    reserved_items=1,
)
budget.register(
    "save_commits",
    commit_ready_saves,
    priority=0,
    max_items_per_frame=2,
    reserved_items=1,
)

frame = budget.run_frame()
```

`run_frame()` stops starting new drain calls when any configured global boundary is reached:

- elapsed time reaches `frame_budget_ms`;
- consumed items reach `max_items_per_frame`;
- drain invocations reach `max_drain_calls_per_frame`.

The controller cannot preempt a callback that is already running. A callback that needs a
harder latency bound should itself process smaller units and honor the item limit it receives.

## Priorities, reservations and fairness

Every lane has a creator priority and a per-frame item cap. The normal pass runs higher
priorities first. Lanes with equal priority use stable registration order rotated by frame
index, preventing one equal-priority lane from winning every tight frame.

`reserved_items` adds a reservation pass before normal priority scheduling. Reservation start
order also rotates by frame index. This is useful for low-priority but latency-sensitive work
such as save finalization or cleanup that should receive a small opportunity even while a
higher-priority renderer/streaming lane is busy.

Reservations are best-effort rather than an overcommit promise: they still obey the global
item, call and time boundaries. Creators therefore retain one coherent frame budget rather
than separate subsystems each assuming they own the whole frame.

## Callback contract

A drain callback has the shape:

```python
def drain(limit: int) -> int:
    ...
    return consumed
```

The returned value must be an integer from `0` through `limit`. Returning fewer items than
requested tells the controller that the lane was exhausted for that frame. Invalid return
values and creator exceptions are isolated to that lane and recorded in the frame report and
diagnostics instead of aborting later lanes.

Lane registration/configuration and `run_frame()` are owning-thread operations. Configuration
changes are rejected during an active frame drain, and `run_frame()` is not reentrant.

## Observability

Each call returns `FrameBudgetFrame`, including:

- configured and measured frame-budget time;
- global item/call budgets and actual consumption;
- whether a global boundary was exhausted;
- lanes deferred to a later frame;
- per-lane call/item/time/error reports.

`diagnostics()` exposes bounded cumulative and latest-frame counters plus per-lane statistics.
The diagnostics intentionally contain counts/timings/configuration only, never creator
payloads.

The controller can bind directly into the additive 1.5 `PerformanceDiagnostics2` provider
surface:

```python
controller.bind_performance(performance)
```

Nested per-lane counters are flattened by `PerformanceDiagnostics2` at frame end, making the
budget visible in the normal deterministic performance capture without modifying the stable
1.x `Profiler` API.

## Suggested integration with 1.7 async systems

Useful owning-thread drains include:

- async asset finalization after worker decode/cook;
- scene activation commits after background/staged construction;
- shader/material finalizers from `ShaderMaterialPreparationCache.poll()`;
- background-save completion/notification work;
- other creator jobs that must cross back to the game/render thread.

The controller remains generic instead of importing those systems. This avoids a hidden global
scheduler and keeps each subsystem independently usable/testable.

## Verification contract

The dedicated `Frame Budget 1.7` workflow validates the controller on Python 3.10, 3.13 and
3.14 with focused budget/fairness/error/thread tests and relevant 1.7 async/performance
regressions. Python 3.13 additionally runs a deterministic 10,000-frame workload with 40,000
bounded drain calls and 320,000 consumed work items under a generous 5-second CI budget.
That workload is a regression contract, not an FPS or real-game frame-time claim.

SwirEngine 1.7 remains a source-only development checkpoint. GitHub Release and PyPI
publication remain frozen until SwirEngine 2.0.
