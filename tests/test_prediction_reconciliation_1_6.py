from __future__ import annotations

import pytest

from swirengine.multiplayer14 import ClientPredictor, PredictionCommand
from swirengine.networking import NetworkPacket
from swirengine.prediction16 import (
    PREDICTION_CORRECTION_PACKET_KIND,
    CorrectionTransition,
    PredictionCorrection,
    PredictionTimeline,
    ReplayBudgetExceeded,
)


def _simulate(state: dict[str, object], command: PredictionCommand) -> dict[str, object]:
    return {
        "x": int(state.get("x", 0)) + int(command.payload.get("dx", 0)),
        "stance": command.payload.get("stance", state.get("stance", "idle")),
    }


def _command(sequence: int, tick: int, dx: int = 1) -> PredictionCommand:
    return PredictionCommand(sequence, tick, {"dx": dx})


def test_prediction_window_accepts_bounded_commands_and_rejects_future_ticks_atomically() -> None:
    timeline = PredictionTimeline({"x": 0}, _simulate, max_prediction_ticks=2)

    assert timeline.predict(_command(1, 2, 3))["x"] == 3
    before = timeline.state.copy()

    with pytest.raises(ValueError, match="prediction window"):
        timeline.predict(_command(2, 3, 5))

    assert timeline.state == before
    assert timeline.last_sequence == 1
    assert [command.sequence for command in timeline.pending_commands] == [1]
    assert timeline.diagnostics()["prediction_window_rejections"] == 1


def test_prediction_rejects_commands_behind_authoritative_timeline() -> None:
    timeline = PredictionTimeline({"x": 0}, _simulate, initial_authoritative_tick=5)

    with pytest.raises(ValueError, match="precedes"):
        timeline.predict(_command(1, 4))


def test_reconciliation_acknowledges_commands_and_replays_remaining_input() -> None:
    timeline = PredictionTimeline({"x": 0}, _simulate, max_prediction_ticks=8)
    timeline.predict(_command(1, 1, 2))
    timeline.predict(_command(2, 2, 3))
    timeline.predict(_command(3, 3, 4))

    result = timeline.reconcile(PredictionCorrection(2, 5, {"x": 10, "stance": "idle"}))

    assert result.applied is True
    assert result.stale is False
    assert result.corrected is True
    assert result.replayed_commands == 1
    assert result.state["x"] == 14
    assert timeline.state["x"] == 14
    assert timeline.last_acknowledged_sequence == 2
    assert timeline.last_authoritative_tick == 5
    assert [command.sequence for command in timeline.pending_commands] == [3]


def test_out_of_order_authoritative_packet_is_ignored_without_regressing_truth() -> None:
    timeline = PredictionTimeline({"x": 0}, _simulate)
    timeline.predict(_command(1, 1, 1))
    fresh = timeline.reconcile(PredictionCorrection(1, 4, {"x": 4, "stance": "idle"}))
    assert fresh.applied is True
    before = timeline.state.copy()

    stale = timeline.reconcile(PredictionCorrection(1, 3, {"x": -100, "stance": "idle"}))

    assert stale.applied is False
    assert stale.stale is True
    assert timeline.state == before
    assert timeline.last_authoritative_tick == 4
    assert timeline.diagnostics()["stale_corrections"] == 1


def test_newer_tick_cannot_regress_command_acknowledgement() -> None:
    timeline = PredictionTimeline({"x": 0}, _simulate)
    timeline.predict(_command(1, 1))
    timeline.predict(_command(2, 2))
    timeline.reconcile(PredictionCorrection(2, 3, {"x": 2, "stance": "idle"}))

    with pytest.raises(ValueError, match="regress"):
        timeline.reconcile(PredictionCorrection(1, 4, {"x": 3, "stance": "idle"}))

    assert timeline.last_authoritative_tick == 3
    assert timeline.last_acknowledged_sequence == 2


def test_server_cannot_acknowledge_unsent_prediction_command() -> None:
    timeline = PredictionTimeline({"x": 0}, _simulate)

    with pytest.raises(ValueError, match="unsent"):
        timeline.reconcile(PredictionCorrection(1, 1, {"x": 0}))


def test_replay_budget_failure_is_atomic() -> None:
    timeline = PredictionTimeline(
        {"x": 0},
        _simulate,
        max_prediction_ticks=16,
        max_replay_commands=2,
    )
    for sequence in range(1, 5):
        timeline.predict(_command(sequence, sequence))
    before_state = timeline.state.copy()
    before_pending = timeline.pending_commands

    with pytest.raises(ReplayBudgetExceeded, match="max_replay_commands"):
        timeline.reconcile(PredictionCorrection(1, 6, {"x": 1, "stance": "idle"}))

    assert timeline.state == before_state
    assert timeline.pending_commands == before_pending
    assert timeline.last_authoritative_tick == 0
    assert timeline.last_acknowledged_sequence == 0
    assert timeline.diagnostics()["replay_budget_rejections"] == 1


