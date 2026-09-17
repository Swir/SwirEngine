from __future__ import annotations

import json
import os

from swirengine.server16 import (
    DedicatedServerRuntime,
    ServerAssetKind,
    ServerAssetReference,
    ServerConfig,
    ServerStartupCheck,
)


def _positive_env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    value = default if raw is None else int(raw)
    if value < 1:
        raise ValueError(f"{name} must be positive")
    return value


def main() -> None:
    config = ServerConfig.from_env()
    max_ticks = _positive_env_int("SWIR_SERVER_MAX_TICKS", 12)
    state = {"simulation_ticks": 0}

    def tick(_runtime: DedicatedServerRuntime, _dt: float) -> None:
        state["simulation_ticks"] += 1

    runtime = DedicatedServerRuntime(
        config=config,
        on_tick=tick,
        startup_checks=(
            ServerStartupCheck("content-manifest", lambda: True),
            ServerStartupCheck("session-backend", lambda: True),
        ),
        assets=(
            ServerAssetReference("config/server.json", ServerAssetKind.CONFIG),
            ServerAssetReference("maps/arena.json", ServerAssetKind.MAP),
        ),
    )

    health = runtime.run(max_ticks=max_ticks)
    if health.failure_code is not None or health.tick != max_ticks:
        raise SystemExit("dedicated server did not complete the requested smoke workload")

    print(
        json.dumps(
            {
                "health": health.portable(),
                "simulation_ticks": state["simulation_ticks"],
                "diagnostics": runtime.diagnostics(),
            },
            sort_keys=True,
            separators=(",", ":"),
        )
    )


if __name__ == "__main__":
    main()
