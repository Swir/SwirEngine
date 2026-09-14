from __future__ import annotations

from pathlib import Path
from time import sleep

from swirengine.asset_streaming import AssetStreamingBudget, AssetStreamingManager
from swirengine.assets import AssetManager


def _manager(tmp_path: Path, count: int = 4) -> AssetManager:
    manager = AssetManager(tmp_path)
    manager.register_loader("txt", lambda path: path.read_text(encoding="utf-8"))
    for index in range(count):
        (tmp_path / f"asset-{index}.txt").write_text("x" * (index + 1), encoding="utf-8")
    return manager


def _drain(streamer: AssetStreamingManager) -> None:
    for _ in range(100):
        streamer.pump(max_completions=16)
        if streamer.diagnostics().pending == 0:
            return
        sleep(0.005)
    raise AssertionError("streaming queue did not drain")


def test_stage_many_loads_in_background_and_pump_finalizes_ready_assets(tmp_path):
    manager = _manager(tmp_path, 3)
    with AssetStreamingManager(manager) as streamer:
        futures = streamer.stage_many(["asset-0.txt", "asset-1.txt", "asset-2.txt"])
        assert len(futures) == 3
        _drain(streamer)
        diag = streamer.diagnostics()

    assert diag.staged == 3
    assert diag.completed == 3
    assert diag.failed == 0
    assert diag.pending == 0
    assert diag.resident_assets == 3
    assert manager.cached("asset-0.txt")


def test_lru_budget_evicts_oldest_unpinned_asset(tmp_path):
    manager = _manager(tmp_path, 3)
    budget = AssetStreamingBudget(max_resident_bytes=1024, max_resident_assets=2)
    with AssetStreamingManager(manager, budget=budget) as streamer:
        streamer.stage("asset-0.txt")
        streamer.stage("asset-1.txt")
        _drain(streamer)
        assert streamer.touch("asset-0.txt")
        streamer.stage("asset-2.txt")
        _drain(streamer)
        residents = tuple(item.path.name for item in streamer.resident())
        diag = streamer.diagnostics()

    assert residents == ("asset-0.txt", "asset-2.txt")
    assert diag.evictions == 1
    assert not manager.cached("asset-1.txt")


def test_byte_budget_is_enforced_with_deterministic_estimator(tmp_path):
    manager = _manager(tmp_path, 3)
    budget = AssetStreamingBudget(max_resident_bytes=20, max_resident_assets=10)
    sizes = {"asset-0.txt": 12, "asset-1.txt": 12, "asset-2.txt": 4}

    def estimate(path, value):
        return sizes[path.name]

    with AssetStreamingManager(manager, budget=budget, size_estimator=estimate) as streamer:
        streamer.stage_many(["asset-0.txt", "asset-1.txt"])
        _drain(streamer)
        assert streamer.diagnostics().resident_bytes == 12
        streamer.stage("asset-2.txt")
        _drain(streamer)
        diag = streamer.diagnostics()

    assert diag.resident_bytes == 16
    assert diag.evictions == 1


def test_pinned_assets_survive_budget_pressure_until_explicitly_unpinned(tmp_path):
    manager = _manager(tmp_path, 3)
    budget = AssetStreamingBudget(max_resident_bytes=1024, max_resident_assets=1)
    with AssetStreamingManager(manager, budget=budget) as streamer:
        streamer.stage("asset-0.txt", pin=True)
        _drain(streamer)
        streamer.stage("asset-1.txt")
        _drain(streamer)
        names = tuple(item.path.name for item in streamer.resident())
        assert names == ("asset-0.txt",)
        assert streamer.unpin("asset-0.txt")
        streamer.stage("asset-2.txt")
        _drain(streamer)
        final_names = tuple(item.path.name for item in streamer.resident())

    assert final_names == ("asset-2.txt",)


def test_duplicate_stage_shares_inflight_request(tmp_path):
    manager = _manager(tmp_path, 1)

    def slow_loader(path):
        sleep(0.03)
        return path.read_text(encoding="utf-8")

    manager.register_loader("txt", slow_loader)
    with AssetStreamingManager(manager) as streamer:
        first = streamer.stage("asset-0.txt")
        second = streamer.stage("asset-0.txt")
        assert first is second
        _drain(streamer)

    assert streamer.diagnostics().staged == 1


def test_pump_never_waits_for_unfinished_background_work(tmp_path):
    manager = _manager(tmp_path, 1)

    def slow_loader(path):
        sleep(0.05)
        return path.read_text(encoding="utf-8")

    manager.register_loader("txt", slow_loader)
    with AssetStreamingManager(manager) as streamer:
        streamer.stage("asset-0.txt")
        started = __import__("time").perf_counter()
        completed = streamer.pump(max_completions=1)
        elapsed = __import__("time").perf_counter() - started
        _drain(streamer)

    assert completed == ()
    assert elapsed < 0.03


def test_invalid_budgets_and_pump_limits_are_rejected(tmp_path):
    manager = _manager(tmp_path, 1)
    for kwargs in (
        {"max_resident_bytes": 0},
        {"max_resident_assets": 0},
        {"hitch_threshold_ms": -1.0},
    ):
        try:
            AssetStreamingBudget(**kwargs)
        except ValueError:
            pass
        else:
            raise AssertionError(f"expected ValueError for {kwargs}")

    with AssetStreamingManager(manager) as streamer:
        try:
            streamer.pump(max_completions=0)
        except ValueError:
            pass
        else:
            raise AssertionError("expected ValueError")
