from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Literal

from .graphics.camera3d import Camera3D
from .graphics.camera_runtime import CameraRig3D
from .input.actions import InputActions
from .math.types import Vec3
from .navigation import NavigationPath3D, NavigationProvider3D
from .physics.collision3d import AABB3D, Collider3D
from .physics.dynamics3d import PhysicsBackend3D, SweepHit3D


def _clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, value))


def _move_toward(current: float, target: float, maximum_delta: float) -> float:
    if current < target:
        return min(current + maximum_delta, target)
    if current > target:
        return max(current - maximum_delta, target)
    return target


def _dot(a: Vec3, b: Vec3) -> float:
    return a.x * b.x + a.y * b.y + a.z * b.z


def _horizontal_length(value: Vec3) -> float:
    return math.hypot(value.x, value.z)


def _horizontal_normalized(value: Vec3) -> Vec3:
    length = _horizontal_length(value)
    if length <= 1e-12:
        return Vec3()
    return Vec3(value.x / length, 0.0, value.z / length)


def _flat_basis(value: Vec3, fallback: Vec3) -> Vec3:
    flattened = _horizontal_normalized(value)
    return flattened if _horizontal_length(flattened) > 0.0 else fallback


def _position(target: object) -> Vec3:
    value = getattr(target, "position", target)
    try:
        return Vec3(float(value.x), float(value.y), float(value.z))
    except AttributeError as exc:
        raise TypeError("character target must expose position.x/y/z or x/y/z") from exc


def _set_position(target: object, value: Vec3) -> None:
    owner = getattr(target, "position", target)
    try:
        owner.x = float(value.x)
        owner.y = float(value.y)
        owner.z = float(value.z)
    except AttributeError as exc:
        raise TypeError("character target position must expose mutable x/y/z") from exc


@dataclass(frozen=True, slots=True)
class CharacterConfig3D:
    """Creator-facing movement and collision tuning for a kinematic 3D character."""

    width: float = 0.8
    height: float = 1.8
    depth: float = 0.8
    walk_speed: float = 6.0
    sprint_speed: float = 9.0
    ground_acceleration: float = 42.0
    air_acceleration: float = 12.0
    gravity: float = 25.0
    jump_speed: float = 8.0
    max_fall_speed: float = 45.0
    slope_limit_degrees: float = 50.0
    step_height: float = 0.35
    ground_snap_distance: float = 0.12
    skin_width: float = 0.02
    coyote_time: float = 0.12
    jump_buffer_time: float = 0.12
    collision_mask: int = 0xFFFFFFFF

    def __post_init__(self) -> None:
        if min(self.width, self.height, self.depth) <= 0.0:
            raise ValueError("character dimensions must be greater than zero")
        if self.walk_speed < 0.0 or self.sprint_speed < 0.0:
            raise ValueError("character speeds must be non-negative")
        if self.ground_acceleration < 0.0 or self.air_acceleration < 0.0:
            raise ValueError("character acceleration must be non-negative")
        if self.gravity < 0.0 or self.jump_speed < 0.0 or self.max_fall_speed < 0.0:
            raise ValueError("gravity, jump_speed and max_fall_speed must be non-negative")
        if not 0.0 <= self.slope_limit_degrees < 90.0:
            raise ValueError("slope_limit_degrees must be in [0, 90)")
        if min(self.step_height, self.ground_snap_distance, self.skin_width) < 0.0:
            raise ValueError("step, snap and skin distances must be non-negative")
        if min(self.coyote_time, self.jump_buffer_time) < 0.0:
            raise ValueError("coyote_time and jump_buffer_time must be non-negative")

    @property
    def minimum_ground_normal_y(self) -> float:
        return math.cos(math.radians(self.slope_limit_degrees))


@dataclass(frozen=True, slots=True)
class CharacterInput3D:
    """One frame of semantic character input.

    ``move_x`` is right/left and ``move_z`` is forward/back relative to the supplied movement basis.
    Look values are deltas consumed by the FPS/TPS wrappers rather than raw mouse pixels.
    """

    move_x: float = 0.0
    move_z: float = 0.0
    jump: bool = False
    sprint: bool = False
    look_yaw: float = 0.0
    look_pitch: float = 0.0


