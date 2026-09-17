from __future__ import annotations

import heapq
import math
import threading
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from enum import Enum
from types import MappingProxyType
from typing import Any

from .jobs17 import JobContext, JobScheduler, JobState


class WorkPhase(str, Enum):
    PREFETCH = "prefetch"
    DECODE = "decode"
    INSTANTIATE = "instantiate"
    UNLOAD = "unload"


class WorkAffinity(str, Enum):
    BACKGROUND = "background"
    MAIN_THREAD = "main_thread"


class WorkNodeState(str, Enum):
    WAITING = "waiting"
    SCHEDULED = "scheduled"
    READY_MAIN = "ready_main"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"
    BLOCKED = "blocked"


_TERMINAL = {
    WorkNodeState.SUCCEEDED,
    WorkNodeState.FAILED,
    WorkNodeState.CANCELLED,
    WorkNodeState.BLOCKED,
}

_PHASE_AFFINITY = {
    WorkPhase.PREFETCH: WorkAffinity.BACKGROUND,
    WorkPhase.DECODE: WorkAffinity.BACKGROUND,
    WorkPhase.INSTANTIATE: WorkAffinity.MAIN_THREAD,
    WorkPhase.UNLOAD: WorkAffinity.MAIN_THREAD,
}


class StreamingWorkGraphError(RuntimeError):
    """Base error for the additive SwirEngine 1.7 streaming work graph."""


