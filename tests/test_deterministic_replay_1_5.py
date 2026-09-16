from __future__ import annotations

import json

import pytest

import swirengine.simulation15 as replay


def test_canonical_hash_is_order_independent_and_normalizes_negative_zero() -> None:
    left = {"z": -0.0, "nested": {"b": 2, "a": [1, True, None]}}
    right = {"nested": {"a": [1, True, None], "b": 2}, "z": 0.0}
    assert replay.canonical_json(left) == replay.canonical_json(right)
    assert replay.state_fingerprint(left) == replay.state_fingerprint(right)


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), float("-inf")])
def test_portable_state_rejects_non_finite_floats(bad: float) -> None:
    with pytest.raises(ValueError, match="finite"):
        replay.portable_state({"value": bad})


def test_portable_state_rejects_non_string_mapping_keys_and_objects() -> None:
    with pytest.raises(TypeError, match="keys"):
        replay.portable_state({1: "bad"})  # type: ignore[dict-item]
    with pytest.raises(TypeError, match="unsupported"):
        replay.portable_state({"value": object()})


def test_fixed_step_clock_accumulates_fractional_time() -> None:
    clock = replay.FixedStepClock(step_seconds=0.1, max_steps_per_advance=8)
    first = clock.advance(0.25)
    second = clock.advance(0.05)

    assert [item.tick for item in first] == [1, 2]
    assert [item.tick for item in second] == [3]
    assert first[-1].simulation_time == pytest.approx(0.2)
    assert second[-1].simulation_time == pytest.approx(0.3)
    assert clock.accumulator == pytest.approx(0.0)
    assert clock.alpha == pytest.approx(0.0)


