from __future__ import annotations

import time

from swirengine.simulation15 import ReplayPlayer, ReplayRecorder, ReplayRecording

FRAME_COUNT = 5_000
MAX_SECONDS = 2.5
MAX_JSON_BYTES = 2_000_000


def main() -> None:
    state = {"x": 0, "y": 0, "health": 100}
    recorder = ReplayRecorder(step_seconds=1.0 / 60.0, checkpoint_interval=300)
    recorder.add_checkpoint(0, state)

    started = time.perf_counter()
    for tick in range(1, FRAME_COUNT + 1):
        dx = (tick % 3) - 1
        dy = ((tick * 7) % 3) - 1
        state["x"] += dx
        state["y"] += dy
        recorder.record(tick, {"dx": dx, "dy": dy}, state=state)

    recording = recorder.build(metadata={"benchmark": "deterministic-replay-1.5"})
    encoded = recording.to_json()
    decoded = ReplayRecording.from_json(encoded)

    replay_state = {"x": 0, "y": 0, "health": 100}

    def step(_tick: int, _dt: float, payload: dict[str, object]) -> None:
        replay_state["x"] += int(payload["dx"])
        replay_state["y"] += int(payload["dy"])

    report = ReplayPlayer(decoded, step, state_provider=lambda: replay_state).play()
    elapsed = time.perf_counter() - started
    payload_bytes = len(encoded.encode("utf-8"))

    if report.verified_frames != FRAME_COUNT:
        raise AssertionError(
            f"expected {FRAME_COUNT} verified frames, got {report.verified_frames}"
        )
    if replay_state != state:
        raise AssertionError("replayed state does not match recorded state")
    if payload_bytes > MAX_JSON_BYTES:
        raise AssertionError(
            f"replay JSON exceeded {MAX_JSON_BYTES} bytes: {payload_bytes}"
        )
    if elapsed > MAX_SECONDS:
        raise AssertionError(
            f"deterministic replay workload exceeded {MAX_SECONDS:.1f}s: {elapsed:.6f}s"
        )

    print(
        "deterministic-replay-1.5",
        f"frames={FRAME_COUNT}",
        f"verified={report.verified_frames}",
        f"json_bytes={payload_bytes}",
        f"elapsed={elapsed:.6f}s",
    )


if __name__ == "__main__":
    main()
