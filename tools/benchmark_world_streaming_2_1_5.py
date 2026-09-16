from __future__ import annotations

from time import perf_counter

from swirengine.core.scene import Scene
from swirengine.large_world import ChunkContent, ChunkKey
from swirengine.world_streaming15 import (
    WorldPartitionCell,
    WorldPartitionRegistry,
    WorldStreamingRuntime,
    WorldStreamingSettings,
)

GRID = 100
UPDATES = 1200
RADIUS = 2
BUDGET_SECONDS = 3.0


def empty_factory(_ctx):
    return ChunkContent()


def main() -> None:
    cells = (
        WorldPartitionCell(
            f"{x}:{y}",
            ChunkKey(x, y, 0),
            empty_factory,
        )
        for y in range(GRID)
        for x in range(GRID)
    )
    registry = WorldPartitionRegistry(cells)
    runtime = WorldStreamingRuntime(
        Scene(),
        registry,
        settings=WorldStreamingSettings(
            dimensions=2,
            chunk_size=32.0,
            active_radius_chunks=RADIUS,
            max_active_cost=(RADIUS * 2 + 1) ** 2,
            max_activations_per_update=32,
            max_deactivations_per_update=32,
            retention_updates=0,
        ),
    )

    started = perf_counter()
    for index in range(UPDATES):
        x = float(index % GRID) * 32.0 + 1.0
        y = float((index * 7) % GRID) * 32.0 + 1.0
        runtime.update((x, y))
    elapsed = perf_counter() - started

    diagnostics = runtime.diagnostics
    max_local_keys = (RADIUS * 2 + 1) ** 2
    if diagnostics.local_keys != max_local_keys:
        raise RuntimeError(
            f"streaming local-window regression: {diagnostics.local_keys} != {max_local_keys}"
        )

    print(
        f"{GRID * GRID} registered cells, {UPDATES} focus updates: "
        f"{elapsed:.6f}s (budget {BUDGET_SECONDS}s)"
    )
    print(
        f"local_keys={diagnostics.local_keys} active={diagnostics.active_cells} "
        f"activations={diagnostics.total_activations} "
        f"deactivations={diagnostics.total_deactivations} "
        f"fingerprint={runtime.state_fingerprint()[:16]}"
    )
    if elapsed > BUDGET_SECONDS:
        raise SystemExit(
            f"world streaming workload exceeded budget: "
            f"{elapsed:.6f}s > {BUDGET_SECONDS}s"
        )


if __name__ == "__main__":
    main()
