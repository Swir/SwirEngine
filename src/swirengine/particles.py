from __future__ import annotations

import math
import random
from dataclasses import dataclass

from .graphics.primitives import Rectangle2D
from .math.types import Color


@dataclass(slots=True)
class _Particle:
    visual: Rectangle2D
    velocity_x: float = 0.0
    velocity_y: float = 0.0
    age: float = 0.0
    lifetime: float = 1.0
    start_alpha: float = 1.0

    @property
    def alive(self) -> bool:
        return self.visual.visible


class ParticleEmitter2D:
    """Pooled 2D particle emitter using renderer-native rectangles."""

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
    ) -> None:
        if max_particles <= 0:
            raise ValueError("max_particles must be greater than zero")
        if rate < 0:
            raise ValueError("rate must be non-negative")
        if min(lifetime) <= 0:
            raise ValueError("particle lifetime must be greater than zero")
        if min(size) < 0:
            raise ValueError("particle size must be non-negative")

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
        self.layer = int(layer)
        self.emitting = bool(emitting)
        self.enabled = True
        self.visible = False
        self._random = random.Random(seed)
        self._emit_accumulator = 0.0
        self._cursor = 0
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

    @property
    def children(self) -> tuple[Rectangle2D, ...]:
        return tuple(p.visual for p in self._particles)

    @property
    def alive_count(self) -> int:
        return sum(p.alive for p in self._particles)

    def _range(self, values: tuple[float, float]) -> float:
        low, high = sorted(values)
        return self._random.uniform(low, high)

    def emit(self, count: int = 1) -> int:
        spawned = 0
        for _ in range(max(0, int(count))):
            particle = self._particles[self._cursor]
            self._cursor = (self._cursor + 1) % self.max_particles
            angle = math.radians(self._range(self.angle))
            speed = self._range(self.speed)
            size = self._range(self.size)
            particle.visual.x = self.x
            particle.visual.y = self.y
            particle.visual.width = size
            particle.visual.height = size
            particle.visual.color = self.color
            particle.visual.visible = True
            particle.velocity_x = math.cos(angle) * speed
            particle.velocity_y = math.sin(angle) * speed
            particle.age = 0.0
            particle.lifetime = self._range(self.lifetime)
            particle.start_alpha = self.color.a
            spawned += 1
        return spawned

    burst = emit

    def clear(self) -> None:
        for particle in self._particles:
            particle.visual.visible = False
            particle.age = 0.0
        self._emit_accumulator = 0.0

    def update(self, dt: float) -> None:
        if not self.enabled or dt <= 0:
            return
        if self.emitting and self.rate > 0:
            self._emit_accumulator += dt * self.rate
            count = int(self._emit_accumulator)
            if count:
                self.emit(count)
                self._emit_accumulator -= count

        gx, gy = self.gravity
        for particle in self._particles:
            if not particle.alive:
                continue
            particle.age += dt
            if particle.age >= particle.lifetime:
                particle.visual.visible = False
                continue
            particle.velocity_x += gx * dt
            particle.velocity_y += gy * dt
            particle.visual.x += particle.velocity_x * dt
            particle.visual.y += particle.velocity_y * dt
            fade = max(0.0, 1.0 - particle.age / particle.lifetime)
            c = self.color
            particle.visual.color = Color(c.r, c.g, c.b, particle.start_alpha * fade)