@dataclass(frozen=True, slots=True)
class CharacterActionBindings3D:
    """Action-name adapter between ``InputActions`` and character controllers."""

    forward: str = "move_forward"
    backward: str = "move_backward"
    left: str = "move_left"
    right: str = "move_right"
    jump: str = "jump"
    sprint: str = "sprint"
    look_right: str = "look_right"
    look_left: str = "look_left"
    look_up: str = "look_up"
    look_down: str = "look_down"

    def sample(self, actions: InputActions) -> CharacterInput3D:
        return CharacterInput3D(
            move_x=actions.value(self.right) - actions.value(self.left),
            move_z=actions.value(self.forward) - actions.value(self.backward),
            jump=actions.pressed(self.jump),
            sprint=actions.down(self.sprint),
            look_yaw=actions.value(self.look_right) - actions.value(self.look_left),
            look_pitch=actions.value(self.look_up) - actions.value(self.look_down),
        )


@dataclass(frozen=True, slots=True)
class CharacterState3D:
    grounded: bool
    position: Vec3
    velocity: Vec3
    ground_normal: Vec3
    horizontal_speed: float


@dataclass(frozen=True, slots=True)
class CharacterDiagnostics3D:
    sweeps: int = 0
    hits: int = 0
    ground_probes: int = 0
    step_attempts: int = 0
    step_successes: int = 0


