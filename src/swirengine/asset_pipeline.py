from __future__ import annotations

from collections.abc import Iterable
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from threading import Lock
from time import perf_counter_ns
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
            if existing is not None and not existing.done():
                return existing
            future = self._executor.submit(self._load_one, str(asset), path, cache)
            self._inflight[path] = future
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
