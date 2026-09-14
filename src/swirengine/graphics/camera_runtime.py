from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Sequence

from ..math.types import Vec2, Vec3
from .camera import Camera2D
from .camera3d import Camera3D


def _smooth_alpha(speed: float, dt: float) -> float:
    if dt <= 0.0 or speed <= 0.0:
        return 0.0
    return 1.0 - math.exp(-float(speed) * float(dt))


def _clamp(value: float, minimum: float, maximum: float) -> float:
    if minimum > maximum:
        minimum, maximum = maximum, minimum
    return max(minimum, min(maximum, value))


@dataclass(slots=True, frozen=True)
class CameraBounds2D:
    min_x: float
    min_y: float
    max_x: float
    max_y: float

    def clamp(self, point: Vec2) -> Vec2:
        return Vec2(
            _clamp(point.x, self.min_x, self.max_x),
            _clamp(point.y, self.min_y, self.max_y),
        )


@dataclass(slots=True, frozen=True)
class CameraBounds3D:
    minimum: Vec3
    maximum: Vec3

    def clamp(self, point: Vec3) -> Vec3:
        return Vec3(
            _clamp(point.x, self.minimum.x, self.maximum.x),
            _clamp(point.y, self.minimum.y, self.maximum.y),
            _clamp(point.z, self.minimum.z, self.maximum.z),
        )


@dataclass(slots=True, frozen=True)
class CameraRail2D:
    points: tuple[Vec2, ...]

    def __init__(self, points: Sequence[Vec2]) -> None:
        if len(points) < 2:
            raise ValueError("CameraRail2D requires at least two points")
        object.__setattr__(self, "points", tuple(Vec2(p.x, p.y) for p in points))

    def sample(self, progress: float) -> Vec2:
        scaled = _clamp(float(progress), 0.0, 1.0) * (len(self.points) - 1)
        index = min(int(scaled), len(self.points) - 2)
        local = scaled - index
        a, b = self.points[index], self.points[index + 1]
        return Vec2(a.x + (b.x - a.x) * local, a.y + (b.y - a.y) * local)


@dataclass(slots=True, frozen=True)
class CameraRail3D:
    points: tuple[Vec3, ...]

    def __init__(self, points: Sequence[Vec3]) -> None:
        if len(points) < 2:
            raise ValueError("CameraRail3D requires at least two points")
        object.__setattr__(self, "points", tuple(Vec3(p.x, p.y, p.z) for p in points))

    def sample(self, progress: float) -> Vec3:
        scaled = _clamp(float(progress), 0.0, 1.0) * (len(self.points) - 1)
        index = min(int(scaled), len(self.points) - 2)
        local = scaled - index
        a, b = self.points[index], self.points[index + 1]
        return Vec3(
            a.x + (b.x - a.x) * local,
            a.y + (b.y - a.y) * local,
            a.z + (b.z - a.z) * local,
        )


@dataclass(slots=True)
class _ShakeState:
    amplitude: float = 0.0
    frequency: float = 18.0
    remaining: float = 0.0
    elapsed: float = 0.0
    seed: float = 0.0

    def start(self, amplitude: float, duration: float, frequency: float, seed: float) -> None:
        self.amplitude = max(0.0, float(amplitude))
        self.frequency = max(0.001, float(frequency))
        self.remaining = max(0.0, float(duration))
        self.elapsed = 0.0
        self.seed = float(seed)

    def sample2(self, dt: float) -> Vec2:
        if self.remaining <= 0.0 or self.amplitude <= 0.0:
            return Vec2()
        step = max(0.0, float(dt))
        self.elapsed += step
        self.remaining = max(0.0, self.remaining - step)
        envelope = self.remaining / max(self.remaining + self.elapsed, 1e-9)
        phase = self.elapsed * self.frequency * math.tau + self.seed
        return Vec2(
            math.sin(phase) * self.amplitude * envelope,
            math.sin(phase * 1.61803398875 + 1.7) * self.amplitude * envelope,
        )

    def sample3(self, dt: float) -> Vec3:
        xy = self.sample2(dt)
        if self.amplitude <= 0.0:
            return Vec3()
        phase = self.elapsed * self.frequency * math.tau + self.seed
        envelope = self.remaining / max(self.remaining + self.elapsed, 1e-9)
        return Vec3(
            xy.x,
            xy.y,
            math.sin(phase * 0.754877666 + 2.3) * self.amplitude * envelope,
        )


