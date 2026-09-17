from __future__ import annotations

import math
import threading
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from time import perf_counter
from types import MappingProxyType
from typing import Any, Protocol

Clock = Callable[[], float]
DrainCallback = Callable[[int], int]


def _positive_int(value: int, *, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{label} must be an integer")
    if value < 1:
        raise ValueError(f"{label} must be >= 1")
    return value


def _nonnegative_int(value: int, *, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{label} must be an integer")
    if value < 0:
        raise ValueError(f"{label} must be >= 0")
    return value


def _positive_ms(value: float, *, label: str) -> float:
    result = float(value)
    if not math.isfinite(result) or result <= 0.0:
        raise ValueError(f"{label} must be finite and > 0")
    return result


def _lane_name(value: str) -> str:
    if not isinstance(value, str):
        raise TypeError("lane name must be a string")
    result = value.strip()
    if not result:
        raise ValueError("lane name must not be empty")
    if len(result) > 128:
        raise ValueError("lane name must contain at most 128 characters")
    return result


class DiagnosticsBindable(Protocol):
    def bind_provider(self, domain: str, provider: Callable[[], object]) -> None: ...

    def unbind_provider(self, domain: str) -> bool: ...


@dataclass(frozen=True, slots=True)
class FrameBudgetLaneConfig:
    name: str
    priority: int
    max_items_per_frame: int
    reserved_items: int
    enabled: bool
    sequence: int


@dataclass(frozen=True, slots=True)
class FrameBudgetLaneReport:
    name: str
    calls: int
    items: int
    elapsed_ms: float
    deferred: bool
    error_type: str | None = None
    error_message: str | None = None

    @property
    def failed(self) -> bool:
        return self.error_type is not None


@dataclass(frozen=True, slots=True)
class FrameBudgetFrame:
    frame_index: int
    budget_ms: float
    elapsed_ms: float
    item_budget: int
    items_drained: int
    drain_call_budget: int
    drain_calls: int
    budget_exhausted: bool
    deferred_lanes: tuple[str, ...]
    lane_reports: tuple[FrameBudgetLaneReport, ...]

    @property
    def overrun_ms(self) -> float:
        return max(0.0, self.elapsed_ms - self.budget_ms)

    @property
    def errors(self) -> int:
        return sum(report.failed for report in self.lane_reports)


@dataclass(frozen=True, slots=True)
class FrameBudgetDiagnostics:
    frame_budget_ms: float
    max_items_per_frame: int
    max_drain_calls_per_frame: int
    max_lanes: int
    frames_total: int
    budget_exhausted_frames: int
    overrun_frames: int
    deferred_frames: int
    drain_calls_total: int
    items_drained_total: int
    lane_errors_total: int
    registered_lanes: int
    enabled_lanes: int
    last_frame_ms: float
    last_frame_items: int
    last_frame_calls: int
    last_deferred_lanes: int
    last_overrun_ms: float
    lanes: Mapping[str, Mapping[str, int | float]]

    def portable(self) -> Mapping[str, object]:
        lane_values = {
            name: dict(values)
            for name, values in sorted(self.lanes.items())
        }
        return MappingProxyType(
            {
                "frame_budget_ms": self.frame_budget_ms,
                "max_items_per_frame": self.max_items_per_frame,
                "max_drain_calls_per_frame": self.max_drain_calls_per_frame,
                "max_lanes": self.max_lanes,
                "frames_total": self.frames_total,
                "budget_exhausted_frames": self.budget_exhausted_frames,
                "overrun_frames": self.overrun_frames,
                "deferred_frames": self.deferred_frames,
                "drain_calls_total": self.drain_calls_total,
                "items_drained_total": self.items_drained_total,
                "lane_errors_total": self.lane_errors_total,
                "registered_lanes": self.registered_lanes,
                "enabled_lanes": self.enabled_lanes,
                "last_frame_ms": self.last_frame_ms,
                "last_frame_items": self.last_frame_items,
                "last_frame_calls": self.last_frame_calls,
                "last_deferred_lanes": self.last_deferred_lanes,
                "last_overrun_ms": self.last_overrun_ms,
                "lanes": lane_values,
            }
        )


@dataclass(slots=True)
class _Lane:
    config: FrameBudgetLaneConfig
    drain: DrainCallback
    calls_total: int = 0
    items_total: int = 0
    errors_total: int = 0
    deferred_frames: int = 0
    exhausted_frames: int = 0
    last_items: int = 0
    last_elapsed_ms: float = 0.0
    max_elapsed_ms: float = 0.0


class FrameTimeBudgetController:
    """Bound owning-thread async/finalize work to explicit per-frame budgets.

    The controller does not own worker threads and never inspects payloads. Creators register
    small drain callbacks that accept a hard item limit and return the number of items actually
    consumed. Time is checked between drain calls, so callbacks remain cooperative and should
    keep their own per-call work bounded.
    """

    def __init__(
        self,
        *,
        frame_budget_ms: float = 2.0,
        max_items_per_frame: int = 128,
        max_drain_calls_per_frame: int = 32,
        max_lanes: int = 32,
        clock: Clock = perf_counter,
    ) -> None:
        self.frame_budget_ms = _positive_ms(frame_budget_ms, label="frame_budget_ms")
        self.max_items_per_frame = _positive_int(
            max_items_per_frame,
            label="max_items_per_frame",
        )
        self.max_drain_calls_per_frame = _positive_int(
            max_drain_calls_per_frame,
            label="max_drain_calls_per_frame",
        )
        self.max_lanes = _positive_int(max_lanes, label="max_lanes")
        if not callable(clock):
            raise TypeError("clock must be callable")
        self._clock = clock
        self._owner_thread = threading.get_ident()
        self._lanes: dict[str, _Lane] = {}
        self._next_sequence = 0
        self._frame_index = 0
        self._running = False
        self._frames_total = 0
        self._budget_exhausted_frames = 0
        self._overrun_frames = 0
        self._deferred_frames = 0
        self._drain_calls_total = 0
        self._items_drained_total = 0
        self._lane_errors_total = 0
        self._last_frame: FrameBudgetFrame | None = None

    def _require_owner_thread(self) -> None:
        if threading.get_ident() != self._owner_thread:
            raise RuntimeError("frame budget controller operation called from another thread")

    def _require_mutable(self) -> None:
        self._require_owner_thread()
        if self._running:
            raise RuntimeError("frame budget lane configuration cannot change during run_frame()")

    @property
    def frame_index(self) -> int:
        return self._frame_index

    @property
    def last_frame(self) -> FrameBudgetFrame | None:
        return self._last_frame

    def register(
        self,
        name: str,
        drain: DrainCallback,
        *,
        priority: int = 0,
        max_items_per_frame: int = 32,
        reserved_items: int = 0,
        enabled: bool = True,
    ) -> FrameBudgetLaneConfig:
        self._require_mutable()
        normalized = _lane_name(name)
        if normalized in self._lanes:
            raise ValueError(f"frame budget lane already exists: {normalized}")
        if len(self._lanes) >= self.max_lanes:
            raise RuntimeError("frame budget max_lanes limit reached")
        if not callable(drain):
            raise TypeError("drain must be callable")
        per_frame = _positive_int(max_items_per_frame, label="lane max_items_per_frame")
        reserved = _nonnegative_int(reserved_items, label="lane reserved_items")
        if reserved > per_frame:
            raise ValueError("lane reserved_items cannot exceed max_items_per_frame")
        if isinstance(priority, bool) or not isinstance(priority, int):
            raise TypeError("lane priority must be an integer")
        config = FrameBudgetLaneConfig(
            name=normalized,
            priority=priority,
            max_items_per_frame=per_frame,
            reserved_items=reserved,
            enabled=bool(enabled),
            sequence=self._next_sequence,
        )
        self._next_sequence += 1
        self._lanes[normalized] = _Lane(config=config, drain=drain)
        return config

    def unregister(self, name: str) -> bool:
        self._require_mutable()
        return self._lanes.pop(_lane_name(name), None) is not None

    def configure(
        self,
        name: str,
        *,
        priority: int | None = None,
        max_items_per_frame: int | None = None,
        reserved_items: int | None = None,
        enabled: bool | None = None,
    ) -> FrameBudgetLaneConfig:
        self._require_mutable()
        normalized = _lane_name(name)
        try:
            lane = self._lanes[normalized]
        except KeyError:
            raise KeyError(normalized) from None
        current = lane.config
        new_priority = current.priority if priority is None else priority
        if isinstance(new_priority, bool) or not isinstance(new_priority, int):
            raise TypeError("lane priority must be an integer")
        new_max = (
            current.max_items_per_frame
            if max_items_per_frame is None
            else _positive_int(max_items_per_frame, label="lane max_items_per_frame")
        )
        new_reserved = (
            current.reserved_items
            if reserved_items is None
            else _nonnegative_int(reserved_items, label="lane reserved_items")
        )
        if new_reserved > new_max:
            raise ValueError("lane reserved_items cannot exceed max_items_per_frame")
        lane.config = FrameBudgetLaneConfig(
            name=current.name,
            priority=new_priority,
            max_items_per_frame=new_max,
            reserved_items=new_reserved,
            enabled=current.enabled if enabled is None else bool(enabled),
            sequence=current.sequence,
        )
        return lane.config

    def lane(self, name: str) -> FrameBudgetLaneConfig:
        try:
            return self._lanes[_lane_name(name)].config
        except KeyError:
            raise KeyError(_lane_name(name)) from None

    def lanes(self) -> tuple[FrameBudgetLaneConfig, ...]:
        return tuple(
            lane.config
            for lane in sorted(self._lanes.values(), key=lambda item: item.config.sequence)
        )

    def _elapsed_ms(self, started: float) -> float:
        elapsed = (float(self._clock()) - started) * 1000.0
        if not math.isfinite(elapsed):
            raise RuntimeError("frame budget clock returned a non-finite elapsed value")
        return max(0.0, elapsed)

    @staticmethod
    def _rotate(items: list[_Lane], offset: int) -> list[_Lane]:
        if not items:
            return []
        normalized = offset % len(items)
        return items[normalized:] + items[:normalized]

    def _priority_order(self, lanes: list[_Lane]) -> list[_Lane]:
        groups: dict[int, list[_Lane]] = {}
        for lane in lanes:
            groups.setdefault(lane.config.priority, []).append(lane)
        ordered: list[_Lane] = []
        for priority in sorted(groups, reverse=True):
            group = sorted(groups[priority], key=lambda item: item.config.sequence)
            ordered.extend(self._rotate(group, self._frame_index))
        return ordered

    def run_frame(
        self,
        *,
        budget_ms: float | None = None,
        max_items: int | None = None,
        max_drain_calls: int | None = None,
    ) -> FrameBudgetFrame:
        """Drain registered owning-thread work without exceeding configured call/item bounds."""
        self._require_owner_thread()
        if self._running:
            raise RuntimeError("frame budget controller run_frame() is not reentrant")
        frame_budget = (
            self.frame_budget_ms
            if budget_ms is None
            else _positive_ms(budget_ms, label="budget_ms")
        )
        item_budget = (
            self.max_items_per_frame
            if max_items is None
            else _positive_int(max_items, label="max_items")
        )
        call_budget = (
            self.max_drain_calls_per_frame
            if max_drain_calls is None
            else _positive_int(max_drain_calls, label="max_drain_calls")
        )
        enabled = [lane for lane in self._lanes.values() if lane.config.enabled]
        enabled.sort(key=lambda item: item.config.sequence)
        started = float(self._clock())
        if not math.isfinite(started):
            raise RuntimeError("frame budget clock returned a non-finite timestamp")

        consumed_by_lane = {lane.config.name: 0 for lane in enabled}
        calls_by_lane = {lane.config.name: 0 for lane in enabled}
        elapsed_by_lane = {lane.config.name: 0.0 for lane in enabled}
        errors: dict[str, tuple[str, str]] = {}
        attempted: set[str] = set()
        explicitly_exhausted: set[str] = set()
        items_drained = 0
        drain_calls = 0
        stopped_for_budget = False
        self._running = True

        def can_continue() -> bool:
            nonlocal stopped_for_budget
            if items_drained >= item_budget or drain_calls >= call_budget:
                stopped_for_budget = True
                return False
            if self._elapsed_ms(started) >= frame_budget:
                stopped_for_budget = True
                return False
            return True

        def drain_lane(lane: _Lane, requested: int) -> None:
            nonlocal items_drained, drain_calls
            if requested <= 0 or not can_continue():
                return
            remaining_global = item_budget - items_drained
            remaining_lane = lane.config.max_items_per_frame - consumed_by_lane[lane.config.name]
            limit = min(requested, remaining_global, remaining_lane)
            if limit <= 0:
                return
            attempted.add(lane.config.name)
            call_started = float(self._clock())
            drain_calls += 1
            calls_by_lane[lane.config.name] += 1
            try:
                consumed = lane.drain(limit)
                if isinstance(consumed, bool) or not isinstance(consumed, int):
                    raise TypeError("frame budget drain callback must return an integer item count")
                if consumed < 0 or consumed > limit:
                    raise ValueError(
                        "frame budget drain callback returned a count outside its requested limit"
                    )
            except Exception as exc:  # noqa: BLE001 - creator drains are intentionally isolated.
                lane.errors_total += 1
                self._lane_errors_total += 1
                errors[lane.config.name] = (type(exc).__name__, str(exc))
                consumed = 0
            call_elapsed = max(0.0, (float(self._clock()) - call_started) * 1000.0)
            if not math.isfinite(call_elapsed):
                raise RuntimeError("frame budget clock returned a non-finite callback duration")
            lane.calls_total += 1
            lane.items_total += consumed
            lane.last_items = consumed
            lane.last_elapsed_ms = call_elapsed
            lane.max_elapsed_ms = max(lane.max_elapsed_ms, call_elapsed)
            elapsed_by_lane[lane.config.name] += call_elapsed
            consumed_by_lane[lane.config.name] += consumed
            items_drained += consumed
            if consumed < limit:
                explicitly_exhausted.add(lane.config.name)

        try:
            reservation_order = self._rotate(enabled, self._frame_index)
            for lane in reservation_order:
                if lane.config.reserved_items <= 0:
                    continue
                if not can_continue():
                    break
                drain_lane(lane, lane.config.reserved_items)

            for lane in self._priority_order(enabled):
                if lane.config.name in errors or lane.config.name in explicitly_exhausted:
                    continue
                remaining = lane.config.max_items_per_frame - consumed_by_lane[lane.config.name]
                if remaining <= 0:
                    continue
                if not can_continue():
                    break
                drain_lane(lane, remaining)
        finally:
            self._running = False

        elapsed_ms = self._elapsed_ms(started)
        budget_exhausted = (
            stopped_for_budget
            or elapsed_ms >= frame_budget
            or items_drained >= item_budget
            or drain_calls >= call_budget
        )
        deferred: list[str] = []
        for lane in enabled:
            name = lane.config.name
            consumed = consumed_by_lane[name]
            was_fully_probed = name in explicitly_exhausted or consumed >= lane.config.max_items_per_frame
            lane_deferred = not was_fully_probed and name not in errors and (
                budget_exhausted or name not in attempted
            )
            if lane_deferred:
                deferred.append(name)
                lane.deferred_frames += 1
            elif name in explicitly_exhausted:
                lane.exhausted_frames += 1

        reports = tuple(
            FrameBudgetLaneReport(
                name=lane.config.name,
                calls=calls_by_lane[lane.config.name],
                items=consumed_by_lane[lane.config.name],
                elapsed_ms=elapsed_by_lane[lane.config.name],
                deferred=lane.config.name in deferred,
                error_type=(errors.get(lane.config.name) or (None, None))[0],
                error_message=(errors.get(lane.config.name) or (None, None))[1],
            )
            for lane in enabled
        )
        frame = FrameBudgetFrame(
            frame_index=self._frame_index,
            budget_ms=frame_budget,
            elapsed_ms=elapsed_ms,
            item_budget=item_budget,
            items_drained=items_drained,
            drain_call_budget=call_budget,
            drain_calls=drain_calls,
            budget_exhausted=budget_exhausted,
            deferred_lanes=tuple(deferred),
            lane_reports=reports,
        )
        self._frame_index += 1
        self._frames_total += 1
        self._drain_calls_total += drain_calls
        self._items_drained_total += items_drained
        if budget_exhausted:
            self._budget_exhausted_frames += 1
        if frame.overrun_ms > 0.0:
            self._overrun_frames += 1
        if deferred:
            self._deferred_frames += 1
        self._last_frame = frame
        return frame

    def diagnostics(self) -> FrameBudgetDiagnostics:
        lane_values: dict[str, Mapping[str, int | float]] = {}
        for name, lane in sorted(self._lanes.items()):
            lane_values[name] = MappingProxyType(
                {
                    "priority": lane.config.priority,
                    "max_items_per_frame": lane.config.max_items_per_frame,
                    "reserved_items": lane.config.reserved_items,
                    "enabled": int(lane.config.enabled),
                    "calls_total": lane.calls_total,
                    "items_total": lane.items_total,
                    "errors_total": lane.errors_total,
                    "deferred_frames": lane.deferred_frames,
                    "exhausted_frames": lane.exhausted_frames,
                    "last_items": lane.last_items,
                    "last_elapsed_ms": lane.last_elapsed_ms,
                    "max_elapsed_ms": lane.max_elapsed_ms,
                }
            )
        last = self._last_frame
        return FrameBudgetDiagnostics(
            frame_budget_ms=self.frame_budget_ms,
            max_items_per_frame=self.max_items_per_frame,
            max_drain_calls_per_frame=self.max_drain_calls_per_frame,
            max_lanes=self.max_lanes,
            frames_total=self._frames_total,
            budget_exhausted_frames=self._budget_exhausted_frames,
            overrun_frames=self._overrun_frames,
            deferred_frames=self._deferred_frames,
            drain_calls_total=self._drain_calls_total,
            items_drained_total=self._items_drained_total,
            lane_errors_total=self._lane_errors_total,
            registered_lanes=len(self._lanes),
            enabled_lanes=sum(lane.config.enabled for lane in self._lanes.values()),
            last_frame_ms=0.0 if last is None else last.elapsed_ms,
            last_frame_items=0 if last is None else last.items_drained,
            last_frame_calls=0 if last is None else last.drain_calls,
            last_deferred_lanes=0 if last is None else len(last.deferred_lanes),
            last_overrun_ms=0.0 if last is None else last.overrun_ms,
            lanes=MappingProxyType(lane_values),
        )

    def bind_performance(
        self,
        diagnostics: DiagnosticsBindable,
        *,
        domain: str = "frame_budget17",
    ) -> None:
        """Expose numeric budget diagnostics to PerformanceDiagnostics2 or a compatible sink."""
        self._require_owner_thread()
        bind = getattr(diagnostics, "bind_provider", None)
        if not callable(bind):
            raise TypeError("diagnostics object must expose bind_provider(domain, provider)")
        bind(domain, lambda: self.diagnostics().portable())

    def unbind_performance(
        self,
        diagnostics: DiagnosticsBindable,
        *,
        domain: str = "frame_budget17",
    ) -> bool:
        self._require_owner_thread()
        unbind = getattr(diagnostics, "unbind_provider", None)
        if not callable(unbind):
            raise TypeError("diagnostics object must expose unbind_provider(domain)")
        return bool(unbind(domain))


__all__ = [
    "DrainCallback",
    "FrameBudgetDiagnostics",
    "FrameBudgetFrame",
    "FrameBudgetLaneConfig",
    "FrameBudgetLaneReport",
    "FrameTimeBudgetController",
]
