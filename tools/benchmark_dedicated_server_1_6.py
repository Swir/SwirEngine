from __future__ import annotations

from time import perf_counter

from swirengine.server16 import (
    DedicatedServerRuntime,
    ServerAssetKind,
    ServerAssetReference,
    ServerConfig,
    ServerStartupCheck,
)


TICKS = 100_000
BUDGET_SECONDS = 2.0


def main() -> None:
    state = {"value": 0}

    def tick(_runtime: DedicatedServerRuntime, _dt: float) -> None:
        state["value"] += 1

    runtime = DedicatedServerRuntime(
        config=ServerConfig(tick_rate_hz=60, ready_after_ticks=1, max_events=32),
        on_tick=tick,
        startup_checks=(ServerStartupCheck("content-index", lambda: True),),
        assets=(
            ServerAssetReference("config/server.json", ServerAssetKind.CONFIG),
            ServerAssetReference("maps/arena.json", ServerAssetKind.MAP),
        ),
    )

    started = perf_counter()
    runtime.start()
    runtime.run_ticks(TICKS)
    runtime.shutdown("benchmark-complete")
    elapsed = perf_counter() - started

    if runtime.tick != TICKS or state["value"] != TICKS:
        raise SystemExit("dedicated-server deterministic tick workload produced an invalid result")
    if elapsed >= BUDGET_SECONDS:
        raise SystemExit(
            f"dedicated-server workload took {elapsed:.4f}s; budget is {BUDGET_SECONDS:.1f}s"
        )

    diagnostics = runtime.diagnostics()
    if diagnostics["event_count"] > runtime.config.max_events:
        raise SystemExit("dedicated-server event history exceeded its configured bound")
    print(
        "Dedicated server 1.6 workload:",
        f"{TICKS} ticks in {elapsed:.4f}s",
        f"events={diagnostics['event_count']}",
        f"event_evictions={diagnostics['event_evictions']}",
    )


if __name__ == "__main__":
    main()
