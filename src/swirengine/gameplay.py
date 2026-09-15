from __future__ import annotations

import heapq
import itertools
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Generic, TypeVar

T = TypeVar("T")


@dataclass(slots=True)
class SchedulerDiagnostics:
    scheduled: int = 0
    fired: int = 0
    cancelled: int = 0
    heap_pops: int = 0
    live_timers: int = 0
    peak_live_timers: int = 0


@dataclass(slots=True)
class TimerHandle:
    """Mutable handle for one scheduled callback."""

    scheduler: Scheduler
    timer_id: int

    @property
    def active(self) -> bool:
        return self.scheduler.is_active(self.timer_id)

    def cancel(self) -> bool:
        return self.scheduler.cancel(self.timer_id)


@dataclass(slots=True)
class _Timer:
    timer_id: int
    due: float
    callback: Callable[..., Any]
    args: tuple[Any, ...]
    kwargs: dict[str, Any]
    interval: float | None = None
    cancelled: bool = False


class Scheduler:
    """Deterministic heap-based timer scheduler.

    Dormant timers stay in a min-heap, so an update that has no due callbacks does not walk the
    full timer registry. Repeating timers schedule their next occurrence relative to the current
    runtime clock, deliberately avoiding unbounded catch-up bursts after a long frame.
    """

    def __init__(self) -> None:
        self.now = 0.0
        self._next_id = itertools.count(1)
        self._order = itertools.count()
        self._heap: list[tuple[float, int, int]] = []
        self._timers: dict[int, _Timer] = {}
        self.diagnostics = SchedulerDiagnostics()

    def _push(self, timer: _Timer) -> None:
        heapq.heappush(self._heap, (timer.due, next(self._order), timer.timer_id))

    def _schedule(
        self,
        delay: float,
        callback: Callable[..., Any],
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
        *,
        interval: float | None,
    ) -> TimerHandle:
        delay = float(delay)
        if delay < 0.0:
            raise ValueError("timer delay must be non-negative")
        if interval is not None and interval <= 0.0:
            raise ValueError("timer interval must be greater than zero")
        timer_id = next(self._next_id)
        timer = _Timer(
            timer_id=timer_id,
            due=self.now + delay,
            callback=callback,
            args=args,
            kwargs=kwargs,
            interval=interval,
        )
        self._timers[timer_id] = timer
        self._push(timer)
        self.diagnostics.scheduled += 1
        self.diagnostics.live_timers = len(self._timers)
        self.diagnostics.peak_live_timers = max(
            self.diagnostics.peak_live_timers,
            self.diagnostics.live_timers,
        )
        return TimerHandle(self, timer_id)

    def call_later(
        self,
        delay: float,
        callback: Callable[..., Any],
        *args: Any,
        **kwargs: Any,
    ) -> TimerHandle:
        return self._schedule(delay, callback, args, kwargs, interval=None)

    def call_every(
        self,
        interval: float,
        callback: Callable[..., Any],
        *args: Any,
        delay: float | None = None,
        **kwargs: Any,
    ) -> TimerHandle:
        interval = float(interval)
        first_delay = interval if delay is None else float(delay)
        return self._schedule(first_delay, callback, args, kwargs, interval=interval)

    def is_active(self, timer_id: int) -> bool:
        timer = self._timers.get(int(timer_id))
        return timer is not None and not timer.cancelled

    def cancel(self, timer_id: int) -> bool:
        timer = self._timers.pop(int(timer_id), None)
        if timer is None or timer.cancelled:
            return False
        timer.cancelled = True
        self.diagnostics.cancelled += 1
        self.diagnostics.live_timers = len(self._timers)
        return True

    def clear(self) -> None:
        for timer in self._timers.values():
            timer.cancelled = True
        self.diagnostics.cancelled += len(self._timers)
        self._timers.clear()
        self._heap.clear()
        self.diagnostics.live_timers = 0

    @property
    def pending_count(self) -> int:
        return len(self._timers)

    @property
    def next_due_in(self) -> float | None:
        while self._heap:
            due, _order, timer_id = self._heap[0]
            timer = self._timers.get(timer_id)
            if timer is not None and not timer.cancelled and timer.due == due:
                return max(0.0, due - self.now)
            heapq.heappop(self._heap)
        return None

    def update(self, dt: float) -> int:
        dt = float(dt)
        if dt < 0.0:
            raise ValueError("scheduler dt must be non-negative")
        self.now += dt
        fired = 0

        while self._heap and self._heap[0][0] <= self.now:
            due, _order, timer_id = heapq.heappop(self._heap)
            self.diagnostics.heap_pops += 1
            timer = self._timers.get(timer_id)
            if timer is None or timer.cancelled or timer.due != due:
                continue

            if timer.interval is None:
                self._timers.pop(timer_id, None)
            timer.callback(*timer.args, **timer.kwargs)
            fired += 1
            self.diagnostics.fired += 1

            timer = self._timers.get(timer_id)
            if timer is None or timer.cancelled:
                continue
            if timer.interval is not None:
                timer.due = self.now + timer.interval
                self._push(timer)

        self.diagnostics.live_timers = len(self._timers)
        return fired


