from __future__ import annotations

from pathlib import Path

import pytest

from swirengine.audio15 import (
    AudioEngine2,
    AudioSnapshot,
    AudioSnapshotBus,
    HeadlessAudioBackend,
)


def _asset(tmp_path: Path, name: str = "tone.wav") -> Path:
    path = tmp_path / name
    path.write_bytes(b"headless-audio")
    return path


def test_headless_factory_plays_without_desktop_audio(tmp_path: Path) -> None:
    _asset(tmp_path)
    audio = AudioEngine2.headless(tmp_path, max_voices=4)
    voice = audio.play("tone.wav", priority=80)

    assert voice is not None
    assert voice.active
    assert voice.priority == 80
    assert isinstance(audio.backend, HeadlessAudioBackend)
    assert len(audio.backend.active_tokens) == 1
    assert audio.diagnostics().active_voices == 1


def test_voice_budget_steals_lowest_priority_then_oldest(tmp_path: Path) -> None:
    _asset(tmp_path)
    audio = AudioEngine2.headless(tmp_path, max_voices=2)
    first = audio.play("tone.wav", priority=10)
    second = audio.play("tone.wav", priority=10)
    incoming = audio.play("tone.wav", priority=20)

    assert first is not None and second is not None and incoming is not None
    assert not first.active
    assert second.active
    assert incoming.active
    assert [voice.voice_id for voice in audio.voices] == [second.voice_id, incoming.voice_id]
    assert audio.diagnostics().stolen_voices == 1


def test_lower_priority_voice_is_rejected_when_budget_is_full(tmp_path: Path) -> None:
    _asset(tmp_path)
    audio = AudioEngine2.headless(tmp_path, max_voices=2)
    high = audio.play("tone.wav", priority=200)
    higher = audio.play("tone.wav", priority=220)

    rejected = audio.play("tone.wav", priority=100)

    assert high is not None and higher is not None
    assert rejected is None
    assert {voice.priority for voice in audio.voices} == {200, 220}
    assert audio.diagnostics().rejected_voices == 1


def test_protected_voice_is_not_selected_for_stealing(tmp_path: Path) -> None:
    _asset(tmp_path)
    audio = AudioEngine2.headless(tmp_path, max_voices=2)
    protected = audio.play("tone.wav", priority=1, protected=True)
    normal = audio.play("tone.wav", priority=20)
    incoming = audio.play("tone.wav", priority=20)

    assert protected is not None and normal is not None and incoming is not None
    assert protected.active
    assert not normal.active
    assert incoming.active


def test_all_protected_voices_reject_new_voice(tmp_path: Path) -> None:
    _asset(tmp_path)
    audio = AudioEngine2.headless(tmp_path, max_voices=1)
    protected = audio.play("tone.wav", priority=0, protected=True)

    assert protected is not None
    assert audio.play("tone.wav", priority=255) is None
    assert protected.active


def test_stopping_voice_immediately_releases_budget(tmp_path: Path) -> None:
    _asset(tmp_path)
    audio = AudioEngine2.headless(tmp_path, max_voices=1)
    first = audio.play("tone.wav")

    assert first is not None
    first.stop()
    second = audio.play("tone.wav")

    assert second is not None
    assert audio.diagnostics().active_voices == 1


def test_missing_incoming_asset_never_steals_an_existing_voice(tmp_path: Path) -> None:
    _asset(tmp_path)
    audio = AudioEngine2.headless(tmp_path, max_voices=1)
    existing = audio.play("tone.wav", priority=1)

    assert existing is not None
    with pytest.raises(FileNotFoundError):
        audio.play("missing.wav", priority=255)

    assert existing.active
    assert audio.voices == (existing,)
    assert audio.diagnostics().stolen_voices == 0


def test_music_is_managed_separately_from_sfx_voice_budget(tmp_path: Path) -> None:
    _asset(tmp_path, "tone.wav")
    _asset(tmp_path, "music.wav")
    audio = AudioEngine2.headless(tmp_path, max_voices=1)

    sfx = audio.play("tone.wav")
    first_music = audio.music("music.wav")
    second_music = audio.music("music.wav")

    assert sfx is not None and sfx.active
    assert not first_music.active
    assert second_music.active
    assert audio.diagnostics().active_voices == 1


def test_instant_snapshot_updates_master_bus_volume_and_mute(tmp_path: Path) -> None:
    _asset(tmp_path)
    audio = AudioEngine2.headless(tmp_path)
    audio.ensure_bus("dialogue", volume=1.0)
    snapshot = AudioSnapshot.from_mapping(
        "pause",
        {
            "sfx": {"volume": 0.25, "muted": True},
            "music": AudioSnapshotBus(volume=0.5, muted=False),
            "dialogue": {"volume": 0.8},
        },
        master_volume=0.7,
    )

    audio.apply_snapshot(snapshot)

    assert audio.current_snapshot == "pause"
    assert audio.engine.master_volume == pytest.approx(0.7)
    assert audio.engine.bus("sfx").volume == pytest.approx(0.25)
    assert audio.engine.bus("sfx").muted
    assert audio.engine.bus("music").volume == pytest.approx(0.5)
    assert not audio.engine.bus("music").muted
    assert audio.engine.bus("dialogue").volume == pytest.approx(0.8)


