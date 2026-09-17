# Background Jobs & Main-thread Handoff — SwirEngine 1.7

SwirEngine 1.7 introduces an additive background-work primitive in `swirengine.jobs17`. It is intended for CPU/file/decode preparation that can safely run away from the game/render thread while preserving explicit ownership of OpenGL, window, audio-backend and live scene mutations.

This is a source-development API. SwirEngine 1.5.0 remains the latest published package and the next public Release/PyPI publication is reserved for 2.0.

## Core contract

`JobScheduler` owns a bounded `ThreadPoolExecutor`. Creators choose `max_workers` and `max_pending`; once the unfinished-job budget is full, a new submission fails atomically with `JobRejectedError(code="backpressure")` instead of silently growing memory or executor queues.

```python
from swirengine.jobs17 import JobScheduler

with JobScheduler(max_workers=4, max_pending=256) as jobs:
    jobs.submit("decode:terrain", decode_terrain, priority=10)
    jobs.submit(
        "build:terrain-index",
        build_index,
        dependencies=["decode:terrain"],
    )
```

Ready jobs use deterministic scheduling priority: higher integer priority first, then immutable submission sequence. Once a worker starts, execution timing is naturally controlled by the operating system and the job itself; the scheduler does not claim deterministic wall-clock completion order.

## Dependencies

Dependencies must already exist when a job is submitted. That simple rule keeps the live graph cycle-free and makes malformed references fail before any work is accepted.

A dependent job becomes runnable only after every dependency succeeds. If one dependency fails, is cancelled, or is itself blocked, the dependent becomes `JobState.BLOCKED` without executing. Blocking propagates transitively.

## Cancellation

Queued/waiting jobs cancel immediately. Running jobs receive cooperative cancellation through `JobContext`:

```python
def decode(context):
    for chunk in chunks:
        context.raise_if_cancelled()
        decode_chunk(chunk)
```

A running job that observes cancellation becomes `CANCELLED`. Its return value is discarded if cancellation was requested before completion delivery.

## Main-thread handoff

Background workers should not mutate renderer/window-owned resources or live game state. Use `drain_completed(max_items=...)` from the owning thread and commit results there:

```python
for outcome in jobs.drain_completed(max_items=8):
    if outcome.successful:
        install_prepared_asset(outcome.value)
```

The bounded drain is the integration point for later 1.7 frame-time budgets. It lets a game accept background throughput without turning all completed work into one unbounded finalize spike.

## Diagnostics and privacy

`JobSchedulerDiagnostics.portable()` contains only numeric counts and configured budgets: waiting/queued/running/terminal counts, accepted/rejected totals, cancellation requests, dependency blocks and drain counts. Result payloads and worker exception objects are not included.

Individual `JobOutcome` values intentionally remain creator-facing runtime objects. Treat them as application data rather than portable diagnostics.

## Shutdown and memory lifecycle

`shutdown(wait=True)` drains accepted work before closing the executor. `shutdown(wait=False)` cannot safely keep work in the scheduler-owned ready queue after executor shutdown, so not-yet-started work is cancelled while already running jobs may finish. `cancel_pending=True` also requests cooperative cancellation from running jobs.

Completed jobs remain addressable until explicitly forgotten so dependency and outcome inspection stay stable. Call `drain_completed()` first, then `forget(job_id)` when neither the creator nor retained dependents need the record. A dependency cannot be forgotten while a retained dependent still references it.

## Verification

Milestone 1 validation covers:

- priority/FIFO scheduling;
- dependency success and transitive blocking;
- malformed/missing dependency rejection;
- hard unfinished-job back-pressure;
- queued and cooperative running cancellation;
- worker-failure isolation;
- bounded result draining and payload-free diagnostics;
- explicit record forgetting rules;
- closed-scheduler rejection;
- a 2,000-job workload with a generous 5.0-second CI budget.

The workload is a scheduler regression contract, not an FPS claim.
