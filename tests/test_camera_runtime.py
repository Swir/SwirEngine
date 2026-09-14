import pytest

from swirengine.graphics.camera import Camera2D
from swirengine.graphics.camera3d import Camera3D
from swirengine.graphics.camera_runtime import (
    CameraBounds2D,
    CameraBounds3D,
    CameraRail2D,
    CameraRail3D,
    CameraRig2D,
    CameraRig3D,
)
from swirengine.math.types import Vec2, Vec3


def test_camera2d_bounds_dead_zone_and_smoothing() -> None:
    camera = Camera2D()
    rig = CameraRig2D(
        camera,
        smoothing=10.0,
        dead_zone=Vec2(4.0, 4.0),
        bounds=CameraBounds2D(-5.0, -5.0, 5.0, 5.0),
    )

    rig.follow(Vec2(1.0, 1.0), 1.0 / 60.0)
    assert camera.x == pytest.approx(0.0)
    assert camera.y == pytest.approx(0.0)

    for _ in range(180):
        rig.follow(Vec2(100.0, 100.0), 1.0 / 60.0)
    assert camera.x <= 5.0
    assert camera.y <= 5.0
    assert camera.x > 4.9
    assert camera.y > 4.9


def test_camera2d_rail_samples_segments() -> None:
    rail = CameraRail2D((Vec2(0.0, 0.0), Vec2(10.0, 0.0), Vec2(10.0, 10.0)))
    assert rail.sample(0.25) == Vec2(5.0, 0.0)
    assert rail.sample(0.75) == Vec2(10.0, 5.0)


def test_camera_shake_is_deterministic_for_equal_inputs() -> None:
    a = CameraRig2D(Camera2D()).shake(3.0, 0.5, frequency=12.0, seed=7.0)
    b = CameraRig2D(Camera2D()).shake(3.0, 0.5, frequency=12.0, seed=7.0)

    samples_a = []
    samples_b = []
    for _ in range(12):
        a.follow(Vec2(), 1.0 / 60.0)
        b.follow(Vec2(), 1.0 / 60.0)
        samples_a.append((a.camera.x, a.camera.y))
        samples_b.append((b.camera.x, b.camera.y))

    assert samples_a == samples_b
    assert any(x != 0.0 or y != 0.0 for x, y in samples_a)


def test_camera3d_follow_preserves_look_direction() -> None:
    camera = Camera3D(position=Vec3(0.0, 2.0, 8.0), target=Vec3(0.0, 2.0, 0.0))
    rig = CameraRig3D(
        camera,
        smoothing=0.0,
        bounds=CameraBounds3D(Vec3(-5.0, 0.0, -5.0), Vec3(5.0, 10.0, 10.0)),
    )

    rig.snap_to(Vec3(20.0, 3.0, 20.0))
    assert camera.position == Vec3(5.0, 3.0, 10.0)
    assert camera.target - camera.position == Vec3(0.0, 0.0, -8.0)


def test_camera3d_rail_and_follow_are_shared_creator_workflow() -> None:
    camera = Camera3D(position=Vec3(0.0, 2.0, 8.0), target=Vec3(0.0, 2.0, 0.0))
    rig = CameraRig3D(camera, smoothing=0.0)
    rail = CameraRail3D((Vec3(0.0, 2.0, 8.0), Vec3(10.0, 4.0, 4.0)))

    rig.move_on_rail(rail, 0.5)
    assert camera.position == Vec3(5.0, 3.0, 6.0)
    rig.follow(Vec3(-2.0, 5.0, 7.0), 1.0 / 60.0)
    assert camera.position == Vec3(5.0, 3.0, 6.0)


def test_camera_rails_reject_single_point() -> None:
    with pytest.raises(ValueError):
        CameraRail2D((Vec2(),))
    with pytest.raises(ValueError):
        CameraRail3D((Vec3(),))
