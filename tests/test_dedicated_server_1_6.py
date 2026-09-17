from __future__ import annotations

from dataclasses import replace

import pytest

from swirengine.server16 import (
    DedicatedServerConfig,
    DedicatedServerRuntime,
    HeadlessRuntimeBoundary,
    ServerAssetRequirement,
    ServerComponent,
    ServerRuntimeError,
    ServerState,
)


class _FakeTime:
    def __init__(self) -> None:
        self.value = 100.0

    def monotonic(self) -> float:
        return self.value

    def sleep(self, seconds: float) -> None:
        self.value += seconds


def test_config_validates_mapping_and_environment_inputs() -> None:
    config = DedicatedServerConfig.from_mapping(
        {
            "tick_rate_hz": 20,
            "max_catchup_ticks": 3,
            "instance_id": "eu-1",
            "environment": "staging",
        }
    )
    assert config.tick_seconds == pytest.approx(0.05)
    assert config.portable()["instance_id"] == "eu-1"

    from_env = DedicatedServerConfig.from_env(
        environ={
            "SWIRENGINE_SERVER_TICK_RATE_HZ": "25",
            "SWIRENGINE_SERVER_MAX_CATCHUP_TICKS": "6",
            "SWIRENGINE_SERVER_INSTANCE_ID": "container-a",
        }
    )
    assert from_env.tick_rate_hz == 25.0
    assert from_env.max_catchup_ticks == 6
    assert from_env.instance_id == "container-a"

    with pytest.raises(ValueError, match="unknown"):
        DedicatedServerConfig.from_mapping({"renderer": "on"})
    with pytest.raises(TypeError, match="integer"):
        DedicatedServerConfig(max_catchup_ticks=True)
    with pytest.raises(ValueError, match="invalid environment"):
        DedicatedServerConfig.from_env(
            environ={"SWIRENGINE_SERVER_MAX_CATCHUP_TICKS": "not-an-int"}
        )


def test_asset_requirements_reject_absolute_and_traversal_paths() -> None:
    assert ServerAssetRequirement("world/maps/arena.json", "map").path == "world/maps/arena.json"
    with pytest.raises(ValueError, match="project-relative"):
        ServerAssetRequirement("../secret.json")
    with pytest.raises(ValueError, match="project-relative"):
        ServerAssetRequirement("/etc/passwd")


def test_headless_boundary_rejects_renderer_audio_and_texture_requirements() -> None:
    runtime = DedicatedServerRuntime()
    runtime.register(ServerComponent("net", lambda tick: None, capabilities=("network",)))
    runtime.register(ServerComponent("render", lambda tick: None, capabilities=("graphics",)))

    with pytest.raises(ServerRuntimeError) as forbidden:
        runtime.validate_startup()
    assert forbidden.value.code == "headless_capability_forbidden"

    other = DedicatedServerRuntime()
    other.register(
        ServerComponent(
            "data",
            lambda tick: None,
            assets=(ServerAssetRequirement("textures/ui.png", "texture"),),
        )
    )
    with pytest.raises(ServerRuntimeError) as asset:
        other.validate_startup()
    assert asset.value.code == "headless_asset_forbidden"


def test_component_order_is_dependency_first_and_registration_order_independent() -> None:
    runtime = DedicatedServerRuntime()
    runtime.register(ServerComponent("world", lambda tick: None, dependencies=("session",)))
    runtime.register(ServerComponent("transport", lambda tick: None))
    runtime.register(ServerComponent("session", lambda tick: None, dependencies=("transport",)))
    runtime.register(ServerComponent("metrics", lambda tick: None))

    report = runtime.validate_startup()

    assert report.component_order == ("metrics", "transport", "session", "world")


def test_missing_dependency_and_cycle_fail_before_any_startup_hook_runs() -> None:
    calls: list[str] = []
    runtime = DedicatedServerRuntime()
    runtime.register(
        ServerComponent(
            "world",
            lambda tick: None,
            startup=lambda ctx: calls.append("world"),
            dependencies=("missing",),
        )
    )
    with pytest.raises(ServerRuntimeError) as missing:
        runtime.start()
    assert missing.value.code == "missing_dependency"
    assert calls == []
    assert runtime.state is ServerState.STOPPED

    cycle = DedicatedServerRuntime()
    cycle.register(ServerComponent("a", lambda tick: None, dependencies=("b",)))
    cycle.register(ServerComponent("b", lambda tick: None, dependencies=("a",)))
    with pytest.raises(ServerRuntimeError) as cyclic:
        cycle.validate_startup()
    assert cyclic.value.code == "dependency_cycle"


