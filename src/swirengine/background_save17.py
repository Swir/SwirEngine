from __future__ import annotations

import hashlib
import json
import math
import threading
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from types import MappingProxyType
from typing import Any, TypeAlias

from typing_extensions import Self

from .jobs17 import JobContext, JobScheduler, JobState
from .storage15 import ProfileSaveManager2, SaveLoadResult, SaveSlotInfo, SaveSlotStore2

JSONValue: TypeAlias = (
    None | bool | int | float | str | list["JSONValue"] | dict[str, "JSONValue"]
)
SnapshotSource: TypeAlias = Mapping[str, Any] | Callable[[], Mapping[str, Any]]
MetadataSource: TypeAlias = Mapping[str, Any] | Callable[[], Mapping[str, Any]] | None


def _identifier(value: str, *, label: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{label} must be a string")
    normalized = value.strip()
    if not normalized or len(normalized) > 128:
        raise ValueError(f"{label} must contain 1 to 128 non-whitespace characters")
    return normalized


def _positive_int(value: int, *, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{label} must be an integer")
    if value < 1:
        raise ValueError(f"{label} must be >= 1")
    return value


def _portable(value: Any) -> JSONValue:
    if value is None or isinstance(value, (bool, str, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("save snapshot floats must be finite")
        return 0.0 if value == 0.0 else value
    if isinstance(value, (list, tuple)):
        return [_portable(item) for item in value]
    if isinstance(value, Mapping):
        normalized: dict[str, JSONValue] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise TypeError("save snapshot mapping keys must be strings")
            normalized[key] = _portable(item)
        return normalized
    raise TypeError(f"unsupported save snapshot value type: {type(value).__name__}")


def _portable_mapping(value: Mapping[str, Any], *, label: str) -> dict[str, JSONValue]:
    normalized = _portable(value)
    if not isinstance(normalized, dict):
        raise TypeError(f"{label} must be a mapping")
    return normalized


def _canonical_json(value: Mapping[str, Any], *, label: str) -> str:
    return json.dumps(
        _portable_mapping(value, label=label),
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    )


def _snapshot_fingerprint(data_json: str, metadata_json: str) -> str:
    digest = hashlib.sha256()
    digest.update(data_json.encode("utf-8"))
    digest.update(b"\n")
    digest.update(metadata_json.encode("utf-8"))
    return digest.hexdigest()


class BackgroundSaveState(str, Enum):
    QUEUED = "queued"
    WRITING = "writing"
    COMMITTING = "committing"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


_TERMINAL_STATES = {
    BackgroundSaveState.SUCCEEDED,
    BackgroundSaveState.FAILED,
    BackgroundSaveState.CANCELLED,
}


@dataclass(frozen=True, slots=True)
class PreparedSaveSnapshot:
    """Immutable JSON snapshot captured before background I/O begins."""

    request_id: str
    data_json: str
    metadata_json: str
    fingerprint: str
    captured_thread_id: int

    @classmethod
    def capture(
        cls,
        request_id: str,
        data: Mapping[str, Any],
        metadata: Mapping[str, Any] | None = None,
    ) -> PreparedSaveSnapshot:
        normalized_id = _identifier(request_id, label="request_id")
        if not isinstance(data, Mapping):
            raise TypeError("save snapshot data must be a mapping")
        if metadata is not None and not isinstance(metadata, Mapping):
            raise TypeError("save snapshot metadata must be a mapping or None")
        data_json = _canonical_json(data, label="save snapshot data")
        metadata_json = _canonical_json(metadata or {}, label="save snapshot metadata")
        return cls(
            request_id=normalized_id,
            data_json=data_json,
            metadata_json=metadata_json,
            fingerprint=_snapshot_fingerprint(data_json, metadata_json),
            captured_thread_id=threading.get_ident(),
        )

    @property
    def byte_size(self) -> int:
        return len(self.data_json.encode("utf-8")) + len(self.metadata_json.encode("utf-8"))

    def decode(self) -> tuple[dict[str, JSONValue], dict[str, JSONValue]]:
        expected = _snapshot_fingerprint(self.data_json, self.metadata_json)
        if expected != self.fingerprint:
            raise ValueError("prepared save snapshot fingerprint mismatch")
        data = json.loads(self.data_json)
        metadata = json.loads(self.metadata_json)
        if not isinstance(data, dict) or not isinstance(metadata, dict):
            raise TypeError("prepared save snapshot roots must be JSON objects")
        return data, metadata


@dataclass(frozen=True, slots=True)
class BackgroundSaveReceipt:
    request_id: str
    path: Path
    revision: int
    snapshot_fingerprint: str
    recovery_available: bool
    snapshot_bytes: int

    def portable(self) -> Mapping[str, object]:
        return MappingProxyType(
            {
                "request_id": self.request_id,
                "path": str(self.path),
                "revision": self.revision,
                "snapshot_fingerprint": self.snapshot_fingerprint,
                "recovery_available": self.recovery_available,
                "snapshot_bytes": self.snapshot_bytes,
            }
        )


@dataclass(frozen=True, slots=True)
class BackgroundSaveOutcome:
    request_id: str
    sequence: int
    state: BackgroundSaveState
    receipt: BackgroundSaveReceipt | None = None
    error_type: str | None = None
    error_message: str | None = None

    @property
    def successful(self) -> bool:
        return self.state is BackgroundSaveState.SUCCEEDED


@dataclass(frozen=True, slots=True)
class BackgroundSaveDiagnostics:
    max_requests: int
    queued: int
    writing: int
    committing: int
    succeeded: int
    failed: int
    cancelled: int
    active_slots: int
    submitted_total: int
    rejected_total: int
    cancellation_requests_total: int
    cancellation_refused_total: int
    snapshot_bytes_total: int
    verified_writes_total: int

    @property
    def unfinished(self) -> int:
        return self.queued + self.writing + self.committing

    def portable(self) -> Mapping[str, int]:
        return MappingProxyType(
            {
                "max_requests": self.max_requests,
                "queued": self.queued,
                "writing": self.writing,
                "committing": self.committing,
                "succeeded": self.succeeded,
                "failed": self.failed,
                "cancelled": self.cancelled,
                "unfinished": self.unfinished,
                "active_slots": self.active_slots,
                "submitted_total": self.submitted_total,
                "rejected_total": self.rejected_total,
                "cancellation_requests_total": self.cancellation_requests_total,
                "cancellation_refused_total": self.cancellation_refused_total,
                "snapshot_bytes_total": self.snapshot_bytes_total,
                "verified_writes_total": self.verified_writes_total,
            }
        )


@dataclass(slots=True)
class _SaveRequest:
    request_id: str
    sequence: int
    store: SaveSlotStore2
    slot_key: str
    snapshot: PreparedSaveSnapshot
    job_id: str
    state: BackgroundSaveState = BackgroundSaveState.QUEUED
    cancel_requested: bool = False
    delivered: bool = False
    receipt: BackgroundSaveReceipt | None = None
    error_type: str | None = None
    error_message: str | None = None


class BackgroundSavePipeline:
    """Snapshot-first asynchronous save I/O layered on Save/Profile 2.0.

    Creator-owned state is converted to a canonical immutable JSON snapshot on the owning
    thread. Workers then perform file I/O through the stable ``SaveSlotStore2`` atomic
    backup/promotion contract and verify the committed primary before success is reported.
    Cancellation is accepted only before the atomic commit boundary begins.
    """

    def __init__(
        self,
        *,
        max_workers: int = 2,
        max_requests: int = 64,
        thread_name_prefix: str = "swir-save",
    ) -> None:
        self.max_requests = _positive_int(max_requests, label="max_requests")
        self._scheduler = JobScheduler(
            max_workers=_positive_int(max_workers, label="max_workers"),
            max_pending=self.max_requests,
            thread_name_prefix=thread_name_prefix,
        )
        self._owner_thread = threading.get_ident()
        self._lock = threading.RLock()
        self._requests: dict[str, _SaveRequest] = {}
        self._active_slots: dict[str, str] = {}
        self._next_sequence = 1
        self._closed = False
        self._submitted_total = 0
        self._rejected_total = 0
        self._cancellation_requests_total = 0
        self._cancellation_refused_total = 0
        self._snapshot_bytes_total = 0
        self._verified_writes_total = 0

    def _require_owner_thread(self) -> None:
        if threading.get_ident() != self._owner_thread:
            raise RuntimeError("background save owner-thread operation called from another thread")

    @staticmethod
    def _slot_key(store: SaveSlotStore2) -> str:
        return str(store.path.expanduser().resolve())

    @staticmethod
    def _resolve_source(source: SnapshotSource, *, label: str) -> Mapping[str, Any]:
        value = source() if callable(source) else source
        if not isinstance(value, Mapping):
            raise TypeError(f"{label} must resolve to a mapping")
        return value

    @staticmethod
    def _resolve_metadata(source: MetadataSource) -> Mapping[str, Any]:
        if source is None:
            return {}
        value = source() if callable(source) else source
        if not isinstance(value, Mapping):
            raise TypeError("save metadata must resolve to a mapping")
        return value

    def submit(
        self,
        request_id: str,
        store: SaveSlotStore2,
        snapshot: SnapshotSource,
        *,
        metadata: MetadataSource = None,
        priority: int = 0,
    ) -> int:
        self._require_owner_thread()
        normalized_id = _identifier(request_id, label="request_id")
        if not isinstance(store, SaveSlotStore2):
            raise TypeError("store must be SaveSlotStore2")

        with self._lock:
            if self._closed:
                self._rejected_total += 1
                raise RuntimeError("background save pipeline is closed")
            self._release_terminal_slots_locked()
            if normalized_id in self._requests:
                self._rejected_total += 1
                raise ValueError(f"save request {normalized_id!r} already exists")
            unfinished = sum(
                request.state not in _TERMINAL_STATES
                for request in self._requests.values()
            )
            if unfinished >= self.max_requests:
                self._rejected_total += 1
                raise RuntimeError("background save max_requests budget reached")
            slot_key = self._slot_key(store)
            busy = self._active_slots.get(slot_key)
            if busy is not None:
                self._rejected_total += 1
                raise RuntimeError(f"save slot is busy with request {busy!r}")

        data = self._resolve_source(snapshot, label="save snapshot")
        resolved_metadata = self._resolve_metadata(metadata)
        prepared = PreparedSaveSnapshot.capture(normalized_id, data, resolved_metadata)

        with self._lock:
            # A creator callback above may have re-entered this pipeline, so validate again.
            self._release_terminal_slots_locked()
            if normalized_id in self._requests:
                self._rejected_total += 1
                raise ValueError(f"save request {normalized_id!r} already exists")
            if slot_key in self._active_slots:
                self._rejected_total += 1
                raise RuntimeError(
                    f"save slot is busy with request {self._active_slots[slot_key]!r}"
                )
            sequence = self._next_sequence
            self._next_sequence += 1
            job_id = f"background-save:{sequence}:{normalized_id}"
            record = _SaveRequest(
                request_id=normalized_id,
                sequence=sequence,
                store=store,
                slot_key=slot_key,
                snapshot=prepared,
                job_id=job_id,
            )
            self._requests[normalized_id] = record
            self._active_slots[slot_key] = normalized_id

            try:
                self._scheduler.submit(
                    job_id,
                    lambda context, current=normalized_id: self._worker(current, context),
                    priority=priority,
                )
            except Exception:
                del self._requests[normalized_id]
                self._active_slots.pop(slot_key, None)
                self._rejected_total += 1
                raise

            self._submitted_total += 1
            self._snapshot_bytes_total += prepared.byte_size
            return sequence

    def submit_profile(
        self,
        request_id: str,
        manager: ProfileSaveManager2,
        slot: str,
        snapshot: SnapshotSource,
        *,
        metadata: MetadataSource = None,
        priority: int = 0,
    ) -> int:
        self._require_owner_thread()
        if not isinstance(manager, ProfileSaveManager2):
            raise TypeError("manager must be ProfileSaveManager2")
        return self.submit(
            request_id,
            manager.slot(slot),
            snapshot,
            metadata=metadata,
            priority=priority,
        )

    def _worker(self, request_id: str, context: JobContext) -> BackgroundSaveReceipt:
        with self._lock:
            request = self._requests[request_id]
            if request.cancel_requested:
                context.raise_if_cancelled()
            request.state = BackgroundSaveState.WRITING
            prepared = request.snapshot
            store = request.store

        data, metadata = prepared.decode()
        context.raise_if_cancelled()

        # The lock defines the cancellation cutoff. Once COMMITTING is visible, cancel()
        # refuses to set the scheduler token, preventing "cancelled" from being reported after
        # stable Save/Profile 2.0 has already promoted a new primary.
        with self._lock:
            request = self._requests[request_id]
            if request.cancel_requested or context.cancelled:
                context.raise_if_cancelled()
            request.state = BackgroundSaveState.COMMITTING

        info = store.save(data, metadata=metadata)
        loaded = store.load()
        self._verify_write(info, loaded, data, metadata)

        receipt = BackgroundSaveReceipt(
            request_id=request_id,
            path=info.path,
            revision=info.revision or loaded.revision,
            snapshot_fingerprint=prepared.fingerprint,
            recovery_available=info.recovery_available,
            snapshot_bytes=prepared.byte_size,
        )
        with self._lock:
            request = self._requests[request_id]
            request.receipt = receipt
            self._verified_writes_total += 1
        return receipt

    @staticmethod
    def _verify_write(
        info: SaveSlotInfo,
        loaded: SaveLoadResult,
        data: Mapping[str, JSONValue],
        metadata: Mapping[str, JSONValue],
    ) -> None:
        if loaded.source != "primary":
            raise RuntimeError("background save verification did not load the committed primary")
        if info.revision is None or loaded.revision != info.revision:
            raise RuntimeError("background save verification revision mismatch")
        if loaded.metadata != dict(metadata):
            raise RuntimeError("background save verification metadata mismatch")
        for key, expected in data.items():
            if key not in loaded.data or loaded.data[key] != expected:
                raise RuntimeError(f"background save verification mismatch for key {key!r}")

    def cancel(self, request_id: str) -> bool:
        normalized_id = _identifier(request_id, label="request_id")
        with self._lock:
            request = self._requests[normalized_id]
            if request.state in _TERMINAL_STATES:
                return False
            self._cancellation_requests_total += 1
            if request.state is BackgroundSaveState.COMMITTING:
                self._cancellation_refused_total += 1
                return False
            request.cancel_requested = True
            return self._scheduler.cancel(request.job_id)

    def state(self, request_id: str) -> BackgroundSaveState:
        normalized_id = _identifier(request_id, label="request_id")
        with self._lock:
            request = self._requests[normalized_id]
            self._synchronize_request_locked(request)
            return request.state

    def outcome(self, request_id: str) -> BackgroundSaveOutcome:
        normalized_id = _identifier(request_id, label="request_id")
        with self._lock:
            request = self._requests[normalized_id]
            self._synchronize_request_locked(request)
            if request.state not in _TERMINAL_STATES:
                raise RuntimeError(f"save request {normalized_id!r} is not complete")
            return self._outcome_locked(request)

    def poll(self, max_items: int | None = None) -> tuple[BackgroundSaveOutcome, ...]:
        self._require_owner_thread()
        outcomes = self._scheduler.drain_completed(max_items=max_items)
        translated: list[BackgroundSaveOutcome] = []
        with self._lock:
            for job_outcome in outcomes:
                request = next(
                    request
                    for request in self._requests.values()
                    if request.job_id == job_outcome.job_id
                )
                self._apply_job_outcome_locked(
                    request,
                    job_outcome.state,
                    job_outcome.error_type,
                    job_outcome.error_message,
                )
                request.delivered = True
                self._active_slots.pop(request.slot_key, None)
                translated.append(self._outcome_locked(request))
        translated.sort(key=lambda outcome: outcome.sequence)
        return tuple(translated)

    def run_until_idle(
        self,
        *,
        timeout: float | None = None,
        max_items_per_poll: int = 64,
    ) -> tuple[BackgroundSaveOutcome, ...]:
        self._require_owner_thread()
        max_items_per_poll = _positive_int(
            max_items_per_poll, label="max_items_per_poll"
        )
        deadline = None if timeout is None else time.monotonic() + float(timeout)
        collected: list[BackgroundSaveOutcome] = []
        while True:
            collected.extend(self.poll(max_items=max_items_per_poll))
            if self.diagnostics().unfinished == 0:
                collected.extend(self.poll(max_items=max_items_per_poll))
                break
            if deadline is not None and time.monotonic() >= deadline:
                raise TimeoutError("background saves did not finish before timeout")
            time.sleep(0.001)
        collected.sort(key=lambda outcome: outcome.sequence)
        return tuple(collected)

    def forget(self, request_id: str) -> None:
        self._require_owner_thread()
        normalized_id = _identifier(request_id, label="request_id")
        with self._lock:
            request = self._requests[normalized_id]
            self._synchronize_request_locked(request)
            if request.state not in _TERMINAL_STATES:
                raise RuntimeError("cannot forget an unfinished background save")
            if not request.delivered:
                raise RuntimeError("poll the terminal save outcome before forgetting it")
            self._scheduler.forget(request.job_id)
            self._active_slots.pop(request.slot_key, None)
            del self._requests[normalized_id]

    def diagnostics(self) -> BackgroundSaveDiagnostics:
        with self._lock:
            for request in self._requests.values():
                self._synchronize_request_locked(request)
            counts = {state: 0 for state in BackgroundSaveState}
            for request in self._requests.values():
                counts[request.state] += 1
            self._release_terminal_slots_locked()
            return BackgroundSaveDiagnostics(
                max_requests=self.max_requests,
                queued=counts[BackgroundSaveState.QUEUED],
                writing=counts[BackgroundSaveState.WRITING],
                committing=counts[BackgroundSaveState.COMMITTING],
                succeeded=counts[BackgroundSaveState.SUCCEEDED],
                failed=counts[BackgroundSaveState.FAILED],
                cancelled=counts[BackgroundSaveState.CANCELLED],
                active_slots=len(self._active_slots),
                submitted_total=self._submitted_total,
                rejected_total=self._rejected_total,
                cancellation_requests_total=self._cancellation_requests_total,
                cancellation_refused_total=self._cancellation_refused_total,
                snapshot_bytes_total=self._snapshot_bytes_total,
                verified_writes_total=self._verified_writes_total,
            )

    def _synchronize_request_locked(self, request: _SaveRequest) -> None:
        if request.state in _TERMINAL_STATES:
            return
        job_state = self._scheduler.state(request.job_id)
        if job_state in {
            JobState.SUCCEEDED,
            JobState.FAILED,
            JobState.CANCELLED,
            JobState.BLOCKED,
        }:
            outcome = self._scheduler.outcome(request.job_id)
            self._apply_job_outcome_locked(
                request,
                outcome.state,
                outcome.error_type,
                outcome.error_message,
            )
            self._active_slots.pop(request.slot_key, None)

    @staticmethod
    def _apply_job_outcome_locked(
        request: _SaveRequest,
        job_state: JobState,
        error_type: str | None,
        error_message: str | None,
    ) -> None:
        if job_state is JobState.SUCCEEDED:
            request.state = BackgroundSaveState.SUCCEEDED
            return
        if job_state is JobState.CANCELLED:
            request.state = BackgroundSaveState.CANCELLED
        else:
            request.state = BackgroundSaveState.FAILED
        request.error_type = error_type
        request.error_message = error_message

    def _release_terminal_slots_locked(self) -> None:
        for request in self._requests.values():
            self._synchronize_request_locked(request)
            if request.state in _TERMINAL_STATES:
                self._active_slots.pop(request.slot_key, None)

    @staticmethod
    def _outcome_locked(request: _SaveRequest) -> BackgroundSaveOutcome:
        return BackgroundSaveOutcome(
            request_id=request.request_id,
            sequence=request.sequence,
            state=request.state,
            receipt=request.receipt,
            error_type=request.error_type,
            error_message=request.error_message,
        )

    def shutdown(self, *, wait: bool = True, cancel_pending: bool = False) -> None:
        self._require_owner_thread()
        if not isinstance(wait, bool) or not isinstance(cancel_pending, bool):
            raise TypeError("wait and cancel_pending must be bool values")
        with self._lock:
            if self._closed:
                return
            self._closed = True

        if cancel_pending:
            with self._lock:
                cancellable = [
                    request.request_id
                    for request in self._requests.values()
                    if request.state
                    in {BackgroundSaveState.QUEUED, BackgroundSaveState.WRITING}
                ]
            for request_id in cancellable:
                self.cancel(request_id)

        if wait:
            self._scheduler.wait_all()
            self.poll()
        self._scheduler.shutdown(wait=wait, cancel_pending=False)

    def __enter__(self) -> Self:
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        self.shutdown(wait=True, cancel_pending=exc is not None)
