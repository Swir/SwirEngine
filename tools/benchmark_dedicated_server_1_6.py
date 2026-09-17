from __future__ import annotations

import time

from swirengine.server16 import DedicatedServerConfig, DedicatedServerRuntime, ServerComponent


def main() -> None:
    ticks = 50_000
    state = {"value": 0}
    runtime = DedicatedServerRuntime(DedicatedServerConfig(tick_rate_hz=60.0))
    runtime.register(
        ServerComponent(
            "simulation",
            lambda tick: state.__setitem__("value", state["value"] + tick.tick),
            capabilities=("metrics",),
        )
    )
    runtime.start()
    started = time.perf_counter()
    runtime.run_ticks(ticks)
    elapsed = time.perf_counter() - started
    runtime.stop("benchmark_complete")

    expected = ticks * (ticks + 1) // 2
    assert state["value"] == expected
    assert runtime.diagnostics()["ticks_executed"] == ticks
    budget_seconds = 3.0
    if elapsed >= budget_seconds:
        raise SystemExit(
            f"dedicated-server workload exceeded {budget_seconds:.1f}s budget: {elapsed:.4f}s"
        )
    print(
        "Dedicated server 1.6 workload: "
        f"{ticks} deterministic ticks in {elapsed:.4f}s (budget < {budget_seconds:.1f}s)"
    )


if __name__ == "__main__":
    main()
