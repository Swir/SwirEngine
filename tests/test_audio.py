from pathlib import Path

import pytest

from swirengine import AssetManager, AudioEngine


class FakeAudioBackend:
    def __init__(self) -> None:
        self.plays: list[tuple[Path, float, bool, bool, object]] = []
        self.stops: list[object] = []
        self.volumes: list[tuple[object, float]] = []
        self.stop_all_calls = 0
        self.closed = False
        self.fail_play = False

    def play(self, path: Path, *, volume: float, loop: bool, music: bool) -> object:
        if self.fail_play:
            raise RuntimeError("play failed")
        token = object()
        self.plays.append((path, volume, loop, music, token))
        return token

    def stop(self, token: object) -> None:
        self.stops.append(token)

    def set_volume(self, token: object, volume: float) -> None:
        self.volumes.append((token, volume))

    def stop_all(self) -> None:
        self.stop_all_calls += 1

    def close(self) -> None:
        self.closed = True


def make_audio(tmp_path):
    assets = AssetManager(tmp_path)
    (tmp_path / "laser.wav").write_bytes(b"fake")
    (tmp_path / "theme.ogg").write_bytes(b"fake")
    backend = FakeAudioBackend()
    return AudioEngine(assets, backend=backend), backend


def test_audio_plays_assets_and_tracks_handles(tmp_path):
    audio, backend = make_audio(tmp_path)
    handle = audio.play("laser.wav", volume=0.8)

    assert handle.active
    assert handle.path == tmp_path / "laser.wav"
    assert backend.plays[0][:4] == (tmp_path / "laser.wav", 0.8, False, False)
    assert audio.active_handles == (handle,)

    handle.stop()
    assert not handle.active
    assert backend.stops == [backend.plays[0][4]]
    assert audio.active_handles == ()


def test_audio_master_and_category_volume_are_composed(tmp_path):
    audio, backend = make_audio(tmp_path)
    handle = audio.play("laser.wav", volume=0.8)

    audio.master_volume = 0.5
    assert backend.volumes[-1][1] == pytest.approx(0.4)

    audio.sound_volume = 0.25
    assert backend.volumes[-1][1] == pytest.approx(0.1)

    handle.set_volume(2.0)
    assert handle.volume == 1.0
    assert backend.volumes[-1][1] == pytest.approx(0.125)


def test_music_replaces_previous_track_and_defaults_to_looping(tmp_path):
    audio, backend = make_audio(tmp_path)
    first = audio.music("theme.ogg")
    second = audio.music("theme.ogg", volume=0.5)

    assert first.loop and not first.active
    assert second.loop and second.active
    assert second is audio.current_music
    assert backend.plays[-1][1:4] == (0.5, True, True)
    assert backend.stops == [backend.plays[0][4]]


def test_audio_aliases_missing_files_and_shutdown(tmp_path):
    audio, backend = make_audio(tmp_path)
    audio.assets.register("laser", "laser.wav")
    handle = audio.play("laser")
    assert handle.path == tmp_path / "laser.wav"

    with pytest.raises(FileNotFoundError):
        audio.play("missing.wav")

    audio.shutdown()
    assert not handle.active
    assert backend.stop_all_calls == 1
    assert backend.closed


def test_live_reload_restarts_music_in_place_and_preserves_settings(tmp_path):
    audio, backend = make_audio(tmp_path)
    audio.master_volume = 0.5
    handle = audio.music("theme.ogg", volume=0.8, loop=True)
    original_token = handle._token
    audio.enable_live_reload()

    theme = tmp_path / "theme.ogg"
    theme.write_bytes(b"changed-audio-data")
    results = audio.poll_live_reload()

    assert len(results) == 1
    assert results[0].kind == "modified"
    assert handle.active
    assert handle is audio.current_music
    assert handle._token is not original_token
    assert backend.stops[-1] is original_token
    assert backend.plays[-1][:4] == (theme, 0.4, True, True)
    assert audio.reload_events[-1].restarted == 1
    assert audio.reload_events[-1].error is None


def test_live_reload_does_not_restart_one_shot_by_default(tmp_path):
    audio, backend = make_audio(tmp_path)
    handle = audio.play("laser.wav", volume=0.7)
    token = handle._token
    audio.enable_live_reload()

    laser = tmp_path / "laser.wav"
    laser.write_bytes(b"changed")
    audio.poll_live_reload()

    assert handle.active
    assert handle._token is token
    assert backend.stops == []
    assert len(backend.plays) == 1
    assert audio.reload_events[-1].skipped == 1


def test_live_reload_can_restart_one_shots_when_requested(tmp_path):
    audio, backend = make_audio(tmp_path)
    handle = audio.play("laser.wav")
    token = handle._token
    audio.enable_live_reload(restart_one_shots=True)

    laser = tmp_path / "laser.wav"
    laser.write_bytes(b"changed")
    audio.poll_live_reload()

    assert handle.active
    assert handle._token is not token
    assert backend.stops[-1] is token
    assert audio.reload_events[-1].restarted == 1


def test_live_reload_stops_active_handle_when_asset_is_deleted(tmp_path):
    audio, backend = make_audio(tmp_path)
    handle = audio.music("theme.ogg")
    token = handle._token
    audio.enable_live_reload()

    (tmp_path / "theme.ogg").unlink()
    results = audio.poll_live_reload()

    assert len(results) == 1
    assert results[0].kind == "deleted"
    assert not handle.active
    assert audio.current_music is None
    assert audio.active_handles == ()
    assert backend.stops[-1] is token
    assert audio.reload_events[-1].stopped == 1


def test_live_reload_failure_deactivates_handle_and_records_error(tmp_path):
    audio, backend = make_audio(tmp_path)
    handle = audio.music("theme.ogg")
    audio.enable_live_reload()
    backend.fail_play = True

    theme = tmp_path / "theme.ogg"
    theme.write_bytes(b"changed")
    audio.poll_live_reload()

    assert not handle.active
    assert audio.current_music is None
    assert audio.active_handles == ()
    assert audio.reload_events[-1].error == "restart failed: play failed"


def test_live_reload_lifecycle_watches_new_handles_and_unbinds(tmp_path):
    audio, _backend = make_audio(tmp_path)
    assert audio.enable_live_reload() is audio
    assert audio.live_reload_enabled

    handle = audio.play("laser.wav", loop=True)
    assert handle.path.resolve() in audio.assets.watcher.paths
    assert audio.disable_live_reload() is True
    assert audio.disable_live_reload() is False
    assert not audio.live_reload_enabled