class WorkGraphRejectedError(StreamingWorkGraphError):
    def __init__(self, code: str, message: str, *, node_id: str | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.node_id = node_id


@dataclass(frozen=True, slots=True)
class WorkContext:
    node_id: str
    phase: WorkPhase
    affinity: WorkAffinity
    dependency_values: Mapping[str, object]
    cancellation_requested: Callable[[], bool]

    @property
    def cancelled(self) -> bool:
        return bool(self.cancellation_requested())

    def raise_if_cancelled(self) -> None:
        if self.cancelled:
            raise StreamingWorkGraphError("work node cancellation requested")


WorkCallable = Callable[[WorkContext], object]


@dataclass(frozen=True, slots=True)
class WorkNodeSpec:
    node_id: str
    phase: WorkPhase
    dependencies: tuple[str, ...]
    priority: int
    sequence: int

    @property
    def affinity(self) -> WorkAffinity:
        return _PHASE_AFFINITY[self.phase]


@dataclass(frozen=True, slots=True)
class WorkNodeResult:
    node_id: str
    phase: WorkPhase
    state: WorkNodeState
    value: object | None = None
    error_type: str | None = None
    error_message: str | None = None

    @property
    def successful(self) -> bool:
        return self.state is WorkNodeState.SUCCEEDED


@dataclass(frozen=True, slots=True)
class WorkGraphDiagnostics:
    total_nodes: int
    max_nodes: int
    max_background_submissions_per_poll: int
    waiting: int
    scheduled: int
    ready_main: int
    succeeded: int
    failed: int
    cancelled: int
    blocked: int
    submitted_background_total: int
    executed_main_total: int
    failed_total: int
    cancelled_total: int
    blocked_total: int
    poll_calls: int
    main_thread_callbacks_last_poll: int
    background_handoffs_last_poll: int
    background_submissions_last_poll: int
    phase_counts: tuple[tuple[str, int], ...]

    @property
    def terminal(self) -> int:
        return self.succeeded + self.failed + self.cancelled + self.blocked

    @property
    def progress(self) -> float:
        if self.total_nodes == 0:
            return 1.0
        return self.terminal / self.total_nodes

    @property
    def complete(self) -> bool:
        return self.total_nodes > 0 and self.terminal == self.total_nodes

    def portable(self) -> Mapping[str, object]:
        return {
            "total_nodes": self.total_nodes,
            "max_nodes": self.max_nodes,
            "max_background_submissions_per_poll": self.max_background_submissions_per_poll,
            "waiting": self.waiting,
            "scheduled": self.scheduled,
            "ready_main": self.ready_main,
            "succeeded": self.succeeded,
            "failed": self.failed,
            "cancelled": self.cancelled,
            "blocked": self.blocked,
            "terminal": self.terminal,
            "progress": self.progress,
            "complete": self.complete,
            "submitted_background_total": self.submitted_background_total,
            "executed_main_total": self.executed_main_total,
            "failed_total": self.failed_total,
            "cancelled_total": self.cancelled_total,
            "blocked_total": self.blocked_total,
            "poll_calls": self.poll_calls,
            "main_thread_callbacks_last_poll": self.main_thread_callbacks_last_poll,
            "background_handoffs_last_poll": self.background_handoffs_last_poll,
            "background_submissions_last_poll": self.background_submissions_last_poll,
            "phase_counts": dict(self.phase_counts),
        }


@dataclass(slots=True)
class _NodeRecord:
    spec: WorkNodeSpec
    function: WorkCallable
    state: WorkNodeState = WorkNodeState.WAITING
    value: object | None = None
    error_type: str | None = None
    error_message: str | None = None
    dependents: set[str] = field(default_factory=set)
    cancel_requested: bool = False


class StreamingWorkGraph:
    """Bounded staged streaming work with explicit owning-thread handoff.

    ``PREFETCH`` and ``DECODE`` nodes are always executed by the private background
    :class:`~swirengine.jobs17.JobScheduler`. ``INSTANTIATE`` and ``UNLOAD`` nodes are
    never sent to workers and execute only from :meth:`poll`, making renderer/window,
    ECS and other thread-affine mutations explicit and bounded.

    Node dependencies must refer to previously added nodes. That construction rule makes
    cycles impossible and gives every graph a deterministic immutable submission order.
    Independent branches remain isolated when another branch fails or is cancelled.
    """

    def __init__(
        self,
        *,
        max_nodes: int = 4096,
        max_workers: int = 4,
        max_pending_background: int = 1024,
        max_background_submissions_per_poll: int = 64,
    ) -> None:
        self.max_nodes = self._positive_int(max_nodes, label="max_nodes")
        self.max_background_submissions_per_poll = self._positive_int(
            max_background_submissions_per_poll,
            label="max_background_submissions_per_poll",
        )
        self._scheduler = JobScheduler(
            max_workers=self._positive_int(max_workers, label="max_workers"),
            max_pending=self._positive_int(
                max_pending_background,
                label="max_pending_background",
            ),
            thread_name_prefix="swir-stream",
        )
        self._lock = threading.RLock()
        self._nodes: dict[str, _NodeRecord] = {}
        self._ready_main: list[tuple[int, int, str]] = []
        self._next_sequence = 1
        self._started = False
        self._closed = False
        self._submitted_background_total = 0
        self._executed_main_total = 0
        self._failed_total = 0
        self._cancelled_total = 0
        self._blocked_total = 0
        self._poll_calls = 0
        self._main_thread_callbacks_last_poll = 0
        self._background_handoffs_last_poll = 0
        self._background_submissions_last_poll = 0

    @staticmethod
    def _positive_int(value: int, *, label: str) -> int:
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            raise ValueError(f"{label} must be a positive integer")
        return value

    @staticmethod
    def _node_id(value: str) -> str:
        if not isinstance(value, str):
            raise WorkGraphRejectedError("invalid_node_id", "node_id must be a string")
        result = value.strip()
        if not result or len(result) > 128:
            raise WorkGraphRejectedError(
                "invalid_node_id",
                "node_id must contain 1 to 128 non-whitespace characters",
                node_id=value,
            )
        return result

    @staticmethod
    def _priority(value: int) -> int:
        if isinstance(value, bool) or not isinstance(value, int):
            raise WorkGraphRejectedError("invalid_priority", "priority must be an integer")
        return value

    @staticmethod
    def _phase(value: WorkPhase | str) -> WorkPhase:
        if isinstance(value, WorkPhase):
            return value
        if isinstance(value, str):
            try:
                return WorkPhase(value.strip().lower())
            except ValueError as error:
                raise WorkGraphRejectedError(
                    "invalid_phase", f"unknown work phase {value!r}"
                ) from error
        raise WorkGraphRejectedError("invalid_phase", "phase must be a WorkPhase or string")

    def add(
        self,
        node_id: str,
        phase: WorkPhase | str,
        function: WorkCallable,
        *,
        dependencies: Sequence[str] = (),
        priority: int = 0,
    ) -> WorkNodeSpec:
        normalized_id = self._node_id(node_id)
        normalized_phase = self._phase(phase)
        normalized_priority = self._priority(priority)
        if not callable(function):
            raise WorkGraphRejectedError(
                "invalid_callable",
                "function must be callable",
                node_id=normalized_id,
            )
        if isinstance(dependencies, (str, bytes)) or not isinstance(dependencies, Sequence):
            raise WorkGraphRejectedError(
                "invalid_dependencies",
                "dependencies must be a sequence of node ids",
                node_id=normalized_id,
            )

        normalized_dependencies: list[str] = []
        seen: set[str] = set()
        for dependency in dependencies:
            dependency_id = self._node_id(dependency)
            if dependency_id == normalized_id:
                raise WorkGraphRejectedError(
                    "self_dependency",
                    "a node cannot depend on itself",
                    node_id=normalized_id,
                )
            if dependency_id in seen:
                raise WorkGraphRejectedError(
                    "duplicate_dependency",
                    f"dependency {dependency_id!r} is repeated",
                    node_id=normalized_id,
                )
            seen.add(dependency_id)
            normalized_dependencies.append(dependency_id)

        with self._lock:
            if self._closed:
                raise WorkGraphRejectedError(
                    "closed", "work graph is closed", node_id=normalized_id
                )
            if self._started:
                raise WorkGraphRejectedError(
                    "already_started",
                    "nodes cannot be added after start()",
                    node_id=normalized_id,
                )
            if normalized_id in self._nodes:
                raise WorkGraphRejectedError(
                    "duplicate_node_id",
                    f"node {normalized_id!r} already exists",
                    node_id=normalized_id,
                )
            if len(self._nodes) >= self.max_nodes:
                raise WorkGraphRejectedError(
                    "graph_capacity",
                    "max_nodes graph budget reached",
                    node_id=normalized_id,
                )
            missing = [item for item in normalized_dependencies if item not in self._nodes]
            if missing:
                raise WorkGraphRejectedError(
                    "missing_dependency",
                    f"dependencies must be added first: {', '.join(missing)}",
                    node_id=normalized_id,
                )

            spec = WorkNodeSpec(
                node_id=normalized_id,
                phase=normalized_phase,
                dependencies=tuple(normalized_dependencies),
                priority=normalized_priority,
                sequence=self._next_sequence,
            )
            self._next_sequence += 1
            self._nodes[normalized_id] = _NodeRecord(spec=spec, function=function)
            for dependency_id in normalized_dependencies:
                self._nodes[dependency_id].dependents.add(normalized_id)
            return spec

    def start(self) -> None:
        with self._lock:
            if self._closed:
                raise StreamingWorkGraphError("work graph is closed")
            if self._started:
                return
            if not self._nodes:
                raise StreamingWorkGraphError("cannot start an empty work graph")
            self._started = True
            self._advance_locked(self.max_background_submissions_per_poll)

    def _dependency_values_locked(self, record: _NodeRecord) -> Mapping[str, object]:
        values = {
            dependency_id: self._nodes[dependency_id].value
            for dependency_id in record.spec.dependencies
        }
        return MappingProxyType(values)

    def _dependency_failed_locked(self, record: _NodeRecord) -> str | None:
        for dependency_id in record.spec.dependencies:
            if self._nodes[dependency_id].state in {
                WorkNodeState.FAILED,
                WorkNodeState.CANCELLED,
                WorkNodeState.BLOCKED,
            }:
                return dependency_id
        return None

    def _dependencies_succeeded_locked(self, record: _NodeRecord) -> bool:
        return all(
            self._nodes[dependency_id].state is WorkNodeState.SUCCEEDED
            for dependency_id in record.spec.dependencies
        )

    def _ready_waiting_locked(self) -> list[_NodeRecord]:
        ready = [
            record
            for record in self._nodes.values()
            if record.state is WorkNodeState.WAITING
            and self._dependencies_succeeded_locked(record)
        ]
        ready.sort(
            key=lambda item: (-item.spec.priority, item.spec.sequence, item.spec.node_id)
        )
        return ready

    def _mark_blocked_locked(self, record: _NodeRecord, dependency_id: str) -> None:
        if record.state in _TERMINAL:
            return
        record.state = WorkNodeState.BLOCKED
        record.error_type = "DependencyBlocked"
        record.error_message = f"dependency {dependency_id!r} did not succeed"
        self._blocked_total += 1

    def _propagate_dependency_blocks_locked(self) -> None:
        changed = True
        while changed:
            changed = False
            for record in sorted(
                self._nodes.values(), key=lambda item: item.spec.sequence
            ):
                if record.state is not WorkNodeState.WAITING:
                    continue
                failed_dependency = self._dependency_failed_locked(record)
                if failed_dependency is not None:
                    self._mark_blocked_locked(record, failed_dependency)
                    changed = True

    def _schedule_background_locked(self, record: _NodeRecord) -> None:
        dependency_values = self._dependency_values_locked(record)
        node_id = record.spec.node_id
        phase = record.spec.phase

        def execute(context: JobContext) -> object:
            work_context = WorkContext(
                node_id=node_id,
                phase=phase,
                affinity=WorkAffinity.BACKGROUND,
                dependency_values=dependency_values,
                cancellation_requested=lambda: context.cancelled,
            )
            return record.function(work_context)

        self._scheduler.submit(
            node_id,
            execute,
            priority=record.spec.priority,
            dependencies=(),
        )
        record.state = WorkNodeState.SCHEDULED
        self._submitted_background_total += 1

    def _queue_main_locked(self, record: _NodeRecord) -> None:
        record.state = WorkNodeState.READY_MAIN
        heapq.heappush(
            self._ready_main,
            (-record.spec.priority, record.spec.sequence, record.spec.node_id),
        )

    def _advance_locked(self, background_submission_budget: int) -> int:
        self._propagate_dependency_blocks_locked()
        scheduler = self._scheduler.diagnostics()
        scheduler_capacity = max(0, scheduler.max_pending - scheduler.unfinished)
        remaining = min(background_submission_budget, scheduler_capacity)
        submitted = 0
        for record in self._ready_waiting_locked():
            if record.spec.affinity is WorkAffinity.BACKGROUND:
                if remaining <= 0:
                    continue
                self._schedule_background_locked(record)
                remaining -= 1
                submitted += 1
            else:
                self._queue_main_locked(record)
        return submitted

    def _process_background_handoffs_locked(self, max_items: int) -> int:
        outcomes = self._scheduler.drain_completed(max_items=max_items)
        for outcome in outcomes:
            record = self._nodes[outcome.job_id]
            if record.state is WorkNodeState.CANCELLED:
                continue
            if outcome.state is JobState.SUCCEEDED:
                record.state = WorkNodeState.SUCCEEDED
                record.value = outcome.value
            elif outcome.state is JobState.CANCELLED:
                record.state = WorkNodeState.CANCELLED
                record.error_type = outcome.error_type
                record.error_message = outcome.error_message
                self._cancelled_total += 1
            else:
                record.state = WorkNodeState.FAILED
                record.error_type = outcome.error_type
                record.error_message = outcome.error_message
                self._failed_total += 1
        return len(outcomes)

    def _execute_main_locked(self, max_items: int) -> int:
        executed = 0
        while executed < max_items and self._ready_main:
            _, _, node_id = heapq.heappop(self._ready_main)
            record = self._nodes[node_id]
            if record.state is not WorkNodeState.READY_MAIN:
                continue
            if record.cancel_requested:
                record.state = WorkNodeState.CANCELLED
                record.error_type = "WorkCancelled"
                record.error_message = "work node cancellation requested"
                self._cancelled_total += 1
                continue
            context = WorkContext(
                node_id=node_id,
                phase=record.spec.phase,
                affinity=WorkAffinity.MAIN_THREAD,
                dependency_values=self._dependency_values_locked(record),
                cancellation_requested=lambda current=record: current.cancel_requested,
            )
            try:
                record.value = record.function(context)
            except Exception as error:  # creator callback isolation is intentional
                record.state = WorkNodeState.FAILED
                record.error_type = type(error).__name__
                record.error_message = str(error)
                self._failed_total += 1
            else:
                record.state = WorkNodeState.SUCCEEDED
            self._executed_main_total += 1
            executed += 1
        return executed

    def poll(self, *, max_items: int = 32) -> tuple[WorkNodeResult, ...]:
        item_budget = self._positive_int(max_items, label="max_items")
        with self._lock:
            if self._closed:
                raise StreamingWorkGraphError("work graph is closed")
            if not self._started:
                raise StreamingWorkGraphError("start() must be called before poll()")
            before = {node_id: record.state for node_id, record in self._nodes.items()}
            handoffs = self._process_background_handoffs_locked(item_budget)
            remaining_items = item_budget - handoffs
            submitted = self._advance_locked(self.max_background_submissions_per_poll)
            main_callbacks = self._execute_main_locked(remaining_items)
            remaining_submissions = max(
                0, self.max_background_submissions_per_poll - submitted
            )
            submitted += self._advance_locked(remaining_submissions)
            self._poll_calls += 1
            self._background_handoffs_last_poll = handoffs
            self._main_thread_callbacks_last_poll = main_callbacks
            self._background_submissions_last_poll = submitted
            changed = [
                self._result_locked(record)
                for node_id, record in sorted(
                    self._nodes.items(), key=lambda item: item[1].spec.sequence
                )
                if record.state != before[node_id] and record.state in _TERMINAL
            ]
            return tuple(changed)

    def cancel(self, node_id: str, *, cascade: bool = True) -> tuple[str, ...]:
        normalized_id = self._node_id(node_id)
        if not isinstance(cascade, bool):
            raise TypeError("cascade must be a bool")
        with self._lock:
            if normalized_id not in self._nodes:
                raise KeyError(normalized_id)
            selected: set[str] = {normalized_id}
            if cascade:
                pending = [normalized_id]
                while pending:
                    current = pending.pop()
                    for dependent in sorted(self._nodes[current].dependents):
                        if dependent not in selected:
                            selected.add(dependent)
                            pending.append(dependent)

            cancelled: list[str] = []
            for current_id in sorted(
                selected, key=lambda item: self._nodes[item].spec.sequence
            ):
                record = self._nodes[current_id]
                if record.state in _TERMINAL:
                    continue
                record.cancel_requested = True
                if record.state is WorkNodeState.SCHEDULED:
                    try:
                        self._scheduler.cancel(current_id)
                    except KeyError:
                        pass
                record.state = WorkNodeState.CANCELLED
                record.value = None
                record.error_type = "WorkCancelled"
                record.error_message = "work node cancellation requested"
                self._cancelled_total += 1
                cancelled.append(current_id)
            self._propagate_dependency_blocks_locked()
            return tuple(cancelled)

    def state(self, node_id: str) -> WorkNodeState:
        normalized_id = self._node_id(node_id)
        with self._lock:
            return self._nodes[normalized_id].state

    def spec(self, node_id: str) -> WorkNodeSpec:
        normalized_id = self._node_id(node_id)
        with self._lock:
            return self._nodes[normalized_id].spec

    def result(self, node_id: str) -> WorkNodeResult:
        normalized_id = self._node_id(node_id)
        with self._lock:
            record = self._nodes[normalized_id]
            if record.state not in _TERMINAL:
                raise StreamingWorkGraphError(f"node {normalized_id!r} is not complete")
            return self._result_locked(record)

    @staticmethod
    def _result_locked(record: _NodeRecord) -> WorkNodeResult:
        return WorkNodeResult(
            node_id=record.spec.node_id,
            phase=record.spec.phase,
            state=record.state,
            value=record.value,
            error_type=record.error_type,
            error_message=record.error_message,
        )

    def diagnostics(self) -> WorkGraphDiagnostics:
        with self._lock:
            counts = {state: 0 for state in WorkNodeState}
            phase_counts = {phase: 0 for phase in WorkPhase}
            for record in self._nodes.values():
                counts[record.state] += 1
                phase_counts[record.spec.phase] += 1
            return WorkGraphDiagnostics(
                total_nodes=len(self._nodes),
                max_nodes=self.max_nodes,
                max_background_submissions_per_poll=self.max_background_submissions_per_poll,
                waiting=counts[WorkNodeState.WAITING],
                scheduled=counts[WorkNodeState.SCHEDULED],
                ready_main=counts[WorkNodeState.READY_MAIN],
                succeeded=counts[WorkNodeState.SUCCEEDED],
                failed=counts[WorkNodeState.FAILED],
                cancelled=counts[WorkNodeState.CANCELLED],
                blocked=counts[WorkNodeState.BLOCKED],
                submitted_background_total=self._submitted_background_total,
                executed_main_total=self._executed_main_total,
                failed_total=self._failed_total,
                cancelled_total=self._cancelled_total,
                blocked_total=self._blocked_total,
                poll_calls=self._poll_calls,
                main_thread_callbacks_last_poll=self._main_thread_callbacks_last_poll,
                background_handoffs_last_poll=self._background_handoffs_last_poll,
                background_submissions_last_poll=self._background_submissions_last_poll,
                phase_counts=tuple(
                    (phase.value, phase_counts[phase]) for phase in WorkPhase
                ),
            )

    @property
    def complete(self) -> bool:
        return self.diagnostics().complete

    def run_until_complete(
        self,
        *,
        max_items: int = 64,
        timeout: float = 5.0,
        sleep_interval: float = 0.0005,
    ) -> tuple[WorkNodeResult, ...]:
        item_budget = self._positive_int(max_items, label="max_items")
        if isinstance(timeout, bool) or not isinstance(timeout, (int, float)):
            raise TypeError("timeout must be a finite positive number")
        timeout_value = float(timeout)
        if not math.isfinite(timeout_value) or timeout_value <= 0.0:
            raise ValueError("timeout must be a finite positive number")
        if isinstance(sleep_interval, bool) or not isinstance(sleep_interval, (int, float)):
            raise TypeError("sleep_interval must be a finite non-negative number")
        sleep_value = float(sleep_interval)
        if not math.isfinite(sleep_value) or sleep_value < 0.0:
            raise ValueError("sleep_interval must be a finite non-negative number")
        if not self._started:
            self.start()
        deadline = time.monotonic() + timeout_value
        while not self.complete:
            self.poll(max_items=item_budget)
            if self.complete:
                break
            if time.monotonic() >= deadline:
                raise TimeoutError("streaming work graph did not finish before timeout")
            if sleep_value:
                time.sleep(sleep_value)
        with self._lock:
            return tuple(
                self._result_locked(record)
                for record in sorted(
                    self._nodes.values(), key=lambda item: item.spec.sequence
                )
            )

    def shutdown(self, *, wait: bool = True, cancel_pending: bool = True) -> None:
        if not isinstance(wait, bool) or not isinstance(cancel_pending, bool):
            raise TypeError("wait and cancel_pending must be bool values")
        with self._lock:
            if self._closed:
                return
            if cancel_pending:
                for record in self._nodes.values():
                    if record.state not in _TERMINAL:
                        record.cancel_requested = True
            self._closed = True
        self._scheduler.shutdown(wait=wait, cancel_pending=cancel_pending)

    def __enter__(self) -> StreamingWorkGraph:
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        self.shutdown(wait=True, cancel_pending=True)


__all__ = [
    "StreamingWorkGraph",
    "StreamingWorkGraphError",
    "WorkAffinity",
    "WorkContext",
    "WorkGraphDiagnostics",
    "WorkGraphRejectedError",
    "WorkNodeResult",
    "WorkNodeSpec",
    "WorkNodeState",
    "WorkPhase",
]
