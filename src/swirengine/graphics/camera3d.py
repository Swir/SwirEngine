from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from ..math.types import Vec3


def _array(v: Vec3) -> np.ndarray:
    return np.asarray((v.x, v.y, v.z), dtype="f4")


@dataclass(slots=True)
class Camera3D:
    """Perspective camera with look-at and local movement helpers."""

    position: Vec3 = field(default_factory=Vec3)
    target: Vec3 = field(default_factory=lambda: Vec3(0.0, 0.0, -1.0))
    up: Vec3 = field(default_factory=lambda: Vec3(0.0, 1.0, 0.0))
    fov: float = 60.0
    near: float = 0.1
    far: float = 1000.0

    @property
    def forward(self) -> Vec3:
        return (self.target - self.position).normalized()

    @property
    def right(self) -> Vec3:
        f = _array(self.forward)
        u = _array(self.up)
        r = np.cross(f, u)
        length = float(np.linalg.norm(r))
        if length == 0.0:
            return Vec3(1.0, 0.0, 0.0)
        r /= length
        return Vec3(float(r[0]), float(r[1]), float(r[2]))

    def look_at(self, target: Vec3) -> Camera3D:
        self.target = Vec3(target.x, target.y, target.z)
        return self

    def move(self, x: float = 0.0, y: float = 0.0, z: float = 0.0) -> Camera3D:
        delta = Vec3(float(x), float(y), float(z))
        self.position = self.position + delta
        self.target = self.target + delta
        return self

    def move_local(
        self,
        *,
        forward: float = 0.0,
        right: float = 0.0,
        up: float = 0.0,
    ) -> Camera3D:
        f = self.forward
        r = self.right
        u = self.up.normalized()
        delta = f * float(forward) + r * float(right) + u * float(up)
        return self.move(delta.x, delta.y, delta.z)

    def view_matrix(self) -> np.ndarray:
        eye = _array(self.position)
        target = _array(self.target)
        up = _array(self.up)

        forward = target - eye
        forward_length = float(np.linalg.norm(forward))
        if forward_length == 0.0:
            raise ValueError("Camera3D position and target must be different")
        forward /= forward_length

        side = np.cross(forward, up)
        side_length = float(np.linalg.norm(side))
        if side_length == 0.0:
            raise ValueError("Camera3D up vector must not be parallel to the view direction")
        side /= side_length
        corrected_up = np.cross(side, forward)

        out = np.eye(4, dtype="f4")
        out[0, :3] = side
        out[1, :3] = corrected_up
        out[2, :3] = -forward
        out[0, 3] = -float(np.dot(side, eye))
        out[1, 3] = -float(np.dot(corrected_up, eye))
        out[2, 3] = float(np.dot(forward, eye))
        return out
