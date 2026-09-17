from __future__ import annotations

from swirengine.multiplayer14 import PredictionCommand
from swirengine.prediction16 import PredictionCorrection, PredictionTimeline


def simulate(state: dict[str, object], command: PredictionCommand) -> dict[str, object]:
    return {"x": float(state.get("x", 0.0)) + float(command.payload.get("dx", 0.0))}


def main() -> None:
    timeline = PredictionTimeline(
        {"x": 0.0},
        simulate,
        max_prediction_ticks=6,
        max_replay_commands=16,
    )

    timeline.predict(PredictionCommand(1, 1, {"dx": 1.0}))
    timeline.predict(PredictionCommand(2, 2, {"dx": 1.0}))
    timeline.predict(PredictionCommand(3, 3, {"dx": 1.0}))
    print("predicted:", timeline.state)

    result = timeline.reconcile(
        PredictionCorrection(
            acknowledged_sequence=2,
            replication_tick=5,
            authoritative_state={"x": 1.7},
        )
    )
    print("authoritative + replay:", result.state)

    if result.transition is not None:
        print("presentation halfway:", result.transition.sample(0.5))
        print("simulation truth:", timeline.state)

    stale = timeline.reconcile(
        PredictionCorrection(
            acknowledged_sequence=2,
            replication_tick=4,
            authoritative_state={"x": -999.0},
        )
    )
    print("reordered packet ignored:", stale.stale)
    print("diagnostics:", timeline.diagnostics())


if __name__ == "__main__":
    main()
