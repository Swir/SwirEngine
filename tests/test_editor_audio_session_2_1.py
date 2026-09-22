from __future__ import annotations

from pathlib import Path

from swirengine.cli import new_project
from swirengine.editor_app21 import EditorProjectSession
from swirengine.editor_asset_app21 import TkIntegratedEditorApp21
from swirengine.editor_asset_drop21 import TkNativeDropAssetPipelineEditorApp21
from swirengine.editor_audio_frontend21 import TkAudioEditorApp21
from swirengine.editor_integrated_session21 import EditorIntegratedProjectSession21


def test_integrated_audio_session_marks_project_dirty_and_saves(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    root = new_project("AudioSession", "2d")
    session = EditorIntegratedProjectSession21.open(root)

    session.audio.create_bus("dialogue", volume=0.75)
    session.audio.create_cue("welcome", "audio/welcome.wav", bus="dialogue")

    assert session.summary().dirty is True
    session.save()
    assert session.summary().dirty is False
    assert (root / "config" / "audio.json").is_file()

    reopened = EditorIntegratedProjectSession21.open(root)
    snapshot = reopened.audio.snapshot()
    assert {bus.name for bus in snapshot.buses} >= {"master", "music", "sfx", "dialogue"}
    assert tuple(cue.name for cue in snapshot.cues) == ("welcome",)
    assert reopened.summary().dirty is False


def test_project_hub_session_can_be_promoted_without_reopening(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    root = new_project("PromotedAudioSession", "3d")
    base = EditorProjectSession.open(root)

    promoted = EditorIntegratedProjectSession21.adopt(base)

    assert promoted.controller is base.controller
    assert promoted.workspace is base.workspace
    assert promoted.manifest is base.manifest
    assert promoted.audio.project_root == root.resolve()


def test_integrated_shell_combines_audio_and_native_asset_pipeline() -> None:
    assert issubclass(TkIntegratedEditorApp21, TkAudioEditorApp21)
    assert issubclass(TkIntegratedEditorApp21, TkNativeDropAssetPipelineEditorApp21)
