from __future__ import annotations

import pytest

from swirengine.gameplay import Cooldown, GameplayRuntime, ObjectPool, Scheduler, Signal, Spawner


def test_scheduler_orders_equal_due_callbacks_deterministically():
    scheduler = Scheduler()
    calls: list[str] = []

    scheduler.call_later(1.0, calls.append, "first")
    scheduler.call_later(0.25, calls.append, "early")
    scheduler.call_later(1.0, calls.append, "second")

    assert scheduler.update(0.24) == 0
    assert scheduler.update(0.01) == 1
    assert calls == ["early"]
    assert scheduler.update(0.75) == 2
    assert calls == ["early", "first", "second"]
    assert scheduler.pending_count == 0


def test_scheduler_dormant_timers_do_not_scan_registry_per_update():
    scheduler = Scheduler()
    for _ in range(10_000):
        scheduler.call_later(100.0, lambda: None)

    pops_before = scheduler.diagnostics.heap_pops
    assert scheduler.update(1.0 / 60.0) == 0
    assert scheduler.diagnostics.heap_pops == pops_before
    assert scheduler.pending_count == 10_000


def test_scheduler_cancelled_timer_is_lazy_and_never_fires():
    scheduler = Scheduler()
    calls: list[int] = []
    handle = scheduler.call_later(1.0, calls.append, 1)

    assert handle.active
    assert handle.cancel()
    assert not handle.active
    assert not handle.cancel()
    scheduler.update(2.0)
    assert calls == []
    assert scheduler.diagnostics.cancelled == 1


def test_repeating_timer_reschedules_without_catch_up_burst():
    scheduler = Scheduler()
    calls: list[float] = []
    handle = scheduler.call_every(0.5, lambda: calls.append(scheduler.now))

    assert scheduler.update(2.0) == 1
    assert calls == [2.0]
    assert handle.active
    assert scheduler.next_due_in == pytest.approx(0.5)
    assert scheduler.update(0.5) == 1
    assert calls == [2.0, 2.5]


def test_signal_preserves_order_supports_once_and_mutation_during_emit():
    signal = Signal()
    calls: list[str] = []
    second = None

    def first() -> None:
        calls.append("first")
        assert second is not None
        second.disconnect()

    signal.connect(first)
    second = signal.connect(lambda: calls.append("second"))
    signal.once(lambda: calls.append("once"))

    assert signal.emit() == 2
    assert calls == ["first", "once"]
    assert signal.emit() == 1
    assert calls == ["first", "once", "first"]
    assert len(signal) == 1


def test_object_pool_reuses_instances_and_runs_hooks():
    serial = 0
    lifecycle: list[tuple[str, int]] = []

    def factory() -> dict[str, int]:
        nonlocal serial
        serial += 1
        return {"id": serial}

    pool = ObjectPool(
        factory,
        prewarm=2,
        on_acquire=lambda obj: lifecycle.append(("acquire", obj["id"])),
        on_release=lambda obj: lifecycle.append(("release", obj["id"])),
    )
    first = pool.acquire()
    second = pool.acquire()
    assert serial == 2
    assert pool.available_count == 0
    assert pool.active_count == 2

    reused_before = pool.diagnostics.reused
    assert pool.release(first)
    assert not pool.release(first)
    reused = pool.acquire()
    assert reused is first
    assert serial == 2
    assert pool.diagnostics.reused == reused_before + 1
    assert lifecycle[0][0] == "acquire"
    assert ("release", first["id"]) in lifecycle
    assert second is not reused


def test_object_pool_respects_bounded_available_reserve():
    pool = ObjectPool(lambda: object(), max_available=1)
    first = pool.acquire()
    second = pool.acquire()
    assert pool.release(first)
    assert pool.release(second)
    assert pool.available_count == 1
    assert pool.diagnostics.dropped == 1


def test_cooldown_uses_shared_clock_without_per_frame_registration():
    now = 10.0
    cooldown = Cooldown(2.0, lambda: now)
    assert cooldown.ready
    assert cooldown.trigger()
    assert not cooldown.ready
    assert cooldown.remaining == pytest.approx(2.0)

    now = 11.5
    assert cooldown.remaining == pytest.approx(0.5)
    assert not cooldown.trigger()
    now = 12.0
    assert cooldown.ready
    assert cooldown.trigger(0.25)
    now = 12.25
    assert cooldown.ready


def test_spawner_is_scheduler_backed_and_honors_limit():
    scheduler = Scheduler()
    values: list[int] = []
    spawned_events: list[int] = []

    def spawn() -> int:
        value = len(values) + 1
        values.append(value)
        return value

    spawner = Spawner(scheduler, spawn, interval=0.5, limit=3)
    spawner.spawned.connect(spawned_events.append)
    spawner.start(immediate=True)
    assert values == [1]
    scheduler.update(0.5)
    scheduler.update(0.5)
    scheduler.update(2.0)

    assert values == [1, 2, 3]
    assert spawned_events == values
    assert not spawner.running


def test_gameplay_runtime_composes_scheduler_cooldown_and_spawner():
    runtime = GameplayRuntime()
    fired: list[str] = []
    runtime.call_later(0.1, fired.append, "timer")
    cooldown = runtime.cooldown(0.2)
    assert cooldown.trigger()
    spawner = runtime.spawner(lambda: "enemy", interval=0.1, limit=2).start()

    runtime.update(0.1)
    runtime.update(0.1)

    assert fired == ["timer"]
    assert cooldown.ready
    assert spawner.spawn_count == 2