class CharacterController3D:
    """Deterministic kinematic character motor backed by Physics 2.0 shape sweeps.

    The controller owns movement, not a dynamic rigid body. This avoids force-tuning for gameplay
    movement while still using the Physics 2.0 world for collision candidates and continuous shape
    tests. An optional collider can be ignored when the same character is registered for queries.
    """

    def __init__(
        self,
        target: object,
        world: PhysicsBackend3D,
        *,
        config: CharacterConfig3D | None = None,
        collider: Collider3D | None = None,
    ) -> None:
        self.target = target
        self.world = world
        self.config = config or CharacterConfig3D()
        self.collider = collider
        self.velocity = Vec3()
        self.grounded = False
        self.ground_normal = Vec3(0.0, 1.0, 0.0)
        self._coyote_remaining = 0.0
        self._jump_buffer_remaining = 0.0
        self._sweeps = 0
        self._hits = 0
        self._ground_probes = 0
        self._step_attempts = 0
        self._step_successes = 0

    @property
    def position(self) -> Vec3:
        return _position(self.target)

    @property
    def state(self) -> CharacterState3D:
        position = self.position
        return CharacterState3D(
            grounded=self.grounded,
            position=position,
            velocity=Vec3(self.velocity.x, self.velocity.y, self.velocity.z),
            ground_normal=Vec3(
                self.ground_normal.x,
                self.ground_normal.y,
                self.ground_normal.z,
            ),
            horizontal_speed=math.hypot(self.velocity.x, self.velocity.z),
        )

    @property
    def diagnostics(self) -> CharacterDiagnostics3D:
        return CharacterDiagnostics3D(
            sweeps=self._sweeps,
            hits=self._hits,
            ground_probes=self._ground_probes,
            step_attempts=self._step_attempts,
            step_successes=self._step_successes,
        )

    def teleport(self, position: Vec3, *, reset_velocity: bool = True) -> CharacterController3D:
        _set_position(self.target, position)
        self.grounded = False
        self.ground_normal = Vec3(0.0, 1.0, 0.0)
        self._coyote_remaining = 0.0
        self._jump_buffer_remaining = 0.0
        if reset_velocity:
            self.velocity = Vec3()
        return self

    def _bounds(self, position: Vec3 | None = None) -> AABB3D:
        point = position or self.position
        return AABB3D(
            point.x,
            point.y,
            point.z,
            self.config.width,
            self.config.height,
            self.config.depth,
        )

    def _sweep(self, bounds: AABB3D, delta: Vec3) -> SweepHit3D | None:
        self._sweeps += 1
        hit = self.world.sweep_box(
            bounds,
            delta,
            mask=self.config.collision_mask,
            ignore=self.collider,
        )
        if hit is not None:
            self._hits += 1
        return hit

    def _walkable(self, normal: Vec3) -> bool:
        return normal.y >= self.config.minimum_ground_normal_y

    def _apply_delta(self, delta: Vec3) -> None:
        current = self.position
        _set_position(
            self.target,
            Vec3(current.x + delta.x, current.y + delta.y, current.z + delta.z),
        )

    def _safe_fraction(self, delta: Vec3, hit: SweepHit3D) -> float:
        distance = delta.length
        if distance <= 1e-12:
            return 0.0
        safe_distance = max(0.0, distance * hit.fraction - self.config.skin_width)
        return min(1.0, safe_distance / distance)

    def _probe_ground(self, *, snap: bool) -> bool:
        self._ground_probes += 1
        lift = self.config.skin_width
        start = self.position + Vec3(0.0, lift, 0.0)
        distance = self.config.ground_snap_distance + lift
        if distance <= 0.0:
            self.grounded = False
            return False
        hit = self._sweep(self._bounds(start), Vec3(0.0, -distance, 0.0))
        if hit is None or not self._walkable(hit.normal):
            self.grounded = False
            return False
        self.grounded = True
        self.ground_normal = Vec3(hit.normal.x, hit.normal.y, hit.normal.z)
        if snap and self.velocity.y <= 0.0:
            travel = distance * hit.fraction
            correction = max(0.0, travel - lift)
            if correction > 0.0:
                self._apply_delta(Vec3(0.0, -correction, 0.0))
            self.velocity.y = 0.0
        return True

    def _try_step(self, delta: Vec3) -> bool:
        if not self.grounded or self.config.step_height <= 0.0:
            return False
        self._step_attempts += 1
        up = Vec3(0.0, self.config.step_height + self.config.skin_width, 0.0)
        if self._sweep(self._bounds(), up) is not None:
            return False

        raised = self.position + Vec3(0.0, self.config.step_height, 0.0)
        if self._sweep(self._bounds(raised), delta) is not None:
            return False

        advanced = raised + delta
        down_distance = self.config.step_height + self.config.ground_snap_distance
        down_hit = self._sweep(
            self._bounds(advanced),
            Vec3(0.0, -down_distance, 0.0),
        )
        if down_hit is None or not self._walkable(down_hit.normal):
            return False

        landing_drop = down_distance * down_hit.fraction
        _set_position(
            self.target,
            Vec3(advanced.x, advanced.y - landing_drop, advanced.z),
        )
        self.grounded = True
        self.ground_normal = Vec3(down_hit.normal.x, down_hit.normal.y, down_hit.normal.z)
        self._step_successes += 1
        return True

    def _move_horizontal_axis(self, delta: Vec3) -> None:
        if delta.length <= 1e-12:
            return
        hit = self._sweep(self._bounds(), delta)
        if hit is None:
            self._apply_delta(delta)
            return
        if self._try_step(delta):
            return
        fraction = self._safe_fraction(delta, hit)
        if fraction > 0.0:
            self._apply_delta(delta * fraction)
        if abs(delta.x) > abs(delta.z):
            self.velocity.x = 0.0
        else:
            self.velocity.z = 0.0

    def _move_horizontal(self, dt: float) -> None:
        self._move_horizontal_axis(Vec3(self.velocity.x * dt, 0.0, 0.0))
        self._move_horizontal_axis(Vec3(0.0, 0.0, self.velocity.z * dt))

    def _move_vertical(self, dt: float) -> None:
        delta = Vec3(0.0, self.velocity.y * dt, 0.0)
        if abs(delta.y) <= 1e-12:
            return
        hit = self._sweep(self._bounds(), delta)
        if hit is None:
            self._apply_delta(delta)
            return
        fraction = self._safe_fraction(delta, hit)
        if fraction > 0.0:
            self._apply_delta(delta * fraction)
        if self.velocity.y < 0.0 and self._walkable(hit.normal):
            self.grounded = True
            self.ground_normal = Vec3(hit.normal.x, hit.normal.y, hit.normal.z)
        self.velocity.y = 0.0

    def _desired_world_direction(
        self,
        command: CharacterInput3D,
        forward: Vec3,
        right: Vec3,
    ) -> Vec3:
        forward_flat = _flat_basis(forward, Vec3(0.0, 0.0, -1.0))
        right_flat = _flat_basis(right, Vec3(1.0, 0.0, 0.0))
        desired = right_flat * float(command.move_x) + forward_flat * float(command.move_z)
        length = _horizontal_length(desired)
        if length > 1.0:
            desired = Vec3(desired.x / length, 0.0, desired.z / length)
        return desired

    def _update_motion(
        self,
        desired: Vec3,
        *,
        jump: bool,
        sprint: bool,
        dt: float,
    ) -> CharacterState3D:
        if dt <= 0.0:
            return self.state

        self._sweeps = 0
        self._hits = 0
        self._ground_probes = 0
        self._step_attempts = 0
        self._step_successes = 0

        was_grounded = self._probe_ground(snap=self.velocity.y <= 0.0)
        if was_grounded:
            self._coyote_remaining = self.config.coyote_time
        else:
            self._coyote_remaining = max(0.0, self._coyote_remaining - dt)

        if jump:
            self._jump_buffer_remaining = self.config.jump_buffer_time
        else:
            self._jump_buffer_remaining = max(0.0, self._jump_buffer_remaining - dt)

        can_jump = self.grounded or self._coyote_remaining > 0.0
        if self._jump_buffer_remaining > 0.0 and can_jump:
            self.velocity.y = self.config.jump_speed
            self.grounded = False
            self._coyote_remaining = 0.0
            self._jump_buffer_remaining = 0.0

        desired = _horizontal_normalized(desired) if _horizontal_length(desired) > 1.0 else desired
        speed = self.config.sprint_speed if sprint else self.config.walk_speed
        target_x = desired.x * speed
        target_z = desired.z * speed
        acceleration = (
            self.config.ground_acceleration if self.grounded else self.config.air_acceleration
        )
        maximum_delta = acceleration * dt
        self.velocity.x = _move_toward(self.velocity.x, target_x, maximum_delta)
        self.velocity.z = _move_toward(self.velocity.z, target_z, maximum_delta)

        if not self.grounded:
            self.velocity.y = max(
                -self.config.max_fall_speed,
                self.velocity.y - self.config.gravity * dt,
            )
        elif self.velocity.y < 0.0:
            self.velocity.y = 0.0

        self._move_horizontal(dt)
        self._move_vertical(dt)

        if self.velocity.y <= 0.0:
            self._probe_ground(snap=True)
        else:
            self.grounded = False
        return self.state

    def update(
        self,
        command: CharacterInput3D,
        dt: float,
        *,
        forward: Vec3 | None = None,
        right: Vec3 | None = None,
    ) -> CharacterState3D:
        desired = self._desired_world_direction(
            command,
            forward or Vec3(0.0, 0.0, -1.0),
            right or Vec3(1.0, 0.0, 0.0),
        )
        return self._update_motion(
            desired,
            jump=command.jump,
            sprint=command.sprint,
            dt=float(dt),
        )

    def update_world(
        self,
        movement: Vec3,
        dt: float,
        *,
        jump: bool = False,
        sprint: bool = False,
    ) -> CharacterState3D:
        desired = _horizontal_normalized(movement)
        return self._update_motion(desired, jump=jump, sprint=sprint, dt=float(dt))


