from __future__ import annotations

from pathlib import Path

import pytest

from swirengine.cli import new_project
from swirengine.editor_app21 import EditorProjectSession
from swirengine.editor_console_navigation21 import TkConsoleNavigationEditorApp21
from swirengine.editor_gameplay_frontend21 import (
    EditorGameplayPanelController21,
    TkGameplayEditorApp21,
)
from swirengine.editor_gameplay_tooling21 import EditorGameplayTooling21
from swirengine.input import InputBinding
from swirengine.shipping19 import ProjectShippingDefaults, ShippingContractError


def test_gameplay_panel_exposes_actions_bindings_conflicts_and_dirty_state(tmp_path: Path) -> None:
    tooling = EditorGameplayTooling21(tmp_path)
    controller = EditorGameplayPanelController21(tooling)

    initial = controller.frame("pause")
    assert initial.selected_action == "pause"
    assert len(initial.bindings) == 2
    assert initial.dirty is False
    assert any("key:escape" in conflict for conflict in initial.conflicts)

    changed = controller.add_key("pause", "p")
    assert changed.dirty is True
    assert [row.binding for row in changed.bindings] == [
        InputBinding("key", "escape"),
        InputBinding("gamepad_button", "START"),
        InputBinding("key", "p"),
    ]
    assert controller.status == "Added key binding to pause"


def test_gameplay_panel_can_create_multi_binding_action_and_remove_one(tmp_path: Path) -> None:
    controller = EditorGameplayPanelController21(EditorGameplayTooling21(tmp_path))

    controller.add_key("jump", "space")
    controller.add_gamepad_button("jump", "a")
    controller.add_gamepad_axis("jump", "left_y", direction=-1, threshold=0.6)

    frame = controller.frame("jump")
    assert len(frame.bindings) == 3
    assert frame.bindings[1].binding.control == "A"
    assert frame.bindings[2].binding.control == "LEFT_Y"
    assert "threshold 0.6" in frame.bindings[2].display

    frame = controller.remove_binding("jump", 1)
    assert [row.binding.kind for row in frame.bindings] == ["key", "gamepad_axis"]


def test_gameplay_panel_cannot_remove_last_required_ui_binding(tmp_path: Path) -> None:
    tooling = EditorGameplayTooling21(tmp_path)
    controller = EditorGameplayPanelController21(tooling)
    tooling.replace_action("ui_accept", (InputBinding("key", "enter"),))

    with pytest.raises(ShippingContractError, match="required shipping actions"):
        controller.remove_binding("ui_accept", 0)

    assert tooling.actions.bindings("ui_accept") == (InputBinding("key", "enter"),)


def test_gameplay_panel_authors_validated_display_and_accessibility_defaults(tmp_path: Path) -> None:
    controller = EditorGameplayPanelController21(EditorGameplayTooling21(tmp_path))

    frame = controller.update_display(
        width=1920,
        height=1080,
        fullscreen=True,
        borderless=True,
        vsync=False,
        max_fps=144,
        ui_scale=1.25,
    )
    assert frame.settings.display.width == 1920
    assert frame.settings.display.borderless is True
    assert frame.settings.display.max_fps == 144
    assert frame.dirty is True

    frame = controller.update_accessibility(
        text_scale=1.4,
        reduced_motion=True,
        high_contrast=True,
        subtitles=True,
        hold_to_confirm=True,
    )
    assert frame.settings.accessibility.text_scale == pytest.approx(1.4)
    assert frame.settings.accessibility.reduced_motion is True
    assert frame.settings.accessibility.high_contrast is True

    with pytest.raises(ShippingContractError, match="borderless"):
        controller.update_display(fullscreen=False, borderless=True)


def test_gameplay_panel_changes_persist_through_project_save(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    root = new_project("GameplayPanel", "2d")
    session = EditorProjectSession.open(root)
    controller = EditorGameplayPanelController21(session.gameplay)

    controller.add_key("jump", "space")
    controller.add_gamepad_button("jump", "a")
    controller.update_display(width=1600, height=900)
    controller.update_accessibility(reduced_motion=True)
    assert session.summary().dirty is True

    session.save()
    runtime = ProjectShippingDefaults.load(root)
    assert runtime.actions.bindings("jump") == (
        InputBinding("key", "space"),
        InputBinding("gamepad_button", "A"),
    )
    assert runtime.settings.display.width == 1600
    assert runtime.settings.display.height == 900
    assert runtime.settings.accessibility.reduced_motion is True
    assert session.summary().dirty is False


def test_gameplay_shell_preserves_console_navigation_capability() -> None:
    assert issubclass(TkGameplayEditorApp21, TkConsoleNavigationEditorApp21)