def test_snapshot_transition_interpolates_and_finishes_deterministically(tmp_path: Path) -> None:
    _asset(tmp_path)
    audio = AudioEngine2.headless(tmp_path)
    snapshot = AudioSnapshot.from_mapping(
        "combat",
        {"sfx": {"volume": 0.2}},
        master_volume=0.5,
    )

    audio.apply_snapshot(snapshot, duration=2.0)
    audio.update(0.5)
    diagnostics = audio.diagnostics()

    assert diagnostics.current_snapshot is None
    assert diagnostics.transition_snapshot == "combat"
    assert diagnostics.transition_progress == pytest.approx(0.25)
    assert audio.engine.master_volume == pytest.approx(0.875)
    assert audio.engine.bus("sfx").volume == pytest.approx(0.8)

    audio.update(1.5)
    assert audio.current_snapshot == "combat"
    assert not audio.snapshot_transitioning
    assert audio.engine.master_volume == pytest.approx(0.5)
    assert audio.engine.bus("sfx").volume == pytest.approx(0.2)


def test_snapshot_mute_happens_at_fade_end_and_unmute_at_fade_start(tmp_path: Path) -> None:
    _asset(tmp_path)
    audio = AudioEngine2.headless(tmp_path)

    mute = AudioSnapshot.from_mapping("mute", {"sfx": {"volume": 0.0, "muted": True}})
    audio.apply_snapshot(mute, duration=1.0)
    assert not audio.engine.bus("sfx").muted
    audio.update(1.0)
    assert audio.engine.bus("sfx").muted

    unmute = AudioSnapshot.from_mapping(
        "unmute",
        {"sfx": {"volume": 1.0, "muted": False}},
    )
    audio.apply_snapshot(unmute, duration=1.0)
    assert not audio.engine.bus("sfx").muted
    audio.update(1.0)
    assert audio.engine.bus("sfx").volume == pytest.approx(1.0)


def test_capture_snapshot_round_trips_bus_state(tmp_path: Path) -> None:
    _asset(tmp_path)
    audio = AudioEngine2.headless(tmp_path)
    audio.ensure_bus("dialogue", volume=0.7, muted=True)
    audio.set_bus_volume("sfx", 0.3)
    audio.engine.master_volume = 0.8

    snapshot = audio.capture_snapshot("captured")
    audio.set_bus_volume("sfx", 1.0)
    audio.set_bus_volume("dialogue", 1.0)
    audio.mute_bus("dialogue", False)
    audio.engine.master_volume = 1.0
    audio.apply_snapshot(snapshot)

    assert audio.engine.master_volume == pytest.approx(0.8)
    assert audio.engine.bus("sfx").volume == pytest.approx(0.3)
    assert audio.engine.bus("dialogue").volume == pytest.approx(0.7)
    assert audio.engine.bus("dialogue").muted


def test_capture_snapshot_can_limit_bus_scope_and_omit_master(tmp_path: Path) -> None:
    _asset(tmp_path)
    audio = AudioEngine2.headless(tmp_path)
    audio.ensure_bus("dialogue", volume=0.6)

    snapshot = audio.capture_snapshot(
        "dialogue-only",
        buses=["dialogue"],
        include_master=False,
    )

    assert snapshot.master_volume is None
    assert [name for name, _ in snapshot.buses] == ["dialogue"]


def test_snapshot_rejects_master_bus_ambiguity() -> None:
    with pytest.raises(ValueError, match="master_volume"):
        AudioSnapshot.from_mapping("bad", {"master": {"volume": 0.5}})


def test_spatial_voice_updates_headless_stereo_and_diagnostics(tmp_path: Path) -> None:
    _asset(tmp_path)
    audio = AudioEngine2.headless(tmp_path)
    audio.set_listener_position((0.0, 0.0, 0.0))
    voice = audio.play(
        "tone.wav",
        position=(5.0, 0.0, 0.0),
        min_distance=1.0,
        max_distance=10.0,
    )

    assert voice is not None
    diagnostics = audio.diagnostics()
    assert diagnostics.voices[0].spatial_position == (5.0, 0.0, 0.0)
    assert isinstance(audio.backend, HeadlessAudioBackend)
    token = audio.backend.active_tokens[0]
    assert token.left is not None
    assert token.right is not None
    assert token.right > token.left