class FirstPersonController3D(CharacterController3D):
    """Character motor with mouse/gamepad-look style first-person camera synchronization."""

    def __init__(
        self,
        target: object,
        world: PhysicsBackend3D,
        camera: Camera3D,
        *,
        config: CharacterConfig3D | None = None,
        collider: Collider3D | None = None,
        camera_rig: CameraRig3D | None = None,
        eye_height: float = 0.72,
        look_sensitivity: float = 120.0,
        pitch_limit: float = 89.0,
    ) -> None:
        super().__init__(target, world, config=config, collider=collider)
        self.camera = camera
        self.camera_rig = camera_rig
        self.eye_height = float(eye_height)
        self.look_sensitivity = float(look_sensitivity)
        self.pitch_limit = _clamp(float(pitch_limit), 1.0, 89.9)
        self.yaw = 0.0
        self.pitch = 0.0

    def _forward(self) -> Vec3:
        radians_yaw = math.radians(self.yaw)
        return Vec3(math.sin(radians_yaw), 0.0, -math.cos(radians_yaw))

    def _view_direction(self) -> Vec3:
        yaw = math.radians(self.yaw)
        pitch = math.radians(self.pitch)
        cosine = math.cos(pitch)
        return Vec3(
            math.sin(yaw) * cosine,
            math.sin(pitch),
            -math.cos(yaw) * cosine,
        ).normalized()

    def _sync_camera(self, dt: float) -> None:
        position = self.position
        eye = Vec3(position.x, position.y + self.eye_height, position.z)
        if self.camera_rig is not None:
            self.camera_rig.follow(eye, dt)
        else:
            self.camera.position = eye
        self.camera.target = self.camera.position + self._view_direction()

    def update(
        self,
        command: CharacterInput3D,
        dt: float,
        *,
        forward: Vec3 | None = None,
        right: Vec3 | None = None,
    ) -> CharacterState3D:
        step = max(0.0, float(dt))
        self.yaw += float(command.look_yaw) * self.look_sensitivity * step
        self.pitch = _clamp(
            self.pitch + float(command.look_pitch) * self.look_sensitivity * step,
            -self.pitch_limit,
            self.pitch_limit,
        )
        movement_forward = self._forward()
        movement_right = Vec3(-movement_forward.z, 0.0, movement_forward.x)
        state = super().update(
            command,
            dt,
            forward=movement_forward,
            right=movement_right,
        )
        self._sync_camera(step)
        return state


