from __future__ import annotations

import hashlib
from collections.abc import Callable, Iterable
from concurrent.futures import Future, ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from threading import Lock
from time import perf_counter, perf_counter_ns
from typing import Any

from .assets import AssetManager


@dataclass(frozen=True, slots=True)
class AssetLoadResult:
    """Result of one background asset load."""

    asset: str
    path: Path
    value: Any
    duration_ns: int
    cache_hit: bool
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.error is None

    @property
    def duration_ms(self) -> float:
        return self.duration_ns / 1_000_000.0


@dataclass(frozen=True, slots=True)
class AssetPreloadReport:
    """Deterministic diagnostics for one preload batch."""

    results: tuple[AssetLoadResult, ...]
    wall_time_ns: int

    @property
    def total(self) -> int:
        return len(self.results)

    @property
    def loaded(self) -> int:
        return sum(result.ok for result in self.results)

    @property
    def failed(self) -> int:
        return self.total - self.loaded

    @property
    def cache_hits(self) -> int:
        return sum(result.cache_hit for result in self.results)

    @property
    def wall_time_ms(self) -> float:
        return self.wall_time_ns / 1_000_000.0

    @property
    def worker_time_ns(self) -> int:
        return sum(result.duration_ns for result in self.results)

    @property
    def stall_reduction_ratio(self) -> float:
        """Estimated serialized wait avoided by concurrent loading.

        This compares summed loader time with observed batch wall time. It intentionally does not
        claim a frame-rate improvement; it only describes the preload wait component.
        """
        worker = self.worker_time_ns
        if worker <= 0:
            return 0.0
        return max(0.0, min(1.0, 1.0 - (self.wall_time_ns / worker)))

    def errors(self) -> tuple[AssetLoadResult, ...]:
        return tuple(result for result in self.results if not result.ok)


class AssetPreloader:
    """Background/preload pipeline layered on top of :class:`AssetManager`.

    Loader work is dispatched to a bounded thread pool so CPU/file decoding can happen away from
    the gameplay thread. Renderer/GPU uploads that require a graphics context should still be
    finalized on the owning render thread after the returned values are ready.
    """

    def __init__(self, assets: AssetManager, *, max_workers: int = 4) -> None:
        if max_workers < 1:
            raise ValueError("max_workers must be >= 1")
        self.assets = assets
        self.max_workers = int(max_workers)
        self._executor = ThreadPoolExecutor(
            max_workers=self.max_workers,
            thread_name_prefix="swir-assets",
        )
        self._coordinator = ThreadPoolExecutor(max_workers=1, thread_name_prefix="swir-preload")
        self._inflight: dict[Path, Future[AssetLoadResult]] = {}
        self._lock = Lock()
        self._closed = False

    def load_async(self, asset: str | Path, *, cache: bool = True) -> Future[AssetLoadResult]:
        """Queue one asset load and return immediately with a Future.

        Requests resolving to the same canonical path share one in-flight operation. Cached assets
        still travel through the same result type so diagnostics stay uniform.
        """
        self._ensure_open()
        path = self.assets.require(asset).expanduser().resolve()
        with self._lock:
            existing = self._inflight.get(path)
            if existing is not None:
                return existing
            future = self._executor.submit(self._load_one, str(asset), path, cache)
            self._inflight[path] = future

        # Register outside the lock: add_done_callback executes synchronously when a very fast
        # Future is already complete, and the callback itself needs the same lock for cleanup.
        future.add_done_callback(lambda done, key=path: self._forget(key, done))
        return future

    def preload(self, assets: Iterable[str | Path], *, cache: bool = True) -> AssetPreloadReport:
        """Load a batch concurrently and return results in input order."""
        self._ensure_open()
        requested = tuple(assets)
        started = perf_counter_ns()
        futures = [self.load_async(asset, cache=cache) for asset in requested]
        results = tuple(future.result() for future in futures)
        return AssetPreloadReport(results=results, wall_time_ns=perf_counter_ns() - started)

    def preload_async(
        self,
        assets: Iterable[str | Path],
        *,
        cache: bool = True,
    ) -> Future[AssetPreloadReport]:
        """Queue an entire preload batch without blocking the caller."""
        self._ensure_open()
        requested = tuple(assets)
        return self._coordinator.submit(self.preload, requested, cache=cache)

    def pending_paths(self) -> tuple[Path, ...]:
        with self._lock:
            pending = (path for path, future in self._inflight.items() if not future.done())
            return tuple(sorted(pending, key=str))

    def shutdown(self, *, wait: bool = True, cancel_futures: bool = False) -> None:
        if self._closed:
            return
        self._closed = True
        self._coordinator.shutdown(wait=wait, cancel_futures=cancel_futures)
        self._executor.shutdown(wait=wait, cancel_futures=cancel_futures)

    def __enter__(self) -> AssetPreloader:  # noqa: PYI034 - Self is Python 3.11+, engine supports 3.10.
        self._ensure_open()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.shutdown()

    def _load_one(self, asset: str, path: Path, cache: bool) -> AssetLoadResult:
        cache_hit = cache and self.assets.cached(path)
        started = perf_counter_ns()
        try:
            value = self.assets.load(path, cache=cache)
        except Exception as exc:  # noqa: BLE001 - user asset loaders may raise arbitrary errors.
            return AssetLoadResult(
                asset=asset,
                path=path,
                value=None,
                duration_ns=perf_counter_ns() - started,
                cache_hit=cache_hit,
                error=f"{type(exc).__name__}: {exc}",
            )
        return AssetLoadResult(
            asset=asset,
            path=path,
            value=value,
            duration_ns=perf_counter_ns() - started,
            cache_hit=cache_hit,
        )

    def _forget(self, path: Path, future: Future[AssetLoadResult]) -> None:
        with self._lock:
            if self._inflight.get(path) is future:
                self._inflight.pop(path, None)

    def _ensure_open(self) -> None:
        if self._closed:
            raise RuntimeError("asset preloader is shut down")


