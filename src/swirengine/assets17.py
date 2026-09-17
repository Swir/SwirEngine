from __future__ import annotations

import threading
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from time import perf_counter_ns
from typing import Any

from .asset_pipeline import AssetFingerprint
from .assets import AssetManager
from .jobs17 import JobContext, JobScheduler, JobSchedulerError, JobState


class AsyncAssetState(str, Enum):
    """Terminal states exposed by the additive SwirEngine 1.7 asset pipeline."""

    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    STALE = "stale"


@dataclass(frozen=True, slots=True)
class AssetBuildContext:
    """Background-only context passed to decode/cook callbacks."""

    job: JobContext
    request_id: int
    dependency_values: Mapping[int, Any]
    file_dependencies: tuple[Path, ...]

    @property
    def cancelled(self) -> bool:
        return self.job.cancelled

    def raise_if_cancelled(self) -> None:
        self.job.raise_if_cancelled()


AssetDecode = Callable[[Path, AssetBuildContext], Any]
AssetCook = Callable[[Any, AssetBuildContext], Any]
AssetDependencyResolver = Callable[[Path], Iterable[str | Path]]
AssetFinalizer = Callable[[Any], Any]


@dataclass(frozen=True, slots=True)
class AsyncAssetRequest:
    request_id: int
    job_id: str
    processor: str
    source: Path
    priority: int
    depends_on: tuple[int, ...]


@dataclass(frozen=True, slots=True)
class AsyncAssetResult:
    request_id: int
    processor: str
    source: Path
    state: AsyncAssetState
    value: Any = None
    cache_hit: bool = False
    worker_ns: int = 0
    error_type: str | None = None
    error_message: str | None = None

    @property
    def successful(self) -> bool:
        return self.state is AsyncAssetState.COMPLETED

    @property
    def worker_ms(self) -> float:
        return self.worker_ns / 1_000_000.0


@dataclass(frozen=True, slots=True)
class AsyncAssetDiagnostics:
    max_workers: int
    max_pending: int
    submitted_total: int
    completed_total: int
    failed_total: int
    cancelled_total: int
    stale_total: int
    cache_hits_total: int
    cache_misses_total: int
    finalize_calls_total: int
    pending: int
    cached_entries: int

    def portable(self) -> Mapping[str, int]:
        return {
            "max_workers": self.max_workers,
            "max_pending": self.max_pending,
            "submitted_total": self.submitted_total,
            "completed_total": self.completed_total,
            "failed_total": self.failed_total,
            "cancelled_total": self.cancelled_total,
            "stale_total": self.stale_total,
            "cache_hits_total": self.cache_hits_total,
            "cache_misses_total": self.cache_misses_total,
            "finalize_calls_total": self.finalize_calls_total,
            "pending": self.pending,
            "cached_entries": self.cached_entries,
        }


@dataclass(frozen=True, slots=True)
class _Processor:
    name: str
    suffixes: tuple[str, ...]
    decode: AssetDecode
    cook: AssetCook | None
    dependencies: AssetDependencyResolver | None
    finalizer: AssetFinalizer | None


@dataclass(frozen=True, slots=True)
class _CacheEntry:
    source_fingerprint: AssetFingerprint
    dependency_fingerprints: tuple[AssetFingerprint, ...]
    value: Any


@dataclass(frozen=True, slots=True)
class _WorkerProduct:
    value: Any
    source_fingerprint: AssetFingerprint
    dependency_fingerprints: tuple[AssetFingerprint, ...]
    cache_hit: bool
    stale: bool
    worker_ns: int


@dataclass(slots=True)
class _RequestRecord:
    request: AsyncAssetRequest
    processor: _Processor
    result: AsyncAssetResult | None = None


