from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from enum import Enum

from .graphics.primitives import Rectangle2D
from .math.types import Color


class ParticleEmissionShape2D(str, Enum):
    """Built-in spawn regions for :class:`ParticleEmitter2D`."""

    POINT = "point"
    BOX = "box"
    CIRCLE = "circle"
    RING = "ring"


@dataclass(slots=True, frozen=True)
class ParticleDiagnostics:
    """Low-cost runtime counters for particle tuning and regression tests."""

    alive: int
    capacity: int
    emitted_total: int
    recycled_total: int
    update_visits: int
    last_spawned: int


@dataclass(slots=True)
class _Particle:
    visual: Rectangle2D
    velocity_x: float = 0.0
    velocity_y: float = 0.0
    angular_velocity: float = 0.0
    age: float = 0.0
    lifetime: float = 1.0
    start_size: float = 0.0
    start_color: Color = field(default_factory=Color)

    @property
    def alive(self) -> bool:
        return self.visual.visible


class ParticleEmitter2D:
    """Pooled, allocation-conscious 2D particle/VFX emitter.

    The original 1.x constructor remains source compatible. The expanded runtime adds
    spawn shapes, color/size-over-life, drag, angular motion and diagnostics while
    updating only active particles instead of scanning the full pool every frame.
    """

    def __init__(
        self,
        x: float = 0.0,
        y: float = 0.0,
        *,
        max_particles: int = 128,
        rate: float = 20.0,
        lifetime: tuple[float, float] = (0.5, 1.0),
        speed: tuple[float, float] = (40.0, 120.0),
        angle: tuple[float, float] = (0.0, 360.0),
        size: tuple[float, float] = (3.0, 8.0),
        gravity: tuple[float, float] = (0.0, -80.0),
        color: Color | None = None,
        layer: int = 0,
        emitting: bool = True,
        seed: int | None = None,
        emission_shape: ParticleEmissionShape2D | str = ParticleEmissionShape2D.POINT,
        emission_size: tuple[float, float] = (0.0, 0.0),
        end_color: Color | None = None,
        end_size_scale: float = 1.0,
        drag: float = 0.0,
        rotation: tuple[float, float] = (0.0, 0.0),
        angular_velocity: tuple[float, float] = (0.0, 0.0),
    ) -> None:
        if max_particles <= 0:
            raise ValueError("max_particles must be greater than zero")
        if rate < 0:
            raise ValueError("rate must be non-negative")
        if min(lifetime) <= 0:
            raise ValueError("particle lifetime must be greater than zero")
        if min(size) < 0:
            raise ValueError("particle size must be non-negative")
        if min(emission_size) < 0:
            raise ValueError("emission_size must be non-negative")
        if end_size_scale < 0:
            raise ValueError("end_size_scale must be non-negative")
        if drag < 0:
            raise ValueError("drag must be non-negative")

        self.x = float(x)
        self.y = float(y)
        self.max_particles = int(max_particles)
        self.rate = float(rate)
        self.lifetime = tuple(map(float, lifetime))
        self.speed = tuple(map(float, speed))
        self.angle = tuple(map(float, angle))
        self.size = tuple(map(float, size))
        self.gravity = (float(gravity[0]), float(gravity[1]))
        self.color = (color or Color()).clamped()
        self.end_color = (
            end_color or Color(self.color.r, self.color.g, self.color.b, 0.0)
        ).clamped()
        self.end_size_scale = float(end_size_scale)
        self.drag = float(drag)
        self.rotation = tuple(map(float, rotation))
        self.angular_velocity = tuple(map(float, angular_velocity))
        self.emission_shape = ParticleEmissionShape2D(emission_shape)
        self.emission_size = (float(emission_size[0]), float(emission_size[1]))
        self.layer = int(layer)
        self.emitting = bool(emitting)
        self.enabled = True
        self.visible = False

        self._random = random.Random(seed)
        self._emit_accumulator = 0.0
        self._cursor = 0
        self._alive_count = 0
        self._active: list[int] = []
        self._emitted_total = 0
        self._recycled_total = 0
        self._update_visits = 0
        self._last_spawned = 0
        self._particles = [
            _Particle(
                Rectangle2D(
                    self.x,
                    self.y,
                    0.0,
                    0.0,
                    color=self.color,
                    visible=False,
                    layer=self.layer,
                )
            )
            for _ in range(self.max_particles)
        ]
        self._children = tuple(p.visual for p in self._particles)

    @property
    def children(self) -> tuple[Rectangle2D, ...]:
        """Renderer children without allocating a new tuple every access."""

        return self._children

    @property
    def alive_count(self) -> int:
        return self._alive_count

    @property
    def diagnostics(self) -> ParticleDiagnostics:
        return ParticleDiagnostics(
            alive=self._alive_count,
            capacity=self.max_particles,
            emitted_total=self._emitted_total,
            recycled_total=self._recycled_total,
            update_visits=self._update_visits,
            last_spawned=self._last_spawned,
        )

    def _range(self, values: tuple[float, float]) -> float:
        """Sample a two-value range without allocating a sorted list per particle property."""
        first, second = values
        low, high = (first, second) if first <= second else (second, first)
        return self._random.uniform(low, high)

    def _spawn_offset(self) -> tuple[float, float]:
        width, height = self.emission_size
        shape = self.emission_shape
        is_point = shape is ParticleEmissionShape2D.POINT
        if is_point or (width == 0.0 and height == 0.0):
            return 0.0, 0.0
        if shape is ParticleEmissionShape2D.BOX:
            return self._random.uniform(-width * 0.5, width * 0.5), self._random.uniform(
                -height * 0.5,
                height * 0.5,
            )

        radius_x = width * 0.5
        radius_y = height * 0.5 if height > 0.0 else radius_x
        theta = self._random.random() * math.tau
        if shape is ParticleEmissionShape2D.RING:
            radius = 1.0
        else:
            radius = math.sqrt(self._random.random())
        return math.cos(theta) * radius_x * radius, math.sin(theta) * radius_y * radius

    @staticmethod
    def _lerp(start: float, end: float, t: float) -> float:
        return start + (end - start) * t

    def emit(self, count: int = 1) -> int:
        spawned = 0
        for _ in range(max(0, int(count))):
            index = self._cursor
            particle = self._particles[index]
            self._cursor = (self._cursor + 1) % self.max_particles
            was_alive = particle.alive

            offset_x, offset_y = self._spawn_offset()
            angle = math.radians(self._range(self.angle))
            speed = self._range(self.speed)
            size = self._range(self.size)
            particle.visual.x = self.x + offset_x
            particle.visual.y = self.y + offset_y
            particle.visual.width = size
            particle.visual.height = size
            particle.visual.color = self.color
            particle.visual.rotation = self._range(self.rotation)
            particle.visual.visible = True
            particle.velocity_x = math.cos(angle) * speed
            particle.velocity_y = math.sin(angle) * speed
            particle.angular_velocity = self._range(self.angular_velocity)
            particle.age = 0.0
            particle.lifetime = self._range(self.lifetime)
            particle.start_size = size
            particle.start_color = self.color

            if was_alive:
                self._recycled_total += 1
            else:
                self._active.append(index)
                self._alive_count += 1
            spawned += 1

        self._last_spawned = spawned
        self._emitted_total += spawned
        return spawned

    burst = emit

    def clear(self) -> None:
        for index in self._active:
            particle = self._particles[index]
            particle.visual.visible = False
            particle.age = 0.0
        self._active.clear()
        self._alive_count = 0
        self._emit_accumulator = 0.0
        self._update_visits = 0
        self._last_spawned = 0

    def update(self, dt: float) -> None:
        self._update_visits = 0
        if not self.enabled or dt <= 0:
            self._last_spawned = 0
            return

        spawned = 0
        if self.emitting and self.rate > 0:
            self._emit_accumulator += dt * self.rate
            count = int(self._emit_accumulator)
            if count:
                spawned = self.emit(count)
                self._emit_accumulator -= count
        if not spawned:
            self._last_spawned = 0

        gx, gy = self.gravity
        damping = max(0.0, 1.0 - self.drag * dt)
        i = 0
        while i < len(self._active):
            index = self._active[i]
            particle = self._particles[index]
            self._update_visits += 1
            particle.age += dt
            if particle.age >= particle.lifetime:
                particle.visual.visible = False
                self._alive_count -= 1
                self._active[i] = self._active[-1]
                self._active.pop()
                continue

            particle.velocity_x = (particle.velocity_x + gx * dt) * damping
            particle.velocity_y = (particle.velocity_y + gy * dt) * damping
            particle.visual.x += particle.velocity_x * dt
            particle.visual.y += particle.velocity_y * dt
            particle.visual.rotation += particle.angular_velocity * dt

            t = max(0.0, min(1.0, particle.age / particle.lifetime))
            start = particle.start_color
            end = self.end_color
            particle.visual.color = Color(
                self._lerp(start.r, end.r, t),
                self._lerp(start.g, end.g, t),
                self._lerp(start.b, end.b, t),
                self._lerp(start.a, end.a, t),
            )
            scale = self._lerp(1.0, self.end_size_scale, t)
            current_size = particle.start_size * scale
            particle.visual.width = current_size
            particle.visual.height = current_size
            i += 1
