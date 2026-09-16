from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pytest

from swirengine import AssetManager, Cube3D, Scene, Sprite2D, Vec3
from swirengine.editor_assets import EditorAssetBrowser
from swirengine.editor_authoring import EditorAuthoringTransaction
from swirengine.editor_authoring_workspace import (
    EditorAuthoringFrontendController,
    EditorAuthoringWorkspace,
)


@dataclass
class Actor:
    name: str
    health: int = 100
    enabled: bool = True


@dataclass
class AssetHolder:
    name: str
    resource: object
    enabled: bool = True


def test_authoring_workspace_preserves_legacy_replace_selection_default() -> None:
    scene = Scene()
    first = scene.add(Actor("First"))
    second = scene.add(Actor("Second"))
    workspace = EditorAuthoringWorkspace(scene)

    assert workspace.select(first) is first
    assert workspace.selection.count == 1
    assert workspace.inspector.selected_target is first

    assert workspace.select(second) is second
    assert workspace.selection.count == 1
    assert workspace.selection.primary_key == workspace.inspector.key_for(second)
    assert workspace.inspector.selected_target is second


def test_authoring_frontend_marks_every_selected_hierarchy_row() -> None:
    scene = Scene()
    first = scene.add(Actor("First"))
    second = scene.add(Actor("Second"))
    third = scene.add(Actor("Third"))
    workspace = EditorAuthoringWorkspace(scene)
    controller = EditorAuthoringFrontendController(workspace)

    controller.select(workspace.inspector.key_for(first))
    controller.select(workspace.inspector.key_for(second), mode="add")
    frame = controller.frame()

    selected = [row.label for row in frame.hierarchy if row.selected]
    assert selected == ["First", "Second"]
    assert workspace.inspector.selected_target is second
    assert controller.status == "Selected 2 items"
    assert third not in workspace.authoring.selected_targets


def test_frontend_range_select_and_property_edit_are_one_logical_undo() -> None:
    scene = Scene()
    first = scene.add(Actor("First", health=100))
    second = scene.add(Actor("Second", health=80))
    third = scene.add(Actor("Third", health=60))
    workspace = EditorAuthoringWorkspace(scene)
    controller = EditorAuthoringFrontendController(workspace)

    controller.select_range(
        workspace.inspector.key_for(first),
        workspace.inspector.key_for(third),
    )
    value = controller.edit_property("health", "25")

    assert value == 25
    assert (first.health, second.health, third.health) == (25, 25, 25)
    assert controller.status == "Changed health on 3 items"
    assert controller.undo() is True
    assert (first.health, second.health, third.health) == (100, 80, 60)
    assert controller.redo() is True
    assert (first.health, second.health, third.health) == (25, 25, 25)


def test_asset_drop_updates_mixed_string_and_path_targets_as_one_transaction(tmp_path) -> None:
    root = tmp_path / "assets"
    (root / "textures").mkdir(parents=True)
    (root / "textures" / "hero.png").write_bytes(b"png")
    browser = EditorAssetBrowser(AssetManager(root))
    payload = browser.drag_payload("textures/hero.png")

    scene = Scene()
    first = scene.add(Sprite2D("textures/old.png", name="First"))
    second = scene.add(Sprite2D(Path("textures/other.png"), name="Second"))
    workspace = EditorAuthoringWorkspace(scene)
    controller = EditorAuthoringFrontendController(workspace)
    controller.select(workspace.inspector.key_for(first))
    controller.select(workspace.inspector.key_for(second), mode="add")

    result = controller.drop_asset_on_property("texture", payload)

    assert result.relative_path == "textures/hero.png"
    assert result.transaction.edit_count == 2
    assert first.texture == "textures/hero.png"
    assert second.texture == Path("textures/hero.png")
    assert controller.status == "Dropped hero.png on texture for 2 items"

    assert controller.undo() is True
    assert first.texture == "textures/old.png"
    assert second.texture == Path("textures/other.png")
    assert controller.redo() is True
    assert first.texture == "textures/hero.png"
    assert second.texture == Path("textures/hero.png")


def test_asset_drop_preflights_mixed_selection_before_first_mutation(tmp_path) -> None:
    root = tmp_path / "assets"
    root.mkdir()
    (root / "theme.dat").write_bytes(b"data")
    payload = EditorAssetBrowser(AssetManager(root)).drag_payload("theme.dat")

    scene = Scene()
    compatible = scene.add(AssetHolder("Compatible", "old.dat"))
    incompatible = scene.add(AssetHolder("Incompatible", 42))
    workspace = EditorAuthoringWorkspace(scene)
    workspace.select(compatible)
    workspace.select(incompatible, mode="add")

    with pytest.raises(TypeError, match="cannot receive an asset path"):
        workspace.drop_asset_on_selected_property(payload, "resource")

    assert compatible.resource == "old.dat"
    assert incompatible.resource == 42
    assert not workspace.inspector.can_undo


def test_workspace_multi_gizmo_uses_viewport_snap_settings() -> None:
    scene = Scene()
    first = scene.add(Cube3D(position=Vec3(0.0, 0.0, -5.0)))
    second = scene.add(Cube3D(position=Vec3(5.0, 0.0, -5.0)))
    workspace = EditorAuthoringWorkspace(scene)
    workspace.select(first)
    workspace.select(second, mode="add")
    workspace.configure_viewport(snap_enabled=True, translation_snap=2.0)

    result = workspace.apply_selected_gizmo("translate", "x", 1.2)

    assert result.transaction.edit_count == 2
    assert first.position.x == pytest.approx(2.0)
    assert second.position.x == pytest.approx(6.0)
    undone = workspace.undo()
    assert isinstance(undone, EditorAuthoringTransaction)
    assert first.position.x == pytest.approx(0.0)
    assert second.position.x == pytest.approx(5.0)


def test_switch_scene_rebinds_authoring_session_to_new_inspector() -> None:
    first_scene = Scene()
    old = first_scene.add(Actor("Old"))
    second_scene = Scene()
    new = second_scene.add(Actor("New"))
    workspace = EditorAuthoringWorkspace(first_scene, scene_id="first")
    workspace.select(old)

    workspace.switch_scene("second", second_scene, restore=False)

    assert workspace.authoring.inspector is workspace.inspector
    assert workspace.selection.count == 0
    assert workspace.select(new) is new
    assert workspace.inspector.selected_target is new
