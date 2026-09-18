from __future__ import annotations

from collections import OrderedDict
from collections.abc import Callable, Iterable
from concurrent.futures import CancelledError, Future
from dataclasses import dataclass
from pathlib import Path
from time import perf_counter_ns

from .asset_pipeline import AssetLoadResult, AssetPreloader
from .assets import AssetManager

AssetSizeEstimator = Callable[[Path, object], int]


@dataclass(frozen=True, slots=True)
class AssetStreamingBudget:
    """Runtime residency limits used by :class:`AssetStreamingManager`."""

    max_resident_bytes: int = 256 * 1024 * 1024
    max_resident_assets: int = 1024
    hitch_threshold_ms: float = 8.0

    def __post_init__(self) -> None:
        if self.max_resident_bytes < 1:
            raise ValueError("max_resident_bytes must be >= 1")
        if self.max_resident_assets < 1:
            raise ValueError("max_resident_assets must be >= 1")
        if self.hitch_threshold_ms < 0:
            raise ValueError("hitch_threshold_ms must be >= 0")


@dataclass(frozen=True, slots=True)
class AssetResidency:
    path: Path
    size_bytes: int
    pinned: bool


@dataclass(frozen=True, slots=True)
class AssetStreamingDiagnostics:
    staged: int
    completed: int
    failed: int
    cancelled: int
    evictions: int
    resident_assets: int
    resident_bytes: int
    peak_resident_assets: int
    peak_resident_bytes: int
    hitch_count: int
    max_finalize_ms: float
    pending: int
    budget_pressure_events: int
    over_budget: bool
    closed: bool