def test_required_asset_probe_runs_before_startup_and_optional_assets_do_not_block() -> None:
    calls: list[str] = []

    def probe(requirement: ServerAssetRequirement) -> bool:
        calls.append(requirement.path)
        return requirement.path != "maps/missing.json"

    runtime = DedicatedServerRuntime(asset_probe=probe)
    runtime.register(
        ServerComponent(
            "world",
            lambda tick: None,
            assets=(
                ServerAssetRequirement("maps/missing.json", "map"),
                ServerAssetRequirement("metadata/optional.json", "metadata", required=False),
            ),
        )
    )

    with pytest.raises(ServerRuntimeError) as missing:
        runtime.start()
    assert missing.value.code == "required_asset_missing"
    assert runtime.state is ServerState.STOPPED
    assert calls == ["maps/missing.json"]


def test_startup_failure_rolls_back_started_components_in_reverse_order() -> None:
    events: list[str] = []

    def failing_startup(ctx: object) -> None:
        events.append("start:c")
        raise RuntimeError("boom")

    runtime = DedicatedServerRuntime()
    runtime.register(
        ServerComponent(
            "a",
            lambda tick: None,
            startup=lambda ctx: events.append("start:a"),
            shutdown=lambda ctx: events.append("stop:a"),
        )
    )
    runtime.register(
        ServerComponent(
            "b",
            lambda tick: None,
            startup=lambda ctx: events.append("start:b"),
            shutdown=lambda ctx: events.append("stop:b"),
            dependencies=("a",),
        )
    )
    runtime.register(
        ServerComponent(
            "c",
            lambda tick: None,
            startup=failing_startup,
            shutdown=lambda ctx: events.append("stop:c"),
            dependencies=("b",),
        )
    )

    with pytest.raises(ServerRuntimeError) as failed:
        runtime.start()

    assert failed.value.code == "startup_failed"
    assert events == ["start:a", "start:b", "start:c", "stop:c", "stop:b", "stop:a"]
    assert runtime.state is ServerState.FAILED
    assert runtime.health().ready is False


def test_fixed_ticks_use_constant_dt_and_dependency_order() -> None:
    fake = _FakeTime()
    seen: list[tuple[str, int, float]] = []
    runtime = DedicatedServerRuntime(
        DedicatedServerConfig(tick_rate_hz=20.0),
        monotonic=fake.monotonic,
        sleeper=fake.sleep,
    )
    runtime.register(
        ServerComponent("net", lambda tick: seen.append(("net", tick.tick, tick.dt)))
    )
    runtime.register(
        ServerComponent(
            "world",
            lambda tick: seen.append(("world", tick.tick, tick.dt)),
            dependencies=("net",),
        )
    )
    runtime.start()

    ticks = runtime.run_ticks(3)

    assert [tick.tick for tick in ticks] == [1, 2, 3]
    assert [tick.simulation_time for tick in ticks] == pytest.approx([0.05, 0.10, 0.15])
    assert seen == [
        ("net", 1, 0.05),
        ("world", 1, 0.05),
        ("net", 2, 0.05),
        ("world", 2, 0.05),
        ("net", 3, 0.05),
        ("world", 3, 0.05),
    ]
    runtime.stop("test_complete")


def test_readiness_and_health_probes_are_fault_contained() -> None:
    readiness = {"ready": False}
    health = {"explode": False}

    def health_check() -> bool:
        if health["explode"]:
            raise RuntimeError("probe failed")
        return True

    runtime = DedicatedServerRuntime()
    runtime.register(
        ServerComponent(
            "world",
            lambda tick: None,
            ready_check=lambda: readiness["ready"],
            health_check=health_check,
        )
    )
    runtime.start()

    first = runtime.health()
    assert first.healthy is True
    assert first.ready is False

    readiness["ready"] = True
    assert runtime.health().ready is True

    health["explode"] = True
    degraded = runtime.health()
    assert degraded.healthy is False
    assert degraded.ready is False
    assert runtime.state is ServerState.RUNNING
    assert runtime.diagnostics()["health_failures"] >= 1


def test_shutdown_request_is_idempotent_and_immediately_removes_readiness() -> None:
    runtime = DedicatedServerRuntime()
    runtime.register(ServerComponent("world", lambda tick: None))
    runtime.start()
    assert runtime.health().ready is True

    assert runtime.request_shutdown("deployment") is True
    assert runtime.request_shutdown("other") is False
    health = runtime.health()
    assert health.ready is False
    assert health.shutdown_reason == "deployment"
    assert runtime.run_ticks(2) == ()

    stopped = runtime.stop()
    assert stopped.state is ServerState.STOPPED
    assert stopped.shutdown_reason == "deployment"


def test_tick_failure_is_atomic_for_tick_counter_and_cleanup_still_runs() -> None:
    events: list[str] = []

    def fail_on_second(tick: object) -> None:
        if tick.tick == 2:
            raise RuntimeError("bad world step")
        events.append(f"tick:{tick.tick}")

    runtime = DedicatedServerRuntime()
    runtime.register(
        ServerComponent(
            "world",
            fail_on_second,
            shutdown=lambda ctx: events.append("shutdown"),
        )
    )
    runtime.start()
    runtime.run_ticks(1)

    with pytest.raises(ServerRuntimeError) as failed:
        runtime.run_ticks(1)
    assert failed.value.code == "tick_failed"
    assert runtime.tick == 1
    assert runtime.state is ServerState.FAILED

    health = runtime.stop()
    assert health.state is ServerState.FAILED
    assert events == ["tick:1", "shutdown"]


