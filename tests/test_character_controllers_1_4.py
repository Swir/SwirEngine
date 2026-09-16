from __future__ import annotations

from dataclasses import dataclass, field

import pytest

from swirengine.character import (
    CharacterConfig3D,
    CharacterController3D,
    CharacterInput3D,
    CharacterNavigationDriver3D,
    FirstPersonController3D,
    PlatformerController3D,
    ThirdPersonController3D,
)
from swirengine.graphics.camera3d import Camera3D
from swirengine.math.types import Vec3
from swirengine.navigation import NavigationPath3D
from swirengine.physics.collision3d import BoxCollider3D
from swirengine.physics.dynamics3d import PhysicsBody3D, PhysicsScene3D


@dataclass
class Target3D:
    position: Vec3 = field(default_factory=Vec3)


def static_box(
    scene: PhysicsScene3D,
    x: float,
    y: float,
    z: float,
    *,
    width: float,
    height: float,
    depth: float,
) -> PhysicsBody3D:
    target = Target3D(Vec3(x, y, z))
    collider = BoxCollider3D(target, width=width, height=height, depth=depth)
    return scene.add(PhysicsBody3D(target, collider, body_type="static"))


def floor_scene() -> PhysicsScene3D:
    scene = PhysicsScene3D(gravity=Vec3())
    static_box(scene, 0.0, -0.5, 0.0, width=30.0, height=1.0, depth=30.0)
    return scene


def test_character_config_validation_and_slope_threshold() -> None:
    with pytest.raises(ValueError):
        CharacterConfig3D(height=0.0)
    with pytest.raises(ValueError):
        CharacterConfig3D(slope_limit_degrees=90.0)

    config = CharacterConfig3D(slope_limit_degrees=60.0)
    assert config.minimum_ground_normal_y == pytest.approx(0.5)


def test_character_falls_to_floor_and_reports_grounded() -> None:
    scene = floor_scene()
    target = Target3D(Vec3(0.0, 3.0, 0.0))
    controller = CharacterController3D(
        target,
        scene,
        config=CharacterConfig3D(gravity=20.0, max_fall_speed=30.0),
    )

    for _ in range(240):
        controller.update(CharacterInput3D(), 1.0 / 120.0)

    assert controller.grounded
    assert target.position.y == pytest.approx(0.9, abs=0.03)
    assert controller.velocity.y == pytest.approx(0.0)
    assert controller.diagnostics.ground_probes >= 1


def test_jump_uses_grounded_state_and_moves_up() -> None:
    scene = floor_scene()
    target = Target3D(Vec3(0.0, 0.9, 0.0))
    controller = CharacterController3D(target, scene)

    controller.update(CharacterInput3D(), 1.0 / 60.0)
    before = target.position.y
    state = controller.update(CharacterInput3D(jump=True), 1.0 / 60.0)

    assert not state.grounded
    assert state.velocity.y > 0.0
    assert target.position.y > before


def test_character_stops_at_wall_instead_of_tunnelling() -> None:
    scene = floor_scene()
    static_box(scene, 2.0, 1.0, 0.0, width=0.2, height=2.0, depth=4.0)
    target = Target3D(Vec3(0.0, 0.9, 0.0))
    controller = CharacterController3D(
        target,
        scene,
        config=CharacterConfig3D(walk_speed=20.0, ground_acceleration=200.0),
    )

    for _ in range(60):
        controller.update_world(Vec3(1.0, 0.0, 0.0), 1.0 / 60.0)

    assert target.position.x == pytest.approx(1.5, abs=1e-6)
    assert controller.diagnostics.hits >= 1


def test_step_up_climbs_low_obstacle() -> None:
    scene = floor_scene()
    static_box(scene, 1.2, 0.15, 0.0, width=0.8, height=0.3, depth=3.0)
    target = Target3D(Vec3(0.0, 0.9, 0.0))
    controller = CharacterController3D(
        target,
        scene,
        config=CharacterConfig3D(
            walk_speed=3.0,
            ground_acceleration=100.0,
            step_height=0.4,
        ),
    )

    climbed = False
    for _ in range(50):
        controller.update_world(Vec3(1.0, 0.0, 0.0), 1.0 / 60.0)
        climbed = climbed or target.position.y > 1.05

    assert climbed
    assert target.position.x > 1.0


