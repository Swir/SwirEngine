from __future__ import annotations

import math

import pytest

from swirengine.server16 import (
    SERVER_SAFE_ASSET_KINDS,
    DedicatedServerRuntime,
    ServerAssetKind,
    ServerAssetReference,
    ServerConfig,
    ServerPhase,
    ServerRuntimeError,
    ServerStartupCheck,
)


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0
        self.sleeps: list[float] = []

    def __call__(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        assert seconds >= 0.0
        self.sleeps.append(seconds)
        self.now += seconds


def test_server_config_validates_bounds_and_loads_environment() -> None:
    config = ServerConfig.from_env(
        environ={
            "SWIR_SERVER_NAME": "EU-1",
            "SWIR_SERVER_TICK_RATE_HZ": "30",
            "SWIR_SERVER_MAX_CATCH_UP_TICKS": "6",
            "SWIR_SERVER_READY_AFTER_TICKS": "3",
            "SWIR_SERVER_MAX_EVENTS": "64",
            "SWIR_SERVER_MAX_ASSETS": "128",
        }
    )

    assert config.server_name == "EU-1"
    assert config.tick_rate_hz == 30.0
    assert config.fixed_dt == pytest.approx(1.0 / 30.0)
    assert config.max_catch_up_ticks == 6
    assert config.ready_after_ticks == 3
    assert config.max_events == 64
    assert config.max_assets == 128

    with pytest.raises(ValueError, match="exceed 1000"):
        ServerConfig(tick_rate_hz=1001)
    with pytest.raises(TypeError, match="integer"):
        ServerConfig(max_catch_up_ticks=True)
    with pytest.raises(ValueError, match="finite"):
        ServerConfig(tick_rate_hz=math.inf)


def test_asset_references_require_normalized_relative_paths() -> None:
    asset = ServerAssetReference("maps/arena.json", ServerAssetKind.MAP)
    assert asset.path == "maps/arena.json"
    assert asset.kind in SERVER_SAFE_ASSET_KINDS

    with pytest.raises(ValueError, match="normalized relative"):
        ServerAssetReference("../secret.json")
    with pytest.raises(ValueError, match="normalized relative"):
        ServerAssetReference("maps//arena.json")
    with pytest.raises(ValueError, match="normalized relative"):
        ServerAssetReference("/absolute/map.json")


def test_client_only_asset_is_rejected_before_creator_start_callback() -> None:
    started: list[str] = []
    runtime = DedicatedServerRuntime(
        on_start=lambda _runtime: started.append("start"),
        assets=(ServerAssetReference("textures/player.png", ServerAssetKind.TEXTURE),),
    )

    with pytest.raises(ServerRuntimeError) as exc:
        runtime.start()

    assert exc.value.code == "client_only_asset"
    assert runtime.phase is ServerPhase.FAILED
    assert started == []
    assert runtime.health().failure_code == "client_only_asset"


def test_startup_checks_are_ordered_and_fail_atomically_before_start() -> None:
    order: list[str] = []
    runtime = DedicatedServerRuntime(
        startup_checks=(
            ServerStartupCheck("database", lambda: order.append("database") or True),
            ServerStartupCheck("content", lambda: order.append("content") or False),
            ServerStartupCheck("never", lambda: order.append("never") or True),
        ),
        on_start=lambda _runtime: order.append("start"),
    )

    with pytest.raises(ServerRuntimeError) as exc:
        runtime.start()

    assert exc.value.code == "startup_check_failed"
    assert order == ["database", "content"]
    health = runtime.health()
    assert health.phase is ServerPhase.FAILED
    assert health.startup_checks_passed == 1
    assert health.startup_checks_total == 3
    assert not health.ready


def test_fixed_tick_harness_uses_constant_dt_and_readiness_threshold() -> None:
    dts: list[float] = []
    runtime = DedicatedServerRuntime(
        config=ServerConfig(tick_rate_hz=20, ready_after_ticks=3),
        on_tick=lambda _runtime, dt: dts.append(dt),
    )

    started = runtime.start()
    assert started.phase is ServerPhase.RUNNING
    assert not started.ready

    runtime.run_ticks(2)
    assert runtime.tick == 2
    assert not runtime.ready

    runtime.run_ticks(1)
    assert runtime.tick == 3
    assert runtime.ready
    assert dts == [0.05, 0.05, 0.05]

    stopped = runtime.shutdown("test-complete")
    assert stopped.phase is ServerPhase.STOPPED
    assert stopped.stop_reason == "test-complete"


def test_real_scheduler_bounds_catch_up_and_accounts_for_dropped_ticks() -> None:
    clock = FakeClock()
    dts: list[float] = []

    def tick(runtime: DedicatedServerRuntime, dt: float) -> None:
        dts.append(dt)
        if runtime.tick == 0:
            clock.now += 0.035

    runtime = DedicatedServerRuntime(
        config=ServerConfig(tick_rate_hz=100, max_catch_up_ticks=2, ready_after_ticks=0),
        on_tick=tick,
        clock=clock,
        sleeper=clock.sleep,
    )

    health = runtime.run(max_ticks=4, install_signal_handlers=False)

    assert health.phase is ServerPhase.STOPPED
    assert health.tick == 4
    assert health.dropped_ticks == 1
    assert dts == [0.01, 0.01, 0.01, 0.01]
    assert sum(clock.sleeps) == pytest.approx(0.005)
    assert any(event.kind == "schedule.ticks_dropped" for event in runtime.events)


def test_graceful_shutdown_calls_stop_once_and_clears_readiness() -> None:
    lifecycle: list[str] = []
    runtime = DedicatedServerRuntime(
        config=ServerConfig(ready_after_ticks=1),
        on_start=lambda _runtime: lifecycle.append("start"),
        on_stop=lambda _runtime: lifecycle.append("stop"),
    )
    runtime.start()
    runtime.run_ticks(1)
    assert runtime.ready

    first = runtime.shutdown("operator")
    second = runtime.shutdown("ignored")

    assert first.phase is ServerPhase.STOPPED
    assert second.phase is ServerPhase.STOPPED
    assert not second.ready
    assert second.stop_reason == "operator"
    assert lifecycle == ["start", "stop"]


def test_run_max_ticks_performs_graceful_stop() -> None:
    clock = FakeClock()
    stops: list[int] = []
    runtime = DedicatedServerRuntime(
        config=ServerConfig(tick_rate_hz=50, ready_after_ticks=1),
        on_stop=lambda current: stops.append(current.tick),
        clock=clock,
        sleeper=clock.sleep,
    )

    health = runtime.run(max_ticks=5, install_signal_handlers=False)

    assert health.phase is ServerPhase.STOPPED
    assert health.tick == 5
    assert health.stop_reason == "max_ticks"
    assert stops == [5]


def test_tick_failure_transitions_to_failed_and_runs_cleanup_once() -> None:
    stopped: list[str] = []

    def broken_tick(_runtime: DedicatedServerRuntime, _dt: float) -> None:
        raise RuntimeError("boom")

    runtime = DedicatedServerRuntime(
        on_tick=broken_tick,
        on_stop=lambda _runtime: stopped.append("cleanup"),
    )
    runtime.start()

    with pytest.raises(ServerRuntimeError) as exc:
        runtime.run_ticks(1)

    assert exc.value.code == "tick_failed"
    assert runtime.phase is ServerPhase.FAILED
    assert runtime.health().failure_code == "tick_failed"
    assert runtime.tick == 0
    assert stopped == ["cleanup"]


def test_start_callback_failure_is_failure_isolated_and_cleaned_up() -> None:
    lifecycle: list[str] = []

    def broken_start(_runtime: DedicatedServerRuntime) -> None:
        lifecycle.append("start")
        raise RuntimeError("bind failed")

    runtime = DedicatedServerRuntime(
        on_start=broken_start,
        on_stop=lambda _runtime: lifecycle.append("stop"),
    )

    with pytest.raises(ServerRuntimeError) as exc:
        runtime.start()

    assert exc.value.code == "startup_failed"
    assert runtime.phase is ServerPhase.FAILED
    assert lifecycle == ["start", "stop"]


def test_event_history_is_bounded_and_diagnostics_are_payload_free() -> None:
    runtime = DedicatedServerRuntime(
        config=ServerConfig(max_events=3, ready_after_ticks=1),
        startup_checks=(ServerStartupCheck("content", lambda: True),),
        assets=(ServerAssetReference("maps/arena.json", ServerAssetKind.MAP),),
    )
    runtime.start()
    runtime.run_ticks(2)
    runtime.shutdown("done")

    diagnostics = runtime.diagnostics()
    assert diagnostics["event_count"] == 3
    assert diagnostics["event_evictions"] >= 1
    assert diagnostics["asset_count"] == 1
    assert diagnostics["phase"] == "stopped"
    assert [event["sequence"] for event in diagnostics["events"]] == sorted(
        event["sequence"] for event in diagnostics["events"]
    )
    assert all(
        set(event) == {"sequence", "kind", "tick", "detail"}
        for event in diagnostics["events"]
    )


def test_asset_manifest_is_sorted_and_duplicate_safe() -> None:
    runtime = DedicatedServerRuntime(
        assets=(
            ServerAssetReference("maps/z.json", ServerAssetKind.MAP),
            ServerAssetReference("config/server.json", ServerAssetKind.CONFIG),
            ServerAssetReference("maps/a.json", ServerAssetKind.MAP),
        )
    )
    assert [(asset.kind.value, asset.path) for asset in runtime.assets] == [
        ("config", "config/server.json"),
        ("map", "maps/a.json"),
        ("map", "maps/z.json"),
    ]

    with pytest.raises(ValueError, match="duplicate"):
        DedicatedServerRuntime(
            assets=(
                ServerAssetReference("maps/a.json", ServerAssetKind.MAP),
                ServerAssetReference("maps/a.json", ServerAssetKind.MAP),
            )
        )


def test_request_stop_before_start_is_safe_and_does_not_call_lifecycle_callbacks() -> None:
    calls: list[str] = []
    runtime = DedicatedServerRuntime(
        on_start=lambda _runtime: calls.append("start"),
        on_stop=lambda _runtime: calls.append("stop"),
    )

    runtime.request_stop("maintenance")

    assert runtime.phase is ServerPhase.STOPPED
    assert runtime.health().stop_reason == "maintenance"
    assert calls == []
    with pytest.raises(ServerRuntimeError) as exc:
        runtime.start()
    assert exc.value.code == "invalid_phase"
