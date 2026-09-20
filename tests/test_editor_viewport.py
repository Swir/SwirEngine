import pytest

from swirengine.core.scene import Scene
from swirengine.editor_viewport import EditorViewportController
from swirengine.editor_workspace import EditorWorkspace
from swirengine.graphics.camera import Camera2D
from swirengine.graphics.camera3d import Camera3D
from swirengine.graphics.mesh import Mesh3D, cube_mesh
from swirengine.graphics.primitives import Cube3D, Rectangle2D, Sprite2D
from swirengine.math.types import Vec3


def _workspace_with_cube(position: Vec3 | None = None):
    if position is None:
        position = Vec3(0.0, 0.0, -5.0)
    scene = Scene()
    cube = scene.add(Mesh3D(cube_mesh(), position=position, name="Cube"))
    workspace = EditorWorkspace(scene)
    return workspace, cube, EditorViewportController(workspace)


def _workspace_with_rectangle(*, x: float = 0.0, y: float = 0.0):
    scene = Scene()
    rectangle = scene.add(Rectangle2D(x, y, 100.0, 80.0, name="Rectangle"))
    workspace = EditorWorkspace(scene)
    workspace.configure_viewport(mode="2d")
    return workspace, rectangle, EditorViewportController(workspace)


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


def test_pick_3d_supports_native_cube_primitive():
    scene = Scene()
    cube = scene.add(Cube3D(position=Vec3(0.0, 0.0, -5.0), size=2.0, name="Cube"))
    workspace = EditorWorkspace(scene)
    viewport = EditorViewportController(workspace)

    hit = viewport.pick_3d(Camera3D(), 400, 300, 800, 600)

    assert hit is not None
    assert hit.target_key == workspace.inspector.key_for(cube)
    assert workspace.inspector.selected_target is cube
    assert hit.distance == pytest.approx(5.0 - 3.0**0.5, rel=1e-6)


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


def test_2d_screen_world_conversion_matches_renderer_camera_convention():
    _, _, viewport = _workspace_with_rectangle()
    camera = Camera2D(x=10.0, y=-5.0, zoom=2.0)

    world = viewport.screen_to_world_2d(camera, 500.0, 250.0, 800.0, 600.0)
    screen = viewport.world_to_screen_2d(camera, world.x, world.y, 800.0, 600.0)

    assert world.x == pytest.approx(60.0)
    assert world.y == pytest.approx(20.0)
    assert screen.x == pytest.approx(500.0)
    assert screen.y == pytest.approx(250.0)


def test_pick_2d_prefers_highest_layer_then_latest_scene_order():
    scene = Scene()
    scene.add(Rectangle2D(0.0, 0.0, 100.0, 100.0, name="Back", layer=1))
    front = scene.add(Rectangle2D(0.0, 0.0, 100.0, 100.0, name="Front", layer=4))
    workspace = EditorWorkspace(scene)
    workspace.configure_viewport(mode="2d")
    viewport = EditorViewportController(workspace)

    hit = viewport.pick_2d(Camera2D(), 400.0, 300.0, 800.0, 600.0)

    assert hit is not None
    assert hit.target_key == workspace.inspector.key_for(front)
    assert hit.distance == 0.0
    assert workspace.inspector.selected_target is front


def test_pick_2d_respects_rotation_and_screen_space():
    scene = Scene()
    rotated = scene.add(
        Rectangle2D(0.0, 0.0, 20.0, 100.0, rotation=90.0, name="Rotated", layer=1)
    )
    overlay = scene.add(
        Rectangle2D(
            0.0,
            0.0,
            20.0,
            20.0,
            name="Overlay",
            layer=5,
            screen_space=True,
        )
    )
    workspace = EditorWorkspace(scene)
    workspace.configure_viewport(mode="2d")
    viewport = EditorViewportController(workspace)
    camera = Camera2D(x=500.0, y=500.0, zoom=2.0)

    center_hit = viewport.pick_2d(camera, 400.0, 300.0, 800.0, 600.0)
    rotated_point = viewport.world_to_screen_2d(camera, 30.0, 0.0, 800.0, 600.0)
    rotated_hit = viewport.pick_2d(
        Camera2D(),
        430.0,
        300.0,
        800.0,
        600.0,
        select=False,
    )

    assert center_hit is not None
    assert center_hit.target_key == workspace.inspector.key_for(overlay)
    assert rotated_point.x == pytest.approx(-540.0)
    assert rotated_hit is not None
    assert rotated_hit.target_key == workspace.inspector.key_for(rotated)


