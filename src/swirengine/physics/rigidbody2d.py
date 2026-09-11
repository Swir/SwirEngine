from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, cast

from .collision2d import BoxCollider2D, CollisionWorld2D

BodyType = Literal["dynamic", "kinematic", "static"]


@dataclass(slots=True)
class RigidBody2D:
    """Arcade-friendly rigid body for center-based 2D scene objects."""

    target: object
    collider: BoxCollider2D
    body_type: BodyType = "dynamic"
    mass: float = 1.0
    gravity_scale: float = 1.0
    linear_damping: float = 0.0
    restitution: float = 0.0
    velocity_x: float = 0.0
    velocity_y: float = 0.0
    enabled: bool = True
    _force_x: float = field(default=0.0, init=False, repr=False)
    _force_y: float = field(default=0.0, init=False, repr=False)

    def __post_init__(self) -> None:
        if self.body_type not in ("dynamic", "kinematic", "static"):
            raise ValueError("body_type must be 'dynamic', 'kinematic' or 'static'")
        if self.mass <= 0:
            raise ValueError("mass must be greater than zero")
        self.restitution = max(0.0, min(1.0, float(self.restitution)))
        self.linear_damping = max(0.0, float(self.linear_damping))
        if self.collider.target is not self.target:
            raise ValueError("rigid body collider must target the same object")

    @property
    def velocity(self) -> tuple[float, float]:
        return self.velocity_x, self.velocity_y

    def set_velocity(self, x: float, y: float) -> RigidBody2D:
        self.velocity_x = float(x)
        self.velocity_y = float(y)
        return self

    def apply_force(self, x: float, y: float) -> None:
        if self.body_type == "dynamic":
            self._force_x += float(x)
            self._force_y += float(y)

    def apply_impulse(self, x: float, y: float) -> None:
        if self.body_type == "dynamic":
            self.velocity_x += float(x) / self.mass
            self.velocity_y += float(y) / self.mass

    def clear_forces(self) -> None:
        self._force_x = 0.0
        self._force_y = 0.0

    def _move_axis(self, world: CollisionWorld2D, amount: float, axis: str) -> None:
        if amount == 0.0:
            return
        target = cast(Any, self.target)
        setattr(target, axis, float(getattr(target, axis)) + amount)
        hits = world.query(self.collider)
        if not hits:
            return

        bounds = self.collider.bounds
        for other in hits:
            other_bounds = other.bounds
            if axis == "x":
                if amount > 0:
                    correction = bounds.right - other_bounds.left
                    target.x -= correction
                else:
                    correction = other_bounds.right - bounds.left
                    target.x += correction
                self.velocity_x = -self.velocity_x * self.restitution
            else:
                if amount > 0:
                    correction = bounds.top - other_bounds.bottom
                    target.y -= correction
                else:
                    correction = other_bounds.top - bounds.bottom
                    target.y += correction
                self.velocity_y = -self.velocity_y * self.restitution
            bounds = self.collider.bounds

    def step(self, dt: float, world: CollisionWorld2D, gravity: tuple[float, float]) -> None:
        if not self.enabled or self.body_type == "static" or dt <= 0:
            self.clear_forces()
            return

        if self.body_type == "dynamic":
            gx, gy = gravity
            self.velocity_x += (gx * self.gravity_scale + self._force_x / self.mass) * dt
            self.velocity_y += (gy * self.gravity_scale + self._force_y / self.mass) * dt
        self.clear_forces()

        damping = max(0.0, 1.0 - self.linear_damping * dt)
        self.velocity_x *= damping
        self.velocity_y *= damping
        self._move_axis(world, self.velocity_x * dt, "x")
        self._move_axis(world, self.velocity_y * dt, "y")


class PhysicsWorld2D:
    """Fixed-step body simulation layered on top of ``CollisionWorld2D``."""

    def __init__(
        self,
        collisions: CollisionWorld2D | None = None,
        *,
        gravity: tuple[float, float] = (0.0, -980.0),
    ) -> None:
        self.collisions = collisions or CollisionWorld2D()
        self.gravity = (float(gravity[0]), float(gravity[1]))
        self._bodies: list[RigidBody2D] = []

    @property
    def bodies(self) -> tuple[RigidBody2D, ...]:
        return tuple(self._bodies)

    def add(self, body: RigidBody2D) -> RigidBody2D:
        if not any(existing is body for existing in self._bodies):
            self._bodies.append(body)
        return body

    def remove(self, body: RigidBody2D) -> bool:
        for index, existing in enumerate(self._bodies):
            if existing is body:
                del self._bodies[index]
                return True
        return False

    def clear(self) -> None:
        self._bodies.clear()

    def step(self, dt: float) -> None:
        for body in tuple(self._bodies):
            body.step(dt, self.collisions, self.gravity)
