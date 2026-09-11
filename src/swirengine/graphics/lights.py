from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field

from ..math.types import Color, Vec3

MAX_DIRECTIONAL_LIGHTS = 4
MAX_POINT_LIGHTS = 4
MAX_SPOT_LIGHTS = 4


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


@dataclass(frozen=True, slots=True)
class LightSelection3D:
    """Active lights selected for one forward-rendering pass."""

    directional: tuple[DirectionalLight3D, ...] = ()
    point: tuple[PointLight3D, ...] = ()
    spot: tuple[SpotLight3D, ...] = ()
    dropped_directional: int = 0
    dropped_point: int = 0
    dropped_spot: int = 0

    @property
    def dropped(self) -> int:
        return self.dropped_directional + self.dropped_point + self.dropped_spot

    @property
    def total(self) -> int:
        return len(self.directional) + len(self.point) + len(self.spot)


def select_lights(
    objects: Iterable[object],
    *,
    max_directional: int = MAX_DIRECTIONAL_LIGHTS,
    max_point: int = MAX_POINT_LIGHTS,
    max_spot: int = MAX_SPOT_LIGHTS,
    default_directional: bool = True,
) -> LightSelection3D:
    """Select visible lights in scene order and report lights beyond GPU budgets."""

    limits = (int(max_directional), int(max_point), int(max_spot))
    if any(limit < 0 for limit in limits):
        raise ValueError("light limits cannot be negative")

    directional: list[DirectionalLight3D] = []
    point: list[PointLight3D] = []
    spot: list[SpotLight3D] = []
    dropped_directional = dropped_point = dropped_spot = 0
    active_user_lights = 0

    for obj in objects:
        if not getattr(obj, "enabled", True) or not getattr(obj, "visible", True):
            continue
        if isinstance(obj, DirectionalLight3D):
            active_user_lights += 1
            if len(directional) < limits[0]:
                directional.append(obj)
            else:
                dropped_directional += 1
        elif isinstance(obj, PointLight3D):
            active_user_lights += 1
            if len(point) < limits[1]:
                point.append(obj)
            else:
                dropped_point += 1
        elif isinstance(obj, SpotLight3D):
            active_user_lights += 1
            if len(spot) < limits[2]:
                spot.append(obj)
            else:
                dropped_spot += 1

    if active_user_lights == 0 and default_directional and limits[0] > 0:
        directional.append(DirectionalLight3D())

    return LightSelection3D(
        directional=tuple(directional),
        point=tuple(point),
        spot=tuple(spot),
        dropped_directional=dropped_directional,
        dropped_point=dropped_point,
        dropped_spot=dropped_spot,
    )