def test_pick_2d_skips_implicit_texture_size_sprite_without_io():
    scene = Scene()
    sprite = scene.add(Sprite2D("missing.png", x=0.0, y=0.0, name="Implicit"))
    rectangle = scene.add(Rectangle2D(0.0, 0.0, 20.0, 20.0, name="Fallback"))
    workspace = EditorWorkspace(scene)
    workspace.configure_viewport(mode="2d")
    viewport = EditorViewportController(workspace)

    hit = viewport.pick_2d(Camera2D(), 400.0, 300.0, 800.0, 600.0)

    assert hit is not None
    assert hit.target_key == workspace.inspector.key_for(rectangle)
    assert workspace.inspector.selected_target is not sprite


def test_drag_selected_2d_uses_zoom_and_gizmo_history():
    workspace, rectangle, viewport = _workspace_with_rectangle()
    workspace.select(rectangle)
    camera = Camera2D(zoom=2.0)

    edits = viewport.drag_selected_2d(camera, 20.0, -10.0)

    assert len(edits) == 2
    assert rectangle.x == pytest.approx(10.0)
    assert rectangle.y == pytest.approx(5.0)
    assert workspace.inspector.can_undo
    workspace.undo()
    workspace.undo()
    assert rectangle.x == pytest.approx(0.0)
    assert rectangle.y == pytest.approx(0.0)


def test_drag_selected_2d_requires_translate_gizmo():
    workspace, rectangle, viewport = _workspace_with_rectangle()
    workspace.select(rectangle)
    workspace.configure_viewport(gizmo="rotate")

    with pytest.raises(RuntimeError, match="translate gizmo"):
        viewport.drag_selected_2d(Camera2D(), 10.0, 0.0)


def test_2d_camera_pan_and_zoom_are_bounded():
    _, _, viewport = _workspace_with_rectangle()
    camera = Camera2D(zoom=2.0)

    viewport.pan_camera_2d(camera, 20.0, 10.0)
    assert camera.x == pytest.approx(-10.0)
    assert camera.y == pytest.approx(5.0)

    viewport.zoom_camera_2d(camera, 100.0, min_zoom=0.5, max_zoom=8.0)
    assert camera.zoom == pytest.approx(8.0)
    viewport.zoom_camera_2d(camera, -100.0, min_zoom=0.5, max_zoom=8.0)
    assert camera.zoom == pytest.approx(0.5)


def test_3d_camera_pan_and_dolly_preserve_view_direction():
    _, _, viewport = _workspace_with_cube()
    camera = Camera3D(position=Vec3(0.0, 0.0, 0.0), target=Vec3(0.0, 0.0, -5.0))
    before_forward = camera.forward

    viewport.pan_camera_3d(camera, 60.0, 30.0, 600.0)

    assert camera.position.x < 0.0
    assert camera.position.y > 0.0
    assert camera.forward.x == pytest.approx(before_forward.x)
    assert camera.forward.y == pytest.approx(before_forward.y)
    assert camera.forward.z == pytest.approx(before_forward.z)

    before_position = Vec3(camera.position.x, camera.position.y, camera.position.z)
    viewport.dolly_camera_3d(camera, 2.0)
    assert camera.position.x == pytest.approx(before_position.x)
    assert camera.position.y == pytest.approx(before_position.y)
    assert camera.position.z == pytest.approx(before_position.z - 2.0)


def test_invalid_viewport_dimensions_are_rejected():
    _, _, viewport = _workspace_with_cube()

    with pytest.raises(ValueError, match="viewport width"):
        viewport.ray_from_screen(Camera3D(), 0, 0, 0, 600)

    with pytest.raises(ValueError, match="zoom factor"):
        viewport.zoom_camera_2d(Camera2D(), 1.0, factor=1.0)
