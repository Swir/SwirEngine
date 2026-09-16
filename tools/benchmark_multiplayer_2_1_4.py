from __future__ import annotations

from time import perf_counter

from swirengine.multiplayer14 import (
    ClientPredictor,
    LagCompensationHistory,
    PredictionCommand,
    ReplicationField,
    ReplicationRegistry,
    SnapshotBuffer,
    SnapshotDelta,
    WorldSnapshot,
)

ENTITY_COUNT = 500
SAMPLE_COUNT = 120
BUDGET_SECONDS = 3.0


def _registry() -> ReplicationRegistry:
    registry = ReplicationRegistry()
    registry.define(
        "transform",
        (
            ReplicationField("x"),
            ReplicationField("y"),
            ReplicationField("z"),
            ReplicationField("mode", interpolate=False),
        ),
    )
    registry.define("health", ("hp",))
    return registry


def _snapshot(
    registry: ReplicationRegistry,
    tick: int,
    server_time: float,
    offset: float,
    *,
    changed_limit: int | None = None,
) -> WorldSnapshot:
    entities = tuple(
        registry.capture(
            net_id,
            {
                "transform": {
                    "x": net_id + (offset if changed_limit is None or net_id <= changed_limit else 0.0),
                    "y": net_id * 0.5 + (offset if changed_limit is None or net_id <= changed_limit else 0.0),
                    "z": offset if changed_limit is None or net_id <= changed_limit else 0.0,
                    "mode": "run",
                },
                "health": {"hp": 100},
            },
        )
        for net_id in range(1, ENTITY_COUNT + 1)
    )
    return WorldSnapshot(tick, server_time, entities)


def main() -> None:
    registry = _registry()
    started = perf_counter()

    baseline = _snapshot(registry, 100, 10.0, 0.0)
    current = _snapshot(registry, 101, 10.05, 1.0, changed_limit=25)
    delta = SnapshotDelta.between(baseline, current)
    restored = delta.apply(baseline)
    if restored != current:
        raise RuntimeError("delta reconstruction mismatch")

    buffer = SnapshotBuffer(registry=registry)
    buffer.push(baseline)
    buffer.push(current)
    for index in range(SAMPLE_COUNT):
        render_time = 10.0 + (0.05 * index / max(1, SAMPLE_COUNT - 1))
        sample = buffer.sample(render_time)
        if len(sample.entities) != ENTITY_COUNT:
            raise RuntimeError("interpolation dropped replicated entities")

    predictor = ClientPredictor(
        {"x": 0.0},
        lambda state, command: {"x": float(state["x"]) + float(command.payload["dx"])},
        max_pending=512,
    )
    for sequence in range(1, 257):
        predictor.predict(PredictionCommand(sequence, sequence, {"dx": 0.25}))
    result = predictor.reconcile(200, {"x": 50.0})
    if result.replayed_commands != 56:
        raise RuntimeError("prediction replay count mismatch")

    lag_history = LagCompensationHistory(
        registry=registry,
        max_seconds=1.0,
        max_frames=64,
    )
    lag_history.record(baseline)
    lag_history.record(current)
    for _ in range(100):
        lag_history.rewind(10.025)

    elapsed = perf_counter() - started
    full_bytes = len(current.to_bytes())
    delta_bytes = len(delta.to_bytes())

    print(
        "multiplayer14 workload "
        f"entities={ENTITY_COUNT} samples={SAMPLE_COUNT} "
        f"full={full_bytes}B delta={delta_bytes}B elapsed={elapsed:.6f}s"
    )
    if delta_bytes >= full_bytes * 0.20:
        raise RuntimeError(
            f"sparse delta is unexpectedly large: full={full_bytes}B delta={delta_bytes}B"
        )
    if elapsed > BUDGET_SECONDS:
        raise RuntimeError(
            f"multiplayer14 workload exceeded {BUDGET_SECONDS:.1f}s budget: {elapsed:.6f}s"
        )


if __name__ == "__main__":
    main()
