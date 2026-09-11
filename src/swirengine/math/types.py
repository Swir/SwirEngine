from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np


@dataclass(slots=True)
class Vec2:
    x: float = 0.0
    y: float = 0.0

    def __add__(self, other: Vec2) -> Vec2:
        return Vec2(self.x + other.x, self.y + other.y)

    def __sub__(self, other: Vec2) -> Vec2:
        return Vec2(self.x - other.x, self.y - other.y)

    def __mul__(self, scalar: float) -> Vec2:
        return Vec2(self.x * scalar, self.y * scalar)

    __rmul__ = __mul__

    @property
    def length(self) -> float:
        return math.hypot(self.x, self.y)

    def normalized(self) -> Vec2:
        length = self.length
        return Vec2() if length == 0 else Vec2(self.x / length, self.y / length)


@dataclass(slots=True)
class Vec3:
    x: float = 0.0
    y: float = 0.0
    z: float = 0.0

    def __add__(self, other: Vec3) -> Vec3:
        return Vec3(self.x + other.x, self.y + other.y, self.z + other.z)

    def __sub__(self, other: Vec3) -> Vec3:
        return Vec3(self.x - other.x, self.y - other.y, self.z - other.z)

    def __mul__(self, scalar: float) -> Vec3:
        return Vec3(self.x * scalar, self.y * scalar, self.z * scalar)

    __rmul__ = __mul__

    @property
    def length(self) -> float:
        return math.sqrt(self.x * self.x + self.y * self.y + self.z * self.z)

    def normalized(self) -> Vec3:
        length = self.length
        return Vec3() if length == 0 else Vec3(self.x / length, self.y / length, self.z / length)


@dataclass(slots=True, frozen=True)
class Color:
    r: float = 1.0
    g: float = 1.0
    b: float = 1.0
    a: float = 1.0

    def clamped(self) -> Color:
        def clamp(value: float) -> float:
            return max(0.0, min(1.0, float(value)))

        return Color(clamp(self.r), clamp(self.g), clamp(self.b), clamp(self.a))


@dataclass(slots=True)
class Transform:
    position: Vec3 = field(default_factory=Vec3)
    rotation: Vec3 = field(default_factory=Vec3)
    scale: Vec3 = field(default_factory=lambda: Vec3(1.0, 1.0, 1.0))

    def matrix(self) -> np.ndarray:
        px, py, pz = self.position.x, self.position.y, self.position.z
        sx, sy, sz = self.scale.x, self.scale.y, self.scale.z
        rx, ry, rz = map(math.radians, (self.rotation.x, self.rotation.y, self.rotation.z))

        cx, sxn = math.cos(rx), math.sin(rx)
        cy, syn = math.cos(ry), math.sin(ry)
        cz, szn = math.cos(rz), math.sin(rz)

        rxm = np.array(
            [[1, 0, 0, 0], [0, cx, -sxn, 0], [0, sxn, cx, 0], [0, 0, 0, 1]],
            dtype="f4",
        )
        rym = np.array(
            [[cy, 0, syn, 0], [0, 1, 0, 0], [-syn, 0, cy, 0], [0, 0, 0, 1]],
            dtype="f4",
        )
        rzm = np.array(
            [[cz, -szn, 0, 0], [szn, cz, 0, 0], [0, 0, 1, 0], [0, 0, 0, 1]],
            dtype="f4",
        )
        sm = np.diag([sx, sy, sz, 1.0]).astype("f4")
        tm = np.eye(4, dtype="f4")
        tm[:3, 3] = [px, py, pz]
        return tm @ rzm @ rym @ rxm @ sm


def perspective(fov_deg: float, aspect: float, near: float, far: float) -> np.ndarray:
    f = 1.0 / math.tan(math.radians(fov_deg) / 2.0)
    out = np.zeros((4, 4), dtype="f4")
    out[0, 0] = f / aspect
    out[1, 1] = f
    out[2, 2] = (far + near) / (near - far)
    out[2, 3] = (2 * far * near) / (near - far)
    out[3, 2] = -1.0
    return out


def orthographic(width: float, height: float) -> np.ndarray:
    out = np.eye(4, dtype="f4")
    out[0, 0] = 2.0 / width
    out[1, 1] = 2.0 / height
    return out
