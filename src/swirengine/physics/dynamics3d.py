from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, field
from math import floor, sqrt
from typing import Literal, Protocol, runtime_checkable

from ..math.types import Vec3
from .collision3d import AABB3D, BoxCollider3D, Collider3D, SphereBounds3D, SphereCollider3D

PhysicsBodyType3D = Literal["dynamic", "kinematic", "static"]


def _dot(a: Vec3, b: Vec3) -> float:
    return a.x * b.x + a.y * b.y + a.z * b.z


def _length_sq(value: Vec3) -> float:
    return value.x * value.x + value.y * value.y + value.z * value.z


def _position(target: object) -> Vec3:
    value = getattr(target, "position", None)
    if value is None:
        value = target
    try:
        return Vec3(float(value.x), float(value.y), float(value.z))
    except AttributeError as exc:
        raise TypeError("physics target must expose position.x/y/z or x/y/z") from exc


def _set_position(target: object, value: Vec3) -> None:
    owner = getattr(target, "position", None)
    if owner is None:
        owner = target
    try:
        owner.x = float(value.x)
        owner.y = float(value.y)
        owner.z = float(value.z)
    except AttributeError as exc:
        raise TypeError("physics target position must expose mutable x/y/z attributes") from exc


def _collider_aabb(collider: Collider3D) -> AABB3D:
    if isinstance(collider, BoxCollider3D):
        return collider.bounds
    return collider.bounds.aabb


def _inverse_mass(body: PhysicsBody3D) -> float:
    if body.body_type != "dynamic" or body.mass <= 0.0:
        return 0.0
    return 1.0 / body.mass


@dataclass(frozen=True, slots=True)
class PhysicsMaterial3D:
    """Contact material used by the deterministic impulse solver."""

    friction: float = 0.5
    restitution: float = 0.0

    def __post_init__(self) -> None:
        if self.friction < 0.0:
            raise ValueError("friction must be non-negative")
        if not 0.0 <= self.restitution <= 1.0:
            raise ValueError("restitution must be between 0 and 1")


@dataclass(frozen=True, slots=True)
class Contact3D:
    """One narrow-phase contact. Normal points from body A toward body B."""

    body_a: PhysicsBody3D
    body_b: PhysicsBody3D
    point: Vec3
    normal: Vec3
    penetration: float


@dataclass(frozen=True, slots=True)
class SweepHit3D:
    """Earliest shape sweep hit represented by normalized travel fraction [0, 1]."""

    collider: Collider3D
    fraction: float
    distance: float
    point: Vec3
    normal: Vec3


@dataclass(frozen=True, slots=True)
class PhysicsDiagnostics3D:
    body_count: int = 0
    dynamic_bodies: int = 0
    sleeping_bodies: int = 0
    occupied_cells: int = 0
    candidate_pairs: int = 0
    narrow_phase_tests: int = 0
    contacts: int = 0
    normal_impulses: int = 0
    friction_impulses: int = 0
    joint_solves: int = 0
    sweep_tests: int = 0
    sweep_hits: int = 0
    substeps: int = 0


