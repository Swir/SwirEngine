from __future__ import annotations

from pathlib import Path

import pytest

from swirengine.cli import new_project
from swirengine.editor_animation_frontend21 import (
    EditorAnimationPanelController21,
    TkAnimationEditorApp21,
    parse_animation_value21,
)
from swirengine.editor_animation_tooling21 import EditorAnimationTooling21
from swirengine.editor_app21 import EditorProjectSession
from swirengine.editor_gameplay_frontend21 import TkGameplayEditorApp21


def test_animation_panel_authors_previews_and_round_trips_runtime_clip(tmp_path: Path) -> None:
    controller = EditorAnimationPanelController21(EditorAnimationTooling21(tmp_path))

    frame = controller.new_clip("Player Run", duration=1.0, loop=True)
    assert frame.name == "Player Run"
    assert frame.path == "assets/animations/player-run.swiranim.json"
    assert frame.dirty is True

    controller.add_track("transform.position", initial_value=[0.0, 0.0])
    controller.set_keyframe("transform.position", 1.0, [8.0, 4.0])
    frame = controller.sample(0.5)
    assert frame.preview_time == pytest.approx(0.5)
    assert frame.preview_values == (("transform.position", [4.0, 2.0]),)

    saved = controller.save()
    assert saved.dirty is False

    reopened = EditorAnimationPanelController21(EditorAnimationTooling21(tmp_path))
    loaded = reopened.load(saved.path or "")
    assert loaded.name == "Player Run"
    assert loaded.tracks[0].binding == "transform.position"
    assert reopened.sample(0.25).preview_values == (("transform.position", [2.0, 1.0]),)


def test_animation_panel_edits_tracks_interpolation_and_keyframes(tmp_path: Path) -> None:
    controller = EditorAnimationPanelController21(EditorAnimationTooling21(tmp_path))
    controller.new_clip("Door", duration=2.0)
    controller.add_track("transform.rotation", initial_value=0.0)
    controller.set_keyframe("transform.rotation", 2.0, 90.0)
    controller.set_interpolation("transform.rotation", "step")

    frame = controller.frame()
    assert frame.tracks[0].interpolation == "step"
    assert frame.tracks[0].keyframe_count == 2
    assert controller.sample(1.5).preview_values == (("transform.rotation", 0.0),)

    frame = controller.remove_keyframe("transform.rotation", 2.0)
    assert frame.tracks[0].keyframe_count == 1
    frame = controller.remove_track("transform.rotation")
    assert frame.tracks == ()


def test_animation_value_parser_is_json_only_and_rejects_objects() -> None:
    assert parse_animation_value21("[1, 2.5, true]") == [1, 2.5, True]
    assert parse_animation_value21('"idle"') == "idle"

    with pytest.raises(ValueError, match="valid JSON"):
        parse_animation_value21("(1, 2)")
    with pytest.raises(ValueError, match="may not be JSON objects"):
        parse_animation_value21('{"x": 1}')


def test_project_session_tracks_and_saves_animation_authoring(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    root = new_project("AnimationPanel", "2d")
    session = EditorProjectSession.open(root)

    session.animation.new_clip("Idle", duration=1.0, loop=True)
    session.animation.add_track("sprite.frame", initial_value=0, interpolation="step")
    session.animation.set_keyframe("sprite.frame", 0.5, 1)
    assert session.summary().dirty is True

    session.save()
    assert session.summary().dirty is False
    target = root / "assets" / "animations" / "idle.swiranim.json"
    assert target.is_file()

    reopened = EditorAnimationTooling21(root)
    reopened.load("assets/animations/idle.swiranim.json")
    assert reopened.sample(0.75).values["sprite.frame"] == 1


def test_animation_shell_preserves_gameplay_editor_capability() -> None:
    assert issubclass(TkAnimationEditorApp21, TkGameplayEditorApp21)