def _deterministic_run(root: Path) -> str:
    _asset(root, "tone.wav")
    audio = AudioEngine2.headless(root, max_voices=2)
    first = audio.play("tone.wav", priority=10, position=(-2.0, 0.0, 0.0))
    second = audio.play("tone.wav", priority=20, position=(2.0, 0.0, 0.0))
    assert first is not None and second is not None
    replacement = audio.play("tone.wav", priority=30, bus="sfx")
    assert replacement is not None
    audio.apply_snapshot(
        AudioSnapshot.from_mapping(
            "focus",
            {"sfx": {"volume": 0.4, "muted": False}},
            master_volume=0.75,
        ),
        duration=1.0,
    )
    audio.update(0.25)
    audio.update(0.75)
    return audio.state_fingerprint()


def test_headless_state_fingerprint_is_independent_of_asset_root(tmp_path: Path) -> None:
    first = tmp_path / "first"
    second = tmp_path / "second"
    first.mkdir()
    second.mkdir()

    assert _deterministic_run(first) == _deterministic_run(second)


def test_fingerprint_changes_when_runtime_state_changes(tmp_path: Path) -> None:
    _asset(tmp_path)
    audio = AudioEngine2.headless(tmp_path)
    voice = audio.play("tone.wav", priority=10)
    assert voice is not None
    before = audio.state_fingerprint()
    voice.set_priority(11)
    after = audio.state_fingerprint()

    assert before != after


def test_headless_event_sequence_is_monotonic_and_inspectable(tmp_path: Path) -> None:
    _asset(tmp_path)
    audio = AudioEngine2.headless(tmp_path)
    voice = audio.play("tone.wav")
    assert voice is not None
    voice.set_volume(0.5)
    voice.stop()

    assert isinstance(audio.backend, HeadlessAudioBackend)
    events = audio.backend.events
    assert [event.sequence for event in events] == list(range(1, len(events) + 1))
    assert events[0].action == "play"
    assert any(event.action == "volume" for event in events)
    assert events[-1].action == "stop"


def test_fade_completion_prunes_voice_from_priority_budget(tmp_path: Path) -> None:
    _asset(tmp_path)
    audio = AudioEngine2.headless(tmp_path, max_voices=1)
    voice = audio.play("tone.wav")
    assert voice is not None

    voice.fade_out(0.5, stop=True)
    audio.update(0.5)

    assert not voice.active
    assert audio.diagnostics().active_voices == 0
    assert audio.play("tone.wav") is not None


def test_cancel_snapshot_transition_keeps_current_interpolated_state(tmp_path: Path) -> None:
    _asset(tmp_path)
    audio = AudioEngine2.headless(tmp_path)
    snapshot = AudioSnapshot.from_mapping("quiet", {"sfx": {"volume": 0.0}})

    audio.apply_snapshot(snapshot, duration=2.0)
    audio.update(1.0)
    halfway = audio.engine.bus("sfx").volume

    assert audio.cancel_snapshot_transition()
    assert not audio.cancel_snapshot_transition()
    audio.update(1.0)
    assert audio.engine.bus("sfx").volume == pytest.approx(halfway)
    assert audio.current_snapshot is None


@pytest.mark.parametrize("value", [-1, 256])
def test_priority_bounds_are_validated(tmp_path: Path, value: int) -> None:
    _asset(tmp_path)
    audio = AudioEngine2.headless(tmp_path)
    with pytest.raises(ValueError, match="priority"):
        audio.play("tone.wav", priority=value)


def test_priority_rejects_boolean(tmp_path: Path) -> None:
    _asset(tmp_path)
    audio = AudioEngine2.headless(tmp_path)
    with pytest.raises(TypeError, match="priority"):
        audio.play("tone.wav", priority=True)  # type: ignore[arg-type]


@pytest.mark.parametrize("value", [0, -1])
def test_voice_budget_requires_positive_integer(tmp_path: Path, value: int) -> None:
    with pytest.raises(ValueError, match="max_voices"):
        AudioEngine2.headless(tmp_path, max_voices=value)


@pytest.mark.parametrize("value", [float("nan"), float("inf"), -0.1])
def test_update_rejects_invalid_delta(tmp_path: Path, value: float) -> None:
    audio = AudioEngine2.headless(tmp_path)
    with pytest.raises(ValueError, match="audio update delta"):
        audio.update(value)


def test_shutdown_stops_headless_tokens_and_closes_backend(tmp_path: Path) -> None:
    _asset(tmp_path)
    audio = AudioEngine2.headless(tmp_path)
    assert audio.play("tone.wav") is not None
    backend = audio.backend
    assert isinstance(backend, HeadlessAudioBackend)

    audio.shutdown()

    assert not backend.active_tokens
    assert backend.closed
    assert audio.diagnostics().active_voices == 0
