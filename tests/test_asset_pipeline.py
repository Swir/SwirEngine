from __future__ import annotations

from pathlib import Path
from threading import Barrier, Lock
from time import sleep

import pytest

from swirengine.asset_pipeline import AssetPreloader
from swirengine.assets import AssetManager


def _text_assets(tmp_path: Path, count: int = 4) -> AssetManager:
    manager = AssetManager(tmp_path)
    manager.register_loader("txt", lambda path: path.read_text(encoding="utf-8"))
    for index in range(count):
        (tmp_path / f"asset-{index}.txt").write_text(f"value-{index}", encoding="utf-8")
    return manager


def test_load_async_returns_result_and_populates_asset_cache(tmp_path):
    manager = _text_assets(tmp_path, 1)
    with AssetPreloader(manager, max_workers=2) as preloader:
        future = preloader.load_async("asset-0.txt")
        result = future.result(timeout=2)

    assert result.ok
    assert result.value == "value-0"
    assert result.path == (tmp_path / "asset-0.txt").resolve()
    assert result.cache_hit is False
    assert result.duration_ns >= 0
    assert manager.cached("asset-0.txt")


def test_preload_preserves_input_order_and_reports_cache_hits(tmp_path):
    manager = _text_assets(tmp_path, 3)
    manager.load("asset-1.txt")

    with AssetPreloader(manager, max_workers=3) as preloader:
        report = preloader.preload(["asset-2.txt", "asset-1.txt", "asset-0.txt"])

    assert [result.value for result in report.results] == ["value-2", "value-1", "value-0"]
    assert report.total == 3
    assert report.loaded == 3
    assert report.failed == 0
    assert report.cache_hits == 1
    assert report.wall_time_ns >= 0
    assert report.errors() == ()


def test_preload_async_does_not_block_caller_and_loads_batch(tmp_path):
    manager = _text_assets(tmp_path, 2)
    gate = Barrier(3)

    def loader(path):
        gate.wait(timeout=2)
        return path.read_text(encoding="utf-8")

    manager.register_loader("txt", loader)
    with AssetPreloader(manager, max_workers=2) as preloader:
        future = preloader.preload_async(["asset-0.txt", "asset-1.txt"])
        assert not future.done()
        gate.wait(timeout=2)
        report = future.result(timeout=2)

    assert report.loaded == 2
    assert {result.value for result in report.results} == {"value-0", "value-1"}


def test_same_path_shares_one_inflight_loader_call(tmp_path):
    manager = _text_assets(tmp_path, 1)
    calls = 0
    calls_lock = Lock()

    def loader(path):
        nonlocal calls
        with calls_lock:
            calls += 1
        sleep(0.03)
        return path.read_text(encoding="utf-8")

    manager.register_loader("txt", loader)
    manager.register("hero", "asset-0.txt")
    with AssetPreloader(manager, max_workers=4) as preloader:
        first = preloader.load_async("hero")
        second = preloader.load_async("asset-0.txt")
        assert first is second
        assert first.result(timeout=2).value == "value-0"

    assert calls == 1


def test_loader_failures_are_captured_per_asset_without_aborting_batch(tmp_path):
    manager = _text_assets(tmp_path, 2)

    def loader(path):
        if path.name == "asset-1.txt":
            raise ValueError("broken data")
        return path.read_text(encoding="utf-8")

    manager.register_loader("txt", loader)
    with AssetPreloader(manager, max_workers=2) as preloader:
        report = preloader.preload(["asset-0.txt", "asset-1.txt"])

    assert report.loaded == 1
    assert report.failed == 1
    assert report.results[0].ok
    assert report.results[1].ok is False
    assert report.results[1].error == "ValueError: broken data"
    assert report.errors() == (report.results[1],)


def test_pending_paths_and_shutdown_contract(tmp_path):
    manager = _text_assets(tmp_path, 1)
    gate = Barrier(2)

    def loader(path):
        gate.wait(timeout=2)
        return path.read_text(encoding="utf-8")

    manager.register_loader("txt", loader)
    preloader = AssetPreloader(manager, max_workers=1)
    future = preloader.load_async("asset-0.txt")
    assert preloader.pending_paths() == ((tmp_path / "asset-0.txt").resolve(),)
    gate.wait(timeout=2)
    future.result(timeout=2)
    preloader.shutdown()

    assert preloader.pending_paths() == ()
    with pytest.raises(RuntimeError, match="shut down"):
        preloader.load_async("asset-0.txt")


def test_max_workers_must_be_positive(tmp_path):
    with pytest.raises(ValueError, match="max_workers"):
        AssetPreloader(AssetManager(tmp_path), max_workers=0)
