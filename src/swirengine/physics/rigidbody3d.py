from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, cast

from ..math.types import Vec3
from .collision3d import BoxCollider3D, CollisionWorld3D

BodyType3D = Literal["dynamic", "kinematic", "static"]


def _position_owner(target: object) -> Any:
    position = getattr(target, "position", None)
    if position is not None:
        try:
            float(position.x)
            float(position.y)
            float(position.z)
        except AttributeError as exc:
            raise TypeError("target.position must expose x, y and z attributes") from exc
        return position

    raw = cast(Any, target)
    try:
        float(raw.x)
        float(raw.y)
        float(raw.z)
    except AttributeError as exc:
        raise TypeError("3D rigid-body target must expose position.x/y/z or x/y/z") from exc
    return raw


@dataclass(slots=True)
class RigidBody3D:
    """Deterministic arcade-style AABB rigid body for 3D gameplay."""

    target: object
    collider: BoxCollider3D
    body_type: BodyType3D = "dynamic"
    mass: float = 1.0
    gravity_scale: float = 1.0
    linear_damping: float = 0.0
    restitution: float = 0.0
    velocity: Vec3 = field(default_factory=Vec3)
    enabled: bool = True
    _force: Vec3 = field(default_factory=Vec3, init=False, repr=False)

    def __post_init__(self) -> None:
        if self.body_type not in ("dynamic", "kinematic", "static"):
            raise ValueError("body_type must be 'dynamic', 'kinematic' or 'static'")
        if self.mass <= 0:
            raise ValueError("mass must be greater than zero")
        self.mass = float(self.mass)
        self.restitution = max(0.0, min(1.0, float(self.restitution)))
        self.linear_damping = max(0.0, float(self.linear_damping))
        if self.collider.target is not self.target:
            raise ValueError("rigid body collider must target the same object")

    def set_velocity(self, x: float, y: float, z: float) -> RigidBody3D:
        self.velocity.x = float(x)
        self.velocity.y = float(y)
        self.velocity.z = float(z)
        return self

    def apply_force(self, x: float, y: float, z: float) -> None:
        if self.body_type == "dynamic":
            self._force.x += float(x)
            self._force.y += float(y)
            self._force.z += float(z)

    def apply_impulse(self, x: float, y: float, z: float) -> None:
        if self.body_type == "dynamic":
            self.velocity.x += float(x) / self.mass
            self.velocity.y += float(y) / self.mass
            self.velocity.z += float(z) / self.mass

    def clear_forces(self) -> None:
        self._force.x = 0.0
        self._force.y = 0.0
        self._force.z = 0.0

    def _move_axis(self, world: CollisionWorld3D, amount: float, axis: str) -> None:
        if amount == 0.0:
            return
        position = _position_owner(self.target)
        setattr(position, axis, float(getattr(position, axis)) + amount)
        hits = world.query(self.collider)
        if not hits:
            return

        bounds = self.collider.bounds
        for other in hits:
            if not isinstance(other, BoxCollider3D):
                continue
            other_bounds = other.bounds
            if axis == "x":
                if amount > 0:
                    correction = bounds.right - other_bounds.left
                    position.x -= correction
                else:
                    correction = other_bounds.right - bounds.left
                    position.x += correction
                self.velocity.x = -self.velocity.x * self.restitution
            elif axis == "y":
                if amount > 0:
                    correction = bounds.top - other_bounds.bottom
                    position.y -= correction
                else:
                    correction = other_bounds.top - bounds.bottom
                    position.y += correction
                self.velocity.y = -self.velocity.y * self.restitution
            else:
                if amount > 0:
                    correction = bounds.front - other_bounds.back
                    position.z -= correction
                else:
                    correction = other_bounds.front - bounds.back
                    position.z += correction
                self.velocity.z = -self.velocity.z * self.restitution
            bounds = self.collider.bounds

    def step(self, dt: float, world: CollisionWorld3D, gravity: Vec3) -> None:
        if not self.enabled or self.body_type == "static" or dt <= 0:
            self.clear_forces()
            return

        if self.body_type == "dynamic":
            inverse_mass = 1.0 / self.mass
            self.velocity.x += (
                float(gravity.x) * self.gravity_scale + self._force.x * inverse_mass
            ) * dt
            self.velocity.y += (
                float(gravity.y) * self.gravity_scale + self._force.y * inverse_mass
            ) * dt
            self.velocity.z += (
                float(gravity.z) * self.gravity_scale + self._force.z * inverse_mass
            ) * dt
        self.clear_forces()

        damping = max(0.0, 1.0 - self.linear_damping * dt)
        self.velocity.x *= damping
        self.velocity.y *= damping
        self.velocity.z *= damping
        self._move_axis(world, self.velocity.x * dt, "x")
        self._move_axis(world, self.velocity.y * dt, "y")
        self._move_axis(world, self.velocity.z * dt, "z")


class PhysicsWorld3D:
    """Fixed-step 3D arcade simulation layered on ``CollisionWorld3D``."""

    def __init__(
        self,
        collisions: CollisionWorld3D | None = None,
        *,
        gravity: Vec3 | None = None,
        fixed_dt: float = 1.0 / 60.0,
        max_substeps: int = 8,
    ) -> None:
        if fixed_dt <= 0:
            raise ValueError("fixed_dt must be greater than zero")
        if max_substeps <= 0:
            raise ValueError("max_substeps must be greater than zero")
        self.collisions = collisions or CollisionWorld3D()
        self.gravity = gravity or Vec3(0.0, -9.81, 0.0)
        self.fixed_dt = float(fixed_dt)
        self.max_substeps = int(max_substeps)
        self._bodies: list[RigidBody3D] = []
        self._accumulator = 0.0
        self._dropped_time = 0.0

    @property
    def bodies(self) -> tuple[RigidBody3D, ...]:
        return tuple(self._bodies)

    @property
    def interpolation_alpha(self) -> float:
        return self._accumulator / self.fixed_dt

    @property
    def dropped_time(self) -> float:
        return self._dropped_time

    def add(self, body: RigidBody3D) -> RigidBody3D:
        if not any(existing is body for existing in self._bodies):
            self._bodies.append(body)
        self.collisions.add(body.collider)
        return body

    def remove(self, body: RigidBody3D) -> bool:
        for index, existing in enumerate(self._bodies):
            if existing is body:
                del self._bodies[index]
                self.collisions.remove(body.collider)
                return True
        return False

    def clear(self) -> None:
        for body in self._bodies:
            self.collisions.remove(body.collider)
        self._bodies.clear()
        self._accumulator = 0.0
        self._dropped_time = 0.0

    def step(self, dt: float) -> int:
        """Advance using deterministic fixed substeps and return the number executed."""
        if dt <= 0:
            return 0
        incoming = float(dt)
        max_time = self.fixed_dt * self.max_substeps
        accepted = min(incoming, max_time)
        self._dropped_time += max(0.0, incoming - accepted)
        self._accumulator += accepted

        steps = 0
        epsilon = self.fixed_dt * 1e-9
        while self._accumulator + epsilon >= self.fixed_dt and steps < self.max_substeps:
            for body in self._bodies:
                body.step(self.fixed_dt, self.collisions, self.gravity)
            self._accumulator -= self.fixed_dt
            if self._accumulator < 0 and abs(self._accumulator) <= epsilon:
                self._accumulator = 0.0
            steps += 1
        return steps
