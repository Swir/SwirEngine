from __future__ import annotations

import json
from pathlib import Path

import pytest

from swirengine.cli import new_project
from swirengine.editor_app21 import EditorProjectSession
from swirengine.editor_gameplay_tooling21 import (
    EditorGameplayTooling21,
    EditorGameplayToolingError,
)
from swirengine.input import InputBinding
from swirengine.shipping19 import ProjectShippingDefaults, ShippingContractError


def test_gameplay_tooling_starts_from_shipping_defaults(tmp_path: Path) -> None:
    tooling = EditorGameplayTooling21(tmp_path)
    snapshot = tooling.snapshot()

    assert snapshot.dirty is False
    assert snapshot.controls_path == "config/controls.json"
    assert snapshot.settings_path == "config/settings.json"
    assert "ui_accept" in snapshot.actions.actions()
    assert snapshot.action_count >= 7
    assert snapshot.settings.display.width == 1280


def test_gameplay_tooling_authors_runtime_input_and_settings_end_to_end(
    tmp_path: Path,
) -> None:
    tooling = EditorGameplayTooling21(tmp_path)

    tooling.apply(
        actions={
            "jump": (
                InputBinding("key", "space"),
                InputBinding("gamepad_button", "A"),
            ),
            "interact": (InputBinding("key", "e"),),
        },
        display={"width": 1920, "height": 1080, "vsync": False, "max_fps": 144},
        accessibility={"subtitles": True, "text_scale": 1.25},
    )
    before_save = tooling.snapshot()
    assert before_save.dirty is True

    saved = tooling.save()
    assert saved.dirty is False
    assert tooling.controls_target.is_file()
    assert tooling.settings_target.is_file()

    runtime = ProjectShippingDefaults.load(tmp_path)
    assert runtime.actions.bindings("jump") == (
        InputBinding("key", "space"),
        InputBinding("gamepad_button", "A"),
    )
    assert runtime.actions.bindings("interact") == (InputBinding("key", "e"),)
    assert runtime.settings.display.width == 1920
    assert runtime.settings.display.height == 1080
    assert runtime.settings.display.vsync is False
    assert runtime.settings.display.max_fps == 144
    assert runtime.settings.accessibility.subtitles is True
    assert runtime.settings.accessibility.text_scale == 1.25


