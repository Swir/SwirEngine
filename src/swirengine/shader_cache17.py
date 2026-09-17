from __future__ import annotations

import hashlib
import json
import math
import threading
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from enum import Enum
from time import perf_counter_ns
from types import MappingProxyType
from typing import Any, TypeAlias

from .jobs17 import JobContext, JobScheduler, JobSchedulerError, JobState

JSONValue: TypeAlias = (
    None | bool | int | float | str | list["JSONValue"] | dict[str, "JSONValue"]
)


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
            raise ValueError("shader/material metadata floats must be finite")
        return 0.0 if value == 0.0 else value
    if isinstance(value, (list, tuple)):
        return [_portable(item) for item in value]
    if isinstance(value, Mapping):
        normalized: dict[str, JSONValue] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise TypeError("shader/material metadata mapping keys must be strings")
            normalized[key] = _portable(item)
        return normalized
    raise TypeError(f"unsupported shader/material metadata type: {type(value).__name__}")


def _canonical_mapping(value: Mapping[str, Any] | None, *, label: str) -> str:
    if value is None:
        value = {}
    if not isinstance(value, Mapping):
        raise TypeError(f"{label} must be a mapping or None")
    normalized = _portable(value)
    if not isinstance(normalized, dict):
        raise TypeError(f"{label} must be a mapping")
    return json.dumps(
        normalized,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    )


def _normalize_stages(
    stages: Mapping[str, str],
    *,
    max_source_bytes: int,
    expected_names: tuple[str, ...] | None = None,
) -> tuple[tuple[str, str], ...]:
    if not isinstance(stages, Mapping):
        raise TypeError("stages must be a mapping of stage names to source strings")
    if not stages:
        raise ValueError("at least one shader stage is required")

    normalized: dict[str, str] = {}
    total_bytes = 0
    for raw_name, source in stages.items():
        if not isinstance(raw_name, str):
            raise TypeError("shader stage names must be strings")
        name = raw_name.strip().lower()
        if not name or len(name) > 32:
            raise ValueError("shader stage names must contain 1 to 32 characters")
        if name in normalized:
            raise ValueError(f"shader stage {name!r} is repeated after normalization")
        if not isinstance(source, str):
            raise TypeError(f"shader stage {name!r} source must be a string")
        if not source.strip():
            raise ValueError(f"shader stage {name!r} source must not be empty")
        total_bytes += len(source.encode("utf-8"))
        if total_bytes > max_source_bytes:
            raise ValueError("combined shader source exceeds max_source_bytes")
        normalized[name] = source

    names = tuple(sorted(normalized))
    if expected_names is not None and names != expected_names:
        raise ValueError("preprocessor must preserve the submitted shader stage set")
    return tuple((name, normalized[name]) for name in names)