@dataclass(slots=True)
class PhysicsBody3D:
    """Production-oriented rigid body for the additive Physics 2.0 path.

    Existing ``RigidBody3D`` remains untouched for 1.x compatibility. ``PhysicsBody3D`` accepts the
    same live targets/colliders while adding material response, sleeping and optional continuous
    motion tests.
    """

    target: object
    collider: Collider3D
    body_type: PhysicsBodyType3D = "dynamic"
    mass: float = 1.0
    material: PhysicsMaterial3D = field(default_factory=PhysicsMaterial3D)
    gravity_scale: float = 1.0
    linear_damping: float = 0.0
    velocity: Vec3 = field(default_factory=Vec3)
    enabled: bool = True
    continuous: bool = False
    allow_sleep: bool = True
    sleep_speed_threshold: float = 0.05
    sleep_time_threshold: float = 0.5
    is_sleeping: bool = field(default=False, init=False)
    _sleep_time: float = field(default=0.0, init=False, repr=False)
    _force: Vec3 = field(default_factory=Vec3, init=False, repr=False)

    def __post_init__(self) -> None:
        if self.body_type not in ("dynamic", "kinematic", "static"):
            raise ValueError("body_type must be 'dynamic', 'kinematic' or 'static'")
        if self.mass <= 0.0:
            raise ValueError("mass must be greater than zero")
        if self.linear_damping < 0.0:
            raise ValueError("linear_damping must be non-negative")
        if self.sleep_speed_threshold < 0.0 or self.sleep_time_threshold < 0.0:
            raise ValueError("sleep thresholds must be non-negative")
        if self.collider.target is not self.target:
            raise ValueError("physics body collider must target the same object")
        self.mass = float(self.mass)
        self.gravity_scale = float(self.gravity_scale)
        self.linear_damping = float(self.linear_damping)

    @property
    def position(self) -> Vec3:
        return _position(self.target)

    @property
    def inverse_mass(self) -> float:
        return _inverse_mass(self)

    def set_position(self, x: float, y: float, z: float) -> PhysicsBody3D:
        _set_position(self.target, Vec3(float(x), float(y), float(z)))
        self.wake()
        return self

    def set_velocity(self, x: float, y: float, z: float) -> PhysicsBody3D:
        self.velocity.x = float(x)
        self.velocity.y = float(y)
        self.velocity.z = float(z)
        if _length_sq(self.velocity) > 0.0:
            self.wake()
        return self

    def apply_force(self, x: float, y: float, z: float) -> None:
        if self.body_type != "dynamic" or not self.enabled:
            return
        self._force.x += float(x)
        self._force.y += float(y)
        self._force.z += float(z)
        if x != 0.0 or y != 0.0 or z != 0.0:
            self.wake()

    def apply_impulse(self, x: float, y: float, z: float) -> None:
        if self.body_type != "dynamic" or not self.enabled:
            return
        inverse_mass = 1.0 / self.mass
        self.velocity.x += float(x) * inverse_mass
        self.velocity.y += float(y) * inverse_mass
        self.velocity.z += float(z) * inverse_mass
        if x != 0.0 or y != 0.0 or z != 0.0:
            self.wake()

    def clear_forces(self) -> None:
        self._force.x = 0.0
        self._force.y = 0.0
        self._force.z = 0.0

    def wake(self) -> None:
        self.is_sleeping = False
        self._sleep_time = 0.0

    def sleep(self) -> None:
        if self.body_type == "dynamic" and self.allow_sleep:
            self.is_sleeping = True
            self._sleep_time = self.sleep_time_threshold
            self.velocity.x = 0.0
            self.velocity.y = 0.0
            self.velocity.z = 0.0
            self.clear_forces()


@dataclass(slots=True)
class DistanceJoint3D:
    """Simple deterministic positional distance constraint between two physics bodies."""

    body_a: PhysicsBody3D
    body_b: PhysicsBody3D
    rest_length: float | None = None
    stiffness: float = 1.0
    damping: float = 0.0
    enabled: bool = True

    def __post_init__(self) -> None:
        if self.rest_length is None:
            delta = self.body_b.position - self.body_a.position
            self.rest_length = delta.length
        self.rest_length = float(self.rest_length)
        if self.rest_length < 0.0:
            raise ValueError("rest_length must be non-negative")
        if not 0.0 <= self.stiffness <= 1.0:
            raise ValueError("stiffness must be between 0 and 1")
        if self.damping < 0.0:
            raise ValueError("damping must be non-negative")

    def solve(self, dt: float) -> bool:
        if not self.enabled:
            return False
        pa = self.body_a.position
        pb = self.body_b.position
        dx = pb.x - pa.x
        dy = pb.y - pa.y
        dz = pb.z - pa.z
        distance_sq = dx * dx + dy * dy + dz * dz
        if distance_sq <= 1e-16:
            return False
        distance = sqrt(distance_sq)
        nx, ny, nz = dx / distance, dy / distance, dz / distance
        error = distance - self.rest_length
        inv_a = self.body_a.inverse_mass
        inv_b = self.body_b.inverse_mass
        total_inv = inv_a + inv_b
        if total_inv <= 0.0:
            return False

        correction = error * self.stiffness / total_inv
        if inv_a > 0.0:
            _set_position(
                self.body_a.target,
                Vec3(
                    pa.x + nx * correction * inv_a,
                    pa.y + ny * correction * inv_a,
                    pa.z + nz * correction * inv_a,
                ),
            )
            self.body_a.wake()
        if inv_b > 0.0:
            _set_position(
                self.body_b.target,
                Vec3(
                    pb.x - nx * correction * inv_b,
                    pb.y - ny * correction * inv_b,
                    pb.z - nz * correction * inv_b,
                ),
            )
            self.body_b.wake()

        if self.damping > 0.0 and dt > 0.0:
            rvx = self.body_b.velocity.x - self.body_a.velocity.x
            rvy = self.body_b.velocity.y - self.body_a.velocity.y
            rvz = self.body_b.velocity.z - self.body_a.velocity.z
            relative = rvx * nx + rvy * ny + rvz * nz
            impulse = relative * min(1.0, self.damping * dt) / total_inv
            if inv_a > 0.0:
                self.body_a.velocity.x += nx * impulse * inv_a
                self.body_a.velocity.y += ny * impulse * inv_a
                self.body_a.velocity.z += nz * impulse * inv_a
            if inv_b > 0.0:
                self.body_b.velocity.x -= nx * impulse * inv_b
                self.body_b.velocity.y -= ny * impulse * inv_b
                self.body_b.velocity.z -= nz * impulse * inv_b
        return True