@dataclass(slots=True)
class CameraRig2D:
    camera: Camera2D
    smoothing: float = 10.0
    dead_zone: Vec2 = field(default_factory=Vec2)
    bounds: CameraBounds2D | None = None
    _logical: Vec2 = field(init=False)
    _shake: _ShakeState = field(default_factory=_ShakeState, init=False)

    def __post_init__(self) -> None:
        self._logical = Vec2(float(self.camera.x), float(self.camera.y))

    def snap_to(self, target: Vec2) -> CameraRig2D:
        self._logical = self._bounded(target)
        self._apply(Vec2())
        return self

    def follow(self, target: Vec2, dt: float) -> CameraRig2D:
        desired = Vec2(float(target.x), float(target.y))
        dx = desired.x - self._logical.x
        dy = desired.y - self._logical.y
        half_x = max(0.0, self.dead_zone.x) * 0.5
        half_y = max(0.0, self.dead_zone.y) * 0.5
        if abs(dx) <= half_x:
            desired.x = self._logical.x
        else:
            desired.x -= math.copysign(half_x, dx)
        if abs(dy) <= half_y:
            desired.y = self._logical.y
        else:
            desired.y -= math.copysign(half_y, dy)
        alpha = _smooth_alpha(self.smoothing, dt)
        self._logical = self._bounded(
            Vec2(
                self._logical.x + (desired.x - self._logical.x) * alpha,
                self._logical.y + (desired.y - self._logical.y) * alpha,
            )
        )
        self._apply(self._shake.sample2(dt))
        return self

    def move_on_rail(self, rail: CameraRail2D, progress: float, dt: float = 0.0) -> CameraRig2D:
        desired = self._bounded(rail.sample(progress))
        alpha = 1.0 if self.smoothing <= 0.0 else _smooth_alpha(self.smoothing, dt)
        self._logical = Vec2(
            self._logical.x + (desired.x - self._logical.x) * alpha,
            self._logical.y + (desired.y - self._logical.y) * alpha,
        )
        self._apply(self._shake.sample2(dt))
        return self

    def shake(
        self,
        amplitude: float,
        duration: float,
        *,
        frequency: float = 18.0,
        seed: float = 0.0,
    ) -> CameraRig2D:
        self._shake.start(amplitude, duration, frequency, seed)
        return self

    def _bounded(self, point: Vec2) -> Vec2:
        return self.bounds.clamp(point) if self.bounds is not None else point

    def _apply(self, offset: Vec2) -> None:
        self.camera.x = self._logical.x + offset.x
        self.camera.y = self._logical.y + offset.y


@dataclass(slots=True)
class CameraRig3D:
    camera: Camera3D
    smoothing: float = 10.0
    bounds: CameraBounds3D | None = None
    _logical: Vec3 = field(init=False)
    _target_offset: Vec3 = field(init=False)
    _shake: _ShakeState = field(default_factory=_ShakeState, init=False)

    def __post_init__(self) -> None:
        self._logical = Vec3(self.camera.position.x, self.camera.position.y, self.camera.position.z)
        self._target_offset = self.camera.target - self.camera.position

    def snap_to(self, position: Vec3) -> CameraRig3D:
        self._logical = self._bounded(position)
        self._apply(Vec3())
        return self

    def follow(self, position: Vec3, dt: float) -> CameraRig3D:
        desired = self._bounded(position)
        alpha = _smooth_alpha(self.smoothing, dt)
        self._logical = Vec3(
            self._logical.x + (desired.x - self._logical.x) * alpha,
            self._logical.y + (desired.y - self._logical.y) * alpha,
            self._logical.z + (desired.z - self._logical.z) * alpha,
        )
        self._apply(self._shake.sample3(dt))
        return self

    def move_on_rail(self, rail: CameraRail3D, progress: float, dt: float = 0.0) -> CameraRig3D:
        desired = self._bounded(rail.sample(progress))
        alpha = 1.0 if self.smoothing <= 0.0 else _smooth_alpha(self.smoothing, dt)
        self._logical = Vec3(
            self._logical.x + (desired.x - self._logical.x) * alpha,
            self._logical.y + (desired.y - self._logical.y) * alpha,
            self._logical.z + (desired.z - self._logical.z) * alpha,
        )
        self._apply(self._shake.sample3(dt))
        return self

    def shake(
        self,
        amplitude: float,
        duration: float,
        *,
        frequency: float = 18.0,
        seed: float = 0.0,
    ) -> CameraRig3D:
        self._shake.start(amplitude, duration, frequency, seed)
        return self

    def _bounded(self, point: Vec3) -> Vec3:
        return self.bounds.clamp(point) if self.bounds is not None else point

    def _apply(self, offset: Vec3) -> None:
        base = self._logical + offset
        self.camera.position = base
        self.camera.target = base + self._target_offset
