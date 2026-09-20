from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pytest

from swirengine import Color, Rectangle2D
from swirengine.cli import new_project
from swirengine.core.scene import Scene
from swirengine.editor_app21 import EditorProjectSession
from swirengine.editor_creator_frontend21 import EditorCreatorFrontendController21
from swirengine.editor_project_authoring21 import EditorProjectAuthoring21
from swirengine.editor_workspace import EditorWorkspace


def _creator_controller(
    scene: Scene,
    asset_root: Path,
    *,
    component_factories=None,
) -> EditorCreatorFrontendController21:
    workspace = EditorWorkspace(scene, scene_id="scenes/main.swirscene", project_name="Creator")
    authoring = EditorProjectAuthoring21(workspace, asset_root=asset_root)
    return EditorCreatorFrontendController21(
        workspace,
        authoring,
        component_factories=component_factories,
    )


def test_creator_frontend_multi_selection_uses_typed_grouped_history(tmp_path: Path) -> None:
    scene = Scene()
    left = scene.add(Rectangle2D(1.0, 2.0, 10.0, 10.0, Color(), name="Left"))
    right = scene.add(Rectangle2D(5.0, 6.0, 10.0, 10.0, Color(), name="Right"))
    controller = _creator_controller(scene, tmp_path / "assets")
    left_key = controller.workspace.inspector.key_for(left)
    right_key = controller.workspace.inspector.key_for(right)

    keys = controller.select_many([left_key, right_key], primary_key=right_key)
    frame = controller.frame()
    x_field = next(field for field in frame.inspector_fields if field.name == "x")

    assert keys == (left_key, right_key)
    assert sum(row.selected for row in frame.hierarchy) == 2
    assert x_field.mixed
    assert x_field.display_value == "<mixed>"

    controller.edit_property("x", "12.5")
    assert left.x == pytest.approx(12.5)
    assert right.x == pytest.approx(12.5)
    assert controller.undo()
    assert left.x == pytest.approx(1.0)
    assert right.x == pytest.approx(5.0)
    assert controller.redo()
    assert left.x == pytest.approx(12.5)
    assert right.x == pytest.approx(12.5)


def test_creator_frontend_asset_assignment_stays_project_relative(tmp_path: Path) -> None:
    @dataclass(slots=True)
    class Visual:
        name: str
        texture: Path = Path("textures/default.png")

    scene = Scene()
    visual = scene.add(Visual("Player"))
    controller = _creator_controller(scene, tmp_path / "assets")
    controller.select(controller.workspace.inspector.key_for(visual))

    texture = next(field for field in controller.frame().inspector_fields if field.name == "texture")
    assert texture.kind == "asset_path"
    assert texture.display_value == "textures/default.png"

    assigned = controller.edit_property("texture", "textures/player.png")
    assert assigned == "textures/player.png"
    assert visual.texture == Path("textures/player.png")

    with pytest.raises(ValueError, match="project-relative"):
        controller.edit_property("texture", "../outside.png")
    assert visual.texture == Path("textures/player.png")


def test_creator_frontend_component_actions_share_creator_history(tmp_path: Path) -> None:
    @dataclass(slots=True)
    class Health:
        value: int = 100

    scene = Scene()
    first = scene.create_entity(name="First")
    second = scene.create_entity(name="Second")
    controller = _creator_controller(
        scene,
        tmp_path / "assets",
        component_factories={"Health": Health},
    )
    controller.select_many(
        [
            controller.workspace.inspector.key_for(first),
            controller.workspace.inspector.key_for(second),
        ]
    )

    assert controller.available_add_component_names() == ("Health",)
    controller.add_component_by_name("Health")
    assert first.require(Health).value == 100
    assert second.require(Health).value == 100

    remove_name = f"{Health.__module__}.{Health.__qualname__}"
    assert controller.available_remove_component_names() == (remove_name,)
    controller.remove_component_by_name(remove_name)
    assert first.get(Health) is None
    assert second.get(Health) is None
    assert controller.undo()
    assert first.require(Health).value == 100
    assert second.require(Health).value == 100


def test_component_factory_discovery_does_not_instantiate_factory(tmp_path: Path) -> None:
    @dataclass(slots=True)
    class Health:
        value: int = 100

    calls = 0

    def make_health() -> Health:
        nonlocal calls
        calls += 1
        return Health()

    scene = Scene()
    entity = scene.create_entity(name="Player")
    controller = _creator_controller(
        scene,
        tmp_path / "assets",
        component_factories={"Health": make_health},
    )
    controller.select(controller.workspace.inspector.key_for(entity))

    assert controller.available_add_component_names() == ("Health",)
    assert calls == 0

    controller.add_component_by_name("Health")
    assert calls == 1
    assert entity.require(Health).value == 100
    assert controller.available_add_component_names() == ()
    assert calls == 1

    remove_name = f"{Health.__module__}.{Health.__qualname__}"
    assert controller.available_remove_component_names() == (remove_name,)
    assert calls == 1


def test_creator_frontend_prefab_create_instantiate_apply_revert(tmp_path: Path) -> None:
    scene = Scene()
    source = scene.add(Rectangle2D(2.0, 3.0, 8.0, 9.0, Color(), name="Source"))
    controller = _creator_controller(scene, tmp_path / "assets")
    controller.select(controller.workspace.inspector.key_for(source))

    asset = controller.create_prefab("crate", relative_path="prefabs/crate.swirprefab")
    assert asset.relative_path == "prefabs/crate.swirprefab"
    assert (tmp_path / "assets" / "prefabs" / "crate.swirprefab").is_file()

    created = controller.instantiate_prefab("crate")
    assert controller.prefab_asset_ids() == ("crate",)
    assert controller.prefab_binding_ids() == (created.binding.binding_id,)
    assert len(scene.objects) == 2

    controller.edit_property("x", "50")
    instance = created.instance.objects[0]
    assert instance.x == pytest.approx(50.0)
    controller.revert_prefab(created.binding.binding_id)
    assert instance.x == pytest.approx(2.0)

    controller.edit_property("x", "25")
    updated = controller.apply_prefab(created.binding.binding_id)
    assert updated.revision == 2
    assert updated.prefab.templates()[0].x == pytest.approx(25.0)


def test_project_session_uses_project_aware_creator_frontend(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    root = new_project("CreatorSession", "2d")

    session = EditorProjectSession.open(root)

    assert isinstance(session.controller, EditorCreatorFrontendController21)
    assert session.controller.authoring is session.authoring
    assert session.authoring.workspace is session.workspace
    assert session.authoring.prefabs.asset_root == root.resolve() / "assets"