@runtime_checkable
class PhysicsBackend3D(Protocol):
    """Backend contract used by creator/runtime integrations without binding to one solver."""

    @property
    def bodies(self) -> tuple[PhysicsBody3D, ...]: ...

    @property
    def diagnostics(self) -> PhysicsDiagnostics3D: ...

    def add(self, body: PhysicsBody3D) -> PhysicsBody3D: ...

    def remove(self, body: PhysicsBody3D) -> bool: ...

    def step(self, dt: float) -> int: ...

    def sweep_box(
        self,
        bounds: AABB3D,
        delta: Vec3,
        *,
        mask: int = 0xFFFFFFFF,
        ignore: Collider3D | None = None,
    ) -> SweepHit3D | None: ...

    def sweep_sphere(
        self,
        sphere: SphereBounds3D,
        delta: Vec3,
        *,
        mask: int = 0xFFFFFFFF,
        ignore: Collider3D | None = None,
    ) -> SweepHit3D | None: ...


def _box_box_contact(a: PhysicsBody3D, b: PhysicsBody3D) -> Contact3D | None:
    if not isinstance(a.collider, BoxCollider3D) or not isinstance(b.collider, BoxCollider3D):
        return None
    first = a.collider.bounds
    second = b.collider.bounds
    ox = min(first.right, second.right) - max(first.left, second.left)
    oy = min(first.top, second.top) - max(first.bottom, second.bottom)
    oz = min(first.front, second.front) - max(first.back, second.back)
    if ox <= 0.0 or oy <= 0.0 or oz <= 0.0:
        return None

    if ox <= oy and ox <= oz:
        sign = 1.0 if second.x >= first.x else -1.0
        normal = Vec3(sign, 0.0, 0.0)
        penetration = ox
    elif oy <= oz:
        sign = 1.0 if second.y >= first.y else -1.0
        normal = Vec3(0.0, sign, 0.0)
        penetration = oy
    else:
        sign = 1.0 if second.z >= first.z else -1.0
        normal = Vec3(0.0, 0.0, sign)
        penetration = oz
    point = Vec3(
        (max(first.left, second.left) + min(first.right, second.right)) * 0.5,
        (max(first.bottom, second.bottom) + min(first.top, second.top)) * 0.5,
        (max(first.back, second.back) + min(first.front, second.front)) * 0.5,
    )
    return Contact3D(a, b, point, normal, penetration)


def _sphere_sphere_contact(a: PhysicsBody3D, b: PhysicsBody3D) -> Contact3D | None:
    if not isinstance(a.collider, SphereCollider3D) or not isinstance(b.collider, SphereCollider3D):
        return None
    first = a.collider.bounds
    second = b.collider.bounds
    dx = second.x - first.x
    dy = second.y - first.y
    dz = second.z - first.z
    radius = first.radius + second.radius
    distance_sq = dx * dx + dy * dy + dz * dz
    if distance_sq >= radius * radius:
        return None
    if distance_sq <= 1e-16:
        normal = Vec3(1.0, 0.0, 0.0)
        distance = 0.0
    else:
        distance = sqrt(distance_sq)
        normal = Vec3(dx / distance, dy / distance, dz / distance)
    penetration = radius - distance
    point = Vec3(
        first.x + normal.x * (first.radius - penetration * 0.5),
        first.y + normal.y * (first.radius - penetration * 0.5),
        first.z + normal.z * (first.radius - penetration * 0.5),
    )
    return Contact3D(a, b, point, normal, penetration)


