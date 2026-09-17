from __future__ import annotations

from swirengine.server16 import DedicatedServerConfig, DedicatedServerRuntime, ServerComponent


def main() -> None:
    players = {"connected": 2}
    world = {"steps": 0}

    runtime = DedicatedServerRuntime(
        DedicatedServerConfig(
            tick_rate_hz=30.0,
            max_catchup_ticks=4,
            instance_id="demo-server",
            environment="development",
        )
    )
    runtime.register(
        ServerComponent(
            "network",
            lambda tick: None,
            capabilities=("network", "metrics"),
            health_check=lambda: True,
            ready_check=lambda: players["connected"] >= 1,
        )
    )
    runtime.register(
        ServerComponent(
            "world",
            lambda tick: world.__setitem__("steps", world["steps"] + 1),
            dependencies=("network",),
            capabilities=("clock", "storage"),
        )
    )

    report = runtime.start()
    runtime.run_ticks(120)
    health = runtime.health()
    runtime.stop("demo_complete")

    print("Dedicated Server 1.6 demo")
    print(f"startup order: {report.component_order}")
    print(f"world steps: {world['steps']}")
    print(f"ready before shutdown: {health.ready}")
    print(f"diagnostics: {runtime.diagnostics()}")


if __name__ == "__main__":
    main()
