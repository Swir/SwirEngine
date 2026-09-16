from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True, slots=True)
class HiZQueryDiagnostics3D:
    level: int
    texels_tested: int
    conservative_depth: float
    object_nearest_depth: float
    occluded: bool


class HiZDepthPyramid3D:
    """Conservative regular-Z depth pyramid for occlusion-ready visibility stages.

    SwirEngine's OpenGL depth convention maps near values toward 0 and far values toward 1. Every
    coarse texel therefore stores the *maximum* depth of its children. A hole/background sample at
    depth 1 propagates upward and prevents an occlusion decision, favoring false negatives over false
    positives. This CPU representation defines and tests the contract used by future GPU Hi-Z paths.
    """

    def __init__(self, depth: np.ndarray) -> None:
        base = np.asarray(depth, dtype="f4")
        if base.ndim != 2 or min(base.shape) < 1:
            raise ValueError("Hi-Z depth input must be a non-empty 2D array")
        if not np.all(np.isfinite(base)):
            raise ValueError("Hi-Z depth input must contain only finite values")
        if np.any(base < 0.0) or np.any(base > 1.0):
            raise ValueError("Hi-Z depth values must be within 0..1")
        self._levels = self._build(np.ascontiguousarray(base))

    @staticmethod
    def _build(base: np.ndarray) -> tuple[np.ndarray, ...]:
        levels: list[np.ndarray] = [base]
        current = base
        while current.shape != (1, 1):
            height, width = current.shape
            next_height = max(1, (height + 1) // 2)
            next_width = max(1, (width + 1) // 2)
            reduced = np.empty((next_height, next_width), dtype="f4")
            for y in range(next_height):
                y0 = y * 2
                y1 = min(height, y0 + 2)
                for x in range(next_width):
                    x0 = x * 2
                    x1 = min(width, x0 + 2)
                    reduced[y, x] = float(np.max(current[y0:y1, x0:x1]))
            reduced.setflags(write=False)
            levels.append(reduced)
            current = reduced
        levels[0].setflags(write=False)
        return tuple(levels)

    @property
    def levels(self) -> tuple[np.ndarray, ...]:
        return self._levels

    @property
    def level_count(self) -> int:
        return len(self._levels)

    @property
    def size(self) -> tuple[int, int]:
        height, width = self._levels[0].shape
        return width, height

    def choose_level(self, uv_rect: tuple[float, float, float, float]) -> int:
        u0, v0, u1, v1 = self._validated_rect(uv_rect)
        width, height = self.size
        pixel_span = max((u1 - u0) * width, (v1 - v0) * height, 1.0)
        return min(self.level_count - 1, max(0, int(math.floor(math.log2(pixel_span)))))

    def conservative_max_depth(
        self,
        uv_rect: tuple[float, float, float, float],
        *,
        level: int | None = None,
    ) -> tuple[float, int, int]:
        u0, v0, u1, v1 = self._validated_rect(uv_rect)
        selected = self.choose_level((u0, v0, u1, v1)) if level is None else int(level)
        if not 0 <= selected < self.level_count:
            raise ValueError("Hi-Z level is out of range")
        data = self._levels[selected]
        height, width = data.shape
        x0 = min(width - 1, max(0, int(math.floor(u0 * width))))
        y0 = min(height - 1, max(0, int(math.floor(v0 * height))))
        x1 = min(width, max(x0 + 1, int(math.ceil(u1 * width))))
        y1 = min(height, max(y0 + 1, int(math.ceil(v1 * height))))
        region = data[y0:y1, x0:x1]
        return float(np.max(region)), int(region.size), selected

    def query_occluded(
        self,
        uv_rect: tuple[float, float, float, float],
        nearest_depth: float,
        *,
        bias: float = 1e-4,
    ) -> HiZQueryDiagnostics3D:
        depth = float(nearest_depth)
        if not 0.0 <= depth <= 1.0:
            raise ValueError("object nearest depth must be within 0..1")
        tolerance = max(0.0, float(bias))
        conservative, tested, level = self.conservative_max_depth(uv_rect)
        occluded = depth > conservative + tolerance
        return HiZQueryDiagnostics3D(
            level=level,
            texels_tested=tested,
            conservative_depth=conservative,
            object_nearest_depth=depth,
            occluded=occluded,
        )

    @staticmethod
    def _validated_rect(
        uv_rect: tuple[float, float, float, float],
    ) -> tuple[float, float, float, float]:
        if len(uv_rect) != 4:
            raise ValueError("Hi-Z UV rectangle must contain four values")
        u0, v0, u1, v1 = (float(value) for value in uv_rect)
        if not all(math.isfinite(value) for value in (u0, v0, u1, v1)):
            raise ValueError("Hi-Z UV rectangle must contain finite values")
        u0 = max(0.0, min(1.0, u0))
        v0 = max(0.0, min(1.0, v0))
        u1 = max(0.0, min(1.0, u1))
        v1 = max(0.0, min(1.0, v1))
        if u1 <= u0 or v1 <= v0:
            raise ValueError("Hi-Z UV rectangle must have positive area")
        return u0, v0, u1, v1
