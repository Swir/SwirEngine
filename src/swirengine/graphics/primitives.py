from __future__ import annotations

from dataclasses import dataclass, field
from ..math.types import Color, Vec3, Transform


@dataclass(slots=True)
class Rectangle2D:
    x: float
    y: float
    width: float
    height: float
    color: Color = field(default_factory=Color)
    rotation: float = 0.0
    enabled: bool = True

    def update(self, dt: float) -> None:
        pass


@dataclass(slots=True)
class Cube3D:
    position: Vec3 = field(default_factory=Vec3)
    size: float = 1.0
    color: Color = field(default_factory=Color)
    rotation: Vec3 = field(default_factory=Vec3)
    enabled: bool = True

    @property
    def transform(self) -> Transform:
        return Transform(position=self.position, rotation=self.rotation, scale=Vec3(self.size, self.size, self.size))

    def update(self, dt: float) -> None:
        pass
