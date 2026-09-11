from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from ..math.types import Color, Transform, Vec3


@dataclass(slots=True)
class Rectangle2D:
    x: float
    y: float
    width: float
    height: float
    color: Color = field(default_factory=Color)
    rotation: float = 0.0
    enabled: bool = True
    visible: bool = True
    name: str = ""
    tags: set[str] = field(default_factory=set)

    def update(self, dt: float) -> None:
        pass


@dataclass(slots=True)
class Sprite2D:
    texture: str | Path
    x: float = 0.0
    y: float = 0.0
    width: float | None = None
    height: float | None = None
    tint: Color = field(default_factory=Color)
    rotation: float = 0.0
    enabled: bool = True
    visible: bool = True
    name: str = ""
    tags: set[str] = field(default_factory=set)

    def update(self, dt: float) -> None:
        pass


@dataclass(slots=True)
class Cube3D:
    position: Vec3 = field(default_factory=Vec3)
    size: float = 1.0
    color: Color = field(default_factory=Color)
    rotation: Vec3 = field(default_factory=Vec3)
    enabled: bool = True
    visible: bool = True
    name: str = ""
    tags: set[str] = field(default_factory=set)

    @property
    def transform(self) -> Transform:
        return Transform(
            position=self.position,
            rotation=self.rotation,
            scale=Vec3(self.size, self.size, self.size),
        )

    def update(self, dt: float) -> None:
        pass
