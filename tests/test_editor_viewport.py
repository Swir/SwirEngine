import pytest

from swirengine.core.scene import Scene
from swirengine.editor_viewport import EditorViewportController
from swirengine.editor_workspace import EditorWorkspace
from swirengine.graphics.camera3d import Camera3D
from swirengine.graphics.mesh import Mesh3D, cube_mesh
from swirengine.math.types import Vec3


def _workspace_with_cube(position: Vec3 = Vec3(0.0, 0.0, -5.0)):
    scene = Scene()
    cube = scene.add(Mesh3D(cube_mesh(), position=position, name="Cube"))
    workspace = EditorWorkspace(scene)
    return workspace, cube, EditorViewportController(workspace)


def test_center_pick_selects_visible_mesh():
    workspace, cube, viewport = _workspace_with_cube()
    camera = Camera3D()

    hit = viewport.pick_3d(camera, 400, 300, 800, 600)

    assert hit is not None
    assert hit.target_key == workspace.inspector.key_for(cube)
    assert workspace.inspector.selected_target is cube
    assert hit.distance == pytest.approx(4.1339746, rel=1e-5)


def test_pick_prefers_nearest_mesh():
    scene = Scene()
    near = scene.add(Mesh3D(cube_mesh(), position=Vec3(0.0, 0.0, -3.0)))
    scene.add(Mesh3D(cube_mesh(), position=Vec3(0.0, 0.0, -7.0)))
    workspace = EditorWorkspace(scene)
    viewport = EditorViewportController(workspace)

    hit = viewport.pick_3d(Camera3D(), 320, 240, 640, 480)

    assert hit is not None
    assert hit.target_key == workspace.inspector.key_for(near)


def test_miss_clears_selection_by_default():
    workspace, cube, viewport = _workspace_with_cube()
    workspace.select(cube)

    hit = viewport.pick_3d(Camera3D(), 0, 0, 800, 600)

    assert hit is None
    assert workspace.inspector.selected_target is None


def test_screen_ray_points_forward_at_viewport_center():
    _, _, viewport = _workspace_with_cube()
    camera = Camera3D()

    ray = viewport.ray_from_screen(camera, 400, 300, 800, 600)

    assert ray.origin == camera.position
    assert ray.direction.x == pytest.approx(0.0)
    assert ray.direction.y == pytest.approx(0.0)
    assert ray.direction.z == pytest.approx(-1.0)


def test_drag_selected_3d_routes_through_gizmo_history():
    workspace, cube, viewport = _workspace_with_cube()
    workspace.select(cube)
    before = Vec3(cube.position.x, cube.position.y, cube.position.z)

    edits = viewport.drag_selected_3d(Camera3D(), 60, -30, 600)

    assert edits
    assert cube.position.x > before.x
    assert cube.position.y > before.y
    assert workspace.inspector.can_undo

    while workspace.inspector.can_undo:
        workspace.undo()
    assert cube.position.x == pytest.approx(before.x)
    assert cube.position.y == pytest.approx(before.y)
    assert cube.position.z == pytest.approx(before.z)


def test_invalid_viewport_dimensions_are_rejected():
    _, _, viewport = _workspace_with_cube()

    with pytest.raises(ValueError, match="viewport width"):
        viewport.ray_from_screen(Camera3D(), 0, 0, 0, 600)
