from __future__ import annotations

from concurrent.futures import Future
from pathlib import Path
from time import sleep

import pytest

from swirengine.asset_pipeline import AssetLoadResult
from swirengine.asset_streaming import AssetStreamingBudget, AssetStreamingManager
from swirengine.assets import AssetManager
from swirengine.render_resources18 import RenderResourceDescriptor, TransientRenderResourcePool


class _FuturePreloader:
    def __init__(self, future: Future[AssetLoadResult]) -> None:
        self.future = future

    def load_async(self, asset, *, cache=True):
        return self.future


def _assets(tmp_path: Path, count: int = 6) -> AssetManager:
    manager = AssetManager(tmp_path)
    manager.register_loader("txt", lambda path: path.read_text(encoding="utf-8"))
    for index in range(count):
        (tmp_path / f"asset-{index}.txt").write_text("x" * (index + 1), encoding="utf-8")
    return manager


def _drain(streamer: AssetStreamingManager) -> None:
    for _ in range(100):
        streamer.pump(max_completions=32)
        if streamer.diagnostics().pending == 0:
            return
        sleep(0.005)
    raise AssertionError("streaming queue did not drain")


def test_exceptional_future_is_drained_and_reported_without_sticky_pending(tmp_path):
    assets = _assets(tmp_path, 1)
    failed: Future[AssetLoadResult] = Future()
    failed.set_exception(RuntimeError("decode worker crashed"))
    streamer = AssetStreamingManager(assets, preloader=_FuturePreloader(failed))

    streamer.stage("asset-0.txt")
    results = streamer.pump()
    diag = streamer.diagnostics()

    assert len(results) == 1
    assert not results[0].ok
    assert "decode worker crashed" in (results[0].error or "")
    assert diag.failed == 1
    assert diag.cancelled == 0
    assert diag.pending == 0
    assert diag.resident_assets == 0


def test_cancelled_future_is_drained_separately_from_failures(tmp_path):
    assets = _assets(tmp_path, 1)
    cancelled: Future[AssetLoadResult] = Future()
    assert cancelled.cancel()
    streamer = AssetStreamingManager(assets, preloader=_FuturePreloader(cancelled))

    streamer.stage("asset-0.txt")
    results = streamer.pump()
    diag = streamer.diagnostics()

    assert len(results) == 1
    assert not results[0].ok
    assert diag.cancelled == 1
    assert diag.failed == 0
    assert diag.pending == 0


def test_pinned_budget_pressure_is_visible_and_recovers_after_unpin(tmp_path):
    assets = _assets(tmp_path, 2)
    budget = AssetStreamingBudget(max_resident_bytes=1024, max_resident_assets=1)
    streamer = AssetStreamingManager(assets, budget=budget)
    try:
        streamer.stage("asset-0.txt", pin=True)
        streamer.stage("asset-1.txt", pin=True)
        _drain(streamer)
        pressured = streamer.diagnostics()
        assert pressured.over_budget
        assert pressured.resident_assets == 2
        assert pressured.budget_pressure_events >= 1
        assert pressured.peak_resident_assets == 2

        assert streamer.unpin("asset-0.txt")
        recovered = streamer.diagnostics()
        assert not recovered.over_budget
        assert recovered.resident_assets == 1
        assert recovered.resident_bytes <= budget.max_resident_bytes
    finally:
        streamer.shutdown(release_resident=True)


def test_release_all_preserves_pins_unless_forced_and_invalidates_cache(tmp_path):
    assets = _assets(tmp_path, 2)
    streamer = AssetStreamingManager(assets)
    try:
        streamer.stage("asset-0.txt", pin=True)
        streamer.stage("asset-1.txt")
        _drain(streamer)
        assert assets.cached("asset-0.txt")
        assert assets.cached("asset-1.txt")

        assert streamer.release_all() == 1
        assert assets.cached("asset-0.txt")
        assert not assets.cached("asset-1.txt")
        assert streamer.release_all(force=True) == 1
        assert not assets.cached("asset-0.txt")
        assert streamer.diagnostics().resident_bytes == 0
    finally:
        streamer.shutdown()


def test_shutdown_can_release_session_residency_and_reject_new_work(tmp_path):
    assets = _assets(tmp_path, 2)
    streamer = AssetStreamingManager(assets)
    streamer.stage_many(["asset-0.txt", "asset-1.txt"])
    _drain(streamer)

    streamer.shutdown(release_resident=True)
    diag = streamer.diagnostics()

    assert streamer.closed
    assert diag.closed
    assert diag.pending == 0
    assert diag.resident_assets == 0
    assert diag.resident_bytes == 0
    assert not assets.cached("asset-0.txt")
    with pytest.raises(RuntimeError, match="shut down"):
        streamer.stage("asset-0.txt")
    streamer.shutdown(release_resident=True)


def test_streaming_residency_stays_bounded_under_repeated_workload(tmp_path):
    assets = _assets(tmp_path, 6)
    sizes = {f"asset-{index}.txt": 8 for index in range(6)}
    budget = AssetStreamingBudget(max_resident_bytes=24, max_resident_assets=3)
    streamer = AssetStreamingManager(
        assets,
        budget=budget,
        size_estimator=lambda path, value: sizes[path.name],
    )
    try:
        for _ in range(8):
            for index in range(6):
                streamer.stage(f"asset-{index}.txt")
                _drain(streamer)
                diag = streamer.diagnostics()
                assert diag.resident_assets <= 3
                assert diag.resident_bytes <= 24
                assert not diag.over_budget
        final = streamer.diagnostics()
        assert final.completed >= 6
        assert final.peak_resident_assets <= 4
        assert final.peak_resident_bytes <= 32
    finally:
        streamer.shutdown(release_resident=True)


def test_transient_render_pool_reuses_resources_and_closes_to_zero_residency():
    created: list[dict[str, int]] = []
    destroyed: list[dict[str, int]] = []

    def create(descriptor):
        resource = {"id": len(created) + 1}
        created.append(resource)
        return resource

    def destroy(resource):
        destroyed.append(resource)

    pool = TransientRenderResourcePool(max_resources=4, max_bytes=4096, create=create, destroy=destroy)
    descriptor = RenderResourceDescriptor("rgba8", 16, 16)

    for _ in range(200):
        lease = pool.acquire(descriptor)
        lease.release()

    before_close = pool.diagnostics()
    assert before_close.creates == 1
    assert before_close.reuses == 199
    assert before_close.resident_resources == 1
    assert before_close.peak_resident_resources == 1

    pool.close()
    after_close = pool.diagnostics()
    assert after_close.resident_resources == 0
    assert after_close.resident_bytes == 0
    assert len(destroyed) == 1
