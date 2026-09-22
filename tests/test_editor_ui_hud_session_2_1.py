from __future__ import annotations

from pathlib import Path

from swirengine.cli import new_project
from swirengine.editor_app21 import EditorProjectSession
from swirengine.editor_asset_app21 import TkIntegratedEditorApp21
from swirengine.editor_asset_drop21 import TkNativeDropAssetPipelineEditorApp21
from swirengine.editor_integrated_session21 import EditorIntegratedProjectSession21
from swirengine.editor_ui_frontend21 import TkUIHudEditorApp21


def test_integrated_ui_hud_session_marks_project_dirty_and_saves(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    root = new_project("UIHudSession", "2d")
    session = EditorIntegratedProjectSession21.open(root)

    session.ui_hud.create_element("health", "progress", value=0.8, x=160, y=64)
    assert session.summary().dirty is True

    session.save()
    assert session.summary().dirty is False
    assert (root / "config" / "ui-hud.json").is_file()

    reopened = EditorIntegratedProjectSession21.open(root)
    snapshot = reopened.ui_hud.snapshot()
    assert tuple(item.name for item in snapshot.elements) == ("health",)
    assert snapshot.elements[0].value == 0.8
    assert reopened.summary().dirty is False


def test_project_hub_promotion_attaches_ui_hud_without_reopening(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    root = new_project("PromotedUIHudSession", "3d")
    base = EditorProjectSession.open(root)

    promoted = EditorIntegratedProjectSession21.adopt(base)

    assert promoted.controller is base.controller
    assert promoted.workspace is base.workspace
    assert promoted.manifest is base.manifest
    assert promoted.ui_hud.project_root == root.resolve()


def test_integrated_shell_combines_ui_hud_and_native_asset_pipeline() -> None:
    assert issubclass(TkIntegratedEditorApp21, TkUIHudEditorApp21)
    assert issubclass(TkIntegratedEditorApp21, TkNativeDropAssetPipelineEditorApp21)
