from __future__ import annotations

import json
from pathlib import Path

import pytest

from swirengine.editor_audio_frontend21 import EditorAudioPanelController21, TkAudioEditorApp21
from swirengine.editor_audio_tooling21 import EditorAudioTooling21, EditorAudioToolingError
from swirengine.editor_navigation_frontend21 import TkNavigationEditorApp21


class RecordingAudioBackend:
    def __init__(self) -> None:
        self.play_calls: list[tuple[Path, float, bool, bool]] = []
        self.volume_calls: list[tuple[object, float]] = []
        self.stopped: list[object] = []
        self.closed = False

    def play(self, path: Path, *, volume: float, loop: bool, music: bool) -> object:
        token = object()
        self.play_calls.append((path, volume, loop, music))
        return token

    def stop(self, token: object) -> None:
        self.stopped.append(token)

    def set_volume(self, token: object, volume: float) -> None:
        self.volume_calls.append((token, volume))

    def stop_all(self) -> None:
        return None

    def close(self) -> None:
        self.closed = True


def _seed_audio(tooling: EditorAudioTooling21, root: Path) -> None:
    (root / "assets" / "audio").mkdir(parents=True)
    (root / "assets" / "audio" / "laser.wav").write_bytes(b"swir-audio-fixture")
    tooling.create_bus("ui", volume=0.5)
    tooling.create_cue("laser", "audio/laser.wav", bus="ui", volume=0.8, pan=0.25)


def test_audio_tooling_round_trips_deterministically(tmp_path: Path) -> None:
    tooling = EditorAudioTooling21(tmp_path)
    _seed_audio(tooling, tmp_path)
    assert tooling.dirty is True

    saved = tooling.save()
    first = (tmp_path / "config" / "audio.json").read_text(encoding="utf-8")
    assert saved.dirty is False

    reopened = EditorAudioTooling21(tmp_path)
    assert reopened.snapshot().buses == saved.buses
    assert reopened.snapshot().cues == saved.cues
    reopened.save()
    assert (tmp_path / "config" / "audio.json").read_text(encoding="utf-8") == first
    payload = json.loads(first)
    assert payload["format"] == "swirengine.audio-profile"
    assert payload["version"] == 1


def test_audio_preview_uses_shipping_audio_engine_and_authored_bus(tmp_path: Path) -> None:
    tooling = EditorAudioTooling21(tmp_path)
    _seed_audio(tooling, tmp_path)
    backend = RecordingAudioBackend()

    engine, handle = tooling.preview_cue("laser", backend=backend)

    assert handle.active is True
    assert handle.bus == "ui"
    assert handle.volume == 0.8
    assert backend.play_calls[0][0] == (tmp_path / "assets" / "audio" / "laser.wav").resolve()
    assert backend.play_calls[0][1] == pytest.approx(0.4)
    assert backend.play_calls[0][2:] == (False, False)
    engine.shutdown()
    assert backend.closed is True


def test_audio_music_and_spatial_contracts_are_validated(tmp_path: Path) -> None:
    tooling = EditorAudioTooling21(tmp_path)
    (tmp_path / "assets").mkdir()

    with pytest.raises(EditorAudioToolingError, match="music cues cannot"):
        tooling.create_cue("music", "music.ogg", music=True, position=(0.0, 0.0, 0.0))
    with pytest.raises(EditorAudioToolingError, match="maximum distance"):
        tooling.create_cue("bad-range", "sfx.wav", min_distance=5.0, max_distance=1.0)
    with pytest.raises(EditorAudioToolingError, match="between -1 and 1"):
        tooling.create_cue("bad-pan", "sfx.wav", pan=2.0)


def test_audio_bus_references_and_builtin_buses_are_protected(tmp_path: Path) -> None:
    tooling = EditorAudioTooling21(tmp_path)
    tooling.create_bus("dialogue")
    tooling.create_cue("voice", "voice.wav", bus="dialogue")

    with pytest.raises(EditorAudioToolingError, match="move audio cues"):
        tooling.remove_bus("dialogue")
    with pytest.raises(EditorAudioToolingError, match="built-in"):
        tooling.remove_bus("master")
    with pytest.raises(EditorAudioToolingError, match="unknown audio bus"):
        tooling.create_cue("bad", "bad.wav", bus="missing")


def test_audio_paths_cannot_escape_project_or_assets(tmp_path: Path) -> None:
    with pytest.raises(EditorAudioToolingError, match="project-relative"):
        EditorAudioTooling21(tmp_path, path="../outside.json")

    tooling = EditorAudioTooling21(tmp_path)
    with pytest.raises(EditorAudioToolingError, match="assets directory"):
        tooling.create_cue("escape", "../secret.wav")


def test_audio_panel_controller_exposes_creator_rows(tmp_path: Path) -> None:
    tooling = EditorAudioTooling21(tmp_path)
    controller = EditorAudioPanelController21(tooling)
    controller.create_bus("ambience", volume=0.35, muted=True)
    frame = controller.create_cue("wind", "audio/wind.ogg", bus="ambience", loop=True)

    assert {row.name for row in frame.buses} >= {"master", "music", "sfx", "ambience"}
    assert frame.cues[0].name == "wind"
    assert frame.cues[0].loop is True
    assert frame.dirty is True


def test_audio_shell_preserves_navigation_editor_capability() -> None:
    assert issubclass(TkAudioEditorApp21, TkNavigationEditorApp21)