AssetImportLoader = Callable[[Path], Any]
AssetDependencyResolver = Callable[[Path], Iterable[str | Path]]
AssetImportFinalizer = Callable[[Any], Any]


class AssetImportState(str, Enum):
    """Terminal and scheduling states exposed by :class:`AssetPipeline`."""

    QUEUED = "queued"
    COMPLETED = "completed"
    FAILED = "failed"
    STALE = "stale"
    CANCELLED = "cancelled"


@dataclass(frozen=True, slots=True)
class AssetFingerprint:
    """Content-aware fingerprint used to guard derived-asset cache entries."""

    path: Path
    exists: bool
    size_bytes: int
    mtime_ns: int
    sha256: str

    @classmethod
    def capture(cls, path: str | Path) -> AssetFingerprint:
        resolved = Path(path).expanduser().resolve()
        try:
            stat = resolved.stat()
        except FileNotFoundError:
            return cls(resolved, False, 0, 0, "")
        if not resolved.is_file():
            raise IsADirectoryError(resolved)
        digest = hashlib.sha256()
        with resolved.open("rb") as handle:
            while True:
                chunk = handle.read(1024 * 1024)
                if not chunk:
                    break
                digest.update(chunk)
        return cls(
            path=resolved,
            exists=True,
            size_bytes=int(stat.st_size),
            mtime_ns=int(stat.st_mtime_ns),
            sha256=digest.hexdigest(),
        )