@dataclass(slots=True)
class SignalDiagnostics:
    emissions: int = 0
    callbacks: int = 0
    connections: int = 0
    disconnections: int = 0


@dataclass(slots=True)
class SignalConnection:
    signal: Signal
    connection_id: int

    @property
    def connected(self) -> bool:
        return self.signal.is_connected(self.connection_id)

    def disconnect(self) -> bool:
        return self.signal.disconnect(self.connection_id)


@dataclass(slots=True)
class _SignalSlot:
    callback: Callable[..., Any]
    once: bool = False


class Signal:
    """Ordered mutation-safe signal with explicit connection handles and one-shot slots."""

    def __init__(self) -> None:
        self._next_id = itertools.count(1)
        self._slots: dict[int, _SignalSlot] = {}
        self.diagnostics = SignalDiagnostics()

    def connect(self, callback: Callable[..., Any], *, once: bool = False) -> SignalConnection:
        connection_id = next(self._next_id)
        self._slots[connection_id] = _SignalSlot(callback, bool(once))
        self.diagnostics.connections += 1
        return SignalConnection(self, connection_id)

    def once(self, callback: Callable[..., Any]) -> SignalConnection:
        return self.connect(callback, once=True)

    def is_connected(self, connection_id: int) -> bool:
        return int(connection_id) in self._slots

    def disconnect(self, connection_id: int) -> bool:
        if self._slots.pop(int(connection_id), None) is None:
            return False
        self.diagnostics.disconnections += 1
        return True

    def clear(self) -> None:
        self.diagnostics.disconnections += len(self._slots)
        self._slots.clear()

    def emit(self, *args: Any, **kwargs: Any) -> int:
        self.diagnostics.emissions += 1
        called = 0
        for connection_id, slot in tuple(self._slots.items()):
            if connection_id not in self._slots:
                continue
            if slot.once:
                self.disconnect(connection_id)
            slot.callback(*args, **kwargs)
            called += 1
        self.diagnostics.callbacks += called
        return called

    def __len__(self) -> int:
        return len(self._slots)


@dataclass(slots=True)
class PoolDiagnostics:
    created: int = 0
    acquired: int = 0
    reused: int = 0
    released: int = 0
    dropped: int = 0
    active: int = 0
    available: int = 0


class ObjectPool(Generic[T]):
    """Small deterministic object pool with optional lifecycle hooks."""

    def __init__(
        self,
        factory: Callable[[], T],
        *,
        prewarm: int = 0,
        max_available: int | None = None,
        on_acquire: Callable[[T], None] | None = None,
        on_release: Callable[[T], None] | None = None,
    ) -> None:
        if prewarm < 0:
            raise ValueError("prewarm must be non-negative")
        if max_available is not None and max_available < 0:
            raise ValueError("max_available must be non-negative")
        self.factory = factory
        self.max_available = max_available
        self.on_acquire = on_acquire
        self.on_release = on_release
        self._available: list[T] = []
        self._active_ids: set[int] = set()
        self.diagnostics = PoolDiagnostics()
        self.prewarm(prewarm)

    def prewarm(self, count: int) -> None:
        count = int(count)
        if count < 0:
            raise ValueError("prewarm count must be non-negative")
        for _ in range(count):
            if self.max_available is not None and len(self._available) >= self.max_available:
                break
            self._available.append(self.factory())
            self.diagnostics.created += 1
        self._sync_diagnostics()

    def _sync_diagnostics(self) -> None:
        self.diagnostics.active = len(self._active_ids)
        self.diagnostics.available = len(self._available)

    def acquire(self) -> T:
        if self._available:
            obj = self._available.pop()
            self.diagnostics.reused += 1
        else:
            obj = self.factory()
            self.diagnostics.created += 1
        object_id = id(obj)
        if object_id in self._active_ids:
            raise RuntimeError("pool factory returned an object that is already active")
        self._active_ids.add(object_id)
        self.diagnostics.acquired += 1
        if self.on_acquire is not None:
            self.on_acquire(obj)
        self._sync_diagnostics()
        return obj

    def release(self, obj: T) -> bool:
        object_id = id(obj)
        if object_id not in self._active_ids:
            return False
        self._active_ids.remove(object_id)
        if self.on_release is not None:
            self.on_release(obj)
        self.diagnostics.released += 1
        if self.max_available is not None and len(self._available) >= self.max_available:
            self.diagnostics.dropped += 1
        else:
            self._available.append(obj)
        self._sync_diagnostics()
        return True

    @property
    def active_count(self) -> int:
        return len(self._active_ids)

    @property
    def available_count(self) -> int:
        return len(self._available)


