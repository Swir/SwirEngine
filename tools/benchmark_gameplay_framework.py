from __future__ import annotations

from time import perf_counter

from swirengine.gameplay import ObjectPool, Scheduler

DORMANT_TIMERS = 10_000
IDLE_UPDATES = 1_000
POOL_SIZE = 5_000


scheduler = Scheduler()
for _ in range(DORMANT_TIMERS):
    scheduler.call_later(120.0, lambda: None)

start = perf_counter()
for _ in range(IDLE_UPDATES):
    scheduler.update(1.0 / 120.0)
idle_elapsed = perf_counter() - start

if scheduler.diagnostics.heap_pops != 0:
    raise SystemExit(
        "gameplay scheduler locality regression: dormant timers were popped during idle updates"
    )
if scheduler.pending_count != DORMANT_TIMERS:
    raise SystemExit("gameplay scheduler locality regression: dormant timer count changed")

created = 0


def factory() -> dict[str, int]:
    global created
    created += 1
    return {"serial": created}


pool = ObjectPool(factory, prewarm=POOL_SIZE)
objects = [pool.acquire() for _ in range(POOL_SIZE)]
for obj in objects:
    if not pool.release(obj):
        raise SystemExit("gameplay pool regression: active object could not be released")

created_after_warm_cycle = created
start = perf_counter()
for _ in range(5):
    cycle = [pool.acquire() for _ in range(POOL_SIZE)]
    for obj in cycle:
        pool.release(obj)
pool_elapsed = perf_counter() - start

if created != created_after_warm_cycle:
    raise SystemExit("gameplay pool regression: warm pool unexpectedly called the factory")
if pool.available_count != POOL_SIZE or pool.active_count != 0:
    raise SystemExit("gameplay pool regression: pool did not return to its warm steady state")

print(
    "Gameplay framework benchmark: "
    f"dormant_timers={DORMANT_TIMERS}, idle_updates={IDLE_UPDATES}, "
    f"heap_pops={scheduler.diagnostics.heap_pops}, idle_seconds={idle_elapsed:.6f}, "
    f"pool_size={POOL_SIZE}, warm_cycles=5, factory_calls={created}, "
    f"pool_seconds={pool_elapsed:.6f}"
)
print("Host timings are diagnostic only; this benchmark makes no FPS claim.")