def test_tall_obstacle_is_not_treated_as_step() -> None:
    scene = floor_scene()
    static_box(scene, 1.2, 0.6, 0.0, width=0.8, height=1.2, depth=3.0)
    target = Target3D(Vec3(0.0, 0.9, 0.0))
    controller = CharacterController3D(
        target,
        scene,
        config=CharacterConfig3D(
            walk_speed=4.0,
            ground_acceleration=100.0,
            step_height=0.35,
        ),
    )

    for _ in range(60):
        controller.update_world(Vec3(1.0, 0.0, 0.0), 1.0 / 60.0)

    assert target.position.x < 0.45
    assert target.position.y == pytest.approx(0.9, abs=0.03)


def test_first_person_controller_syncs_camera_and_look() -> None:
    scene = floor_scene()
    target = Target3D(Vec3(0.0, 0.9, 0.0))
    camera = Camera3D()
    controller = FirstPersonController3D(
        target,
        scene,
        camera,
        look_sensitivity=90.0,
    )

    controller.update(
        CharacterInput3D(move_z=1.0, look_yaw=1.0, look_pitch=0.25),
        0.5,
    )

    assert controller.yaw == pytest.approx(45.0)
    assert controller.pitch == pytest.approx(11.25)
    assert camera.position.y == pytest.approx(target.position.y + controller.eye_height)
    assert camera.forward.length == pytest.approx(1.0)


def test_third_person_controller_uses_follow_rig_and_orbit_target() -> None:
    scene = floor_scene()
    target = Target3D(Vec3(0.0, 0.9, 0.0))
    camera = Camera3D(position=Vec3(0.0, 3.0, 6.0))
    controller = ThirdPersonController3D(
        target,
        scene,
        camera,
        camera_distance=4.0,
        camera_collision_size=0.0,
    )

    controller.update(CharacterInput3D(look_yaw=1.0), 0.25)

    assert controller.yaw == pytest.approx(25.0)
    expected_target_y = target.position.y + controller.target_height
    assert camera.target.y == pytest.approx(expected_target_y)
    assert (camera.target - camera.position).length > 0.0


def test_platformer_axis_lock_blocks_depth_movement() -> None:
    scene = floor_scene()
    target = Target3D(Vec3(0.0, 0.9, 0.0))
    controller = PlatformerController3D(
        target,
        scene,
        movement_mode="x",
        config=CharacterConfig3D(ground_acceleration=100.0),
    )

    for _ in range(10):
        controller.update(CharacterInput3D(move_x=1.0, move_z=1.0), 1.0 / 60.0)

    assert target.position.x > 0.0
    assert target.position.z == pytest.approx(0.0)


class NavigationProviderStub:
    def __init__(self) -> None:
        self.revision = 1
        self.calls = 0

    def find_path(
        self,
        start: Vec3,
        goal: Vec3,
        *,
        max_expansions: int | None = None,
    ) -> NavigationPath3D:
        self.calls += 1
        return NavigationPath3D(
            cells=((0, 0), (1, 0), (2, 0)),
            points=(
                Vec3(start.x, start.y, start.z),
                Vec3(1.0, start.y, 0.0),
                Vec3(goal.x, goal.y, goal.z),
            ),
            cost=2.0,
        )


def test_navigation_driver_repaths_on_revision_and_steers_character() -> None:
    scene = floor_scene()
    target = Target3D(Vec3(0.0, 0.9, 0.0))
    controller = CharacterController3D(
        target,
        scene,
        config=CharacterConfig3D(walk_speed=3.0, ground_acceleration=100.0),
    )
    provider = NavigationProviderStub()
    driver = CharacterNavigationDriver3D(controller, provider, waypoint_tolerance=0.15)
    driver.set_goal(Vec3(2.0, 0.9, 0.0))

    for _ in range(10):
        driver.update(1.0 / 60.0)

    assert provider.calls == 1
    assert target.position.x > 0.0

    provider.revision += 1
    driver.update(1.0 / 60.0)
    assert provider.calls == 2