def test_pending_history_limit_rejects_without_advancing_sequence() -> None:
    timeline = PredictionTimeline({"x": 0}, _simulate, max_pending=1)
    timeline.predict(_command(1, 1))

    with pytest.raises(OverflowError, match="history is full"):
        timeline.predict(_command(2, 2))

    assert timeline.last_sequence == 1
    assert timeline.diagnostics()["pending_overflow_rejections"] == 1


def test_correction_transition_smooths_presentation_without_delaying_truth() -> None:
    timeline = PredictionTimeline({"x": 0, "stance": "idle"}, _simulate)
    timeline.predict(_command(1, 1, 10))

    result = timeline.reconcile(PredictionCorrection(1, 2, {"x": 4, "stance": "run"}))

    assert timeline.state == {"x": 4, "stance": "run"}
    assert result.transition is not None
    assert result.transition.sample(0.0) == {"stance": "idle", "x": 10.0}
    assert result.transition.sample(0.5) == {"stance": "idle", "x": 7.0}
    assert result.transition.sample(1.0) == {"stance": "run", "x": 4.0}
    assert timeline.state == {"x": 4, "stance": "run"}


def test_correction_transition_supports_creator_smoothing_hook() -> None:
    transition = CorrectionTransition({"x": 10}, {"x": 4})

    def snap_after_half(
        previous: dict[str, object], corrected: dict[str, object], alpha: float
    ) -> dict[str, object]:
        return previous if alpha < 0.5 else corrected

    assert transition.sample(0.49, blend=snap_after_half) == {"x": 10}
    assert transition.sample(0.5, blend=snap_after_half) == {"x": 4}

    with pytest.raises(ValueError, match="\[0, 1\]"):
        transition.sample(1.1)


def test_correction_packet_round_trips_through_stable_network_packet() -> None:
    correction = PredictionCorrection(7, 42, {"x": 12.5, "flags": [1, 2]})
    framed = correction.to_packet().to_bytes()
    decoded_packet = NetworkPacket.from_body(framed[4:])

    decoded = PredictionCorrection.from_packet(decoded_packet)

    assert decoded == correction
    assert decoded_packet.kind == PREDICTION_CORRECTION_PACKET_KIND


def test_correction_packet_rejects_wrong_kind_and_malformed_state() -> None:
    with pytest.raises(ValueError, match="expected"):
        PredictionCorrection.from_packet(NetworkPacket("other", {}))
    with pytest.raises(TypeError, match="state"):
        PredictionCorrection.from_packet(
            NetworkPacket(
                PREDICTION_CORRECTION_PACKET_KIND,
                {
                    "acknowledged_sequence": 0,
                    "replication_tick": 1,
                    "authoritative_state": 123,
                },
            )
        )


def test_diagnostics_account_for_prediction_replay_and_corrections() -> None:
    timeline = PredictionTimeline({"x": 0}, _simulate)
    timeline.predict(_command(1, 1, 2))
    timeline.predict(_command(2, 2, 3))
    timeline.reconcile(PredictionCorrection(1, 3, {"x": 5, "stance": "idle"}))

    assert timeline.diagnostics() == {
        "predicted_commands": 2,
        "reconciliations": 1,
        "stale_corrections": 0,
        "corrected_reconciliations": 1,
        "replayed_commands": 1,
        "replay_budget_rejections": 0,
        "prediction_window_rejections": 0,
        "pending_overflow_rejections": 0,
        "peak_pending_commands": 2,
    }


def test_existing_1_4_client_predictor_contract_remains_usable() -> None:
    predictor = ClientPredictor({"x": 0}, _simulate)
    predictor.predict(_command(1, 1, 2))
    result = predictor.reconcile(1, {"x": 1, "stance": "idle"})

    assert result.state["x"] == 1
    assert predictor.pending_commands == ()


def test_prediction_correction_validates_portable_state_and_ids() -> None:
    with pytest.raises(ValueError, match="negative"):
        PredictionCorrection(-1, 1, {"x": 0})
    with pytest.raises(TypeError, match="integer"):
        PredictionCorrection(True, 1, {"x": 0})
    with pytest.raises(ValueError, match="finite"):
        PredictionCorrection(0, 1, {"x": float("nan")})
