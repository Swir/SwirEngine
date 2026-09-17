from __future__ import annotations

import time

from swirengine.multiplayer14 import PredictionCommand
from swirengine.prediction16 import PredictionCorrection, PredictionTimeline

ROUNDS = 400
FIRST_BATCH = 32
NEXT_BATCH = 24
REPLAY_TAIL = 8
MAX_SECONDS = 4.0


def simulate(state: dict[str, object], command: PredictionCommand) -> dict[str, object]:
    return {"x": int(state.get("x", 0)) + int(command.payload["dx"])}


def main() -> None:
    timeline = PredictionTimeline(
        {"x": 0},
        simulate,
        max_pending=64,
        max_prediction_ticks=2,
        max_replay_commands=16,
    )
    sequence = 0
    encoded_bytes = 0
    started = time.perf_counter()

    for round_index in range(ROUNDS):
        batch = FIRST_BATCH if round_index == 0 else NEXT_BATCH
        command_tick = timeline.last_authoritative_tick + 1
        for _ in range(batch):
            sequence += 1
            timeline.predict(PredictionCommand(sequence, command_tick, {"dx": 1}))

        acknowledged = sequence - REPLAY_TAIL
        correction = PredictionCorrection(
            acknowledged,
            round_index + 1,
            {"x": acknowledged},
        )
        encoded_bytes += len(correction.to_packet().to_bytes())
        result = timeline.reconcile(correction)
        assert result.replayed_commands == REPLAY_TAIL
        assert timeline.state == {"x": sequence}

    elapsed = time.perf_counter() - started
    diagnostics = timeline.diagnostics()

    assert diagnostics["predicted_commands"] == sequence
    assert diagnostics["reconciliations"] == ROUNDS
    assert diagnostics["replayed_commands"] == ROUNDS * REPLAY_TAIL
    assert diagnostics["stale_corrections"] == 0
    assert diagnostics["replay_budget_rejections"] == 0
    assert len(timeline.pending_commands) == REPLAY_TAIL
    assert encoded_bytes > 0
    if elapsed > MAX_SECONDS:
        raise SystemExit(
            f"prediction/reconciliation workload exceeded {MAX_SECONDS:.1f}s budget: {elapsed:.3f}s"
        )

    print(
        "prediction16 benchmark: "
        f"commands={sequence} reconciliations={ROUNDS} "
        f"replayed={diagnostics['replayed_commands']} bytes={encoded_bytes} "
        f"elapsed={elapsed:.3f}s"
    )


if __name__ == "__main__":
    main()
