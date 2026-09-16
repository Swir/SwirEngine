from __future__ import annotations

from swirengine.simulation15 import FixedStepClock, ReplayPlayer, ReplayRecorder


def main() -> None:
    state = {"position": 0, "score": 0}
    recorder = ReplayRecorder(step_seconds=1.0 / 60.0, checkpoint_interval=3)
    recorder.add_checkpoint(0, state)

    clock = FixedStepClock(step_seconds=1.0 / 60.0)
    inputs = (1, 1, 2, -1, 3, 1)
    for tick_info, movement in zip(clock.advance(0.1), inputs, strict=True):
        state["position"] += movement
        state["score"] += max(0, movement)
        recorder.record(
            tick_info.tick,
            {"movement": movement},
            state=state,
        )

    recording = recorder.build(
        metadata={"demo": "SwirEngine 1.5 deterministic replay"},
    )
    replay_state = {"position": 0, "score": 0}

    def replay_step(_tick: int, _dt: float, payload: dict[str, object]) -> None:
        movement = int(payload["movement"])
        replay_state["position"] += movement
        replay_state["score"] += max(0, movement)

    report = ReplayPlayer(
        recording,
        replay_step,
        state_provider=lambda: replay_state,
    ).play()

    if replay_state != state:
        raise AssertionError("replay did not reproduce the recorded state")
    if report.verified_frames != len(inputs):
        raise AssertionError("not every replay frame was verified")

    print("SwirEngine 1.5 deterministic replay demo")
    print(f"frames: {report.frames_played}")
    print(f"verified: {report.verified_frames}")
    print(f"final state: {replay_state}")
    print(f"recording bytes: {len(recording.to_json().encode('utf-8'))}")


if __name__ == "__main__":
    main()