def test_fixed_step_clock_bounds_catch_up_and_reports_drops() -> None:
    clock = replay.FixedStepClock(step_seconds=0.1, max_steps_per_advance=3)
    ticks = clock.advance(0.75)

    assert [item.tick for item in ticks] == [1, 2, 3]
    assert clock.dropped_steps == 4
    assert clock.accumulator == pytest.approx(0.05)
    assert clock.alpha == pytest.approx(0.5)


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"step_seconds": 0.0}, "step_seconds"),
        ({"step_seconds": float("nan")}, "step_seconds"),
        ({"max_steps_per_advance": 0}, "max_steps"),
    ],
)
def test_fixed_step_clock_validates_configuration(
    kwargs: dict[str, object], message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        replay.FixedStepClock(**kwargs)  # type: ignore[arg-type]


def test_fixed_step_clock_rejects_invalid_advances_and_reset() -> None:
    clock = replay.FixedStepClock(step_seconds=0.25)
    with pytest.raises(ValueError, match="elapsed_seconds"):
        clock.advance(-0.1)
    with pytest.raises(ValueError, match="elapsed_seconds"):
        clock.advance(float("inf"))
    with pytest.raises(ValueError, match="tick"):
        clock.reset(tick=-1)
    with pytest.raises(ValueError, match="accumulator"):
        clock.reset(accumulator=0.25)


def _record_counter() -> replay.ReplayRecording:
    state = {"value": 0, "flags": {"alive": True}}
    recorder = replay.ReplayRecorder(step_seconds=0.05, checkpoint_interval=2)
    recorder.add_checkpoint(0, state)
    for tick, delta in enumerate((3, -1, 4, 2, -5), start=1):
        state["value"] += delta
        recorder.record(tick, {"delta": delta}, state=state)
    return recorder.build(metadata={"scenario": "counter", "seed": 1337})


def test_recording_json_round_trip_is_canonical_and_versioned() -> None:
    recording = _record_counter()
    encoded = recording.to_json()
    decoded = replay.ReplayRecording.from_json(encoded)

    assert decoded == recording
    assert encoded == decoded.to_json()
    payload = json.loads(encoded)
    assert payload["format"] == replay.REPLAY_FORMAT
    assert payload["version"] == replay.REPLAY_VERSION
    assert payload["metadata"]["seed"] == 1337
    assert [item["tick"] for item in payload["checkpoints"]] == [0, 2, 4]


def test_recording_pretty_json_round_trip() -> None:
    recording = _record_counter()
    pretty = recording.to_json(pretty=True)
    assert "\n" in pretty
    assert replay.ReplayRecording.from_json(pretty) == recording


def test_recording_rejects_unknown_format_and_version() -> None:
    payload = _record_counter().to_payload()
    payload["format"] = "other"
    with pytest.raises(ValueError, match="format"):
        replay.ReplayRecording.from_payload(payload)

    payload = _record_counter().to_payload()
    payload["version"] = 999
    with pytest.raises(ValueError, match="version"):
        replay.ReplayRecording.from_payload(payload)


def test_recording_requires_increasing_unique_ticks() -> None:
    frame = replay.ReplayFrame(1, {"move": 1})
    with pytest.raises(ValueError, match="frame ticks"):
        replay.ReplayRecording(0.1, (frame, frame))

    checkpoint = replay.ReplayCheckpoint(0, {"x": 0})
    with pytest.raises(ValueError, match="checkpoint ticks"):
        replay.ReplayRecording(0.1, (), (checkpoint, checkpoint))


def test_recorder_validates_order_and_checkpoint_state() -> None:
    recorder = replay.ReplayRecorder()
    recorder.record(1, {"a": 1})
    with pytest.raises(ValueError, match="strictly increasing"):
        recorder.record(1, {"a": 2})
    with pytest.raises(ValueError, match="requires state"):
        recorder.record(2, {"a": 2}, checkpoint=True)


def test_bounded_recorder_prunes_unusable_old_checkpoints() -> None:
    recorder = replay.ReplayRecorder(
        step_seconds=0.1, max_frames=3, checkpoint_interval=2
    )
    recorder.add_checkpoint(0, {"x": 0})
    state = {"x": 0}
    for tick in range(1, 7):
        state["x"] = tick
        recorder.record(tick, {"x": tick}, state=state)

    recording = recorder.build()
    assert [frame.tick for frame in recording.frames] == [4, 5, 6]
    assert [checkpoint.tick for checkpoint in recording.checkpoints] == [4, 6]


def test_replay_player_reproduces_and_verifies_recorded_state() -> None:
    recording = _record_counter()
    state = {"value": 0, "flags": {"alive": True}}

    def step(_tick: int, _dt: float, payload: dict[str, replay.Portable]) -> None:
        state["value"] += int(payload["delta"])

    player = replay.ReplayPlayer(recording, step, state_provider=lambda: state)
    report = player.play()

    assert state["value"] == 3
    assert report == replay.ReplayReport(5, 1, 5, 5)
    assert player.remaining == 0
    assert player.step_once() is None


def test_replay_player_detects_first_divergence_with_hashes() -> None:
    recording = _record_counter()
    state = {"value": 0, "flags": {"alive": True}}

    def broken_step(
        _tick: int, _dt: float, payload: dict[str, replay.Portable]
    ) -> None:
        state["value"] += int(payload["delta"]) + 1

    player = replay.ReplayPlayer(recording, broken_step, state_provider=lambda: state)
    with pytest.raises(replay.ReplayDivergenceError) as caught:
        player.play()

    result = caught.value.result
    assert result.tick == 1
    assert result.expected_state_hash is not None
    assert result.actual_state_hash is not None
    assert result.expected_state_hash != result.actual_state_hash


def test_player_requires_provider_only_when_verification_is_requested() -> None:
    recording = _record_counter()
    state = {"value": 0}

    def step(_tick: int, _dt: float, payload: dict[str, replay.Portable]) -> None:
        state["value"] += int(payload["delta"])

    player = replay.ReplayPlayer(recording, step)
    report = player.play(verify=False)
    assert report.frames_played == 5
    assert report.verified_frames == 0

    player.reset()
    with pytest.raises(RuntimeError, match="state_provider"):
        player.step_once()


def test_player_play_limit_supports_incremental_consumption() -> None:
    recording = _record_counter()
    state = {"value": 0, "flags": {"alive": True}}

    def step(_tick: int, _dt: float, payload: dict[str, replay.Portable]) -> None:
        state["value"] += int(payload["delta"])

    player = replay.ReplayPlayer(recording, step, state_provider=lambda: state)
    first = player.play(max_frames=2)
    second = player.play(max_frames=2)
    third = player.play(max_frames=2)

    assert (first.frames_played, second.frames_played, third.frames_played) == (2, 2, 1)
    assert player.remaining == 0


def test_seek_restores_nearest_checkpoint_and_replays_forward() -> None:
    recording = _record_counter()
    state = {"value": -999, "flags": {"alive": False}}

    def restore(snapshot: dict[str, object]) -> None:
        state.clear()
        state.update(snapshot)

    def step(_tick: int, _dt: float, payload: dict[str, replay.Portable]) -> None:
        state["value"] = int(state["value"]) + int(payload["delta"])

    player = replay.ReplayPlayer(
        recording,
        step,
        state_provider=lambda: state,
        state_restorer=restore,
    )
    report = player.seek(3)

    assert state == {"value": 6, "flags": {"alive": True}}
    assert report == replay.ReplayReport(1, 3, 3, 1)
    assert player.remaining == 2


def test_seek_can_restore_exact_checkpoint_without_replaying_frame() -> None:
    recording = _record_counter()
    state: dict[str, object] = {}

    player = replay.ReplayPlayer(
        recording,
        lambda *_args: pytest.fail("step should not run"),
        state_provider=lambda: state,
        state_restorer=lambda snapshot: state.update(snapshot),
    )
    report = player.seek(4)

    assert state["value"] == 8
    assert report.frames_played == 0
    assert player.remaining == 1


def test_seek_requires_restorer_and_available_checkpoint() -> None:
    recording = replay.ReplayRecording(
        step_seconds=0.1,
        frames=(replay.ReplayFrame(1, {"x": 1}),),
    )
    player = replay.ReplayPlayer(recording, lambda *_args: None)
    with pytest.raises(RuntimeError, match="state_restorer"):
        player.seek(1)

    player = replay.ReplayPlayer(
        recording,
        lambda *_args: None,
        state_restorer=lambda _state: None,
    )
    with pytest.raises(ValueError, match="no checkpoint"):
        player.seek(1)


def test_invalid_replay_configuration_is_rejected() -> None:
    with pytest.raises(ValueError, match="max_frames"):
        replay.ReplayRecorder(max_frames=0)
    with pytest.raises(ValueError, match="checkpoint_interval"):
        replay.ReplayRecorder(checkpoint_interval=-1)
    with pytest.raises(ValueError, match="step_seconds"):
        replay.ReplayRecording(0.0, ())
    with pytest.raises(ValueError, match="max_frames"):
        replay.ReplayPlayer(_record_counter(), lambda *_args: None).play(max_frames=-1)