def _sphere_box_contact(
    sphere_body: PhysicsBody3D,
    box_body: PhysicsBody3D,
    *,
    sphere_is_a: bool,
) -> Contact3D | None:
    if not isinstance(sphere_body.collider, SphereCollider3D) or not isinstance(
        box_body.collider, BoxCollider3D
    ):
        return None
    sphere = sphere_body.collider.bounds
    box = box_body.collider.bounds
    cx = min(max(sphere.x, box.left), box.right)
    cy = min(max(sphere.y, box.bottom), box.top)
    cz = min(max(sphere.z, box.back), box.front)
    dx = cx - sphere.x
    dy = cy - sphere.y
    dz = cz - sphere.z
    distance_sq = dx * dx + dy * dy + dz * dz
    if distance_sq >= sphere.radius * sphere.radius:
        return None

    if distance_sq > 1e-16:
        distance = sqrt(distance_sq)
        sx, sy, sz = dx / distance, dy / distance, dz / distance
        penetration = sphere.radius - distance
    else:
        distances = (
            (abs(sphere.x - box.left), Vec3(-1.0, 0.0, 0.0)),
            (abs(box.right - sphere.x), Vec3(1.0, 0.0, 0.0)),
            (abs(sphere.y - box.bottom), Vec3(0.0, -1.0, 0.0)),
            (abs(box.top - sphere.y), Vec3(0.0, 1.0, 0.0)),
            (abs(sphere.z - box.back), Vec3(0.0, 0.0, -1.0)),
            (abs(box.front - sphere.z), Vec3(0.0, 0.0, 1.0)),
        )
        face_distance, face_normal = min(distances, key=lambda item: item[0])
        sx, sy, sz = face_normal.x, face_normal.y, face_normal.z
        penetration = sphere.radius + face_distance
        cx = sphere.x + sx * face_distance
        cy = sphere.y + sy * face_distance
        cz = sphere.z + sz * face_distance

    if sphere_is_a:
        # Calculated direction is sphere -> box, which matches A -> B.
        normal = Vec3(sx, sy, sz)
        return Contact3D(sphere_body, box_body, Vec3(cx, cy, cz), normal, penetration)
    normal = Vec3(-sx, -sy, -sz)
    return Contact3D(box_body, sphere_body, Vec3(cx, cy, cz), normal, penetration)


def _contact(a: PhysicsBody3D, b: PhysicsBody3D) -> Contact3D | None:
    if isinstance(a.collider, BoxCollider3D) and isinstance(b.collider, BoxCollider3D):
        return _box_box_contact(a, b)
    if isinstance(a.collider, SphereCollider3D) and isinstance(b.collider, SphereCollider3D):
        return _sphere_sphere_contact(a, b)
    if isinstance(a.collider, SphereCollider3D):
        return _sphere_box_contact(a, b, sphere_is_a=True)
    return _sphere_box_contact(b, a, sphere_is_a=False)


def _swept_aabb(moving: AABB3D, delta: Vec3, target: AABB3D) -> tuple[float, Vec3] | None:
    """Ray-vs-expanded-AABB TOI for an axis-aligned moving box."""
    expanded = AABB3D(
        target.x,
        target.y,
        target.z,
        target.width + moving.width,
        target.height + moving.height,
        target.depth + moving.depth,
    )
    origin = Vec3(moving.x, moving.y, moving.z)
    t_enter = 0.0
    t_exit = 1.0
    hit_normal = Vec3()
    for axis, origin_value, delta_value, lower, upper in (
        ("x", origin.x, delta.x, expanded.left, expanded.right),
        ("y", origin.y, delta.y, expanded.bottom, expanded.top),
        ("z", origin.z, delta.z, expanded.back, expanded.front),
    ):
        if abs(delta_value) <= 1e-12:
            if origin_value < lower or origin_value > upper:
                return None
            continue
        inv = 1.0 / delta_value
        near = (lower - origin_value) * inv
        far = (upper - origin_value) * inv
        near_normal = -1.0
        if near > far:
            near, far = far, near
            near_normal = 1.0
        if near > t_enter:
            t_enter = near
            if axis == "x":
                hit_normal = Vec3(near_normal, 0.0, 0.0)
            elif axis == "y":
                hit_normal = Vec3(0.0, near_normal, 0.0)
            else:
                hit_normal = Vec3(0.0, 0.0, near_normal)
        t_exit = min(t_exit, far)
        if t_enter > t_exit:
            return None
    if t_enter < 0.0 or t_enter > 1.0:
        return None
    return t_enter, hit_normal


def _expanded_for_sphere(target: AABB3D, radius: float) -> AABB3D:
    return AABB3D(
        target.x,
        target.y,
        target.z,
        target.width + radius * 2.0,
        target.height + radius * 2.0,
        target.depth + radius * 2.0,
    )


def _ray_aabb_fraction(origin: Vec3, delta: Vec3, target: AABB3D) -> tuple[float, Vec3] | None:
    point_box = AABB3D(origin.x, origin.y, origin.z, 0.0, 0.0, 0.0)
    return _swept_aabb(point_box, delta, target)


