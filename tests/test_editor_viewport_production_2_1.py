import math
from pathlib import Path

import pytest

from swirengine.core.scene import Scene
from swirengine.editor_project_authoring21 import EditorProjectAuthoring21
from swirengine.editor_viewport_frontend21 import EditorProductionViewportController21
from swirengine.editor_viewport_overlay import EditorViewportOverlay
from swirengine.editor_workspace import EditorWorkspace
from swirengine.graphics.camera import Camera2D
from swirengine.graphics.camera3d import Camera3D
from swirengine.graphics.primitives import Cube3D, Rectangle2D
from swirengine.math.types import Vec3


def _controller(
    scene: Scene, tmp_path: Path, *, mode: str
) -> EditorProductionViewportController21:
    workspace = EditorWorkspace(scene, project_name="ViewportProduction")
    workspace.configure_viewport(mode=mode)
    authoring = EditorProjectAuthoring21(workspace, asset_root=tmp_path / "assets")
    return EditorProductionViewportController21(workspace, authoring)


def test_2d_rotate_drag_uses_active_gizmo_and_rotation_snap(tmp_path: Path) -> None:
    scene = Scene()
    rectangle = scene.add(Rectangle2D(0.0, 0.0, 80.0, 40.0, name="Rotating"))
    controller = _controller(scene, tmp_path, mode="2d")
    controller.select(controller.workspace.inspector.key_for(rectangle))
    controller.workspace.configure_viewport(
        gizmo="rotate",
        snap_enabled=True,
        rotation_snap=15.0,
    )

    results = controller.viewport_transform_selection(20.0, 0.0, 600.0)

    assert len(results) == 1
    assert results[0].mode == "rotate"
    assert results[0].axis == "z"
    assert rectangle.rotation == pytest.approx(15.0)
    assert controller.undo()
    assert rectangle.rotation == pytest.approx(0.0)


def test_3d_rotate_all_maps_pointer_motion_to_pitch_and_yaw(tmp_path: Path) -> None:
    scene = Scene()
    cube = scene.add(Cube3D(position=Vec3(0.0, 0.0, -5.0), name="Cube"))
    controller = _controller(scene, tmp_path, mode="3d")
    controller.select(controller.workspace.inspector.key_for(cube))
    controller.workspace.configure_viewport(gizmo="rotate")

    results = controller.viewport_transform_selection(20.0, -10.0, 600.0)

    assert tuple(result.axis for result in results) == ("x", "y")
    assert cube.rotation.x == pytest.approx(5.0)
    assert cube.rotation.y == pytest.approx(10.0)
    assert cube.rotation.z == pytest.approx(0.0)


def test_3d_scale_drag_supports_uniform_cube_scale(tmp_path: Path) -> None:
    scene = Scene()
    cube = scene.add(Cube3D(position=Vec3(0.0, 0.0, -5.0), size=2.0, name="Cube"))
    controller = _controller(scene, tmp_path, mode="3d")
    controller.select(controller.workspace.inspector.key_for(cube))
    controller.workspace.configure_viewport(gizmo="scale")

    results = controller.viewport_transform_selection(20.0, 0.0, 600.0)

    assert len(results) == 1
    assert results[0].axis == "all"
    assert cube.size == pytest.approx(2.2)
    assert controller.undo()
    assert cube.size == pytest.approx(2.0)


def test_2d_scale_drag_resizes_explicit_rectangle_dimensions(tmp_path: Path) -> None:
    scene = Scene()
    rectangle = scene.add(Rectangle2D(0.0, 0.0, 80.0, 40.0, name="Resizable"))
    controller = _controller(scene, tmp_path, mode="2d")
    controller.select(controller.workspace.inspector.key_for(rectangle))
    controller.workspace.configure_viewport(gizmo="scale")

    results = controller.viewport_transform_selection(20.0, 0.0, 600.0)

    assert tuple(result.axis for result in results) == ("x", "y")
    assert rectangle.width == pytest.approx(80.2)
    assert rectangle.height == pytest.approx(40.2)


