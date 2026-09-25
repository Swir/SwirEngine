from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any


class EditorVFXError22(ValueError):
    """Raised when project VFX data cannot be authored safely and deterministically."""


@dataclass(frozen=True, slots=True)
class VFXEffectSpec22:
    name: str
    backend: str = "cpu2d"
    capacity: int = 128
    rate: float = 20.0
    lifetime: tuple[float, float] = (0.5, 1.0)
    speed: tuple[float, float] = (40.0, 120.0)
    angle: tuple[float, float] = (0.0, 360.0)
    size: tuple[float, float] = (3.0, 8.0)
    gravity: tuple[float, float, float] = (0.0, -80.0, 0.0)
    start_color: tuple[float, float, float, float] = (1.0, 1.0, 1.0, 1.0)
    end_color: tuple[float, float, float, float] = (1.0, 1.0, 1.0, 0.0)
    end_size_scale: float = 1.0
    drag: float = 0.0
    emission_shape: str = "point"
    emission_extent: tuple[float, float, float] = (0.0, 0.0, 0.0)
    velocity_min: tuple[float, float, float] = (-1.5, 1.0, -1.5)
    velocity_max: tuple[float, float, float] = (1.5, 5.0, 1.5)
    blend_mode: str = "additive"
    render_mode: str = "sprite"
    emissive_strength: float = 1.0
    texture: str | None = None
    trail_enabled: bool = False
    trail_alpha_scale: float = 0.45
    seed: int = 1

    def __post_init__(self) -> None:
        object.__setattr__(self, "name", _name(self.name))
        backend = str(self.backend).strip().lower()
        if backend not in {"cpu2d", "gpu3d"}:
            raise EditorVFXError22("backend must be cpu2d or gpu3d")
        object.__setattr__(self, "backend", backend)
        object.__setattr__(self, "capacity", _positive_int(self.capacity, "capacity"))
        object.__setattr__(self, "rate", _non_negative(self.rate, "rate"))
        object.__setattr__(self, "lifetime", _positive_pair(self.lifetime, "lifetime"))
        object.__setattr__(self, "speed", _pair(self.speed, "speed"))
        object.__setattr__(self, "angle", _pair(self.angle, "angle"))
        object.__setattr__(self, "size", _non_negative_pair(self.size, "size"))
        object.__setattr__(self, "gravity", _triplet(self.gravity, "gravity"))
        object.__setattr__(self, "start_color", _color(self.start_color, "start_color"))
        object.__setattr__(self, "end_color", _color(self.end_color, "end_color"))
        object.__setattr__(self, "end_size_scale", _non_negative(self.end_size_scale, "end_size_scale"))
        object.__setattr__(self, "drag", _non_negative(self.drag, "drag"))
        shape = str(self.emission_shape).strip().lower()
        allowed = {"point", "box", "circle", "ring"} if backend == "cpu2d" else {"point", "box", "sphere"}
        if shape not in allowed:
            raise EditorVFXError22(f"unsupported {backend} emission shape: {shape}")
        object.__setattr__(self, "emission_shape", shape)
        object.__setattr__(self, "emission_extent", _non_negative_triplet(self.emission_extent, "emission_extent"))
        object.__setattr__(self, "velocity_min", _triplet(self.velocity_min, "velocity_min"))
        object.__setattr__(self, "velocity_max", _triplet(self.velocity_max, "velocity_max"))
        if self.blend_mode not in {"alpha", "additive"}:
            raise EditorVFXError22("blend_mode must be alpha or additive")
        if self.render_mode not in {"sprite", "mesh"}:
            raise EditorVFXError22("render_mode must be sprite or mesh")
        object.__setattr__(self, "emissive_strength", _non_negative(self.emissive_strength, "emissive_strength"))
        object.__setattr__(self, "texture", None if self.texture is None else project_asset_path(self.texture))
        object.__setattr__(self, "trail_enabled", bool(self.trail_enabled))
        object.__setattr__(self, "trail_alpha_scale", _unit(self.trail_alpha_scale, "trail_alpha_scale"))
        object.__setattr__(self, "seed", int(self.seed))


def project_relative_path(value: Any, label: str) -> str:
    raw = str(value).strip()
    posix = PurePosixPath(raw.replace("\\", "/"))
    windows = PureWindowsPath(raw)
    if not raw or posix.is_absolute() or windows.is_absolute() or bool(windows.drive) or ".." in posix.parts:
        raise EditorVFXError22(f"{label} must stay project-relative")
    return posix.as_posix()


def project_asset_path(value: Any) -> str:
    return project_relative_path(value, "texture")


def safe_target(root: Path, relative: str, label: str) -> Path:
    target = (root / PurePosixPath(relative)).resolve()
    try:
        target.relative_to(root)
    except ValueError as exc:
        raise EditorVFXError22(f"{label} escapes the project") from exc
    return target


def _name(value: Any) -> str:
    if not isinstance(value, str):
        raise TypeError("VFX effect name must be a string")
    clean = value.strip()
    if not clean or len(clean) > 96 or "/" in clean or "\\" in clean or "\x00" in clean:
        raise EditorVFXError22("VFX effect name must be a portable 1-96 character label")
    return clean


def _finite(value: Any, label: str) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise EditorVFXError22(f"{label} must be numeric") from exc
    if not math.isfinite(result):
        raise EditorVFXError22(f"{label} must be finite")
    return result


def _non_negative(value: Any, label: str) -> float:
    result = _finite(value, label)
    if result < 0:
        raise EditorVFXError22(f"{label} must be non-negative")
    return result


def _unit(value: Any, label: str) -> float:
    result = _finite(value, label)
    if not 0 <= result <= 1:
        raise EditorVFXError22(f"{label} must be within 0..1")
    return result


def _positive_int(value: Any, label: str) -> int:
    result = int(value)
    if result <= 0:
        raise EditorVFXError22(f"{label} must be greater than zero")
    return result


def _values(value: Any, length: int, label: str) -> tuple[float, ...]:
    try:
        values = tuple(_finite(item, label) for item in value)
    except TypeError as exc:
        raise EditorVFXError22(f"{label} must contain {length} values") from exc
    if len(values) != length:
        raise EditorVFXError22(f"{label} must contain {length} values")
    return values


def _pair(value: Any, label: str) -> tuple[float, float]:
    return _values(value, 2, label)  # type: ignore[return-value]


def _positive_pair(value: Any, label: str) -> tuple[float, float]:
    values = _pair(value, label)
    if min(values) <= 0:
        raise EditorVFXError22(f"{label} values must be greater than zero")
    return values


def _non_negative_pair(value: Any, label: str) -> tuple[float, float]:
    values = _pair(value, label)
    if min(values) < 0:
        raise EditorVFXError22(f"{label} values must be non-negative")
    return values


def _triplet(value: Any, label: str) -> tuple[float, float, float]:
    return _values(value, 3, label)  # type: ignore[return-value]


def _non_negative_triplet(value: Any, label: str) -> tuple[float, float, float]:
    values = _triplet(value, label)
    if min(values) < 0:
        raise EditorVFXError22(f"{label} values must be non-negative")
    return values


def _color(value: Any, label: str) -> tuple[float, float, float, float]:
    values = _values(value, 4, label)
    return tuple(_unit(item, label) for item in values)  # type: ignore[return-value]
