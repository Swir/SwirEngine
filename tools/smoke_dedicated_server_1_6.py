from __future__ import annotations

import json

from swirengine.server16 import DedicatedServerConfig, DedicatedServerRuntime, ServerComponent


def main() -> None:
    state = {"ticks": 0}
    runtime = DedicatedServerRuntime(
        DedicatedServerConfig(
            tick_rate_hz=60.0,
            max_catchup_ticks=4,
            instance_id="linux-wheel-smoke",
            environment="ci",
        )
    )
    runtime.register(
        ServerComponent(
            "network",
            lambda tick: None,
            capabilities=("network", "metrics"),
        )
    )
    runtime.register(
        ServerComponent(
            "simulation",
            lambda tick: state.__setitem__("ticks", state["ticks"] + 1),
            dependencies=("network",),
            capabilities=("clock", "storage"),
        )
    )

    report = runtime.start()
    if not runtime.health().ready:
        raise SystemExit("dedicated server never reached readiness")
    runtime.run_ticks(256)
    if state["ticks"] != 256:
        raise SystemExit(f"expected 256 simulation ticks, got {state['ticks']}")
    runtime.stop("linux_wheel_smoke_complete")
    if runtime.diagnostics()["ticks_executed"] != 256:
        raise SystemExit("tick diagnostics did not match executed smoke workload")

    print(
        json.dumps(
            {
                "component_order": report.component_order,
                "ticks": state["ticks"],
                "state": runtime.state.value,
                "shutdown_reason": runtime.health().shutdown_reason,
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