def test_axis_constraint_limits_2d_translation_to_requested_axis(tmp_path: Path) -> None:
    scene = Scene()
    rectangle = scene.add(Rectangle2D(0.0, 0.0, 40.0, 40.0, name="AxisLocked"))
    controller = _controller(scene, tmp_path, mode="2d")
    controller.select(controller.workspace.inspector.key_for(rectangle))
    controller.set_viewport_axis("x")

    results = controller.viewport_transform_selection(30.0, -50.0, 600.0)

    assert len(results) == 1
    assert results[0].axis == "x"
    assert rectangle.x == pytest.approx(30.0)
    assert rectangle.y == pytest.approx(0.0)


def test_3d_orbit_preserves_target_and_radius(tmp_path: Path) -> None:
    controller = _controller(Scene(), tmp_path, mode="3d")
    controller.camera_3d = Camera3D(
        position=Vec3(0.0, 0.0, 5.0),
        target=Vec3(0.0, 0.0, 0.0),
    )
    before_target = controller.camera_3d.target
    before_radius = (controller.camera_3d.position - before_target).length

    controller.viewport_orbit(40.0, -20.0)

    after_radius = (controller.camera_3d.position - before_target).length
    assert controller.camera_3d.target == before_target
    assert after_radius == pytest.approx(before_radius)
    assert controller.camera_3d.position.x != pytest.approx(0.0)
    assert controller.camera_3d.position.y != pytest.approx(0.0)


def test_grid_visibility_control_updates_persisted_viewport_state(tmp_path: Path) -> None:
    controller = _controller(Scene(), tmp_path, mode="2d")

    assert controller.set_grid_visible(False) is False
    assert not controller.workspace.viewport.grid_visible
    assert controller.set_grid_visible(True) is True
    assert controller.workspace.viewport.grid_visible


def test_2d_overlay_builds_adaptive_grid_and_selected_gizmo() -> None:
    overlay = EditorViewportOverlay()
    target = Rectangle2D(0.0, 0.0, 80.0, 40.0)

    frame = overlay.build(
        mode="2d",
        camera_2d=Camera2D(zoom=1.0),
        camera_3d=Camera3D(),
        width=800,
        height=600,
        grid_visible=True,
        grid_spacing=1.0,
        selected_target=target,
        gizmo="translate",
    )

    roles = {line.role for line in frame.lines}
    assert frame.width == 800
    assert frame.height == 600
    assert "grid_minor" in roles or "grid_major" in roles
    assert "axis_x" in roles
    assert "axis_y" in roles
    assert "gizmo_x" in roles
    assert "gizmo_y" in roles
    assert len(frame.lines) < 100


def test_3d_overlay_projects_ground_grid_and_xyz_gizmo() -> None:
    overlay = EditorViewportOverlay()
    camera = Camera3D(
        position=Vec3(6.0, 6.0, 6.0),
        target=Vec3(0.0, 0.0, 0.0),
    )
    target = Cube3D(position=Vec3(0.0, 0.0, 0.0))

    frame = overlay.build(
        mode="3d",
        camera_2d=Camera2D(),
        camera_3d=camera,
        width=1280,
        height=720,
        grid_visible=True,
        grid_spacing=1.0,
        selected_target=target,
        gizmo="translate",
    )

    roles = {line.role for line in frame.lines}
    assert "grid_minor" in roles or "grid_major" in roles
    assert {"gizmo_x", "gizmo_y", "gizmo_z"}.issubset(roles)
    assert all(
        all(math.isfinite(value) for value in (line.x1, line.y1, line.x2, line.y2))
        for line in frame.lines
    )


def test_overlay_rejects_invalid_dimensions_and_spacing() -> None:
    overlay = EditorViewportOverlay()

    with pytest.raises(ValueError, match="viewport width"):
        overlay.build(
            mode="2d",
            camera_2d=Camera2D(),
            camera_3d=Camera3D(),
            width=0,
            height=600,
            grid_visible=True,
            grid_spacing=1.0,
            selected_target=None,
            gizmo="translate",
        )

    with pytest.raises(ValueError, match="grid spacing"):
        overlay.build(
            mode="2d",
            camera_2d=Camera2D(),
            camera_3d=Camera3D(),
            width=800,
            height=600,
            grid_visible=True,
            grid_spacing=0.0,
            selected_target=None,
            gizmo="translate",
        )
