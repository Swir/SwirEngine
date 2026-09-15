from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from ..math.types import Color, Transform, Vec3

UVRect = tuple[float, float, float, float]


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
    layer: int = 0
    screen_space: bool = False

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
    layer: int = 0
    uv_rect: UVRect = (0.0, 0.0, 1.0, 1.0)
    screen_space: bool = False
    _render_owner_id: int | None = field(default=None, init=False, repr=False, compare=False)

    @property
    def render_managed(self) -> bool:
        """Whether a parent render source owns submission for this sprite."""
        return self._render_owner_id is not None

    def update(self, dt: float) -> None:
        pass


@dataclass(slots=True)
class Text2D:
    text: str
    x: float = 0.0
    y: float = 0.0
    color: Color = field(default_factory=Color)
    font_size: int = 24
    font: str | Path | None = None
    scale: float = 1.0
    enabled: bool = True
    visible: bool = True
    name: str = ""
    tags: set[str] = field(default_factory=set)
    layer: int = 0
    screen_space: bool = False

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