def test_editor_project_save_persists_gameplay_configuration(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    root = new_project("EditorGameplay", "2d")
    session = EditorProjectSession.open(root)

    assert session.gameplay.dirty is False
    session.gameplay.bind_key("pause", "p")
    session.gameplay.update_display(width=1600, height=900)
    assert session.summary().dirty is True

    session.save()

    assert session.gameplay.dirty is False
    runtime = ProjectShippingDefaults.load(root)
    assert runtime.actions.bindings("pause") == (InputBinding("key", "p"),)
    assert runtime.settings.display.width == 1600
    assert runtime.settings.display.height == 900

    reopened = EditorProjectSession.open(root)
    assert reopened.gameplay.actions.bindings("pause") == (InputBinding("key", "p"),)
    assert reopened.gameplay.settings.display.width == 1600
    assert reopened.summary().dirty is False


def test_gameplay_tooling_reload_discards_unsaved_editor_changes(tmp_path: Path) -> None:
    tooling = EditorGameplayTooling21(tmp_path)
    tooling.bind_key("pause", "p")
    tooling.update_display(width=1600, height=900)
    tooling.save()

    tooling.bind_key("pause", "q")
    tooling.update_display(width=1280, height=720)
    assert tooling.dirty is True

    restored = tooling.reload()
    assert restored.dirty is False
    assert restored.actions.bindings("pause") == (InputBinding("key", "p"),)
    assert restored.settings.display.width == 1600
    assert restored.settings.display.height == 900


def test_gameplay_tooling_reports_conflicts_without_blocking_known_shared_controls(
    tmp_path: Path,
) -> None:
    tooling = EditorGameplayTooling21(tmp_path)
    conflict = next(
        item for item in tooling.snapshot().conflicts if item.control == "key:escape"
    )

    assert conflict.actions == ("pause", "ui_back")
    tooling.bind_key("interact", "escape")
    updated = next(
        item for item in tooling.snapshot().conflicts if item.control == "key:escape"
    )
    assert updated.actions == ("interact", "pause", "ui_back")


def test_gameplay_tooling_preserves_required_ui_navigation(tmp_path: Path) -> None:
    tooling = EditorGameplayTooling21(tmp_path)

    with pytest.raises(ShippingContractError, match="required shipping actions"):
        tooling.replace_action("ui_accept", ())

    assert tooling.actions.bindings("ui_accept")
    assert tooling.dirty is False


def test_gameplay_tooling_binding_helpers_use_shipping_validation(tmp_path: Path) -> None:
    tooling = EditorGameplayTooling21(tmp_path)

    tooling.bind_gamepad_button("jump", "x", gamepad_id=1)
    assert tooling.actions.bindings("jump") == (
        InputBinding("gamepad_button", "X", gamepad_id=1),
    )

    tooling.bind_gamepad_axis(
        "move_x",
        "left_x",
        direction=1,
        threshold=0.6,
        scale=0.8,
    )
    binding = tooling.actions.bindings("move_x")[0]
    assert binding.control == "LEFT_X"
    assert binding.direction == 1
    assert binding.threshold == 0.6
    assert binding.scale == 0.8

    with pytest.raises(ShippingContractError, match="unknown gamepad button"):
        tooling.bind_gamepad_button("jump", "not-a-button")


def test_gameplay_tooling_reset_action_restores_standard_binding(tmp_path: Path) -> None:
    tooling = EditorGameplayTooling21(tmp_path)
    standard = tooling.actions.bindings("pause")

    tooling.bind_key("pause", "p")
    assert tooling.actions.bindings("pause") != standard
    tooling.reset_action("pause")
    assert tooling.actions.bindings("pause") == standard

    with pytest.raises(EditorGameplayToolingError, match="no standard"):
        tooling.reset_action("custom_action")


def test_gameplay_tooling_rejects_paths_outside_project(tmp_path: Path) -> None:
    with pytest.raises(EditorGameplayToolingError, match="project-relative"):
        EditorGameplayTooling21(tmp_path, controls_path="../controls.json")
    with pytest.raises(EditorGameplayToolingError, match="project-relative"):
        EditorGameplayTooling21(tmp_path, settings_path="C:\\settings.json")


def test_gameplay_tooling_revalidates_symlink_targets_before_save(tmp_path: Path) -> None:
    tooling = EditorGameplayTooling21(tmp_path)
    outside = tmp_path.parent / f"{tmp_path.name}-outside-config"
    outside.mkdir()
    config = tmp_path / "config"
    try:
        config.symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip("directory symlinks are unavailable on this runner")

    tooling.bind_key("pause", "p")
    with pytest.raises(EditorGameplayToolingError, match="escapes the project root"):
        tooling.save()

    assert not (outside / "controls.json").exists()
    assert not (outside / "settings.json").exists()


def test_gameplay_tooling_writes_canonical_shipping_envelopes(tmp_path: Path) -> None:
    tooling = EditorGameplayTooling21(tmp_path)
    tooling.bind_key("jump", "space")
    tooling.update_accessibility(reduced_motion=True)
    tooling.save()

    controls = json.loads(tooling.controls_target.read_text(encoding="utf-8"))
    settings = json.loads(tooling.settings_target.read_text(encoding="utf-8"))

    assert controls["format"] == "swirengine-input-profile"
    assert controls["version"] == 1
    assert settings["format"] == "swirengine-game-settings"
    assert settings["version"] == 1
    assert settings["accessibility"]["reduced_motion"] is True
