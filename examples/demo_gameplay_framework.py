from __future__ import annotations

from dataclasses import dataclass

from swirengine.gameplay import GameplayRuntime, ObjectPool, Signal


@dataclass(slots=True)
class Enemy:
    serial: int
    active: bool = False


serial = 0


def make_enemy() -> Enemy:
    global serial
    serial += 1
    return Enemy(serial)


pool = ObjectPool(
    make_enemy,
    prewarm=4,
    on_acquire=lambda enemy: setattr(enemy, "active", True),
    on_release=lambda enemy: setattr(enemy, "active", False),
)
runtime = GameplayRuntime()
wave_finished = Signal()
spawned: list[Enemy] = []


def spawn_enemy() -> Enemy:
    enemy = pool.acquire()
    spawned.append(enemy)
    print(f"spawn enemy #{enemy.serial} at t={runtime.time:.1f}s")
    return enemy


spawner = runtime.spawner(spawn_enemy, interval=0.5, limit=4)
spawner.spawned.connect(lambda enemy: print(f"  pool active={pool.active_count}"))
spawner.start(immediate=True)

ability = runtime.cooldown(1.0)
wave_finished.once(lambda count: print(f"wave finished with {count} enemies"))

for _frame in range(12):
    if ability.trigger():
        print(f"ability fired at t={runtime.time:.1f}s")
    runtime.update(0.25)

wave_finished.emit(len(spawned))
for enemy in tuple(spawned):
    pool.release(enemy)

print(
    "final: "
    f"spawned={spawner.spawn_count}, timers={runtime.scheduler.pending_count}, "
    f"pool_available={pool.available_count}, factory_calls={serial}"
)
