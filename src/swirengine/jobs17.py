from __future__ import annotations

import heapq
import math
import threading
import time
from collections import deque
from collections.abc import Callable, Mapping
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass, field
from enum import Enum
from types import TracebackType
from typing import Any, Generic, TypeVar

from typing_extensions import Self


T = TypeVar("T")


class JobState(str, Enum):
    WAITING = "waiting"
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"
    BLOCKED = "blocked"


_TERMINAL_STATES = {
    JobState.SUCCEEDED,
    JobState.FAILED,
    JobState.CANCELLED,
    JobState.BLOCKED,
}


class JobSchedulerError(RuntimeError):
    """Base error raised by the additive SwirEngine 1.7 job system."""


class JobRejectedError(JobSchedulerError):
    """Raised when a job cannot be accepted without violating scheduler contracts."""

    def __init__(self, code: str, message: str, *, job_id: str | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.job_id = job_id


class JobCancelled(JobSchedulerError):
    """Cooperative cancellation signal for worker functions."""


class CancellationToken:
    """Thread-safe cooperative cancellation token owned by one submitted job."""

    def __init__(self) -> None:
        self._event = threading.Event()

    @property
    def cancelled(self) -> bool:
        return self._event.is_set()

    def cancel(self) -> None:
        self._event.set()

    def raise_if_cancelled(self) -> None:
        if self.cancelled:
            raise JobCancelled("job cancellation requested")


@dataclass(frozen=True, slots=True)
class JobContext:
    job_id: str
    sequence: int
    cancellation: CancellationToken

    @property
    def cancelled(self) -> bool:
        return self.cancellation.cancelled

    def raise_if_cancelled(self) -> None:
        self.cancellation.raise_if_cancelled()


@dataclass(frozen=True, slots=True)
class JobOutcome(Generic[T]):
    job_id: str
    sequence: int
    state: JobState
    value: T | None = None
    error_type: str | None = None
    error_message: str | None = None

    @property
    def successful(self) -> bool:
        return self.state is JobState.SUCCEEDED


@dataclass(frozen=True, slots=True)
class JobSchedulerDiagnostics:
    max_workers: int
    max_pending: int
    waiting: int
    queued: int
    running: int
    succeeded: int
    failed: int
    cancelled: int
    blocked: int
    undrained: int
    accepted_total: int
    rejected_total: int
    delivered_total: int
    dependency_blocks_total: int
    cancellation_requests_total: int

    @property
    def unfinished(self) -> int:
        return self.waiting + self.queued + self.running

    def portable(self) -> Mapping[str, int]:
        return {
            "max_workers": self.max_workers,
            "max_pending": self.max_pending,
            "waiting": self.waiting,
            "queued": self.queued,
            "running": self.running,
            "succeeded": self.succeeded,
            "failed": self.failed,
            "cancelled": self.cancelled,
            "blocked": self.blocked,
            "undrained": self.undrained,
            "unfinished": self.unfinished,
            "accepted_total": self.accepted_total,
            "rejected_total": self.rejected_total,
            "delivered_total": self.delivered_total,
            "dependency_blocks_total": self.dependency_blocks_total,
            "cancellation_requests_total": self.cancellation_requests_total,
        }


JobCallable = Callable[[JobContext], T]


@dataclass(slots=True)
class _JobRecord:
    job_id: str
    sequence: int
    priority: int
    function: JobCallable[Any]
    dependencies: tuple[str, ...]
    cancellation: CancellationToken = field(default_factory=CancellationToken)
    state: JobState = JobState.WAITING
    value: Any = None
    error_type: str | None = None
    error_message: str | None = None
    future: Future[Any] | None = None
    dependents: set[str] = field(default_factory=set)
    delivered: bool = False


class JobScheduler:
    """Bounded background job scheduler with explicit main-thread result handoff.

    The scheduler is additive and intentionally does not mutate ``Game`` or renderer state.
    Worker functions receive a :class:`JobContext` and should keep engine-owned GPU/window
    operations on the owning thread. Results are transferred back explicitly with
    :meth:`drain_completed`.
    """

    def __init__(
        self,
        *,
        max_workers: int = 4,
        max_pending: int = 1024,
        thread_name_prefix: str = "swir-job",
    ) -> None:
        if isinstance(max_workers, bool) or not isinstance(max_workers, int) or max_workers <= 0:
            raise ValueError("max_workers must be a positive integer")
        if isinstance(max_pending, bool) or not isinstance(max_pending, int) or max_pending <= 0:
            raise ValueError("max_pending must be a positive integer")
        if not isinstance(thread_name_prefix, str) or not thread_name_prefix.strip():
            raise ValueError("thread_name_prefix must be a non-empty string")

        self.max_workers = max_workers
        self.max_pending = max_pending
        self._executor = ThreadPoolExecutor(
            max_workers=max_workers,
            thread_name_prefix=thread_name_prefix.strip(),
        )
        self._lock = threading.RLock()
        self._condition = threading.Condition(self._lock)
        self._records: dict[str, _JobRecord] = {}
        self._ready: list[tuple[int, int, str]] = []
        self._running: set[str] = set()
        self._completed: deque[str] = deque()
        self._next_sequence = 1
        self._closed = False
        self._accepted_total = 0
        self._rejected_total = 0
        self._delivered_total = 0
        self._dependency_blocks_total = 0
        self._cancellation_requests_total = 0

    @staticmethod
    def _validate_job_id(job_id: str) -> str:
        if not isinstance(job_id, str):
            raise JobRejectedError("invalid_job_id", "job_id must be a string")
        normalized = job_id.strip()
        if not normalized or len(normalized) > 128:
            raise JobRejectedError(
                "invalid_job_id",
                "job_id must contain 1 to 128 non-whitespace characters",
                job_id=job_id,
            )
        return normalized

    @staticmethod
    def _validate_priority(priority: int) -> int:
        if isinstance(priority, bool) or not isinstance(priority, int):
            raise JobRejectedError("invalid_priority", "priority must be an integer")
        return priority

    @staticmethod
    def _normalize_dependencies(
        job_id: str, dependencies: tuple[str, ...] | list[str]
    ) -> tuple[str, ...]:
        if isinstance(dependencies, str):
            raise JobRejectedError(
                "invalid_dependencies",
                "dependencies must be a sequence of job ids, not one string",
                job_id=job_id,
            )
        normalized: list[str] = []
        seen: set[str] = set()
        for dependency in dependencies:
            dependency_id = JobScheduler._validate_job_id(dependency)
            if dependency_id == job_id:
                raise JobRejectedError(
                    "self_dependency",
                    "a job cannot depend on itself",
                    job_id=job_id,
                )
            if dependency_id in seen:
                raise JobRejectedError(
                    "duplicate_dependency",
                    f"dependency {dependency_id!r} is repeated",
                    job_id=job_id,
                )
            seen.add(dependency_id)
            normalized.append(dependency_id)
        return tuple(normalized)

    def _reject(self, error: JobRejectedError) -> None:
        self._rejected_total += 1
        raise error

    def _unfinished_count_locked(self) -> int:
        return sum(record.state not in _TERMINAL_STATES for record in self._records.values())

    def submit(
        self,
        job_id: str,
        function: JobCallable[T],
        *,
        priority: int = 0,
        dependencies: tuple[str, ...] | list[str] = (),
    ) -> int:
        try:
            normalized_id = self._validate_job_id(job_id)
            normalized_priority = self._validate_priority(priority)
            normalized_dependencies = self._normalize_dependencies(normalized_id, dependencies)
            if not callable(function):
                raise JobRejectedError(
                    "invalid_callable",
                    "function must be callable",
                    job_id=normalized_id,
                )
        except JobRejectedError:
            with self._lock:
                self._rejected_total += 1
            raise

        with self._condition:
            if self._closed:
                self._reject(
                    JobRejectedError(
                        "closed",
                        "scheduler is closed",
                        job_id=normalized_id,
                    )
                )
            if normalized_id in self._records:
                self._reject(
                    JobRejectedError(
                        "duplicate_job_id",
                        f"job {normalized_id!r} already exists",
                        job_id=normalized_id,
                    )
                )
            if self._unfinished_count_locked() >= self.max_pending:
                self._reject(
                    JobRejectedError(
                        "backpressure",
                        "max_pending unfinished-job budget reached",
                        job_id=normalized_id,
                    )
                )
            missing = [dep for dep in normalized_dependencies if dep not in self._records]
            if missing:
                self._reject(
                    JobRejectedError(
                        "missing_dependency",
                        f"unknown dependencies: {', '.join(missing)}",
                        job_id=normalized_id,
                    )
                )

            sequence = self._next_sequence
            self._next_sequence += 1
            record = _JobRecord(
                job_id=normalized_id,
                sequence=sequence,
                priority=normalized_priority,
                function=function,
                dependencies=normalized_dependencies,
            )
            self._records[normalized_id] = record
            self._accepted_total += 1
            for dependency_id in normalized_dependencies:
                self._records[dependency_id].dependents.add(normalized_id)

            if self._has_failed_dependency_locked(record):
                self._mark_blocked_locked(record)
                self._resolve_dependents_locked(record.job_id)
            elif self._dependencies_succeeded_locked(record):
                self._queue_locked(record)
            self._dispatch_locked()
            self._condition.notify_all()
            return sequence

    def _dependencies_succeeded_locked(self, record: _JobRecord) -> bool:
        return all(
            self._records[dependency_id].state is JobState.SUCCEEDED
            for dependency_id in record.dependencies
        )

    def _has_failed_dependency_locked(self, record: _JobRecord) -> bool:
        return any(
            self._records[dependency_id].state
            in {JobState.FAILED, JobState.CANCELLED, JobState.BLOCKED}
            for dependency_id in record.dependencies
        )

    def _queue_locked(self, record: _JobRecord) -> None:
        if record.state is not JobState.WAITING:
            return
        record.state = JobState.QUEUED
        heapq.heappush(self._ready, (-record.priority, record.sequence, record.job_id))

    def _dispatch_locked(self) -> None:
        while len(self._running) < self.max_workers and self._ready:
            _, _, job_id = heapq.heappop(self._ready)
            record = self._records.get(job_id)
            if record is None or record.state is not JobState.QUEUED:
                continue
            if record.cancellation.cancelled:
                self._mark_cancelled_locked(record)
                self._resolve_dependents_locked(record.job_id)
                continue
            record.state = JobState.RUNNING
            self._running.add(job_id)
            future = self._executor.submit(self._execute, job_id)
            record.future = future
            future.add_done_callback(
                lambda completed, current=job_id: self._on_done(current, completed)
            )

    def _execute(self, job_id: str) -> Any:
        with self._lock:
            record = self._records[job_id]
            context = JobContext(
                job_id=record.job_id,
                sequence=record.sequence,
                cancellation=record.cancellation,
            )
            function = record.function
        context.raise_if_cancelled()
        return function(context)

    def _on_done(self, job_id: str, future: Future[Any]) -> None:
        try:
            value = future.result()
            error: Exception | None = None
        except Exception as caught:  # Future intentionally isolates worker failures.
            value = None
            error = caught

        with self._condition:
            record = self._records[job_id]
            self._running.discard(job_id)
            if record.cancellation.cancelled or isinstance(error, JobCancelled):
                self._mark_cancelled_locked(record)
            elif error is not None:
                record.state = JobState.FAILED
                record.error_type = type(error).__name__
                record.error_message = str(error)
                self._completed.append(job_id)
            else:
                record.state = JobState.SUCCEEDED
                record.value = value
                self._completed.append(job_id)
            self._resolve_dependents_locked(job_id)
            self._dispatch_locked()
            self._condition.notify_all()

    def _mark_cancelled_locked(self, record: _JobRecord) -> None:
        if record.state in _TERMINAL_STATES:
            return
        record.state = JobState.CANCELLED
        record.value = None
        record.error_type = "JobCancelled"
        record.error_message = "job cancellation requested"
        self._completed.append(record.job_id)

    def _mark_blocked_locked(self, record: _JobRecord) -> None:
        if record.state in _TERMINAL_STATES:
            return
        failed_dependency = next(
            dependency_id
            for dependency_id in record.dependencies
            if self._records[dependency_id].state
            in {JobState.FAILED, JobState.CANCELLED, JobState.BLOCKED}
        )
        record.state = JobState.BLOCKED
        record.error_type = "DependencyBlocked"
        record.error_message = f"dependency {failed_dependency!r} did not succeed"
        self._dependency_blocks_total += 1
        self._completed.append(record.job_id)

    def _resolve_dependents_locked(self, job_id: str) -> None:
        pending = deque([job_id])
        while pending:
            completed_id = pending.popleft()
            completed = self._records[completed_id]
            dependent_ids = sorted(
                completed.dependents,
                key=lambda dependent_id: self._records[dependent_id].sequence,
            )
            for dependent_id in dependent_ids:
                dependent = self._records[dependent_id]
                if dependent.state is not JobState.WAITING:
                    continue
                if self._has_failed_dependency_locked(dependent):
                    self._mark_blocked_locked(dependent)
                    pending.append(dependent_id)
                elif self._dependencies_succeeded_locked(dependent):
                    self._queue_locked(dependent)

    def cancel(self, job_id: str) -> bool:
        normalized_id = self._validate_job_id(job_id)
        with self._condition:
            record = self._records.get(normalized_id)
            if record is None:
                raise KeyError(normalized_id)
            if record.state in _TERMINAL_STATES:
                return False
            self._cancellation_requests_total += 1
            record.cancellation.cancel()
            if record.state in {JobState.WAITING, JobState.QUEUED}:
                self._mark_cancelled_locked(record)
                self._resolve_dependents_locked(record.job_id)
                self._dispatch_locked()
                self._condition.notify_all()
            return True

    def state(self, job_id: str) -> JobState:
        normalized_id = self._validate_job_id(job_id)
        with self._lock:
            return self._records[normalized_id].state

    def outcome(self, job_id: str) -> JobOutcome[Any]:
        normalized_id = self._validate_job_id(job_id)
        with self._lock:
            record = self._records[normalized_id]
            if record.state not in _TERMINAL_STATES:
                raise JobSchedulerError(f"job {normalized_id!r} is not complete")
            return self._outcome_locked(record)

    @staticmethod
    def _outcome_locked(record: _JobRecord) -> JobOutcome[Any]:
        return JobOutcome(
            job_id=record.job_id,
            sequence=record.sequence,
            state=record.state,
            value=record.value,
            error_type=record.error_type,
            error_message=record.error_message,
        )

    def wait(self, job_id: str, timeout: float | None = None) -> JobOutcome[Any]:
        normalized_id = self._validate_job_id(job_id)
        deadline = self._deadline(timeout)
        with self._condition:
            while True:
                record = self._records[normalized_id]
                if record.state in _TERMINAL_STATES:
                    return self._outcome_locked(record)
                remaining = self._remaining(deadline)
                if remaining == 0.0:
                    raise TimeoutError(f"job {normalized_id!r} did not finish before timeout")
                self._condition.wait(remaining)

    def wait_all(self, timeout: float | None = None) -> tuple[JobOutcome[Any], ...]:
        deadline = self._deadline(timeout)
        with self._condition:
            while self._unfinished_count_locked() > 0:
                remaining = self._remaining(deadline)
                if remaining == 0.0:
                    raise TimeoutError("jobs did not finish before timeout")
                self._condition.wait(remaining)
            return tuple(
                self._outcome_locked(record)
                for record in sorted(self._records.values(), key=lambda item: item.sequence)
            )

    @staticmethod
    def _deadline(timeout: float | None) -> float | None:
        if timeout is None:
            return None
        if isinstance(timeout, bool) or not isinstance(timeout, (int, float)):
            raise TypeError("timeout must be a finite non-negative number or None")
        timeout_value = float(timeout)
        if not math.isfinite(timeout_value) or timeout_value < 0.0:
            raise ValueError("timeout must be a finite non-negative number or None")
        return time.monotonic() + timeout_value

    @staticmethod
    def _remaining(deadline: float | None) -> float | None:
        if deadline is None:
            return None
        return max(0.0, deadline - time.monotonic())

    def drain_completed(self, max_items: int | None = None) -> tuple[JobOutcome[Any], ...]:
        if max_items is not None and (
            isinstance(max_items, bool) or not isinstance(max_items, int) or max_items <= 0
        ):
            raise ValueError("max_items must be a positive integer or None")
        with self._condition:
            available = (
                len(self._completed)
                if max_items is None
                else min(max_items, len(self._completed))
            )
            selected: list[_JobRecord] = []
            for _ in range(available):
                job_id = self._completed.popleft()
                record = self._records[job_id]
                if record.delivered:
                    continue
                record.delivered = True
                selected.append(record)
            selected.sort(key=lambda record: record.sequence)
            self._delivered_total += len(selected)
            return tuple(self._outcome_locked(record) for record in selected)

    def forget(self, job_id: str) -> None:
        normalized_id = self._validate_job_id(job_id)
        with self._condition:
            record = self._records[normalized_id]
            if record.state not in _TERMINAL_STATES:
                raise JobSchedulerError("cannot forget an unfinished job")
            if not record.delivered:
                raise JobSchedulerError("drain the completed outcome before forgetting the job")
            live_dependents = [
                dependent_id for dependent_id in record.dependents if dependent_id in self._records
            ]
            if live_dependents:
                raise JobSchedulerError(
                    "cannot forget a job while retained dependents reference it"
                )
            for dependency_id in record.dependencies:
                dependency = self._records.get(dependency_id)
                if dependency is not None:
                    dependency.dependents.discard(normalized_id)
            del self._records[normalized_id]

    def diagnostics(self) -> JobSchedulerDiagnostics:
        with self._lock:
            counts = {state: 0 for state in JobState}
            for record in self._records.values():
                counts[record.state] += 1
            return JobSchedulerDiagnostics(
                max_workers=self.max_workers,
                max_pending=self.max_pending,
                waiting=counts[JobState.WAITING],
                queued=counts[JobState.QUEUED],
                running=counts[JobState.RUNNING],
                succeeded=counts[JobState.SUCCEEDED],
                failed=counts[JobState.FAILED],
                cancelled=counts[JobState.CANCELLED],
                blocked=counts[JobState.BLOCKED],
                undrained=sum(not record.delivered for record in self._terminal_records_locked()),
                accepted_total=self._accepted_total,
                rejected_total=self._rejected_total,
                delivered_total=self._delivered_total,
                dependency_blocks_total=self._dependency_blocks_total,
                cancellation_requests_total=self._cancellation_requests_total,
            )

    def _terminal_records_locked(self) -> tuple[_JobRecord, ...]:
        return tuple(
            record for record in self._records.values() if record.state in _TERMINAL_STATES
        )

    def shutdown(self, *, wait: bool = True, cancel_pending: bool = False) -> None:
        if not isinstance(wait, bool) or not isinstance(cancel_pending, bool):
            raise TypeError("wait and cancel_pending must be bool values")

        if wait and not cancel_pending:
            self.wait_all()

        with self._condition:
            if self._closed:
                return
            self._closed = True
            cancel_not_started = cancel_pending or not wait
            for record in sorted(self._records.values(), key=lambda item: item.sequence):
                if record.state in _TERMINAL_STATES:
                    continue
                if record.state in {JobState.WAITING, JobState.QUEUED} and cancel_not_started:
                    self._cancellation_requests_total += 1
                    record.cancellation.cancel()
                    self._mark_cancelled_locked(record)
                    self._resolve_dependents_locked(record.job_id)
                elif record.state is JobState.RUNNING and cancel_pending:
                    self._cancellation_requests_total += 1
                    record.cancellation.cancel()
            self._condition.notify_all()
        self._executor.shutdown(wait=wait, cancel_futures=False)

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.shutdown(wait=True, cancel_pending=True)


__all__ = [
    "CancellationToken",
    "JobCancelled",
    "JobContext",
    "JobOutcome",
    "JobRejectedError",
    "JobScheduler",
    "JobSchedulerDiagnostics",
    "JobSchedulerError",
    "JobState",
]
