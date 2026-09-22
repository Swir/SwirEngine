from __future__ import annotations

import json
from pathlib import Path

import pytest

from swirengine.cli import new_project
from swirengine.editor_app21 import EditorProjectSession
from swirengine.editor_asset_app21 import TkIntegratedEditorApp21
from swirengine.editor_asset_drop21 import TkNativeDropAssetPipelineEditorApp21
from swirengine.editor_integrated_session21 import EditorIntegratedProjectSession21
from swirengine.editor_save_profile_frontend21 import (
    EditorSaveProfilePanelController21,
    TkSaveProfileEditorApp21,
)
from swirengine.editor_save_profile_tooling21 import (
    EditorSaveProfileTooling21,
    EditorSaveProfileToolingError,
)
from swirengine.editor_ui_frontend21 import TkUIHudEditorApp21


def test_save_profile_tooling_round_trips_deterministically(tmp_path: Path) -> None:
    tooling = EditorSaveProfileTooling21(tmp_path, project_name="Creator Game")
    assert tooling.config.app_id == "Creator-Game"
    assert tooling.dirty is False

    tooling.update_identity(default_profile="player-1", version=3)
    tooling.update_policy(
        autosave_keep=5,
        autosave_interval_seconds=45.0,
        max_manual_slots=24,
    )
    tooling.replace_defaults({"level": 1, "position": [0.0, 2.5]})
    assert tooling.dirty is True

    saved = tooling.save()
    first = (tmp_path / "config" / "save-profile.json").read_text(encoding="utf-8")
    assert saved.dirty is False

    reopened = EditorSaveProfileTooling21(tmp_path, project_name="Ignored")
    assert reopened.config == saved.config
    reopened.save()
    assert (tmp_path / "config" / "save-profile.json").read_text(encoding="utf-8") == first

    payload = json.loads(first)
    assert payload["format"] == "swirengine.save-profile"
    assert payload["format_version"] == 1
    assert payload["policy"]["autosave_keep"] == 5


def test_save_profile_runtime_preview_exercises_shipping_save_load(tmp_path: Path) -> None:
    tooling = EditorSaveProfileTooling21(tmp_path / "project", project_name="Runtime Game")
    user_data = tmp_path / "userdata"

    snapshot = tooling.validate_runtime(user_data)

    assert snapshot.dirty is False
    assert user_data.exists()


def test_save_profile_tooling_rejects_unsafe_paths_and_policy(tmp_path: Path) -> None:
    with pytest.raises(EditorSaveProfileToolingError, match="project-relative"):
        EditorSaveProfileTooling21(tmp_path, path="../outside.json")

    tooling = EditorSaveProfileTooling21(tmp_path, project_name="Safe")
    with pytest.raises(EditorSaveProfileToolingError, match="autosave_keep"):
        tooling.update_policy(autosave_keep=0)
    with pytest.raises(EditorSaveProfileToolingError, match="default profile"):
        tooling.update_identity(default_profile="../other")
    with pytest.raises(EditorSaveProfileToolingError, match="finite"):
        tooling.replace_defaults({"bad": float("nan")})


def test_save_profile_tooling_rejects_corrupt_or_unknown_config(tmp_path: Path) -> None:
    target = tmp_path / "config" / "save-profile.json"
    target.parent.mkdir(parents=True)
    target.write_text("{broken", encoding="utf-8")
    with pytest.raises(EditorSaveProfileToolingError, match="cannot read"):
        EditorSaveProfileTooling21(tmp_path, project_name="Broken")

    target.write_text(
        json.dumps(
            {
                "format": "swirengine.save-profile",
                "format_version": 1,
                "app_id": "Broken",
                "default_profile": "default",
                "version": 1,
                "policy": {"not_a_policy": 1},
                "defaults": {},
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(EditorSaveProfileToolingError, match="unknown save policy"):
        EditorSaveProfileTooling21(tmp_path, project_name="Broken")


def test_save_profile_panel_controller_validates_real_runtime(tmp_path: Path) -> None:
    controller = EditorSaveProfilePanelController21(
        EditorSaveProfileTooling21(tmp_path, project_name="Panel Game")
    )
    frame = controller.update_policy(autosave_keep=4, max_manual_slots=20)
    assert frame.dirty is True
    assert frame.autosave_keep == 4
    assert frame.max_manual_slots == 20

    controller.validate_runtime()
    assert controller.status == "Runtime save/load preview valid"


def test_integrated_save_profile_session_marks_project_dirty_and_saves(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    root = new_project("SaveProfileSession", "2d")
    session = EditorIntegratedProjectSession21.open(root)

    session.save_profile.update_identity(default_profile="campaign", version=2)
    session.save_profile.update_policy(autosave_keep=4, max_manual_slots=20)
    assert session.summary().dirty is True

    session.save()
    assert session.summary().dirty is False
    assert (root / "config" / "save-profile.json").is_file()

    reopened = EditorIntegratedProjectSession21.open(root)
    assert reopened.save_profile.config.default_profile == "campaign"
    assert reopened.save_profile.config.version == 2
    assert reopened.save_profile.config.policy.autosave_keep == 4
    assert reopened.summary().dirty is False


def test_project_hub_promotion_attaches_save_profile_without_reopening(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    root = new_project("PromotedSaveProfile", "3d")
    base = EditorProjectSession.open(root)

    promoted = EditorIntegratedProjectSession21.adopt(base)

    assert promoted.controller is base.controller
    assert promoted.workspace is base.workspace
    assert promoted.manifest is base.manifest
    assert promoted.save_profile.project_root == root.resolve()
    assert promoted.save_profile.config.app_id == "PromotedSaveProfile"


def test_save_profile_shell_preserves_ui_hud_and_asset_capabilities() -> None:
    assert issubclass(TkSaveProfileEditorApp21, TkUIHudEditorApp21)
    assert issubclass(TkIntegratedEditorApp21, TkSaveProfileEditorApp21)
    assert issubclass(TkIntegratedEditorApp21, TkNativeDropAssetPipelineEditorApp21)
