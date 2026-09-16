from __future__ import annotations

import math

import pytest

from swirengine.multiplayer14 import (
    ClientPredictor,
    LagCompensationHistory,
    MultiplayerBandwidthDiagnostics,
    MultiplayerPacketCodec,
    PredictionCommand,
    ReplicatedEntity,
    ReplicationComponent,
    ReplicationField,
    ReplicationRegistry,
    SnapshotBuffer,
    SnapshotDelta,
    WorldSnapshot,
)


def _registry() -> ReplicationRegistry:
    registry = ReplicationRegistry()
    registry.register(
        ReplicationComponent(
            "transform",
            (
                ReplicationField("x"),
                ReplicationField("y"),
                ReplicationField("stance", interpolate=False),
            ),
        )
    )
    registry.define("health", ("hp",))
    return registry


def _entity(
    registry: ReplicationRegistry,
    net_id: int,
    x: float,
    *,
    hp: int = 100,
    stance: str = "idle",
) -> ReplicatedEntity:
    return registry.capture(
        net_id,
        {
            "transform": {"x": x, "y": x * 2.0, "stance": stance, "local_only": "ignored"},
            "health": {"hp": hp, "debug": True},
        },
    )


def test_replication_registry_captures_declared_fields_only() -> None:
    registry = _registry()

    entity = _entity(registry, 7, 2.0)

    assert entity.net_id == 7
    assert entity.components == {
        "transform": {"x": 2.0, "y": 4.0, "stance": "idle"},
        "health": {"hp": 100},
    }


def test_replication_registry_rejects_unknown_and_missing_fields() -> None:
    registry = _registry()

    with pytest.raises(KeyError, match="unregistered"):
        registry.capture(1, {"missing": {"x": 1}})
    with pytest.raises(KeyError, match=r"transform\.y"):
        registry.capture(1, {"transform": {"x": 1, "stance": "idle"}})


def test_snapshot_encoding_is_canonical_and_round_trips() -> None:
    registry = _registry()
    first = _entity(registry, 2, 4.0)
    second = _entity(registry, 1, 2.0)
    snapshot = WorldSnapshot(4, 0.25, (first, second))

    encoded = snapshot.to_bytes()
    decoded = WorldSnapshot.from_bytes(encoded)

    assert decoded == snapshot
    assert [entity.net_id for entity in decoded.entities] == [1, 2]
    assert encoded == snapshot.to_bytes()


def test_snapshot_rejects_nonfinite_replicated_values() -> None:
    registry = _registry()

    with pytest.raises(ValueError, match="finite"):
        _entity(registry, 1, math.inf)


def test_snapshot_delta_tracks_changes_removals_and_applies() -> None:
    registry = _registry()
    baseline = WorldSnapshot(
        10,
        1.0,
        (_entity(registry, 1, 1.0), _entity(registry, 2, 2.0)),
    )
    current = WorldSnapshot(
        11,
        1.05,
        (_entity(registry, 1, 3.0), _entity(registry, 3, 5.0)),
    )

    delta = SnapshotDelta.between(baseline, current)

    assert tuple(item.net_id for item in delta.upserts) == (1, 3)
    assert delta.removed == (2,)
    assert delta.apply(baseline) == current
    assert SnapshotDelta.from_payload(delta.to_payload()) == delta
    assert SnapshotDelta.from_bytes(delta.to_bytes()) == delta


def test_delta_requires_matching_baseline() -> None:
    registry = _registry()
    baseline = WorldSnapshot(1, 0.0, (_entity(registry, 1, 1.0),))
    current = WorldSnapshot(2, 0.1, (_entity(registry, 1, 2.0),))
    delta = SnapshotDelta.between(baseline, current)

    with pytest.raises(ValueError, match="baseline mismatch"):
        delta.apply(WorldSnapshot(0, 0.0, baseline.entities))


def test_snapshot_buffer_interpolates_and_respects_noninterpolated_fields() -> None:
    registry = _registry()
    buffer = SnapshotBuffer(registry=registry, max_snapshots=4)
    buffer.push(WorldSnapshot(1, 1.0, (_entity(registry, 1, 0.0, stance="idle"),)))
    buffer.push(WorldSnapshot(2, 2.0, (_entity(registry, 1, 10.0, stance="run"),)))

    sample = buffer.sample(1.5)

    assert sample.older_tick == 1
    assert sample.newer_tick == 2
    assert sample.alpha == pytest.approx(0.5)
    assert sample.entities[0].components["transform"]["x"] == pytest.approx(5.0)
    assert sample.entities[0].components["transform"]["y"] == pytest.approx(10.0)
    assert sample.entities[0].components["transform"]["stance"] == "idle"


