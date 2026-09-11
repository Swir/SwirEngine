from __future__ import annotations

from dataclasses import dataclass, field

from ..math.types import Color, Vec3


def _positive(value: float, name: str) -> float:
    value = float(value)
    if value <= 0.0:
        raise ValueError(f"{name} must be greater than 0")
    return value


def _direction(value: Vec3, name: str = "direction") -> Vec3:
    if value.length == 0.0:
        raise ValueError(f"{name} cannot be zero")
    return value.normalized()


@dataclass(slots=True)
class DirectionalLight3D:
    """Infinite directional light for sun/moon-style lighting."""

    direction: Vec3 = field(default_factory=lambda: Vec3(-0.4, -0.8, -0.6))
    color: Color = field(default_factory=Color)
    intensity: float = 1.0
    enabled: bool = True
    visible: bool = True
    name: str = ""
    tags: set[str] = field(default_factory=set)

    def __post_init__(self) -> None:
        self.direction = _direction(self.direction)
        self.intensity = max(0.0, float(self.intensity))

    def update(self, dt: float) -> None:
        pass


@dataclass(slots=True)
class PointLight3D:
    """Omnidirectional light with distance attenuation."""

    position: Vec3 = field(default_factory=Vec3)
    color: Color = field(default_factory=Color)
    intensity: float = 1.0
    range: float = 10.0
    enabled: bool = True
    visible: bool = True
    name: str = ""
    tags: set[str] = field(default_factory=set)

    def __post_init__(self) -> None:
        self.intensity = max(0.0, float(self.intensity))
        self.range = _positive(self.range, "range")

    def update(self, dt: float) -> None:
        pass


@dataclass(slots=True)
class SpotLight3D:
    """Cone light with smooth inner/outer cutoff and distance attenuation."""

    position: Vec3 = field(default_factory=Vec3)
    direction: Vec3 = field(default_factory=lambda: Vec3(0.0, -1.0, 0.0))
    color: Color = field(default_factory=Color)
    intensity: float = 1.0
    range: float = 12.0
    inner_angle: float = 20.0
    outer_angle: float = 30.0
    enabled: bool = True
    visible: bool = True
    name: str = ""
    tags: set[str] = field(default_factory=set)

    def __post_init__(self) -> None:
        self.direction = _direction(self.direction)
        self.intensity = max(0.0, float(self.intensity))
        self.range = _positive(self.range, "range")
        self.inner_angle = float(self.inner_angle)
        self.outer_angle = float(self.outer_angle)
        if not 0.0 <= self.inner_angle < self.outer_angle < 90.0:
            raise ValueError("spot angles must satisfy 0 <= inner_angle < outer_angle < 90")

    def update(self, dt: float) -> None:
        pass
