# Advanced Gameplay Framework — SwirEngine 1.3

SwirEngine 1.3 milestone 8 adds composition-friendly gameplay utilities without replacing the existing `EventBus`, scene lifecycle or fixed-update APIs. The framework lives in `swirengine.gameplay` and is designed so dormant gameplay state does not automatically become per-frame scan work.

## Gameplay runtime

`GameplayRuntime` owns one deterministic `Scheduler` clock and is intentionally easy to compose with the existing game loop:

```python
from swirengine import Game
from swirengine.gameplay import GameplayRuntime


game = Game("Gameplay", mode="2d")
gameplay = GameplayRuntime()
game.update(gameplay.update)

gameplay.call_later(1.0, print, "one second later")
```

The runtime is additive: existing `Game.update`, `Game.fixed_update` and `EventBus` behavior stays unchanged.

## Heap-based timers

`Scheduler` provides:

- `call_later(delay, callback, ...)`
- `call_every(interval, callback, ..., delay=...)`
- cancellable `TimerHandle` objects
- deterministic ordering for callbacks with equal due times
- `pending_count`, `next_due_in` and diagnostics

Timers are held in a min-heap. If no callback is due, `update()` checks only the heap head instead of walking the complete timer registry. Repeating callbacks intentionally reschedule from the current runtime clock so a long frame does not create an unbounded catch-up burst.

The regression contract schedules **10,000 dormant timers** and performs **1,000 idle updates**. It requires exactly **zero timer heap pops** during those idle updates and all 10,000 timers to remain pending.

## Signals

`Signal` is an ordered, mutation-safe callback surface for local gameplay composition. It supports:

- explicit `SignalConnection` handles,
- disconnect during emission,
- one-shot connections with `once(...)`,
- creator-visible emission/callback/connection diagnostics.

The existing string-based `EventBus` remains untouched for compatibility. `Signal` is intended for object/component-local relationships where explicit connection ownership is useful.

## Object pools

`ObjectPool[T]` supports:

- factory-based creation,
- optional prewarming,
- optional bounded available reserve,
- acquire/release hooks,
- deterministic reuse and diagnostics.

A warm pool does not call its factory again while enough released objects remain available. The benchmark prewarms **5,000 objects** and runs five complete acquire/release cycles while requiring no additional factory calls.

## Cooldowns

`Cooldown` uses a shared clock and stores only a `ready_at` timestamp. It requires no registration in an update list and therefore no per-frame scan. `GameplayRuntime.cooldown(duration)` binds the cooldown directly to the runtime clock.

## Scheduler-backed spawners

`Spawner[T]` composes a spawn callback with the scheduler and exposes:

- `start(immediate=...)`
- `stop()`
- `burst(count)`
- optional total spawn limit
- a `spawned` signal

Periodic spawning therefore reuses the timer heap instead of adding another frame-scanned subsystem.

## Performance contract

`tools/benchmark_gameplay_framework.py` verifies two bounded-work properties:

1. **10,000 dormant timers + 1,000 idle updates => 0 heap pops.**
2. **5,000 prewarmed objects + five full reuse cycles => no additional factory calls.**

Host elapsed timings are printed as diagnostics only. They are not converted into FPS claims.

## Current boundaries

This milestone does not claim a coroutine engine, async task runtime, rollback scheduler, behavior tree, full dependency-injection framework or network-replicated timers. It provides small deterministic gameplay primitives that compose with the stable 1.x API.

## Verification

```bash
pytest tests/test_gameplay_framework.py
ruff check src/swirengine/gameplay.py tests/test_gameplay_framework.py examples/demo_gameplay_framework.py tools/benchmark_gameplay_framework.py
python -m compileall -q src/swirengine/gameplay.py tests/test_gameplay_framework.py examples/demo_gameplay_framework.py tools/benchmark_gameplay_framework.py
python tools/benchmark_gameplay_framework.py
python examples/demo_gameplay_framework.py
```