def test_shutdown_continues_in_reverse_order_when_one_hook_fails() -> None:
    events: list[str] = []

    def stop_b(ctx: object) -> None:
        events.append("stop:b")
        raise RuntimeError("cannot flush")

    runtime = DedicatedServerRuntime()
    runtime.register(
        ServerComponent("a", lambda tick: None, shutdown=lambda ctx: events.append("stop:a"))
    )
    runtime.register(
        ServerComponent(
            "b",
            lambda tick: None,
            dependencies=("a",),
            shutdown=stop_b,
        )
    )
    runtime.start()

    health = runtime.stop("rolling_restart")

    assert events == ["stop:b", "stop:a"]
    assert health.state is ServerState.FAILED
    assert health.last_error_code == "shutdown_failed"
    assert runtime.diagnostics()["shutdown_failures"] == 1


def test_serve_uses_fixed_cadence_and_stops_cleanly_at_tick_limit() -> None:
    fake = _FakeTime()
    ticks: list[int] = []
    runtime = DedicatedServerRuntime(
        DedicatedServerConfig(tick_rate_hz=10.0, max_sleep_seconds=0.025),
        monotonic=fake.monotonic,
        sleeper=fake.sleep,
    )
    runtime.register(ServerComponent("world", lambda tick: ticks.append(tick.tick)))

    health = runtime.serve(max_ticks=5)

    assert ticks == [1, 2, 3, 4, 5]
    assert health.state is ServerState.STOPPED
    assert health.shutdown_requested is True
    assert health.shutdown_reason == "max_ticks_reached"
    assert runtime.diagnostics()["ticks_executed"] == 5


def test_serve_bounds_catchup_and_accounts_for_dropped_tick_slots() -> None:
    fake = _FakeTime()
    calls = {"count": 0}

    def tick(step: object) -> None:
        calls["count"] += 1
        if calls["count"] == 1:
            fake.value += 1.0

    runtime = DedicatedServerRuntime(
        DedicatedServerConfig(tick_rate_hz=10.0, max_catchup_ticks=2),
        monotonic=fake.monotonic,
        sleeper=fake.sleep,
    )
    runtime.register(ServerComponent("world", tick))

    runtime.serve(max_ticks=4)

    assert runtime.tick == 4
    assert runtime.diagnostics()["dropped_tick_slots"] >= 8


def test_diagnostics_are_payload_only_and_do_not_expose_callbacks() -> None:
    runtime = DedicatedServerRuntime(
        DedicatedServerConfig(instance_id="server-42", environment="prod")
    )
    runtime.register(ServerComponent("world", lambda tick: None, capabilities=("metrics",)))
    runtime.start()
    runtime.run_ticks(2)

    diagnostics = runtime.diagnostics()
    health = runtime.health().portable()

    assert diagnostics["component_order"] == ["world"]
    assert diagnostics["config"]["instance_id"] == "server-42"
    assert diagnostics["ticks_executed"] == 2
    assert health["components"] == {"world": {"healthy": True, "ready": True}}
    assert "callback" not in repr(diagnostics).lower()
    runtime.stop("done")


def test_shutdown_grace_budget_is_measured_without_skipping_cleanup() -> None:
    fake = _FakeTime()
    events: list[str] = []

    def slow_shutdown(ctx: object) -> None:
        events.append("stop")
        fake.value += 0.25

    runtime = DedicatedServerRuntime(
        DedicatedServerConfig(shutdown_grace_seconds=0.1),
        monotonic=fake.monotonic,
        sleeper=fake.sleep,
    )
    runtime.register(ServerComponent("world", lambda tick: None, shutdown=slow_shutdown))
    runtime.start()

    health = runtime.stop("deploy")

    assert events == ["stop"]
    assert health.state is ServerState.STOPPED
    assert health.healthy is False
    assert runtime.diagnostics()["shutdown_grace_exceeded"] == 1


def test_boundary_can_be_explicitly_narrowed_for_hardened_hosts() -> None:
    boundary = HeadlessRuntimeBoundary(
        allowed_capabilities=frozenset({"network", "metrics"}),
        allowed_asset_kinds=frozenset({"metadata"}),
    )
    runtime = DedicatedServerRuntime(boundary=boundary)
    runtime.register(
        ServerComponent(
            "net",
            lambda tick: None,
            capabilities=("network",),
            assets=(ServerAssetRequirement("server/manifest.json", "metadata"),),
        )
    )
    assert runtime.validate_startup().component_order == ("net",)

    broader = replace(boundary, allowed_capabilities=frozenset({"network", "filesystem"}))
    assert "filesystem" in broader.allowed_capabilities