class ThirdPersonController3D(CharacterController3D):
    """Orbit-style third-person controller reusing the engine's smooth ``CameraRig3D``."""

    def __init__(
        self,
        target: object,
        world: PhysicsBackend3D,
        camera: Camera3D,
        *,
        config: CharacterConfig3D | None = None,
        collider: Collider3D | None = None,
        camera_rig: CameraRig3D | None = None,
        camera_distance: float = 5.0,
        target_height: float = 0.65,
        look_sensitivity: float = 100.0,
        pitch_limit: float = 75.0,
        camera_collision_size: float = 0.2,
    ) -> None:
        super().__init__(target, world, config=config, collider=collider)
        self.camera = camera
        self.camera_rig = camera_rig or CameraRig3D(camera, smoothing=12.0)
        self.camera_distance = max(0.0, float(camera_distance))
        self.target_height = float(target_height)
        self.look_sensitivity = float(look_sensitivity)
        self.pitch_limit = _clamp(float(pitch_limit), 1.0, 89.0)
        self.camera_collision_size = max(0.0, float(camera_collision_size))
        self.yaw = 0.0
        self.pitch = 15.0

    def _flat_forward(self) -> Vec3:
        yaw = math.radians(self.yaw)
        return Vec3(math.sin(yaw), 0.0, -math.cos(yaw))

    def _view_forward(self) -> Vec3:
        yaw = math.radians(self.yaw)
        pitch = math.radians(self.pitch)
        cosine = math.cos(pitch)
        return Vec3(
            math.sin(yaw) * cosine,
            math.sin(pitch),
            -math.cos(yaw) * cosine,
        ).normalized()

    def _camera_position(self) -> tuple[Vec3, Vec3]:
        character = self.position
        pivot = Vec3(character.x, character.y + self.target_height, character.z)
        desired = pivot - self._view_forward() * self.camera_distance
        if self.camera_collision_size <= 0.0 or self.camera_distance <= 0.0:
            return desired, pivot
        size = self.camera_collision_size
        bounds = AABB3D(pivot.x, pivot.y, pivot.z, size, size, size)
        delta = desired - pivot
        hit = self._sweep(bounds, delta)
        if hit is None:
            return desired, pivot
        safe = self._safe_fraction(delta, hit)
        return pivot + delta * safe, pivot

    def update(
        self,
        command: CharacterInput3D,
        dt: float,
        *,
        forward: Vec3 | None = None,
        right: Vec3 | None = None,
    ) -> CharacterState3D:
        step = max(0.0, float(dt))
        self.yaw += float(command.look_yaw) * self.look_sensitivity * step
        self.pitch = _clamp(
            self.pitch + float(command.look_pitch) * self.look_sensitivity * step,
            -self.pitch_limit,
            self.pitch_limit,
        )
        movement_forward = self._flat_forward()
        movement_right = Vec3(-movement_forward.z, 0.0, movement_forward.x)
        state = super().update(
            command,
            dt,
            forward=movement_forward,
            right=movement_right,
        )
        desired_camera, pivot = self._camera_position()
        self.camera_rig.follow(desired_camera, step)
        self.camera.look_at(pivot)
        return state