class AssetDependencyGraph:
    """Deterministic source/dependency graph with reverse invalidation queries."""

    def __init__(self) -> None:
        self._dependencies: dict[Path, tuple[Path, ...]] = {}
        self._dependents: dict[Path, set[Path]] = {}

    @staticmethod
    def _path(path: str | Path) -> Path:
        return Path(path).expanduser().resolve()

    @property
    def node_count(self) -> int:
        nodes = set(self._dependencies)
        nodes.update(self._dependents)
        for values in self._dependencies.values():
            nodes.update(values)
        return len(nodes)

    def set_dependencies(
        self,
        source: str | Path,
        dependencies: Iterable[str | Path],
    ) -> tuple[Path, ...]:
        source_path = self._path(source)
        normalized = {self._path(item) for item in dependencies}
        normalized.discard(source_path)
        ordered = tuple(sorted(normalized, key=lambda item: item.as_posix().lower()))
        previous = self._dependencies.get(source_path, ())
        for dependency in previous:
            reverse = self._dependents.get(dependency)
            if reverse is not None:
                reverse.discard(source_path)
                if not reverse:
                    self._dependents.pop(dependency, None)
        self._dependencies[source_path] = ordered
        for dependency in ordered:
            self._dependents.setdefault(dependency, set()).add(source_path)
        return ordered

    def remove(self, source: str | Path) -> bool:
        source_path = self._path(source)
        previous = self._dependencies.pop(source_path, None)
        if previous is None:
            return False
        for dependency in previous:
            reverse = self._dependents.get(dependency)
            if reverse is not None:
                reverse.discard(source_path)
                if not reverse:
                    self._dependents.pop(dependency, None)
        return True

    def dependencies(self, source: str | Path) -> tuple[Path, ...]:
        return self._dependencies.get(self._path(source), ())

    def direct_dependents(self, dependency: str | Path) -> tuple[Path, ...]:
        values = self._dependents.get(self._path(dependency), set())
        return tuple(sorted(values, key=lambda item: item.as_posix().lower()))

    def affected_by(self, changed: str | Path) -> tuple[Path, ...]:
        """Return the changed path plus all transitive dependents, cycle-safe and deterministic."""
        root = self._path(changed)
        pending = [root]
        seen: set[Path] = set()
        while pending:
            current = pending.pop()
            if current in seen:
                continue
            seen.add(current)
            pending.extend(self._dependents.get(current, ()))
        return tuple(sorted(seen, key=lambda item: item.as_posix().lower()))

    def clear(self) -> None:
        self._dependencies.clear()
        self._dependents.clear()


@dataclass(frozen=True, slots=True)
class AssetImportRequest:
    """One immutable import request submitted to the bounded worker pool."""

    request_id: int
    processor: str
    source: Path
    source_fingerprint: AssetFingerprint


@dataclass(frozen=True, slots=True)
class AssetImportResult:
    """Terminal result finalized on the thread that calls ``poll()`` or ``wait()``."""

    request_id: int
    processor: str
    source: Path
    state: AssetImportState
    cache_hit: bool
    dependencies: tuple[Path, ...] = ()
    value: Any = None
    worker_seconds: float = 0.0
    error: str | None = None

    @property
    def successful(self) -> bool:
        return self.state is AssetImportState.COMPLETED


@dataclass(frozen=True, slots=True)
class AssetImportDiagnostics:
    """Low-cost Asset Pipeline 2.0 scheduling and cache counters."""

    max_workers: int
    queued: int
    running: int
    completed: int
    failed: int
    stale: int
    cancelled: int
    cache_hits: int
    cache_misses: int
    cached_entries: int
    invalidated_entries: int
    dependency_nodes: int


@dataclass(frozen=True, slots=True)
class _Processor:
    name: str
    suffixes: tuple[str, ...]
    loader: AssetImportLoader
    dependencies: AssetDependencyResolver | None
    finalizer: AssetImportFinalizer | None


@dataclass(frozen=True, slots=True)
class _WorkerProduct:
    value: Any
    source_fingerprint: AssetFingerprint
    dependency_fingerprints: tuple[AssetFingerprint, ...]
    worker_seconds: float


@dataclass(frozen=True, slots=True)
class _CacheEntry:
    source_fingerprint: AssetFingerprint
    dependency_fingerprints: tuple[AssetFingerprint, ...]
    value: Any