class PhysicsScene3D:
    """Deterministic fixed-step Physics 2.0 scene.

    Broad phase is rebuilt once per substep, then all sorted candidate pairs share that index. This
    avoids the previous pattern of rebuilding the collision spatial hash once for every moving body.
    """

    def __init__(
        self,
        *,
        gravity: Vec3 | None = None,
        fixed_dt: float = 1.0 / 60.0,
        max_substeps: int = 8,
        cell_size: float = 4.0,
        solver_iterations: int = 4,
        joint_iterations: int = 2,
        penetration_slop: float = 0.001,
        correction_percent: float = 0.8,
    ) -> None:
        if fixed_dt <= 0.0:
            raise ValueError("fixed_dt must be greater than zero")
        if max_substeps < 1:
            raise ValueError("max_substeps must be >= 1")
        if cell_size <= 0.0:
            raise ValueError("cell_size must be greater than zero")
        if solver_iterations < 1 or joint_iterations < 1:
            raise ValueError("solver iteration counts must be >= 1")
        if penetration_slop < 0.0:
            raise ValueError("penetration_slop must be non-negative")
        if not 0.0 <= correction_percent <= 1.0:
            raise ValueError("correction_percent must be between 0 and 1")
        self.gravity = gravity or Vec3(0.0, -9.81, 0.0)
        self.fixed_dt = float(fixed_dt)
        self.max_substeps = int(max_substeps)
        self.cell_size = float(cell_size)
        self.solver_iterations = int(solver_iterations)
        self.joint_iterations = int(joint_iterations)
        self.penetration_slop = float(penetration_slop)
        self.correction_percent = float(correction_percent)
        self._bodies: list[PhysicsBody3D] = []
        self._joints: list[DistanceJoint3D] = []
        self._accumulator = 0.0
        self._dropped_time = 0.0
        self._grid: dict[tuple[int, int, int], list[int]] = {}
        self._bounds: list[AABB3D] = []
        self._diagnostics = PhysicsDiagnostics3D()

    @property
    def bodies(self) -> tuple[PhysicsBody3D, ...]:
        return tuple(self._bodies)

    @property
    def joints(self) -> tuple[DistanceJoint3D, ...]:
        return tuple(self._joints)

    @property
    def diagnostics(self) -> PhysicsDiagnostics3D:
        return self._diagnostics

    @property
    def interpolation_alpha(self) -> float:
        return self._accumulator / self.fixed_dt

    @property
    def dropped_time(self) -> float:
        return self._dropped_time

    def add(self, body: PhysicsBody3D) -> PhysicsBody3D:
        if not any(existing is body for existing in self._bodies):
            self._bodies.append(body)
        return body

    def remove(self, body: PhysicsBody3D) -> bool:
        for index, existing in enumerate(self._bodies):
            if existing is body:
                del self._bodies[index]
                self._joints[:] = [
                    joint
                    for joint in self._joints
                    if joint.body_a is not body and joint.body_b is not body
                ]
                return True
        return False

    def add_joint(self, joint: DistanceJoint3D) -> DistanceJoint3D:
        if not any(existing is joint for existing in self._joints):
            self._joints.append(joint)
        return joint

    def remove_joint(self, joint: DistanceJoint3D) -> bool:
        for index, existing in enumerate(self._joints):
            if existing is joint:
                del self._joints[index]
                return True
        return False

    def clear(self) -> None:
        self._bodies.clear()
        self._joints.clear()
        self._grid.clear()
        self._bounds.clear()
        self._accumulator = 0.0
        self._dropped_time = 0.0
        self._diagnostics = PhysicsDiagnostics3D()

    def _iter_cells(self, bounds: AABB3D) -> Iterator[tuple[int, int, int]]:
        left = floor(bounds.left / self.cell_size)
        right = floor(bounds.right / self.cell_size)
        bottom = floor(bounds.bottom / self.cell_size)
        top = floor(bounds.top / self.cell_size)
        back = floor(bounds.back / self.cell_size)
        front = floor(bounds.front / self.cell_size)
        for z in range(back, front + 1):
            for y in range(bottom, top + 1):
                for x in range(left, right + 1):
                    yield x, y, z

    def _rebuild_index(self) -> None:
        self._grid.clear()
        self._bounds.clear()
        for index, body in enumerate(self._bodies):
            bounds = _collider_aabb(body.collider)
            self._bounds.append(bounds)
            if not body.enabled or not body.collider.enabled:
                continue
            for cell in self._iter_cells(bounds):
                self._grid.setdefault(cell, []).append(index)

    def _candidate_pairs(self) -> list[tuple[int, int]]:
        pairs: set[tuple[int, int]] = set()
        for indexes in self._grid.values():
            count = len(indexes)
            for left in range(count):
                a = indexes[left]
                for right in range(left + 1, count):
                    b = indexes[right]
                    if a == b:
                        continue
                    pair = (a, b) if a < b else (b, a)
                    pairs.add(pair)
        return sorted(pairs)

    @staticmethod
    def _can_pair(a: PhysicsBody3D, b: PhysicsBody3D) -> bool:
        if not a.enabled or not b.enabled or not a.collider.enabled or not b.collider.enabled:
            return False
        if a.body_type == "static" and b.body_type == "static":
            return False
        return a.collider.can_collide_with(b.collider)

    def _integrate_forces(self, body: PhysicsBody3D, dt: float) -> None:
        if body.body_type != "dynamic" or not body.enabled or body.is_sleeping:
            body.clear_forces()
            return
        inverse_mass = 1.0 / body.mass
        body.velocity.x += (
            self.gravity.x * body.gravity_scale + body._force.x * inverse_mass
        ) * dt
        body.velocity.y += (
            self.gravity.y * body.gravity_scale + body._force.y * inverse_mass
        ) * dt
        body.velocity.z += (
            self.gravity.z * body.gravity_scale + body._force.z * inverse_mass
        ) * dt
        body.clear_forces()
        damping = max(0.0, 1.0 - body.linear_damping * dt)
        body.velocity.x *= damping
        body.velocity.y *= damping
        body.velocity.z *= damping

    def _integrate_position(self, body: PhysicsBody3D, dt: float) -> tuple[int, int]:
        if (
            body.body_type == "static"
            or not body.enabled
            or (body.body_type == "dynamic" and body.is_sleeping)
        ):
            return 0, 0
        delta = Vec3(body.velocity.x * dt, body.velocity.y * dt, body.velocity.z * dt)
        sweep_tests = 0
        sweep_hits = 0
        fraction = 1.0
        hit: SweepHit3D | None = None
        if body.continuous and _length_sq(delta) > 1e-16:
            if isinstance(body.collider, BoxCollider3D):
                hit = self.sweep_box(body.collider.bounds, delta, ignore=body.collider)
            else:
                hit = self.sweep_sphere(body.collider.bounds, delta, ignore=body.collider)
            sweep_tests = max(0, len(self._bodies) - 1)
            if hit is not None:
                fraction = max(0.0, hit.fraction - 1e-5)
                sweep_hits = 1
        current = body.position
        _set_position(
            body.target,
            Vec3(
                current.x + delta.x * fraction,
                current.y + delta.y * fraction,
                current.z + delta.z * fraction,
            ),
        )
        if hit is not None:
            normal_speed = _dot(body.velocity, hit.normal)
            if normal_speed < 0.0:
                bounce = 1.0 + body.material.restitution
                body.velocity.x -= hit.normal.x * normal_speed * bounce
                body.velocity.y -= hit.normal.y * normal_speed * bounce
                body.velocity.z -= hit.normal.z * normal_speed * bounce
        return sweep_tests, sweep_hits

    def _generate_contacts(self) -> tuple[list[Contact3D], int, int]:
        self._rebuild_index()
        pairs = self._candidate_pairs()
        contacts: list[Contact3D] = []
        tests = 0
        for a_index, b_index in pairs:
            a = self._bodies[a_index]
            b = self._bodies[b_index]
            if not self._can_pair(a, b):
                continue
            if not self._bounds[a_index].intersects(self._bounds[b_index]):
                continue
            tests += 1
            generated = _contact(a, b)
            if generated is not None:
                contacts.append(generated)
        return contacts, len(pairs), tests

    def _solve_contact(self, contact: Contact3D) -> tuple[int, int]:
        a = contact.body_a
        b = contact.body_b
        inv_a = a.inverse_mass
        inv_b = b.inverse_mass
        total_inv = inv_a + inv_b
        if total_inv <= 0.0:
            return 0, 0

        if contact.penetration > self.penetration_slop:
            correction = (
                (contact.penetration - self.penetration_slop)
                * self.correction_percent
                / total_inv
            )
            if inv_a > 0.0:
                pa = a.position
                _set_position(
                    a.target,
                    Vec3(
                        pa.x - contact.normal.x * correction * inv_a,
                        pa.y - contact.normal.y * correction * inv_a,
                        pa.z - contact.normal.z * correction * inv_a,
                    ),
                )
            if inv_b > 0.0:
                pb = b.position
                _set_position(
                    b.target,
                    Vec3(
                        pb.x + contact.normal.x * correction * inv_b,
                        pb.y + contact.normal.y * correction * inv_b,
                        pb.z + contact.normal.z * correction * inv_b,
                    ),
                )

        rv = Vec3(
            b.velocity.x - a.velocity.x,
            b.velocity.y - a.velocity.y,
            b.velocity.z - a.velocity.z,
        )
        velocity_normal = _dot(rv, contact.normal)
        if velocity_normal > 0.0:
            return 0, 0
        restitution = max(a.material.restitution, b.material.restitution)
        normal_impulse = -(1.0 + restitution) * velocity_normal / total_inv
        ix = contact.normal.x * normal_impulse
        iy = contact.normal.y * normal_impulse
        iz = contact.normal.z * normal_impulse
        if inv_a > 0.0:
            a.velocity.x -= ix * inv_a
            a.velocity.y -= iy * inv_a
            a.velocity.z -= iz * inv_a
        if inv_b > 0.0:
            b.velocity.x += ix * inv_b
            b.velocity.y += iy * inv_b
            b.velocity.z += iz * inv_b

        rvx = b.velocity.x - a.velocity.x
        rvy = b.velocity.y - a.velocity.y
        rvz = b.velocity.z - a.velocity.z
        tangent_x = rvx - contact.normal.x * (rvx * contact.normal.x + rvy * contact.normal.y + rvz * contact.normal.z)
        tangent_y = rvy - contact.normal.y * (rvx * contact.normal.x + rvy * contact.normal.y + rvz * contact.normal.z)
        tangent_z = rvz - contact.normal.z * (rvx * contact.normal.x + rvy * contact.normal.y + rvz * contact.normal.z)
        tangent_length_sq = tangent_x * tangent_x + tangent_y * tangent_y + tangent_z * tangent_z
        if tangent_length_sq <= 1e-16:
            return 1, 0
        tangent_length = sqrt(tangent_length_sq)
        tx, ty, tz = tangent_x / tangent_length, tangent_y / tangent_length, tangent_z / tangent_length
        tangent_velocity = rvx * tx + rvy * ty + rvz * tz
        friction_impulse = -tangent_velocity / total_inv
        friction = sqrt(a.material.friction * b.material.friction)
        limit = abs(normal_impulse) * friction
        friction_impulse = max(-limit, min(limit, friction_impulse))
        fix, fiy, fiz = tx * friction_impulse, ty * friction_impulse, tz * friction_impulse
        if inv_a > 0.0:
            a.velocity.x -= fix * inv_a
            a.velocity.y -= fiy * inv_a
            a.velocity.z -= fiz * inv_a
        if inv_b > 0.0:
            b.velocity.x += fix * inv_b
            b.velocity.y += fiy * inv_b
            b.velocity.z += fiz * inv_b
        return 1, 1

    def _update_sleeping(self, body: PhysicsBody3D, dt: float) -> None:
        if body.body_type != "dynamic" or not body.enabled or not body.allow_sleep:
            body._sleep_time = 0.0
            body.is_sleeping = False
            return
        threshold_sq = body.sleep_speed_threshold * body.sleep_speed_threshold
        if _length_sq(body.velocity) <= threshold_sq and _length_sq(body._force) <= 1e-16:
            body._sleep_time += dt
            if body._sleep_time >= body.sleep_time_threshold:
                body.sleep()
        else:
            body._sleep_time = 0.0
            body.is_sleeping = False

    def _substep(self, dt: float) -> PhysicsDiagnostics3D:
        sweep_tests = 0
        sweep_hits = 0
        for body in self._bodies:
            self._integrate_forces(body, dt)
        for body in self._bodies:
            tests, hits = self._integrate_position(body, dt)
            sweep_tests += tests
            sweep_hits += hits

        contacts, candidate_pairs, narrow_tests = self._generate_contacts()
        normal_impulses = 0
        friction_impulses = 0
        for _ in range(self.solver_iterations):
            for contact in contacts:
                normal_count, friction_count = self._solve_contact(contact)
                normal_impulses += normal_count
                friction_impulses += friction_count

        joint_solves = 0
        for _ in range(self.joint_iterations):
            for joint in self._joints:
                if joint.solve(dt):
                    joint_solves += 1

        for body in self._bodies:
            self._update_sleeping(body, dt)

        return PhysicsDiagnostics3D(
            body_count=len(self._bodies),
            dynamic_bodies=sum(
                1 for body in self._bodies if body.enabled and body.body_type == "dynamic"
            ),
            sleeping_bodies=sum(1 for body in self._bodies if body.is_sleeping),
            occupied_cells=len(self._grid),
            candidate_pairs=candidate_pairs,
            narrow_phase_tests=narrow_tests,
            contacts=len(contacts),
            normal_impulses=normal_impulses,
            friction_impulses=friction_impulses,
            joint_solves=joint_solves,
            sweep_tests=sweep_tests,
            sweep_hits=sweep_hits,
            substeps=1,
        )

    def step(self, dt: float) -> int:
        """Advance by bounded deterministic fixed substeps and return executed count."""
        if dt <= 0.0:
            return 0
        incoming = float(dt)
        max_time = self.fixed_dt * self.max_substeps
        accepted = min(incoming, max_time)
        self._dropped_time += max(0.0, incoming - accepted)
        self._accumulator += accepted
        steps = 0
        aggregate = PhysicsDiagnostics3D(body_count=len(self._bodies))
        epsilon = self.fixed_dt * 1e-9
        while self._accumulator + epsilon >= self.fixed_dt and steps < self.max_substeps:
            current = self._substep(self.fixed_dt)
            aggregate = PhysicsDiagnostics3D(
                body_count=current.body_count,
                dynamic_bodies=current.dynamic_bodies,
                sleeping_bodies=current.sleeping_bodies,
                occupied_cells=current.occupied_cells,
                candidate_pairs=aggregate.candidate_pairs + current.candidate_pairs,
                narrow_phase_tests=aggregate.narrow_phase_tests + current.narrow_phase_tests,
                contacts=aggregate.contacts + current.contacts,
                normal_impulses=aggregate.normal_impulses + current.normal_impulses,
                friction_impulses=aggregate.friction_impulses + current.friction_impulses,
                joint_solves=aggregate.joint_solves + current.joint_solves,
                sweep_tests=aggregate.sweep_tests + current.sweep_tests,
                sweep_hits=aggregate.sweep_hits + current.sweep_hits,
                substeps=aggregate.substeps + 1,
            )
            self._accumulator -= self.fixed_dt
            if self._accumulator < 0.0 and abs(self._accumulator) <= epsilon:
                self._accumulator = 0.0
            steps += 1
        if steps:
            self._diagnostics = aggregate
        return steps

    def sweep_box(
        self,
        bounds: AABB3D,
        delta: Vec3,
        *,
        mask: int = 0xFFFFFFFF,
        ignore: Collider3D | None = None,
    ) -> SweepHit3D | None:
        best: SweepHit3D | None = None
        distance = sqrt(_length_sq(delta))
        for body in self._bodies:
            collider = body.collider
            if collider is ignore or not body.enabled or not collider.enabled or not (mask & collider.layer):
                continue
            result = _swept_aabb(bounds, delta, _collider_aabb(collider))
            if result is None:
                continue
            fraction, normal = result
            if best is None or fraction < best.fraction:
                best = SweepHit3D(
                    collider=collider,
                    fraction=fraction,
                    distance=distance * fraction,
                    point=Vec3(
                        bounds.x + delta.x * fraction,
                        bounds.y + delta.y * fraction,
                        bounds.z + delta.z * fraction,
                    ),
                    normal=normal,
                )
        return best

    def sweep_sphere(
        self,
        sphere: SphereBounds3D,
        delta: Vec3,
        *,
        mask: int = 0xFFFFFFFF,
        ignore: Collider3D | None = None,
    ) -> SweepHit3D | None:
        best: SweepHit3D | None = None
        distance = sqrt(_length_sq(delta))
        origin = Vec3(sphere.x, sphere.y, sphere.z)
        for body in self._bodies:
            collider = body.collider
            if collider is ignore or not body.enabled or not collider.enabled or not (mask & collider.layer):
                continue
            expanded = _expanded_for_sphere(_collider_aabb(collider), sphere.radius)
            result = _ray_aabb_fraction(origin, delta, expanded)
            if result is None:
                continue
            fraction, normal = result
            if best is None or fraction < best.fraction:
                best = SweepHit3D(
                    collider=collider,
                    fraction=fraction,
                    distance=distance * fraction,
                    point=Vec3(
                        sphere.x + delta.x * fraction,
                        sphere.y + delta.y * fraction,
                        sphere.z + delta.z * fraction,
                    ),
                    normal=normal,
                )
        return best