class AssetStreamingManager:
    """Budgeted staged loading with deterministic residency and hitch diagnostics.

    Background decode/file work is delegated to ``AssetPreloader``. ``pump()`` is intentionally
    called from the game loop and only finalizes already-completed futures, so creators control the
    amount of work admitted per frame. Residency uses deterministic LRU eviction and never evicts
    explicitly pinned assets.

    The manager owns its scheduling/residency lifecycle even when the underlying preloader is shared.
    ``shutdown()`` always detaches pending work and closes this manager; it only shuts down the
    preloader when the manager created it. Resident cache entries are preserved by default for 1.x
    compatibility and can be released explicitly with ``release_all()`` or ``release_resident=True``.
    """

    def __init__(
        self,
        assets: AssetManager,
        *,
        preloader: AssetPreloader | None = None,
        budget: AssetStreamingBudget | None = None,
        size_estimator: AssetSizeEstimator | None = None,
    ) -> None:
        self.assets = assets
        self.preloader = preloader or AssetPreloader(assets)
        self._owns_preloader = preloader is None
        self.budget = budget or AssetStreamingBudget()
        self._size_estimator = size_estimator or self._default_size_estimator
        self._pending: OrderedDict[Path, Future[AssetLoadResult]] = OrderedDict()
        self._pending_pin: dict[Path, bool] = {}
        self._resident: OrderedDict[Path, AssetResidency] = OrderedDict()
        self._resident_bytes = 0
        self._staged = 0
        self._completed = 0
        self._failed = 0
        self._cancelled = 0
        self._evictions = 0
        self._peak_resident_assets = 0
        self._peak_resident_bytes = 0
        self._hitch_count = 0
        self._max_finalize_ns = 0
        self._budget_pressure_events = 0
        self._closed = False

    def stage(self, asset: str | Path, *, pin: bool = False) -> Future[AssetLoadResult]:
        self._ensure_open()
        path = self.assets.require(asset).expanduser().resolve()
        if path in self._resident:
            self.touch(path)
            if pin and not self._resident[path].pinned:
                current = self._resident[path]
                self._resident[path] = AssetResidency(path, current.size_bytes, True)
            completed: Future[AssetLoadResult] = Future()
            completed.set_result(
                AssetLoadResult(
                    asset=str(asset),
                    path=path,
                    value=self.assets.load(path),
                    duration_ns=0,
                    cache_hit=True,
                )
            )
            return completed
        existing = self._pending.get(path)
        if existing is not None:
            self._pending_pin[path] = self._pending_pin[path] or bool(pin)
            return existing
        future = self.preloader.load_async(asset)
        self._pending[path] = future
        self._pending_pin[path] = bool(pin)
        self._staged += 1
        return future

    def stage_many(
        self,
        assets: Iterable[str | Path],
        *,
        pin: bool = False,
    ) -> tuple[Future[AssetLoadResult], ...]:
        self._ensure_open()
        return tuple(self.stage(asset, pin=pin) for asset in assets)

    def pump(self, *, max_completions: int = 4) -> tuple[AssetLoadResult, ...]:
        """Finalize ready loads without waiting on unfinished background work."""
        self._ensure_open()
        if max_completions < 1:
            raise ValueError("max_completions must be >= 1")
        finalized: list[AssetLoadResult] = []
        for path, future in tuple(self._pending.items()):
            if len(finalized) >= max_completions:
                break
            if not future.done():
                continue
            started = perf_counter_ns()
            self._pending.pop(path, None)
            pin = self._pending_pin.pop(path, False)
            try:
                result = future.result()
            except CancelledError:
                self._cancelled += 1
                result = AssetLoadResult(
                    asset=str(path),
                    path=path,
                    value=None,
                    duration_ns=0,
                    cache_hit=False,
                    error="CancelledError: streaming request was cancelled",
                )
            except Exception as exc:  # noqa: BLE001 - custom/shared preloaders may fail unexpectedly.
                self._failed += 1
                result = AssetLoadResult(
                    asset=str(path),
                    path=path,
                    value=None,
                    duration_ns=0,
                    cache_hit=False,
                    error=f"{type(exc).__name__}: {exc}",
                )
            finalize_ns = perf_counter_ns() - started
            self._max_finalize_ns = max(self._max_finalize_ns, finalize_ns)
            if finalize_ns >= int(self.budget.hitch_threshold_ms * 1_000_000):
                self._hitch_count += 1
            if result.ok:
                size = max(0, int(self._size_estimator(path, result.value)))
                previous = self._resident.get(path)
                if previous is not None:
                    self._resident_bytes -= previous.size_bytes
                self._resident[path] = AssetResidency(path, size, pin)
                self._resident_bytes += size
                self._resident.move_to_end(path)
                self._completed += 1
                self._peak_resident_assets = max(
                    self._peak_resident_assets,
                    len(self._resident),
                )
                self._peak_resident_bytes = max(
                    self._peak_resident_bytes,
                    self._resident_bytes,
                )
                self._evict_to_budget()
            elif not isinstance(future.exception(), CancelledError):
                # Normal AssetPreloader failures arrive as an AssetLoadResult rather than an
                # exceptional Future; exceptional futures were counted in the except branch above.
                if future.exception() is None:
                    self._failed += 1
            finalized.append(result)
        return tuple(finalized)

    def touch(self, asset: str | Path) -> bool:
        self._ensure_open()
        path = self.assets.resolve(asset).expanduser().resolve()
        if path not in self._resident:
            return False
        self._resident.move_to_end(path)
        return True

    def pin(self, asset: str | Path) -> bool:
        self._ensure_open()
        path = self.assets.resolve(asset).expanduser().resolve()
        current = self._resident.get(path)
        if current is None:
            return False
        self._resident[path] = AssetResidency(path, current.size_bytes, True)
        self._resident.move_to_end(path)
        return True

    def unpin(self, asset: str | Path) -> bool:
        self._ensure_open()
        path = self.assets.resolve(asset).expanduser().resolve()
        current = self._resident.get(path)
        if current is None:
            return False
        self._resident[path] = AssetResidency(path, current.size_bytes, False)
        self._evict_to_budget()
        return True

    def evict(self, asset: str | Path, *, force: bool = False) -> bool:
        self._ensure_open()
        return self._evict_path(asset, force=force)

    def release_all(self, *, force: bool = False) -> int:
        """Release resident streaming assets and invalidate their shared asset-cache entries.

        By default pinned assets remain resident. ``force=True`` is intended for project/session
        teardown where the caller owns the lifetime boundary.
        """
        self._ensure_open()
        released = 0
        for path in tuple(self._resident):
            if self._evict_path(path, force=force):
                released += 1
        return released

    def resident(self) -> tuple[AssetResidency, ...]:
        return tuple(self._resident.values())

    @property
    def resident_bytes(self) -> int:
        return self._resident_bytes

    @property
    def closed(self) -> bool:
        return self._closed

    def diagnostics(self) -> AssetStreamingDiagnostics:
        return AssetStreamingDiagnostics(
            staged=self._staged,
            completed=self._completed,
            failed=self._failed,
            cancelled=self._cancelled,
            evictions=self._evictions,
            resident_assets=len(self._resident),
            resident_bytes=self._resident_bytes,
            peak_resident_assets=self._peak_resident_assets,
            peak_resident_bytes=self._peak_resident_bytes,
            hitch_count=self._hitch_count,
            max_finalize_ms=self._max_finalize_ns / 1_000_000.0,
            pending=len(self._pending),
            budget_pressure_events=self._budget_pressure_events,
            over_budget=self._over_budget(),
            closed=self._closed,
        )

    def shutdown(
        self,
        *,
        wait: bool = True,
        cancel_futures: bool = False,
        release_resident: bool = False,
    ) -> None:
        if self._closed:
            return
        if cancel_futures and self._owns_preloader:
            for future in tuple(self._pending.values()):
                future.cancel()
        self._pending.clear()
        self._pending_pin.clear()
        if release_resident:
            for path in tuple(self._resident):
                self._evict_path(path, force=True)
        self._closed = True
        if self._owns_preloader:
            self.preloader.shutdown(wait=wait, cancel_futures=cancel_futures)

    def __enter__(self) -> AssetStreamingManager:  # noqa: PYI034
        self._ensure_open()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.shutdown()

    def _evict_to_budget(self) -> None:
        was_over_budget = self._over_budget()
        while self._over_budget():
            candidate = next(
                (item for item in self._resident.values() if not item.pinned),
                None,
            )
            if candidate is None:
                if was_over_budget:
                    self._budget_pressure_events += 1
                return
            self._evict_path(candidate.path)

    def _evict_path(self, asset: str | Path, *, force: bool = False) -> bool:
        path = self.assets.resolve(asset).expanduser().resolve()
        current = self._resident.get(path)
        if current is None or (current.pinned and not force):
            return False
        self._resident.pop(path, None)
        self._resident_bytes -= current.size_bytes
        self.assets.invalidate(path)
        self._evictions += 1
        return True

    def _over_budget(self) -> bool:
        return (
            len(self._resident) > self.budget.max_resident_assets
            or self._resident_bytes > self.budget.max_resident_bytes
        )

    def _ensure_open(self) -> None:
        if self._closed:
            raise RuntimeError("asset streaming manager is shut down")

    @staticmethod
    def _default_size_estimator(path: Path, _value: object) -> int:
        try:
            return path.stat().st_size
        except OSError:
            return 0
