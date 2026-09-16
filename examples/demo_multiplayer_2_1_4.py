from __future__ import annotations

from swirengine.multiplayer14 import (
    ClientPredictor,
    LagCompensationHistory,
    MultiplayerBandwidthDiagnostics,
    MultiplayerPacketCodec,
    PredictionCommand,
    ReplicationField,
    ReplicationRegistry,
    SnapshotBuffer,
    SnapshotDelta,
    WorldSnapshot,
)


def build_snapshot(
    registry: ReplicationRegistry,
    tick: int,
    server_time: float,
    x: float,
    hp: int,
) -> WorldSnapshot:
    player = registry.capture(
        1,
        {
            "transform": {"x": x, "y": 0.0, "animation": "run"},
            "health": {"hp": hp},
        },
    )
    return WorldSnapshot(tick, server_time, (player,))


def main() -> None:
    registry = ReplicationRegistry()
    registry.define(
        "transform",
        (
            ReplicationField("x"),
            ReplicationField("y"),
            ReplicationField("animation", interpolate=False),
        ),
    )
    registry.define("health", ("hp",))

    first = build_snapshot(registry, 40, 2.00, 10.0, 100)
    second = build_snapshot(registry, 41, 2.05, 12.0, 95)
    delta = SnapshotDelta.between(first, second)
    assert delta.apply(first) == second

    interpolation = SnapshotBuffer(registry=registry)
    interpolation.push(first)
    interpolation.push(second)
    render = interpolation.sample(2.025)
    render_x = render.entities[0].components["transform"]["x"]

    def simulate(state: dict[str, object], command: PredictionCommand) -> dict[str, object]:
        return {"x": float(state["x"]) + float(command.payload["dx"])}

    predictor = ClientPredictor({"x": 10.0}, simulate)
    predictor.predict(PredictionCommand(1, 41, {"dx": 1.0}))
    predictor.predict(PredictionCommand(2, 42, {"dx": 1.0}))
    reconciliation = predictor.reconcile(1, {"x": 10.8})

    lag_history = LagCompensationHistory(registry=registry)
    lag_history.record(first)
    lag_history.record(second)
    rewind = lag_history.rewind(2.025)
    rewind_x = rewind.entities[0].components["transform"]["x"]

    diagnostics = MultiplayerBandwidthDiagnostics()
    snapshot_packet = MultiplayerPacketCodec.snapshot_packet(second)
    delta_packet = MultiplayerPacketCodec.delta_packet(delta)
    diagnostics.record_sent(snapshot_packet.to_bytes(), channel="snapshot")
    diagnostics.record_sent(delta_packet.to_bytes(), channel="delta")
    report = diagnostics.report(1.0)

    print(
        "SwirEngine Multiplayer 2.0 demo "
        f"render_x={render_x:.2f} "
        f"predicted_x={float(reconciliation.state['x']):.2f} "
        f"rewind_x={rewind_x:.2f} "
        f"sent={report.sent_bytes}B"
    )


if __name__ == "__main__":
    main()
