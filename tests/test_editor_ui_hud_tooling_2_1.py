from __future__ import annotations

import json
from pathlib import Path

import pytest

from swirengine.core.scene import Scene
from swirengine.editor_audio_frontend21 import TkAudioEditorApp21
from swirengine.editor_ui_frontend21 import EditorUIHudPanelController21, TkUIHudEditorApp21
from swirengine.editor_ui_tooling21 import EditorUIHudTooling21, EditorUIHudToolingError
from swirengine.ui import UIButton, UILabel, UIPanel, UIProgressBar


def _seed(tooling: EditorUIHudTooling21) -> None:
    tooling.create_element("title", "label", text="SWIR", x=120, y=60, layer=1200)
    tooling.create_element(
        "health-bg",
        "panel",
        x=180,
        y=110,
        width=300,
        height=42,
        color=(0.05, 0.08, 0.12, 0.9),
    )
    tooling.create_element(
        "health",
        "progress",
        x=180,
        y=110,
        width=280,
        height=20,
        value=0.75,
        color=(0.0, 0.53, 1.0, 1.0),
        layer=1002,
    )
    tooling.create_element("pause", "button", text="Pause", x=900, y=60)


def test_ui_hud_tooling_round_trips_deterministically(tmp_path: Path) -> None:
    tooling = EditorUIHudTooling21(tmp_path)
    _seed(tooling)
    assert tooling.dirty is True

    saved = tooling.save()
    first = (tmp_path / "config" / "ui-hud.json").read_text(encoding="utf-8")
    assert saved.dirty is False

    reopened = EditorUIHudTooling21(tmp_path)
    assert reopened.snapshot().elements == saved.elements
    reopened.save()
    assert (tmp_path / "config" / "ui-hud.json").read_text(encoding="utf-8") == first

    payload = json.loads(first)
    assert payload["format"] == "swirengine.ui-hud"
    assert payload["version"] == 1
    assert [item["name"] for item in payload["elements"]] == sorted(
        item["name"] for item in payload["elements"]
    )


def test_ui_hud_runtime_preview_uses_shipping_ui_manager(tmp_path: Path) -> None:
    tooling = EditorUIHudTooling21(tmp_path)
    _seed(tooling)
    scene = Scene()

    manager = tooling.build_runtime(scene)

    assert manager.scene is scene
    assert len(manager.controls) == 4
    assert any(isinstance(control, UILabel) for control in manager.controls)
    assert any(isinstance(control, UIPanel) for control in manager.controls)
    assert any(isinstance(control, UIButton) for control in manager.controls)
    assert any(isinstance(control, UIProgressBar) for control in manager.controls)
    assert len(scene.objects) == 6
    progress = next(control for control in manager.controls if isinstance(control, UIProgressBar))
    assert progress.value == pytest.approx(0.75)


def test_ui_hud_validation_rejects_invalid_values_and_paths(tmp_path: Path) -> None:
    with pytest.raises(EditorUIHudToolingError, match="project-relative"):
        EditorUIHudTooling21(tmp_path, path="../outside.json")

    tooling = EditorUIHudTooling21(tmp_path)
    with pytest.raises(EditorUIHudToolingError, match="kind"):
        tooling.create_element("unknown", "video")
    with pytest.raises(EditorUIHudToolingError, match="between 0 and 1"):
        tooling.create_element("health", "progress", value=2.0)
    with pytest.raises(EditorUIHudToolingError, match="greater than zero"):
        tooling.create_element("bad-panel", "panel", width=0)


def test_ui_hud_duplicate_and_update_preserve_unique_creator_ids(tmp_path: Path) -> None:
    tooling = EditorUIHudTooling21(tmp_path)
    tooling.create_element("score", "label", text="Score", x=10, y=20)
    tooling.duplicate_element("score", "score-shadow")
    snapshot = tooling.update_element("score-shadow", text="Shadow", layer=999)

    by_name = {item.name: item for item in snapshot.elements}
    assert by_name["score-shadow"].x == pytest.approx(34.0)
    assert by_name["score-shadow"].y == pytest.approx(44.0)
    assert by_name["score-shadow"].text == "Shadow"
    with pytest.raises(EditorUIHudToolingError, match="already exists"):
        tooling.duplicate_element("score", "score-shadow")


def test_ui_hud_panel_controller_exposes_runtime_validation(tmp_path: Path) -> None:
    controller = EditorUIHudPanelController21(EditorUIHudTooling21(tmp_path))
    controller.create_element("ammo", "label", text="Ammo: 30")
    frame = controller.create_element("reload", "button", text="Reload", x=320, y=80)
    assert tuple(row.name for row in frame.elements) == ("ammo", "reload")
    assert frame.dirty is True

    validated = controller.validate_runtime()
    assert validated.dirty is True
    assert controller.status.startswith("Runtime preview valid:")


def test_ui_hud_shell_preserves_audio_creator_capability() -> None:
    assert issubclass(TkUIHudEditorApp21, TkAudioEditorApp21)