class PlatformerController3D(CharacterController3D):
    """Platformer preset with optional axis lock and smooth follow camera."""

    def __init__(
        self,
        target: object,
        world: PhysicsBackend3D,
        *,
        config: CharacterConfig3D | None = None,
        collider: Collider3D | None = None,
        movement_mode: Literal["xz", "x", "z"] = "xz",
        camera_rig: CameraRig3D | None = None,
        camera_offset: Vec3 | None = None,
    ) -> None:
        super().__init__(target, world, config=config, collider=collider)
        if movement_mode not in ("xz", "x", "z"):
            raise ValueError("movement_mode must be 'xz', 'x' or 'z'")
        self.movement_mode = movement_mode
        self.camera_rig = camera_rig
        self.camera_offset = camera_offset or Vec3(0.0, 2.5, 6.0)

    def update(
        self,
        command: CharacterInput3D,
        dt: float,
        *,
        forward: Vec3 | None = None,
        right: Vec3 | None = None,
    ) -> CharacterState3D:
        move_x = command.move_x
        move_z = command.move_z
        if self.movement_mode == "x":
            move_z = 0.0
        elif self.movement_mode == "z":
            move_x = 0.0
        state = super().update(
            CharacterInput3D(
                move_x=move_x,
                move_z=move_z,
                jump=command.jump,
                sprint=command.sprint,
            ),
            dt,
            forward=forward,
            right=right,
        )
        if self.camera_rig is not None:
            position = state.position
            desired = Vec3(
                position.x + self.camera_offset.x,
                position.y + self.camera_offset.y,
                position.z + self.camera_offset.z,
            )
            self.camera_rig.follow(desired, max(0.0, float(dt)))
            self.camera_rig.camera.look_at(position)
        return state


class CharacterNavigationDriver3D:
    """Revision-aware path follower that steers a character through ``NavigationProvider3D``."""

    def __init__(
        self,
        controller: CharacterController3D,
        provider: NavigationProvider3D,
        *,
        waypoint_tolerance: float = 0.2,
        sprint: bool = False,
    ) -> None:
        if waypoint_tolerance <= 0.0:
            raise ValueError("waypoint_tolerance must be greater than zero")
        self.controller = controller
        self.provider = provider
        self.waypoint_tolerance = float(waypoint_tolerance)
        self.sprint = bool(sprint)
        self.goal: Vec3 | None = None
        self._path: tuple[Vec3, ...] = ()
        self._index = 0
        self._revision = -1

    @property
    def path(self) -> tuple[Vec3, ...]:
        return self._path

    @property
    def waypoint_index(self) -> int:
        return self._index

    def set_goal(self, goal: Vec3) -> None:
        self.goal = Vec3(float(goal.x), float(goal.y), float(goal.z))
        self._path = ()
        self._index = 0
        self._revision = -1

    def clear_goal(self) -> None:
        self.goal = None
        self._path = ()
        self._index = 0
        self._revision = -1

    def _repath(self) -> None:
        if self.goal is None:
            self._path = ()
            self._index = 0
            return
        result: NavigationPath3D | None = self.provider.find_path(
            self.controller.position,
            self.goal,
        )
        self._revision = self.provider.revision
        self._path = () if result is None else tuple(result.points)
        self._index = 0

    def _advance_waypoints(self) -> None:
        position = self.controller.position
        while self._index < len(self._path):
            point = self._path[self._index]
            if math.hypot(point.x - position.x, point.z - position.z) > self.waypoint_tolerance:
                break
            self._index += 1

    def update(self, dt: float) -> CharacterState3D:
        if self.goal is None:
            return self.controller.update_world(Vec3(), dt)
        if not self._path or self._revision != self.provider.revision:
            self._repath()
        self._advance_waypoints()
        if self._index >= len(self._path):
            return self.controller.update_world(Vec3(), dt)
        target = self._path[self._index]
        position = self.controller.position
        direction = Vec3(target.x - position.x, 0.0, target.z - position.z)
        return self.controller.update_world(direction, dt, sprint=self.sprint)


def follow_character_path(
    controller: CharacterController3D,
    points: Sequence[Vec3],
    dt: float,
    *,
    waypoint_tolerance: float = 0.2,
    sprint: bool = False,
) -> tuple[CharacterState3D, int]:
    """Stateless helper for creator-managed paths; returns state and the next waypoint index."""
    if waypoint_tolerance <= 0.0:
        raise ValueError("waypoint_tolerance must be greater than zero")
    position = controller.position
    index = 0
    while index < len(points):
        point = points[index]
        if math.hypot(point.x - position.x, point.z - position.z) > waypoint_tolerance:
            break
        index += 1
    if index >= len(points):
        return controller.update_world(Vec3(), dt), index
    point = points[index]
    direction = Vec3(point.x - position.x, 0.0, point.z - position.z)
    return controller.update_world(direction, dt, sprint=sprint), index


__all__ = [
    "CharacterActionBindings3D",
    "CharacterConfig3D",
    "CharacterController3D",
    "CharacterDiagnostics3D",
    "CharacterInput3D",
    "CharacterNavigationDriver3D",
    "CharacterState3D",
    "FirstPersonController3D",
    "PlatformerController3D",
    "ThirdPersonController3D",
    "follow_character_path",
]