def _fingerprint_payload(
    stages: tuple[tuple[str, str], ...],
    defines_json: str,
    material_json: str,
) -> str:
    canonical = json.dumps(
        {
            "defines": json.loads(defines_json),
            "material": json.loads(material_json),
            "stages": {name: source for name, source in stages},
        },
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _validate_fingerprint(value: str) -> str:
    if not isinstance(value, str):
        raise TypeError("fingerprint must be a string")
    normalized = value.strip().lower()
    if len(normalized) != 64 or any(char not in "0123456789abcdef" for char in normalized):
        raise ValueError("fingerprint must be a 64-character lowercase SHA-256 hex digest")
    return normalized


@dataclass(frozen=True, slots=True)
class ShaderMaterialSource:
    """Canonical immutable source description used as the preparation cache key."""

    stages: tuple[tuple[str, str], ...]
    defines_json: str
    material_json: str
    fingerprint: str
    source_bytes: int

    @classmethod
    def capture(
        cls,
        stages: Mapping[str, str],
        *,
        defines: Mapping[str, Any] | None = None,
        material: Mapping[str, Any] | None = None,
        max_source_bytes: int = 4 * 1024 * 1024,
    ) -> ShaderMaterialSource:
        limit = _positive_int(max_source_bytes, label="max_source_bytes")
        normalized_stages = _normalize_stages(stages, max_source_bytes=limit)
        defines_json = _canonical_mapping(defines, label="defines")
        material_json = _canonical_mapping(material, label="material")
        return cls(
            stages=normalized_stages,
            defines_json=defines_json,
            material_json=material_json,
            fingerprint=_fingerprint_payload(
                normalized_stages,
                defines_json,
                material_json,
            ),
            source_bytes=sum(len(source.encode("utf-8")) for _, source in normalized_stages),
        )

    @property
    def stage_names(self) -> tuple[str, ...]:
        return tuple(name for name, _ in self.stages)

    def stage_mapping(self) -> Mapping[str, str]:
        return MappingProxyType(dict(self.stages))

    def defines(self) -> Mapping[str, JSONValue]:
        return MappingProxyType(json.loads(self.defines_json))

    def material(self) -> Mapping[str, JSONValue]:
        return MappingProxyType(json.loads(self.material_json))


@dataclass(frozen=True, slots=True)
class PreparedShaderMaterial:
    """CPU-side prepared shader/material data safe to cache before GPU finalization."""

    source_fingerprint: str
    stages: tuple[tuple[str, str], ...]
    defines_json: str
    material_json: str

    def stage_mapping(self) -> Mapping[str, str]:
        return MappingProxyType(dict(self.stages))

    def defines(self) -> Mapping[str, JSONValue]:
        return MappingProxyType(json.loads(self.defines_json))

    def material(self) -> Mapping[str, JSONValue]:
        return MappingProxyType(json.loads(self.material_json))


@dataclass(frozen=True, slots=True)
class ShaderPreparationContext:
    job: JobContext
    request_id: int
    source: ShaderMaterialSource

    @property
    def cancelled(self) -> bool:
        return self.job.cancelled

    def raise_if_cancelled(self) -> None:
        self.job.raise_if_cancelled()


ShaderPreprocessor: TypeAlias = Callable[
    [ShaderMaterialSource, ShaderPreparationContext], Mapping[str, str]
]
ShaderFinalizer: TypeAlias = Callable[[PreparedShaderMaterial], Any]


class ShaderMaterialRequestState(str, Enum):
    QUEUED = "queued"
    PREPARING = "preparing"
    FINALIZING = "finalizing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    STALE = "stale"


_TERMINAL_STATES = {
    ShaderMaterialRequestState.COMPLETED,
    ShaderMaterialRequestState.FAILED,
    ShaderMaterialRequestState.CANCELLED,
    ShaderMaterialRequestState.STALE,
}


@dataclass(frozen=True, slots=True)
class ShaderMaterialRequest:
    request_id: int
    job_id: str
    fingerprint: str
    priority: int


@dataclass(frozen=True, slots=True)
class ShaderMaterialOutcome:
    request_id: int
    fingerprint: str
    state: ShaderMaterialRequestState
    value: Any = None
    cache_hit: bool = False
    worker_ns: int = 0
    error_type: str | None = None
    error_message: str | None = None

    @property
    def successful(self) -> bool:
        return self.state is ShaderMaterialRequestState.COMPLETED

    @property
    def worker_ms(self) -> float:
        return self.worker_ns / 1_000_000.0


@dataclass(frozen=True, slots=True)
class ShaderMaterialDiagnostics:
    max_workers: int
    max_pending: int
    max_requests: int
    max_cache_entries: int
    submitted_total: int
    completed_total: int
    failed_total: int
    cancelled_total: int
    stale_total: int
    cache_hits_total: int
    cache_misses_total: int
    cache_evictions_total: int
    preprocess_calls_total: int
    finalize_calls_total: int
    invalidations_total: int
    pending: int
    cached_entries: int

    def portable(self) -> Mapping[str, int]:
        return MappingProxyType(
            {
                "max_workers": self.max_workers,
                "max_pending": self.max_pending,
                "max_requests": self.max_requests,
                "max_cache_entries": self.max_cache_entries,
                "submitted_total": self.submitted_total,
                "completed_total": self.completed_total,
                "failed_total": self.failed_total,
                "cancelled_total": self.cancelled_total,
                "stale_total": self.stale_total,
                "cache_hits_total": self.cache_hits_total,
                "cache_misses_total": self.cache_misses_total,
                "cache_evictions_total": self.cache_evictions_total,
                "preprocess_calls_total": self.preprocess_calls_total,
                "finalize_calls_total": self.finalize_calls_total,
                "invalidations_total": self.invalidations_total,
                "pending": self.pending,
                "cached_entries": self.cached_entries,
            }
        )


@dataclass(frozen=True, slots=True)
class _WorkerProduct:
    prepared: PreparedShaderMaterial
    cache_hit: bool
    worker_ns: int


@dataclass(slots=True)
class _RequestRecord:
    request: ShaderMaterialRequest
    source: ShaderMaterialSource
    preprocess: ShaderPreprocessor | None
    finalize: ShaderFinalizer
    global_generation: int
    fingerprint_generation: int
    state: ShaderMaterialRequestState = ShaderMaterialRequestState.QUEUED
    result: ShaderMaterialOutcome | None = None


class ShaderMaterialPreparationCache:
    """Background shader preprocessing with explicit owning-thread finalization.

    Only canonical CPU-side prepared data is cached. Creator-provided ``finalize`` callbacks
    are executed exclusively by :meth:`poll` on the thread that created this object, making
    the GPU/material compilation boundary explicit without changing stable 1.x material APIs.
    """

    def __init__(
        self,
        *,
        max_workers: int = 2,
        max_pending: int = 128,
        max_requests: int = 256,
        max_cache_entries: int = 256,
        max_source_bytes: int = 4 * 1024 * 1024,
    ) -> None:
        self.max_requests = _positive_int(max_requests, label="max_requests")
        self.max_cache_entries = _positive_int(
            max_cache_entries,
            label="max_cache_entries",
        )
        self.max_source_bytes = _positive_int(max_source_bytes, label="max_source_bytes")
        self._scheduler = JobScheduler(
            max_workers=_positive_int(max_workers, label="max_workers"),
            max_pending=_positive_int(max_pending, label="max_pending"),
            thread_name_prefix="swir-shader17",
        )
        self._owner_thread = threading.get_ident()
        self._lock = threading.RLock()
        self._records: dict[int, _RequestRecord] = {}
        self._job_to_request: dict[str, int] = {}
        self._cache: dict[str, PreparedShaderMaterial] = {}
        self._cancel_after_worker: set[int] = set()
        self._fingerprint_generations: dict[str, int] = {}
        self._global_generation = 0
        self._next_request_id = 1
        self._closed = False
        self._submitted_total = 0
        self._completed_total = 0
        self._failed_total = 0
        self._cancelled_total = 0
        self._stale_total = 0
        self._cache_hits_total = 0
        self._cache_misses_total = 0
        self._cache_evictions_total = 0
        self._preprocess_calls_total = 0
        self._finalize_calls_total = 0
        self._invalidations_total = 0

    def _require_owner_thread(self) -> None:
        if threading.get_ident() != self._owner_thread:
            raise RuntimeError("shader/material owning-thread operation called from another thread")

    def _ensure_open(self) -> None:
        if self._closed:
            raise RuntimeError("shader/material preparation cache is shut down")

    def submit(
        self,
        stages: Mapping[str, str],
        *,
        finalize: ShaderFinalizer,
        defines: Mapping[str, Any] | None = None,
        material: Mapping[str, Any] | None = None,
        preprocess: ShaderPreprocessor | None = None,
        priority: int = 0,
    ) -> ShaderMaterialRequest:
        """Capture one source description and queue background-safe preparation."""
        self._require_owner_thread()
        self._ensure_open()
        if not callable(finalize):
            raise TypeError("finalize must be callable")
        if preprocess is not None and not callable(preprocess):
            raise TypeError("preprocess must be callable or None")
        source = ShaderMaterialSource.capture(
            stages,
            defines=defines,
            material=material,
            max_source_bytes=self.max_source_bytes,
        )

        with self._lock:
            if sum(record.result is None for record in self._records.values()) >= self.max_requests:
                raise RuntimeError("shader/material max_requests budget reached")
            request_id = self._next_request_id
            self._next_request_id += 1
            job_id = f"shader17:{request_id}"
            request = ShaderMaterialRequest(
                request_id=request_id,
                job_id=job_id,
                fingerprint=source.fingerprint,
                priority=priority,
            )
            record = _RequestRecord(
                request=request,
                source=source,
                preprocess=preprocess,
                finalize=finalize,
                global_generation=self._global_generation,
                fingerprint_generation=self._fingerprint_generations.get(source.fingerprint, 0),
            )
            self._records[request_id] = record
            self._job_to_request[job_id] = request_id

        try:
            self._scheduler.submit(
                job_id,
                lambda context, current=request_id: self._run_worker(current, context),
                priority=priority,
            )
        except Exception:
            with self._lock:
                self._records.pop(request_id, None)
                self._job_to_request.pop(job_id, None)
                self._next_request_id = request_id
            raise

        with self._lock:
            self._submitted_total += 1
        return request

    def _record_is_current_locked(self, record: _RequestRecord) -> bool:
        return (
            record.global_generation == self._global_generation
            and record.fingerprint_generation
            == self._fingerprint_generations.get(record.source.fingerprint, 0)
        )

    def _run_worker(self, request_id: int, job: JobContext) -> _WorkerProduct:
        started = perf_counter_ns()
        with self._lock:
            record = self._records[request_id]
            record.state = ShaderMaterialRequestState.PREPARING
            source = record.source
            preprocess = record.preprocess
            cached = self._cache.get(source.fingerprint)
            generation_current = self._record_is_current_locked(record)

        job.raise_if_cancelled()
        if cached is not None and generation_current:
            with self._lock:
                self._cache_hits_total += 1
            return _WorkerProduct(
                prepared=cached,
                cache_hit=True,
                worker_ns=perf_counter_ns() - started,
            )

        with self._lock:
            self._cache_misses_total += 1
            self._preprocess_calls_total += 1
        context = ShaderPreparationContext(job=job, request_id=request_id, source=source)
        if preprocess is None:
            prepared_stages = source.stage_mapping()
        else:
            prepared_stages = preprocess(source, context)
        context.raise_if_cancelled()
        normalized_stages = _normalize_stages(
            prepared_stages,
            max_source_bytes=self.max_source_bytes,
            expected_names=source.stage_names,
        )
        prepared = PreparedShaderMaterial(
            source_fingerprint=source.fingerprint,
            stages=normalized_stages,
            defines_json=source.defines_json,
            material_json=source.material_json,
        )
        return _WorkerProduct(
            prepared=prepared,
            cache_hit=False,
            worker_ns=perf_counter_ns() - started,
        )

    def poll(self, *, max_items: int = 32) -> tuple[ShaderMaterialOutcome, ...]:
        """Finalize at most ``max_items`` prepared products on the owning thread."""
        self._require_owner_thread()
        if isinstance(max_items, bool) or not isinstance(max_items, int) or max_items <= 0:
            raise ValueError("max_items must be a positive integer")
        outcomes = self._scheduler.drain_completed(max_items=max_items)
        results: list[ShaderMaterialOutcome] = []
        for outcome in outcomes:
            request_id = self._job_to_request[outcome.job_id]
            results.append(
                self._finish_outcome(
                    request_id,
                    outcome.state,
                    outcome.value,
                    outcome.error_type,
                    outcome.error_message,
                )
            )
        return tuple(results)

    def _finish_outcome(
        self,
        request_id: int,
        state: JobState,
        value: Any,
        error_type: str | None,
        error_message: str | None,
    ) -> ShaderMaterialOutcome:
        with self._lock:
            record = self._records[request_id]
            if record.result is not None:
                return record.result
            request = record.request
            generation_current = self._record_is_current_locked(record)

        if request_id in self._cancel_after_worker or state is JobState.CANCELLED:
            return self._commit_result(
                record,
                ShaderMaterialOutcome(
                    request_id=request_id,
                    fingerprint=request.fingerprint,
                    state=ShaderMaterialRequestState.CANCELLED,
                    error_type="JobCancelled",
                    error_message="shader/material request cancellation requested",
                ),
            )

        if state is not JobState.SUCCEEDED or not isinstance(value, _WorkerProduct):
            return self._commit_result(
                record,
                ShaderMaterialOutcome(
                    request_id=request_id,
                    fingerprint=request.fingerprint,
                    state=ShaderMaterialRequestState.FAILED,
                    error_type=error_type or "ShaderPreparationError",
                    error_message=error_message or "shader preparation did not produce a valid product",
                ),
            )

        if not generation_current:
            return self._commit_result(
                record,
                ShaderMaterialOutcome(
                    request_id=request_id,
                    fingerprint=request.fingerprint,
                    state=ShaderMaterialRequestState.STALE,
                    cache_hit=value.cache_hit,
                    worker_ns=value.worker_ns,
                    error_type="ShaderPreparationInvalidated",
                    error_message="shader/material source was invalidated before finalization",
                ),
            )

        prepared = value.prepared
        if prepared.source_fingerprint != request.fingerprint:
            return self._commit_result(
                record,
                ShaderMaterialOutcome(
                    request_id=request_id,
                    fingerprint=request.fingerprint,
                    state=ShaderMaterialRequestState.FAILED,
                    cache_hit=value.cache_hit,
                    worker_ns=value.worker_ns,
                    error_type="ShaderFingerprintMismatch",
                    error_message="prepared artifact fingerprint does not match its request",
                ),
            )

        if not value.cache_hit:
            self._store_prepared(prepared)

        with self._lock:
            record.state = ShaderMaterialRequestState.FINALIZING
            self._finalize_calls_total += 1
        try:
            final_value = record.finalize(prepared)
        except Exception as exc:  # noqa: BLE001 - creator finalizers may raise arbitrary errors.
            return self._commit_result(
                record,
                ShaderMaterialOutcome(
                    request_id=request_id,
                    fingerprint=request.fingerprint,
                    state=ShaderMaterialRequestState.FAILED,
                    cache_hit=value.cache_hit,
                    worker_ns=value.worker_ns,
                    error_type=type(exc).__name__,
                    error_message=str(exc),
                ),
            )

        return self._commit_result(
            record,
            ShaderMaterialOutcome(
                request_id=request_id,
                fingerprint=request.fingerprint,
                state=ShaderMaterialRequestState.COMPLETED,
                value=final_value,
                cache_hit=value.cache_hit,
                worker_ns=value.worker_ns,
            ),
        )

    def _store_prepared(self, prepared: PreparedShaderMaterial) -> None:
        with self._lock:
            fingerprint = prepared.source_fingerprint
            if fingerprint in self._cache:
                self._cache[fingerprint] = prepared
                return
            while len(self._cache) >= self.max_cache_entries:
                oldest = next(iter(self._cache))
                del self._cache[oldest]
                self._cache_evictions_total += 1
            self._cache[fingerprint] = prepared

    def _commit_result(
        self,
        record: _RequestRecord,
        result: ShaderMaterialOutcome,
    ) -> ShaderMaterialOutcome:
        with self._lock:
            record.result = result
            record.state = result.state
            self._cancel_after_worker.discard(result.request_id)
            if result.state is ShaderMaterialRequestState.COMPLETED:
                self._completed_total += 1
            elif result.state is ShaderMaterialRequestState.CANCELLED:
                self._cancelled_total += 1
            elif result.state is ShaderMaterialRequestState.STALE:
                self._stale_total += 1
            else:
                self._failed_total += 1
            return result

    def cancel(self, request_id: int) -> bool:
        record = self._record(request_id)
        with self._lock:
            if record.result is not None:
                return False
            self._cancel_after_worker.add(request_id)
        cancelled = self._scheduler.cancel(record.request.job_id)
        if not cancelled and self._scheduler.state(record.request.job_id) is not JobState.SUCCEEDED:
            with self._lock:
                self._cancel_after_worker.discard(request_id)
            return False
        return True

    def invalidate(self, fingerprint: str | None = None) -> int:
        """Invalidate one fingerprint or the entire cache and any matching in-flight work."""
        self._require_owner_thread()
        with self._lock:
            self._invalidations_total += 1
            if fingerprint is None:
                removed = len(self._cache)
                self._cache.clear()
                self._global_generation += 1
                return removed
            normalized = _validate_fingerprint(fingerprint)
            removed = int(self._cache.pop(normalized, None) is not None)
            self._fingerprint_generations[normalized] = (
                self._fingerprint_generations.get(normalized, 0) + 1
            )
            return removed

    def invalidate_source(
        self,
        stages: Mapping[str, str],
        *,
        defines: Mapping[str, Any] | None = None,
        material: Mapping[str, Any] | None = None,
    ) -> int:
        source = ShaderMaterialSource.capture(
            stages,
            defines=defines,
            material=material,
            max_source_bytes=self.max_source_bytes,
        )
        return self.invalidate(source.fingerprint)

    def clear_cache(self) -> int:
        return self.invalidate()

    def state(self, request_id: int) -> ShaderMaterialRequestState:
        return self._record(request_id).state

    def result(self, request_id: int) -> ShaderMaterialOutcome:
        record = self._record(request_id)
        if record.result is None:
            raise JobSchedulerError(f"shader/material request {request_id} is not finalized")
        return record.result

    def request(self, request_id: int) -> ShaderMaterialRequest:
        return self._record(request_id).request

    def _record(self, request_id: int) -> _RequestRecord:
        if isinstance(request_id, bool) or not isinstance(request_id, int) or request_id <= 0:
            raise ValueError("request_id must be a positive integer")
        with self._lock:
            try:
                return self._records[request_id]
            except KeyError:
                raise KeyError(request_id) from None

    def pending_request_ids(self) -> tuple[int, ...]:
        with self._lock:
            return tuple(
                request_id
                for request_id, record in sorted(self._records.items())
                if record.result is None
            )

    def forget(self, request_id: int) -> None:
        self._require_owner_thread()
        record = self._record(request_id)
        if record.result is None:
            raise JobSchedulerError("cannot forget an unfinished shader/material request")
        self._scheduler.forget(record.request.job_id)
        with self._lock:
            self._records.pop(request_id, None)
            self._job_to_request.pop(record.request.job_id, None)
            self._cancel_after_worker.discard(request_id)

    def diagnostics(self) -> ShaderMaterialDiagnostics:
        with self._lock:
            return ShaderMaterialDiagnostics(
                max_workers=self._scheduler.max_workers,
                max_pending=self._scheduler.max_pending,
                max_requests=self.max_requests,
                max_cache_entries=self.max_cache_entries,
                submitted_total=self._submitted_total,
                completed_total=self._completed_total,
                failed_total=self._failed_total,
                cancelled_total=self._cancelled_total,
                stale_total=self._stale_total,
                cache_hits_total=self._cache_hits_total,
                cache_misses_total=self._cache_misses_total,
                cache_evictions_total=self._cache_evictions_total,
                preprocess_calls_total=self._preprocess_calls_total,
                finalize_calls_total=self._finalize_calls_total,
                invalidations_total=self._invalidations_total,
                pending=sum(record.result is None for record in self._records.values()),
                cached_entries=len(self._cache),
            )

    def wait_workers(self, timeout: float | None = None) -> None:
        """Wait for workers only; creator finalizers still require explicit owner-thread poll."""
        self._scheduler.wait_all(timeout=timeout)

    def shutdown(self, *, wait: bool = True, cancel_pending: bool = True) -> None:
        if self._closed:
            return
        self._closed = True
        self._scheduler.shutdown(wait=wait, cancel_pending=cancel_pending)


__all__ = [
    "PreparedShaderMaterial",
    "ShaderFinalizer",
    "ShaderMaterialDiagnostics",
    "ShaderMaterialOutcome",
    "ShaderMaterialPreparationCache",
    "ShaderMaterialRequest",
    "ShaderMaterialRequestState",
    "ShaderMaterialSource",
    "ShaderPreparationContext",
    "ShaderPreprocessor",
]