class AssetPipeline:
    """Bounded, dependency-aware import runtime for SwirEngine 1.4.

    File parsing/CPU processing runs in a worker pool. Optional finalizers deliberately run only
    from :meth:`poll` or :meth:`wait`, allowing renderer-facing callers to keep GPU/resource creation
    on their owning thread. Cache entries are committed transactionally only when source and dependency
    fingerprints still match the worker product.
    """

    def __init__(self, assets: AssetManager, *, max_workers: int = 2) -> None:
        workers = int(max_workers)
        if workers <= 0:
            raise ValueError("max_workers must be greater than zero")
        self.assets = assets
        self.max_workers = workers
        self.dependencies = AssetDependencyGraph()
        self._executor = ThreadPoolExecutor(
            max_workers=workers,
            thread_name_prefix="swir-asset-import",
        )
        self._processors: dict[str, _Processor] = {}
        self._processor_by_suffix: dict[str, str] = {}
        self._jobs: dict[int, tuple[AssetImportRequest, _Processor, Future[_WorkerProduct]]] = {}
        self._finished: dict[int, AssetImportResult] = {}
        self._delivery: list[int] = []
        self._cache: dict[tuple[str, Path], _CacheEntry] = {}
        self._next_request_id = 1
        self._bound = False
        self._closed = False
        self._completed = 0
        self._failed = 0
        self._stale = 0
        self._cancelled = 0
        self._cache_hits = 0
        self._cache_misses = 0
        self._invalidated_entries = 0
        self._lock = Lock()

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
        loader: AssetImportLoader,
        dependencies: AssetDependencyResolver | None = None,
        finalizer: AssetImportFinalizer | None = None,
    ) -> None:
        key = str(name).strip()
        if not key:
            raise ValueError("asset processor name cannot be empty")
        if not callable(loader):
            raise TypeError("asset processor loader must be callable")
        if dependencies is not None and not callable(dependencies):
            raise TypeError("asset dependency resolver must be callable")
        if finalizer is not None and not callable(finalizer):
            raise TypeError("asset finalizer must be callable")
        normalized = tuple(
            sorted(
                {self._normalize_suffix(item) for item in suffixes if self._normalize_suffix(item)}
            )
        )
        if not normalized:
            raise ValueError("asset processor must register at least one suffix")
        for suffix in normalized:
            owner = self._processor_by_suffix.get(suffix)
            if owner is not None and owner != key:
                raise ValueError(f"asset suffix {suffix!r} is already owned by processor {owner!r}")
        previous = self._processors.get(key)
        if previous is not None:
            for suffix in previous.suffixes:
                if self._processor_by_suffix.get(suffix) == key:
                    self._processor_by_suffix.pop(suffix, None)
        processor = _Processor(key, normalized, loader, dependencies, finalizer)
        self._processors[key] = processor
        for suffix in normalized:
            self._processor_by_suffix[suffix] = key

    def unregister_processor(self, name: str) -> bool:
        key = str(name)
        processor = self._processors.pop(key, None)
        if processor is None:
            return False
        for suffix in processor.suffixes:
            if self._processor_by_suffix.get(suffix) == key:
                self._processor_by_suffix.pop(suffix, None)
        return True

    def processor_names(self) -> tuple[str, ...]:
        return tuple(sorted(self._processors))

    def _select_processor(self, source: Path, explicit: str | None) -> _Processor:
        if explicit is not None:
            try:
                return self._processors[str(explicit)]
            except KeyError as exc:
                raise ValueError(f"unknown asset processor {explicit!r}") from exc
        name = self._processor_by_suffix.get(source.suffix.lower())
        if name is None:
            raise ValueError(f"no asset processor registered for suffix {source.suffix.lower()!r}")
        return self._processors[name]

    @staticmethod
    def _current_matches(fingerprint: AssetFingerprint) -> bool:
        return AssetFingerprint.capture(fingerprint.path) == fingerprint

    @classmethod
    def _cache_entry_current(cls, entry: _CacheEntry) -> bool:
        if not cls._current_matches(entry.source_fingerprint):
            return False
        return all(cls._current_matches(item) for item in entry.dependency_fingerprints)

    @staticmethod
    def _run_processor(processor: _Processor, request: AssetImportRequest) -> _WorkerProduct:
        started = perf_counter()
        dependency_paths: tuple[Path, ...] = ()
        if processor.dependencies is not None:
            source_parent = request.source.parent
            resolved: set[Path] = set()
            for item in processor.dependencies(request.source):
                candidate = Path(item).expanduser()
                if not candidate.is_absolute():
                    candidate = source_parent / candidate
                candidate = candidate.resolve()
                if candidate != request.source:
                    resolved.add(candidate)
            dependency_paths = tuple(sorted(resolved, key=lambda item: item.as_posix().lower()))
        value = processor.loader(request.source)
        dependency_fingerprints = tuple(AssetFingerprint.capture(path) for path in dependency_paths)
        return _WorkerProduct(
            value=value,
            source_fingerprint=request.source_fingerprint,
            dependency_fingerprints=dependency_fingerprints,
            worker_seconds=perf_counter() - started,
        )

    def submit(
        self,
        asset: str | Path,
        *,
        processor: str | None = None,
        force: bool = False,
    ) -> AssetImportRequest:
        if self._closed:
            raise RuntimeError("asset pipeline is closed")
        source = self.assets.require(asset).expanduser().resolve()
        selected = self._select_processor(source, processor)
        fingerprint = AssetFingerprint.capture(source)
        with self._lock:
            request = AssetImportRequest(
                request_id=self._next_request_id,
                processor=selected.name,
                source=source,
                source_fingerprint=fingerprint,
            )
            self._next_request_id += 1
            cache_key = (selected.name, source)
            cached = self._cache.get(cache_key)
            if not force and cached is not None and self._cache_entry_current(cached):
                result = AssetImportResult(
                    request_id=request.request_id,
                    processor=selected.name,
                    source=source,
                    state=AssetImportState.COMPLETED,
                    cache_hit=True,
                    dependencies=tuple(item.path for item in cached.dependency_fingerprints),
                    value=cached.value,
                )
                self._cache_hits += 1
                self._completed += 1
                self._finished[request.request_id] = result
                self._delivery.append(request.request_id)
                return request
            self._cache_misses += 1
            future = self._executor.submit(self._run_processor, selected, request)
            self._jobs[request.request_id] = (request, selected, future)
            return request

    def _finalize_job(self, request_id: int) -> AssetImportResult:
        finished = self._finished.get(request_id)
        if finished is not None:
            return finished
        request, processor, future = self._jobs.pop(request_id)
        if future.cancelled():
            result = AssetImportResult(
                request.request_id,
                request.processor,
                request.source,
                AssetImportState.CANCELLED,
                False,
            )
            self._cancelled += 1
        else:
            try:
                product = future.result()
            except Exception as exc:  # noqa: BLE001 - import processors are user-extensible.
                result = AssetImportResult(
                    request.request_id,
                    request.processor,
                    request.source,
                    AssetImportState.FAILED,
                    False,
                    error=str(exc),
                )
                self._failed += 1
            else:
                current = self._current_matches(product.source_fingerprint) and all(
                    self._current_matches(item) for item in product.dependency_fingerprints
                )
                if not current:
                    result = AssetImportResult(
                        request.request_id,
                        request.processor,
                        request.source,
                        AssetImportState.STALE,
                        False,
                        dependencies=tuple(item.path for item in product.dependency_fingerprints),
                        worker_seconds=product.worker_seconds,
                        error="source or dependency changed while the import was running",
                    )
                    self._stale += 1
                else:
                    try:
                        value = (
                            processor.finalizer(product.value)
                            if processor.finalizer is not None
                            else product.value
                        )
                    except Exception as exc:  # noqa: BLE001 - finalizers are user-extensible.
                        result = AssetImportResult(
                            request.request_id,
                            request.processor,
                            request.source,
                            AssetImportState.FAILED,
                            False,
                            dependencies=tuple(item.path for item in product.dependency_fingerprints),
                            worker_seconds=product.worker_seconds,
                            error=str(exc),
                        )
                        self._failed += 1
                    else:
                        dependency_paths = tuple(item.path for item in product.dependency_fingerprints)
                        self.dependencies.set_dependencies(request.source, dependency_paths)
                        self._cache[(request.processor, request.source)] = _CacheEntry(
                            product.source_fingerprint,
                            product.dependency_fingerprints,
                            value,
                        )
                        result = AssetImportResult(
                            request.request_id,
                            request.processor,
                            request.source,
                            AssetImportState.COMPLETED,
                            False,
                            dependencies=dependency_paths,
                            value=value,
                            worker_seconds=product.worker_seconds,
                        )
                        self._completed += 1
        self._finished[request_id] = result
        self._delivery.append(request_id)
        return result

    def poll(self) -> tuple[AssetImportResult, ...]:
        """Finalize finished worker jobs and return results once, ordered by request id."""
        with self._lock:
            for request_id in sorted(tuple(self._jobs)):
                future = self._jobs[request_id][2]
                if future.done():
                    self._finalize_job(request_id)
            ids = tuple(self._delivery)
            self._delivery.clear()
            return tuple(self._finished[request_id] for request_id in ids)

    def wait(
        self,
        request: AssetImportRequest | int,
        *,
        timeout: float | None = None,
    ) -> AssetImportResult:
        """Wait for one request and finalize it on the caller thread."""
        request_id = request.request_id if isinstance(request, AssetImportRequest) else int(request)
        with self._lock:
            finished = self._finished.get(request_id)
            if finished is not None:
                if request_id in self._delivery:
                    self._delivery.remove(request_id)
                return finished
            try:
                future = self._jobs[request_id][2]
            except KeyError as exc:
                raise KeyError(f"unknown asset import request {request_id}") from exc
        try:
            future.result(timeout=timeout)
        except FutureTimeoutError as exc:
            raise TimeoutError(f"asset import request {request_id} did not finish in time") from exc
        except Exception:
            pass
        with self._lock:
            result = self._finalize_job(request_id)
            if request_id in self._delivery:
                self._delivery.remove(request_id)
            return result

    def cancel(self, request: AssetImportRequest | int) -> bool:
        request_id = request.request_id if isinstance(request, AssetImportRequest) else int(request)
        with self._lock:
            job = self._jobs.get(request_id)
            if job is None:
                return False
            return job[2].cancel()

    def cached(self, asset: str | Path, *, processor: str | None = None) -> bool:
        source = self.assets.resolve(asset).expanduser().resolve()
        selected = self._select_processor(source, processor)
        entry = self._cache.get((selected.name, source))
        return entry is not None and self._cache_entry_current(entry)

    def invalidate(self, asset: str | Path) -> tuple[Path, ...]:
        """Drop cached imports for a path and every transitive dependent asset."""
        changed = self.assets.resolve(asset).expanduser().resolve()
        affected = self.dependencies.affected_by(changed)
        affected_set = set(affected)
        removed = 0
        with self._lock:
            for key in tuple(self._cache):
                if key[1] in affected_set:
                    self._cache.pop(key, None)
                    removed += 1
            self._invalidated_entries += removed
        return affected

    def bind(self) -> AssetPipeline:
        """Bind dependency-aware cache invalidation to the existing ``AssetManager``."""
        if not self._bound:
            self.assets.add_invalidator(self._on_asset_invalidated)
            self._bound = True
        return self

    def unbind(self) -> bool:
        if not self._bound:
            return False
        self.assets.remove_invalidator(self._on_asset_invalidated)
        self._bound = False
        return True

    def _on_asset_invalidated(self, path: Path) -> None:
        self.invalidate(path)

    @property
    def diagnostics(self) -> AssetImportDiagnostics:
        with self._lock:
            futures = tuple(job[2] for job in self._jobs.values())
            return AssetImportDiagnostics(
                max_workers=self.max_workers,
                queued=sum(1 for future in futures if not future.running() and not future.done()),
                running=sum(1 for future in futures if future.running() and not future.done()),
                completed=self._completed,
                failed=self._failed,
                stale=self._stale,
                cancelled=self._cancelled,
                cache_hits=self._cache_hits,
                cache_misses=self._cache_misses,
                cached_entries=len(self._cache),
                invalidated_entries=self._invalidated_entries,
                dependency_nodes=self.dependencies.node_count,
            )

    def close(self, *, wait: bool = True, cancel_futures: bool = False) -> None:
        if self._closed:
            return
        self.unbind()
        self._executor.shutdown(wait=wait, cancel_futures=cancel_futures)
        self._closed = True

    def __enter__(self) -> AssetPipeline:
        return self.bind()

    def __exit__(self, _exc_type, _exc, _tb) -> None:
        self.close()