def test_snapshot_buffer_accepts_out_of_order_delivery_and_replaces_tick() -> None:
    registry = _registry()
    buffer = SnapshotBuffer(registry=registry, max_snapshots=3)
    buffer.push(WorldSnapshot(3, 3.0, (_entity(registry, 1, 3.0),)))
    buffer.push(WorldSnapshot(1, 1.0, (_entity(registry, 1, 1.0),)))
    buffer.push(WorldSnapshot(2, 2.0, (_entity(registry, 1, 2.0),)))
    buffer.push(WorldSnapshot(2, 2.0, (_entity(registry, 1, 20.0),)))

    assert buffer.ticks == (1, 2, 3)
    assert buffer.sample(2.0).entities[0].components["transform"]["x"] == 20.0


def test_snapshot_buffer_clamps_outside_history() -> None:
    registry = _registry()
    buffer = SnapshotBuffer(registry=registry)
    buffer.push(WorldSnapshot(5, 5.0, (_entity(registry, 1, 5.0),)))
    buffer.push(WorldSnapshot(6, 6.0, (_entity(registry, 1, 6.0),)))

    early = buffer.sample(4.0)
    late = buffer.sample(7.0)

    assert early.clamped is True
    assert early.older_tick == early.newer_tick == 5
    assert late.clamped is True
    assert late.older_tick == late.newer_tick == 6


def test_client_prediction_reconciles_and_replays_unacknowledged_commands() -> None:
    def simulate(state: dict[str, object], command: PredictionCommand) -> dict[str, object]:
        return {"x": int(state["x"]) + int(command.payload["dx"])}

    predictor = ClientPredictor({"x": 0}, simulate)
    predictor.predict(PredictionCommand(1, 1, {"dx": 3}))
    predictor.predict(PredictionCommand(2, 2, {"dx": 4}))
    predictor.predict(PredictionCommand(3, 3, {"dx": 2}))
    assert predictor.state == {"x": 9}

    result = predictor.reconcile(2, {"x": 8})

    assert result.corrected is True
    assert result.replayed_commands == 1
    assert result.state == {"x": 10}
    assert [item.sequence for item in predictor.pending_commands] == [3]


def test_client_prediction_rejects_duplicate_sequence_and_overflow() -> None:
    predictor = ClientPredictor({"x": 0}, lambda state, _command: state, max_pending=1)
    predictor.predict(PredictionCommand(1, 1))

    with pytest.raises(ValueError, match="increase"):
        predictor.predict(PredictionCommand(1, 2))
    with pytest.raises(OverflowError, match="full"):
        predictor.predict(PredictionCommand(2, 2))


def test_lag_compensation_history_prunes_window_and_rewinds() -> None:
    registry = _registry()
    history = LagCompensationHistory(registry=registry, max_seconds=1.0, max_frames=8)
    history.record(WorldSnapshot(1, 0.0, (_entity(registry, 1, 0.0),)))
    history.record(WorldSnapshot(2, 0.5, (_entity(registry, 1, 5.0),)))
    history.record(WorldSnapshot(3, 1.0, (_entity(registry, 1, 10.0),)))
    history.record(WorldSnapshot(4, 1.5, (_entity(registry, 1, 15.0),)))

    sample = history.rewind(1.25)

    assert len(history) == 3
    assert history.oldest_time == 0.5
    assert sample.entities[0].components["transform"]["x"] == pytest.approx(12.5)


def test_lag_compensation_history_rejects_time_reversal() -> None:
    registry = _registry()
    history = LagCompensationHistory(registry=registry)
    history.record(WorldSnapshot(1, 1.0, (_entity(registry, 1, 1.0),)))

    with pytest.raises(ValueError, match="time order"):
        history.record(WorldSnapshot(2, 0.9, (_entity(registry, 1, 2.0),)))


def test_bandwidth_diagnostics_reports_deterministic_rates_and_channels() -> None:
    diagnostics = MultiplayerBandwidthDiagnostics()
    diagnostics.record_sent(b"12345", channel="snapshot")
    diagnostics.record_sent(3, channel="input")
    diagnostics.record_received(b"1234567", channel="snapshot")

    report = diagnostics.report(2.0)

    assert report.sent_packets == 2
    assert report.sent_bytes == 8
    assert report.received_packets == 1
    assert report.received_bytes == 7
    assert report.sent_bytes_per_second == 4.0
    assert report.received_bytes_per_second == 3.5
    assert report.channels["snapshot"]["sent_bytes"] == 5
    assert report.channels["input"]["sent_bytes"] == 3


def test_packet_codec_bridges_snapshot_and_delta_to_stable_network_packet() -> None:
    registry = _registry()
    baseline = WorldSnapshot(1, 0.0, (_entity(registry, 1, 1.0),))
    current = WorldSnapshot(2, 0.1, (_entity(registry, 1, 2.0),))
    delta = SnapshotDelta.between(baseline, current)

    snapshot_packet = MultiplayerPacketCodec.snapshot_packet(current)
    delta_packet = MultiplayerPacketCodec.delta_packet(delta)

    assert MultiplayerPacketCodec.decode_snapshot(snapshot_packet) == current
    assert MultiplayerPacketCodec.decode_delta(delta_packet) == delta