class AsyncAssetPipeline:
    """Bounded decode/cook jobs with explicit owning-thread finalization.

    File reads, hashing, dependency discovery, decoding and cooking run through the 1.7
    :class:`~swirengine.jobs17.JobScheduler`. GPU/audio/resource finalizers never execute on a
    worker: callers explicitly run them by calling :meth:`poll` from the owning thread.

    The class is additive and deliberately does not replace the stable ``AssetManager`` or
    ``AssetPipeline`` APIs.
    """

    def __init__(
        self,
        assets: AssetManager,
        *,
        max_workers: int = 4,
        max_pending: int = 256,
    ) -> None:
        if not isinstance(assets, AssetManager):
            raise TypeError("assets must be an AssetManager")
        self.assets = assets
        self._scheduler = JobScheduler(
            max_workers=max_workers,
            max_pending=max_pending,
            thread_name_prefix="swir-assets17",
        )
        self._processors: dict[str, _Processor] = {}
        self._processor_by_suffix: dict[str, str] = {}
        self._records: dict[int, _RequestRecord] = {}
        self._job_to_request: dict[str, int] = {}
        self._cache: dict[tuple[str, Path], _CacheEntry] = {}
        self._cancel_after_worker: set[int] = set()
        self._next_request_id = 1
        self._closed = False
        self._lock = threading.RLock()
        self._submitted_total = 0
        self._completed_total = 0
        self._failed_total = 0
        self._cancelled_total = 0
        self._stale_total = 0
        self._cache_hits_total = 0
        self._cache_misses_total = 0
        self._finalize_calls_total = 0

    @staticmethod
    def _normalize_suffix(suffix: str) -> str:
        normalized = str(suffix).strip().lower()
        if normalized and not normalized.startswith("."):
            normalized = "." + normalized
        return normalized

    def register_processor(
        self,
        name: str,
        *,
        suffixes: Iterable[str],
        decode: AssetDecode,
        cook: AssetCook | None = None,
        dependencies: AssetDependencyResolver | None = None,
        finalizer: AssetFinalizer | None = None,
    ) -> None:
        self._ensure_open()
        key = str(name).strip()
        if not key or len(key) > 64:
            raise ValueError("processor name must contain 1 to 64 non-whitespace characters")
        if not callable(decode):
            raise TypeError("decode must be callable")
        if cook is not None and not callable(cook):
            raise TypeError("cook must be callable or None")
        if dependencies is not None and not callable(dependencies):
            raise TypeError("dependencies must be callable or None")
        if finalizer is not None and not callable(finalizer):
            raise TypeError("finalizer must be callable or None")

        normalized = tuple(
            sorted(
                {
                    current
                    for item in suffixes
                    if (current := self._normalize_suffix(item))
                }
            )
        )
        if not normalized:
            raise ValueError("processor must register at least one non-empty suffix")

        with self._lock:
            if key in self._processors:
                raise ValueError(f"processor {key!r} is already registered")
            collisions = [suffix for suffix in normalized if suffix in self._processor_by_suffix]
            if collisions:
                raise ValueError(f"suffixes already registered: {', '.join(collisions)}")
            processor = _Processor(
                name=key,
                suffixes=normalized,
                decode=decode,
                cook=cook,
                dependencies=dependencies,
                finalizer=finalizer,
            )
            self._processors[key] = processor
            for suffix in normalized:
                self._processor_by_suffix[suffix] = key

    def submit(
        self,
        asset: str | Path,
        *,
        processor: str | None = None,
        priority: int = 0,
        depends_on: Iterable[int] = (),
    ) -> AsyncAssetRequest:
        """Queue one asset build without waiting for file/decode/cook work."""
        self._ensure_open()
        source = self.assets.require(asset).expanduser().resolve()
        selected = self._select_processor(source, processor)
        dependency_ids = self._normalize_request_dependencies(depends_on)

        with self._lock:
            request_id = self._next_request_id
            self._next_request_id += 1
            job_id = f"asset17:{request_id}"
            scheduler_dependencies = [self._records[item].request.job_id for item in dependency_ids]
            request = AsyncAssetRequest(
                request_id=request_id,
                job_id=job_id,
                processor=selected.name,
                source=source,
                priority=priority,
                depends_on=dependency_ids,
            )
            record = _RequestRecord(request=request, processor=selected)
            self._records[request_id] = record
            self._job_to_request[job_id] = request_id

        try:
            self._scheduler.submit(
                job_id,
                lambda context, current=request_id: self._run_worker(current, context),
                priority=priority,
                dependencies=scheduler_dependencies,
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

    def _select_processor(self, source: Path, processor: str | None) -> _Processor:
        with self._lock:
            if processor is None:
                key = self._processor_by_suffix.get(source.suffix.lower())
                if key is None:
                    raise ValueError(
                        f"no async asset processor registered for suffix {source.suffix.lower()!r}"
                    )
            else:
                key = str(processor).strip()
                if key not in self._processors:
                    raise KeyError(key)
            return self._processors[key]

    def _normalize_request_dependencies(self, values: Iterable[int]) -> tuple[int, ...]:
        if isinstance(values, (str, bytes)):
            raise TypeError("depends_on must be an iterable of request ids")
        normalized: list[int] = []
        seen: set[int] = set()
        for value in values:
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise ValueError("dependency request ids must be positive integers")
            if value in seen:
                raise ValueError(f"dependency request id {value} is repeated")
            if value not in self._records:
                raise KeyError(value)
            seen.add(value)
            normalized.append(value)
        return tuple(normalized)

    def _run_worker(self, request_id: int, job: JobContext) -> _WorkerProduct:
        started = perf_counter_ns()
        with self._lock:
            record = self._records[request_id]
            request = record.request
            processor = record.processor
            cache_entry = self._cache.get((processor.name, request.source))

        job.raise_if_cancelled()
        dependency_paths = self._resolve_file_dependencies(processor, request.source)
        source_fingerprint = AssetFingerprint.capture(request.source)
        dependency_fingerprints = tuple(AssetFingerprint.capture(path) for path in dependency_paths)
        job.raise_if_cancelled()

        if cache_entry is not None and self._cache_matches(
            cache_entry,
            source_fingerprint,
            dependency_fingerprints,
        ):
            return _WorkerProduct(
                value=cache_entry.value,
                source_fingerprint=source_fingerprint,
                dependency_fingerprints=dependency_fingerprints,
                cache_hit=True,
                stale=False,
                worker_ns=perf_counter_ns() - started,
            )

        dependency_values = self._dependency_values(request.depends_on)
        context = AssetBuildContext(
            job=job,
            request_id=request_id,
            dependency_values=dependency_values,
            file_dependencies=dependency_paths,
        )
        decoded = processor.decode(request.source, context)
        context.raise_if_cancelled()
        cooked = processor.cook(decoded, context) if processor.cook is not None else decoded
        context.raise_if_cancelled()

        final_source = AssetFingerprint.capture(request.source)
        final_dependencies = tuple(AssetFingerprint.capture(path) for path in dependency_paths)
        stale = (
            final_source != source_fingerprint
            or final_dependencies != dependency_fingerprints
        )
        return _WorkerProduct(
            value=cooked,
            source_fingerprint=source_fingerprint,
            dependency_fingerprints=dependency_fingerprints,
            cache_hit=False,
            stale=stale,
            worker_ns=perf_counter_ns() - started,
        )

    @staticmethod
    def _cache_matches(
        entry: _CacheEntry,
        source: AssetFingerprint,
        dependencies: tuple[AssetFingerprint, ...],
    ) -> bool:
        return entry.source_fingerprint == source and entry.dependency_fingerprints == dependencies

    def _resolve_file_dependencies(self, processor: _Processor, source: Path) -> tuple[Path, ...]:
        if processor.dependencies is None:
            return ()
        values = processor.dependencies(source)
        if isinstance(values, (str, bytes, Path)):
            raise TypeError("asset dependency resolver must return an iterable of paths")
        normalized = {Path(item).expanduser().resolve() for item in values}
        normalized.discard(source)
        return tuple(sorted(normalized, key=lambda item: item.as_posix().lower()))

    def _dependency_values(self, dependency_ids: tuple[int, ...]) -> Mapping[int, Any]:
        values: dict[int, Any] = {}
        for request_id in dependency_ids:
            with self._lock:
                job_id = self._records[request_id].request.job_id
            outcome = self._scheduler.outcome(job_id)
            if not outcome.successful or not isinstance(outcome.value, _WorkerProduct):
                raise JobSchedulerError(
                    f"dependency request {request_id} has no successful worker product"
                )
            values[request_id] = outcome.value.value
        return values

    def poll(self, *, max_items: int = 64) -> tuple[AsyncAssetResult, ...]:
        """Finalize at most ``max_items`` completed jobs on the calling/owning thread."""
        if isinstance(max_items, bool) or not isinstance(max_items, int) or max_items <= 0:
            raise ValueError("max_items must be a positive integer")
        outcomes = self._scheduler.drain_completed(max_items=max_items)
        results: list[AsyncAssetResult] = []
        for outcome in outcomes:
            request_id = self._job_to_request[outcome.job_id]
            result = self._finish_outcome(request_id, outcome.state, outcome.value, outcome.error_type, outcome.error_message)
            results.append(result)
        return tuple(results)

    def _finish_outcome(
        self,
        request_id: int,
        state: JobState,
        value: Any,
        error_type: str | None,
        error_message: str | None,
    ) -> AsyncAssetResult:
        with self._lock:
            record = self._records[request_id]
            if record.result is not None:
                return record.result
            request = record.request
            processor = record.processor

        if request_id in self._cancel_after_worker or state is JobState.CANCELLED:
            result = AsyncAssetResult(
                request_id=request_id,
                processor=request.processor,
                source=request.source,
                state=AsyncAssetState.CANCELLED,
                error_type="JobCancelled",
                error_message="asset request cancellation requested",
            )
            return self._commit_result(record, result)

        if state is not JobState.SUCCEEDED or not isinstance(value, _WorkerProduct):
            result = AsyncAssetResult(
                request_id=request_id,
                processor=request.processor,
                source=request.source,
                state=AsyncAssetState.FAILED,
                error_type=error_type or "AssetWorkerError",
                error_message=error_message or "asset worker did not produce a valid product",
            )
            return self._commit_result(record, result)

        if value.stale or not self._fingerprints_still_current(value):
            result = AsyncAssetResult(
                request_id=request_id,
                processor=request.processor,
                source=request.source,
                state=AsyncAssetState.STALE,
                cache_hit=value.cache_hit,
                worker_ns=value.worker_ns,
                error_type="AssetChangedDuringBuild",
                error_message="source or dependency changed before owning-thread finalization",
            )
            return self._commit_result(record, result)

        final_value = value.value
        if processor.finalizer is not None:
            try:
                with self._lock:
                    self._finalize_calls_total += 1
                final_value = processor.finalizer(value.value)
            except Exception as exc:  # noqa: BLE001 - creator finalizers can raise arbitrary errors.
                result = AsyncAssetResult(
                    request_id=request_id,
                    processor=request.processor,
                    source=request.source,
                    state=AsyncAssetState.FAILED,
                    cache_hit=value.cache_hit,
                    worker_ns=value.worker_ns,
                    error_type=type(exc).__name__,
                    error_message=str(exc),
                )
                return self._commit_result(record, result)

        if not value.cache_hit:
            with self._lock:
                self._cache[(processor.name, request.source)] = _CacheEntry(
                    source_fingerprint=value.source_fingerprint,
                    dependency_fingerprints=value.dependency_fingerprints,
                    value=value.value,
                )

        result = AsyncAssetResult(
            request_id=request_id,
            processor=request.processor,
            source=request.source,
            state=AsyncAssetState.COMPLETED,
            value=final_value,
            cache_hit=value.cache_hit,
            worker_ns=value.worker_ns,
        )
        return self._commit_result(record, result)

    @staticmethod
    def _fingerprint_path_still_current(fingerprint: AssetFingerprint) -> bool:
        path = fingerprint.path
        try:
            stat = path.stat()
        except FileNotFoundError:
            return not fingerprint.exists
        if not fingerprint.exists or not path.is_file():
            return False
        return stat.st_size == fingerprint.size_bytes and stat.st_mtime_ns == fingerprint.mtime_ns

    def _fingerprints_still_current(self, product: _WorkerProduct) -> bool:
        if not self._fingerprint_path_still_current(product.source_fingerprint):
            return False
        return all(
            self._fingerprint_path_still_current(fingerprint)
            for fingerprint in product.dependency_fingerprints
        )

    def _commit_result(
        self,
        record: _RequestRecord,
        result: AsyncAssetResult,
    ) -> AsyncAssetResult:
        with self._lock:
            record.result = result
            self._cancel_after_worker.discard(result.request_id)
            if result.state is AsyncAssetState.COMPLETED:
                self._completed_total += 1
                if result.cache_hit:
                    self._cache_hits_total += 1
                else:
                    self._cache_misses_total += 1
            elif result.state is AsyncAssetState.CANCELLED:
                self._cancelled_total += 1
            elif result.state is AsyncAssetState.STALE:
                self._stale_total += 1
                if result.cache_hit:
                    self._cache_hits_total += 1
                else:
                    self._cache_misses_total += 1
            else:
                self._failed_total += 1
            return result

    def cancel(self, request_id: int) -> bool:
        request = self._record(request_id).request
        with self._lock:
            if self._records[request_id].result is not None:
                return False
            self._cancel_after_worker.add(request_id)
        cancelled = self._scheduler.cancel(request.job_id)
        if not cancelled and self._scheduler.state(request.job_id) is not JobState.SUCCEEDED:
            with self._lock:
                self._cancel_after_worker.discard(request_id)
            return False
        return True

    def result(self, request_id: int) -> AsyncAssetResult:
        record = self._record(request_id)
        if record.result is None:
            raise JobSchedulerError(f"asset request {request_id} is not finalized")
        return record.result

    def request(self, request_id: int) -> AsyncAssetRequest:
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

    def invalidate(self, asset: str | Path, *, processor: str | None = None) -> int:
        source = self.assets.resolve(asset).expanduser().resolve()
        with self._lock:
            keys = [
                key
                for key in self._cache
                if key[1] == source and (processor is None or key[0] == processor)
            ]
            for key in keys:
                del self._cache[key]
            return len(keys)

    def clear_cache(self) -> int:
        with self._lock:
            count = len(self._cache)
            self._cache.clear()
            return count

    def diagnostics(self) -> AsyncAssetDiagnostics:
        with self._lock:
            return AsyncAssetDiagnostics(
                max_workers=self._scheduler.max_workers,
                max_pending=self._scheduler.max_pending,
                submitted_total=self._submitted_total,
                completed_total=self._completed_total,
                failed_total=self._failed_total,
                cancelled_total=self._cancelled_total,
                stale_total=self._stale_total,
                cache_hits_total=self._cache_hits_total,
                cache_misses_total=self._cache_misses_total,
                finalize_calls_total=self._finalize_calls_total,
                pending=sum(record.result is None for record in self._records.values()),
                cached_entries=len(self._cache),
            )

    def wait_workers(self, timeout: float | None = None) -> None:
        """Wait for worker completion only; finalizers still require explicit ``poll`` calls."""
        self._scheduler.wait_all(timeout=timeout)

    def shutdown(self, *, wait: bool = True, cancel_pending: bool = True) -> None:
        if self._closed:
            return
        self._closed = True
        self._scheduler.shutdown(wait=wait, cancel_pending=cancel_pending)

    def _ensure_open(self) -> None:
        if self._closed:
            raise RuntimeError("async asset pipeline is shut down")


__all__ = [
    "AssetBuildContext",
    "AsyncAssetDiagnostics",
    "AsyncAssetPipeline",
    "AsyncAssetRequest",
    "AsyncAssetResult",
    "AsyncAssetState",
]
