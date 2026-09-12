import pytest

from swirengine import Cube3D, EditorTransformGizmo, Scene, Sprite2D, Vec3
from swirengine.editor_workspace import EditorViewportState


def test_gizmo_snapshot_exposes_3d_transform_capabilities():
    scene = Scene()
    cube = scene.add(Cube3D(position=Vec3(1.0, 2.0, 3.0), rotation=Vec3(4.0, 5.0, 6.0)))
    gizmo = EditorTransformGizmo.from_workspace(__import__("swirengine").EditorWorkspace(scene))
    gizmo.inspector.select(cube)

    snapshot = gizmo.snapshot()

    assert snapshot is not None
    assert snapshot.modes == ("translate", "rotate", "scale")
    assert snapshot.translation == (1.0, 2.0, 3.0)
    assert snapshot.rotation == (4.0, 5.0, 6.0)
    assert snapshot.scale == 1.0


def test_gizmo_3d_translation_uses_snapping_and_inspector_undo():
    scene = Scene()
    cube = scene.add(Cube3D(position=Vec3(0.2, 2.0, 3.0)))
    from swirengine import EditorWorkspace

    workspace = EditorWorkspace(scene)
    workspace.select(cube)
    gizmo = EditorTransformGizmo.from_workspace(workspace)

    result = gizmo.apply("translate", "x", 1.1, snap=0.5)

    assert cube.position == Vec3(1.5, 2.0, 3.0)
    assert result.before == Vec3(0.2, 2.0, 3.0)
    assert result.after == Vec3(1.5, 2.0, 3.0)
    workspace.undo()
    assert cube.position == Vec3(0.2, 2.0, 3.0)
    workspace.redo()
    assert cube.position == Vec3(1.5, 2.0, 3.0)


def test_gizmo_applies_viewport_mode_and_snap_settings():
    scene = Scene()
    cube = scene.add(Cube3D(rotation=Vec3(0.0, 2.0, 0.0)))
    from swirengine import EditorWorkspace

    workspace = EditorWorkspace(scene)
    workspace.select(cube)
    gizmo = EditorTransformGizmo.from_workspace(workspace)
    viewport = EditorViewportState(gizmo="rotate", snap_enabled=True, rotation_snap=15.0)

    gizmo.apply_viewport(viewport, "y", 10.0)

    assert cube.rotation == Vec3(0.0, 15.0, 0.0)


def test_gizmo_supports_existing_2d_xy_and_scalar_rotation_convention():
    scene = Scene()
    sprite = scene.add(Sprite2D("hero.png", x=3.0, y=5.0, rotation=10.0))
    from swirengine import EditorWorkspace

    workspace = EditorWorkspace(scene)
    workspace.select(sprite)
    gizmo = EditorTransformGizmo.from_workspace(workspace)

    snapshot = gizmo.snapshot()
    gizmo.apply("translate", "y", 2.25)
    gizmo.apply("rotate", "z", 12.0, snap=5.0)

    assert snapshot is not None
    assert snapshot.modes == ("translate", "rotate")
    assert sprite.y == pytest.approx(7.25)
    assert sprite.rotation == pytest.approx(20.0)


def test_gizmo_uniformly_scales_cube_size_and_validates_axes():
    scene = Scene()
    cube = scene.add(Cube3D(size=2.0))
    from swirengine import EditorWorkspace

    workspace = EditorWorkspace(scene)
    workspace.select(cube)
    gizmo = EditorTransformGizmo.from_workspace(workspace)

    gizmo.apply("scale", "all", 0.6, snap=0.25)
    assert cube.size == pytest.approx(2.5)

    with pytest.raises(ValueError, match="uniform scalar"):
        gizmo.apply("scale", "x", 1.0)
    with pytest.raises(ValueError, match="concrete axis"):
        gizmo.apply("translate", "all", 1.0)
    with pytest.raises(ValueError, match="gizmo snap"):
        gizmo.apply("scale", "all", 1.0, snap=0.0)


def test_disabled_viewport_gizmo_rejects_mutation():
    scene = Scene()
    cube = scene.add(Cube3D())
    from swirengine import EditorWorkspace

    workspace = EditorWorkspace(scene)
    workspace.select(cube)
    gizmo = EditorTransformGizmo.from_workspace(workspace)

    with pytest.raises(RuntimeError, match="disabled"):
        gizmo.apply_viewport(EditorViewportState(gizmo="none"), "x", 1.0)