@dataclass(slots=True)
class Cooldown:
    """Clock-backed cooldown that requires no per-frame registration or scanning."""

    duration: float
    clock: Callable[[], float]
    _ready_at: float = 0.0

    def __post_init__(self) -> None:
        self.duration = float(self.duration)
        if self.duration < 0.0:
            raise ValueError("cooldown duration must be non-negative")

    @property
    def ready(self) -> bool:
        return self.clock() >= self._ready_at

    @property
    def remaining(self) -> float:
        return max(0.0, self._ready_at - self.clock())

    def trigger(self, duration: float | None = None) -> bool:
        if not self.ready:
            return False
        delay = self.duration if duration is None else float(duration)
        if delay < 0.0:
            raise ValueError("cooldown duration must be non-negative")
        self._ready_at = self.clock() + delay
        return True

    def reset(self) -> None:
        self._ready_at = self.clock()


class Spawner(Generic[T]):
    """Scheduler-backed spawn helper with start/stop/burst controls."""

    def __init__(
        self,
        scheduler: Scheduler,
        spawn: Callable[[], T],
        *,
        interval: float,
        limit: int | None = None,
    ) -> None:
        if interval <= 0.0:
            raise ValueError("spawn interval must be greater than zero")
        if limit is not None and limit < 0:
            raise ValueError("spawn limit must be non-negative")
        self.scheduler = scheduler
        self.spawn = spawn
        self.interval = float(interval)
        self.limit = limit
        self.spawned = Signal()
        self.spawn_count = 0
        self._timer: TimerHandle | None = None

    @property
    def running(self) -> bool:
        return self._timer is not None and self._timer.active

    def _spawn_one(self) -> T | None:
        if self.limit is not None and self.spawn_count >= self.limit:
            self.stop()
            return None
        obj = self.spawn()
        self.spawn_count += 1
        self.spawned.emit(obj)
        if self.limit is not None and self.spawn_count >= self.limit:
            self.stop()
        return obj

    def start(self, *, immediate: bool = False) -> Spawner[T]:
        if self.running:
            return self
        if immediate:
            self._spawn_one()
        if self.limit is None or self.spawn_count < self.limit:
            self._timer = self.scheduler.call_every(self.interval, self._spawn_one)
        return self

    def stop(self) -> bool:
        timer = self._timer
        self._timer = None
        return timer.cancel() if timer is not None else False

    def burst(self, count: int) -> tuple[T, ...]:
        if count < 0:
            raise ValueError("burst count must be non-negative")
        spawned: list[T] = []
        for _ in range(count):
            obj = self._spawn_one()
            if obj is None:
                break
            spawned.append(obj)
        return tuple(spawned)


class GameplayRuntime:
    """Game-owned composition point for timers, cooldowns and scheduled spawners."""

    def __init__(self) -> None:
        self.scheduler = Scheduler()

    @property
    def time(self) -> float:
        return self.scheduler.now

    def update(self, dt: float) -> int:
        return self.scheduler.update(dt)

    def call_later(
        self,
        delay: float,
        callback: Callable[..., Any],
        *args: Any,
        **kwargs: Any,
    ) -> TimerHandle:
        return self.scheduler.call_later(delay, callback, *args, **kwargs)

    def call_every(
        self,
        interval: float,
        callback: Callable[..., Any],
        *args: Any,
        delay: float | None = None,
        **kwargs: Any,
    ) -> TimerHandle:
        return self.scheduler.call_every(
            interval,
            callback,
            *args,
            delay=delay,
            **kwargs,
        )

    def cooldown(self, duration: float) -> Cooldown:
        return Cooldown(duration, lambda: self.time)

    def spawner(
        self,
        spawn: Callable[[], T],
        *,
        interval: float,
        limit: int | None = None,
    ) -> Spawner[T]:
        return Spawner(self.scheduler, spawn, interval=interval, limit=limit)
