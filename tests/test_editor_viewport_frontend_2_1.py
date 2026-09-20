from pathlib import Path

import pytest

from swirengine.core.scene import Scene
from swirengine.editor_project_authoring21 import EditorProjectAuthoring21
from swirengine.editor_viewport_frontend21 import EditorProductionViewportController21
from swirengine.editor_workspace import EditorWorkspace
from swirengine.graphics.camera3d import Camera3D
from swirengine.graphics.primitives import Cube3D, Rectangle2D
from swirengine.math.types import Vec3


def _controller(scene: Scene, tmp_path: Path, *, mode: str) -> EditorProductionViewportController21:
    workspace = EditorWorkspace(scene, project_name="Viewport")
    workspace.configure_viewport(mode=mode)
    authoring = EditorProjectAuthoring21(workspace, asset_root=tmp_path / "assets")
    return EditorProductionViewportController21(workspace, authoring)


def test_viewport_pick_synchronizes_creator_selection(tmp_path: Path) -> None:
    scene = Scene()
    back = scene.add(Rectangle2D(0.0, 0.0, 100.0, 100.0, name="Back", layer=1))
    front = scene.add(Rectangle2D(0.0, 0.0, 60.0, 60.0, name="Front", layer=5))
    controller = _controller(scene, tmp_path, mode="2d")

    hit = controller.viewport_pick(400.0, 300.0, 800.0, 600.0)

    assert hit is not None
    assert controller.workspace.inspector.selected_target is front
    assert controller.authoring.components.selection_snapshot.keys == (
        controller.workspace.inspector.key_for(front),
    )
    assert controller.workspace.inspector.selected_target is not back

    assert controller.viewport_pick(0.0, 0.0, 800.0, 600.0) is None
    assert controller.authoring.components.selection_snapshot.count == 0


def test_viewport_translation_uses_grouped_creator_history(tmp_path: Path) -> None:
    scene = Scene()
    left = scene.add(Rectangle2D(-20.0, 0.0, 20.0, 20.0, name="Left"))
    right = scene.add(Rectangle2D(20.0, 0.0, 20.0, 20.0, name="Right"))
    controller = _controller(scene, tmp_path, mode="2d")
    left_key = controller.workspace.inspector.key_for(left)
    right_key = controller.workspace.inspector.key_for(right)
    controller.select_many([left_key, right_key], primary_key=right_key)

    transactions = controller.viewport_translate_selection(10.0, 0.0, 600.0)

    assert len(transactions) == 1
    assert transactions[0].transaction.edit_count == 2
    assert left.x == pytest.approx(-10.0)
    assert right.x == pytest.approx(30.0)
    assert controller.undo()
    assert left.x == pytest.approx(-20.0)
    assert right.x == pytest.approx(20.0)


def test_viewport_controller_rebinds_after_workspace_scene_switch(tmp_path: Path) -> None:
    first_scene = Scene()
    first_scene.add(Rectangle2D(0.0, 0.0, 50.0, 50.0, name="First"))
    controller = _controller(first_scene, tmp_path, mode="2d")
    first_viewport = controller.viewport_controller

    second_scene = Scene()
    second = second_scene.add(Rectangle2D(0.0, 0.0, 80.0, 80.0, name="Second"))
    controller.workspace.switch_scene("second", second_scene, restore=False)
    controller.workspace.configure_viewport(mode="2d")

    hit = controller.viewport_pick(400.0, 300.0, 800.0, 600.0)

    assert hit is not None
    assert controller.viewport_controller is not first_viewport
    assert controller.workspace.inspector.selected_target is second
    assert controller.authoring.components.selection_snapshot.primary_key == hit.target_key


def test_3d_creator_viewport_pick_pan_and_dolly(tmp_path: Path) -> None:
    scene = Scene()
    cube = scene.add(Cube3D(position=Vec3(0.0, 0.0, -5.0), size=2.0, name="Cube"))
    controller = _controller(scene, tmp_path, mode="3d")
    controller.camera_3d = Camera3D(
        position=Vec3(0.0, 0.0, 0.0),
        target=Vec3(0.0, 0.0, -5.0),
    )

    hit = controller.viewport_pick(400.0, 300.0, 800.0, 600.0)
    assert hit is not None
    assert controller.workspace.inspector.selected_target is cube

    before_x = controller.camera_3d.position.x
    controller.viewport_pan(60.0, 0.0, 600.0)
    assert controller.camera_3d.position.x < before_x

    before_z = controller.camera_3d.position.z
    controller.viewport_zoom(1.0)
    assert controller.camera_3d.position.z < before_z


def test_3d_viewport_translation_moves_multi_selection_together(tmp_path: Path) -> None:
    scene = Scene()
    left = scene.add(Cube3D(position=Vec3(-1.0, 0.0, -5.0), name="Left"))
    right = scene.add(Cube3D(position=Vec3(1.0, 0.0, -5.0), name="Right"))
    controller = _controller(scene, tmp_path, mode="3d")
    controller.camera_3d = Camera3D(
        position=Vec3(0.0, 0.0, 0.0),
        target=Vec3(0.0, 0.0, -5.0),
    )
    controller.select_many(
        [
            controller.workspace.inspector.key_for(left),
            controller.workspace.inspector.key_for(right),
        ],
        primary_key=controller.workspace.inspector.key_for(right),
    )

    transactions = controller.viewport_translate_selection(60.0, 0.0, 600.0)

    assert transactions
    assert left.position.x > -1.0
    assert right.position.x > 1.0
    assert left.position.x + 2.0 == pytest.approx(right.position.x)
    while controller.undo():
        pass
    assert left.position.x == pytest.approx(-1.0)
    assert right.position.x == pytest.approx(1.0)
