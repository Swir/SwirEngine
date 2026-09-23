from __future__ import annotations

import json
from dataclasses import dataclass, field
from math import floor, isfinite, sqrt
from pathlib import PurePosixPath
from typing import Literal

import numpy as np

from .terrain import (
    HeightmapTerrain,
    TerrainConfig,
    TerrainMaterialLayer,
    TerrainMaterialSet,
    TerrainSplatMap,
)

BrushMode = Literal["raise", "lower", "flatten", "smooth"]


@dataclass(frozen=True, order=True, slots=True)
class DirtyTerrainChunk:
    x: int
    z: int


@dataclass(frozen=True, slots=True)
class FoliagePlacement:
    asset: str
    x: float
    z: float
    yaw: float = 0.0
    scale: float = 1.0

    def __post_init__(self) -> None:
        path = PurePosixPath(self.asset.replace("\\", "/"))
        if not self.asset or path.is_absolute() or ".." in path.parts:
            raise ValueError("foliage asset must be project-relative")
        if not all(isfinite(value) for value in (self.x, self.z, self.yaw, self.scale)):
            raise ValueError("foliage transform must be finite")
        if self.scale <= 0.0:
            raise ValueError("foliage scale must be greater than zero")


@dataclass(frozen=True, slots=True)
class WorldStreamingAuthoring:
    active_radius_chunks: int = 1
    preload_radius_chunks: int = 2
    retention_radius_chunks: int = 3
    max_activations_per_update: int = 4

    def __post_init__(self) -> None:
        if self.active_radius_chunks < 0:
            raise ValueError("active radius must be non-negative")
        if self.preload_radius_chunks < self.active_radius_chunks:
            raise ValueError("preload radius must cover active radius")
        if self.retention_radius_chunks < self.preload_radius_chunks:
            raise ValueError("retention radius must cover preload radius")
        if self.max_activations_per_update < 1:
            raise ValueError("activation budget must be positive")


@dataclass(frozen=True, slots=True)
class TerrainStroke:
    mode: BrushMode
    samples: tuple[tuple[int, int], ...]
    before: tuple[float, ...]
    after: tuple[float, ...]


@dataclass(slots=True)
class TerrainAuthoringAsset:
    heights: np.ndarray
    config: TerrainConfig = field(default_factory=TerrainConfig)
    layers: tuple[TerrainMaterialLayer, ...] = ()
    splat: np.ndarray | None = None
    foliage: list[FoliagePlacement] = field(default_factory=list)
    streaming: WorldStreamingAuthoring = field(default_factory=WorldStreamingAuthoring)
    _dirty: set[DirtyTerrainChunk] = field(default_factory=set, init=False, repr=False)

    FORMAT = "swirengine-terrain"
    VERSION = 1

    def __post_init__(self) -> None:
        heights = np.asarray(self.heights, dtype="f4")
        if heights.ndim != 2 or min(heights.shape) < 2:
            raise ValueError("terrain heights must be a 2D array at least 2x2")
        if not np.all(np.isfinite(heights)):
            raise ValueError("terrain heights must be finite")
        self.heights = np.ascontiguousarray(heights.copy())
        self.foliage = list(self.foliage)
        if self.splat is not None:
            splat = np.asarray(self.splat, dtype="f4")
            expected = (*self.heights.shape, len(self.layers))
            if not self.layers or splat.shape != expected:
                raise ValueError("splat map dimensions must match heights and material layers")
            if np.any(splat < 0.0) or not np.all(np.isfinite(splat)):
                raise ValueError("splat weights must be finite and non-negative")
            self.splat = np.ascontiguousarray(splat.copy())
            self._normalize_splat()

    @classmethod
    def flat(
        cls,
        width: int,
        height: int,
        *,
        value: float = 0.0,
        config: TerrainConfig | None = None,
    ) -> TerrainAuthoringAsset:
        if min(width, height) < 2 or not isfinite(value):
            raise ValueError("flat terrain requires finite value and dimensions >= 2")
        heights = np.full((height, width), value, dtype="f4")
        return cls(heights, config=config or TerrainConfig())

    def sculpt(
        self,
        *,
        x: float,
        z: float,
        radius: float,
        strength: float,
        mode: BrushMode = "raise",
        target_height: float | None = None,
    ) -> TerrainStroke:
        if radius <= 0.0 or strength < 0.0 or not all(map(isfinite, (radius, strength))):
            raise ValueError("brush radius/strength are invalid")
        if mode == "flatten" and (target_height is None or not isfinite(target_height)):
            raise ValueError("flatten requires a finite target height")
        if mode not in ("raise", "lower", "flatten", "smooth"):
            raise ValueError(f"unsupported brush mode: {mode}")

        gx, gz = x / self.config.cell_size, z / self.config.cell_size
        radius_cells = radius / self.config.cell_size
        source = self.heights.copy() if mode == "smooth" else self.heights
        samples: list[tuple[int, int]] = []
        before: list[float] = []
        after: list[float] = []
        x0 = max(0, floor(gx - radius_cells))
        x1 = min(self.heights.shape[1] - 1, floor(gx + radius_cells) + 1)
        z0 = max(0, floor(gz - radius_cells))
        z1 = min(self.heights.shape[0] - 1, floor(gz + radius_cells) + 1)

        for row in range(z0, z1 + 1):
            for col in range(x0, x1 + 1):
                distance = sqrt((col - gx) ** 2 + (row - gz) ** 2)
                if distance > radius_cells:
                    continue
                falloff = max(0.0, 1.0 - distance / max(radius_cells, 1e-8))
                old = float(self.heights[row, col])
                if mode == "raise":
                    new = old + strength * falloff
                elif mode == "lower":
                    new = old - strength * falloff
                elif mode == "flatten":
                    assert target_height is not None
                    new = old + (target_height - old) * min(1.0, strength * falloff)
                else:
                    neighborhood = source[
                        max(0, row - 1) : row + 2,
                        max(0, col - 1) : col + 2,
                    ]
                    new = old + (float(neighborhood.mean()) - old) * min(
                        1.0, strength * falloff
                    )
                if new != old:
                    self.heights[row, col] = new
                    samples.append((row, col))
                    before.append(old)
                    after.append(float(new))

        self._mark_dirty(samples)
        return TerrainStroke(mode, tuple(samples), tuple(before), tuple(after))

    def apply_stroke(self, stroke: TerrainStroke, *, reverse: bool = False) -> None:
        values = stroke.before if reverse else stroke.after
        for (row, col), value in zip(stroke.samples, values, strict=True):
            self.heights[row, col] = value
        self._mark_dirty(stroke.samples)

    def paint(self, layer: int, *, x: float, z: float, radius: float, strength: float) -> int:
        if self.splat is None or not 0 <= layer < len(self.layers):
            raise ValueError("terrain paint layer is unavailable")
        if radius <= 0.0 or strength < 0.0:
            raise ValueError("paint radius/strength are invalid")
        gx, gz = x / self.config.cell_size, z / self.config.cell_size
        radius_cells = radius / self.config.cell_size
        changed = 0
        for row in range(self.heights.shape[0]):
            for col in range(self.heights.shape[1]):
                distance = sqrt((col - gx) ** 2 + (row - gz) ** 2)
                if distance > radius_cells:
                    continue
                amount = min(
                    1.0,
                    strength * (1.0 - distance / max(radius_cells, 1e-8)),
                )
                weights = self.splat[row, col]
                weights *= 1.0 - amount
                weights[layer] += amount
                weights /= max(float(weights.sum()), 1e-8)
                self._mark_dirty(((row, col),))
                changed += 1
        return changed

    def add_foliage(self, placement: FoliagePlacement) -> None:
        max_x = (self.heights.shape[1] - 1) * self.config.cell_size
        max_z = (self.heights.shape[0] - 1) * self.config.cell_size
        if not 0.0 <= placement.x <= max_x or not 0.0 <= placement.z <= max_z:
            raise ValueError("foliage placement is outside terrain")
        self.foliage.append(placement)
        self.foliage.sort(key=lambda item: (item.asset, item.z, item.x, item.yaw, item.scale))

    def dirty_chunks(self) -> tuple[DirtyTerrainChunk, ...]:
        return tuple(sorted(self._dirty))

    def drain_dirty_chunks(self) -> tuple[DirtyTerrainChunk, ...]:
        result = self.dirty_chunks()
        self._dirty.clear()
        return result

    def to_runtime(self) -> HeightmapTerrain:
        materials = None
        if self.layers and self.splat is not None:
            materials = TerrainMaterialSet(self.layers, TerrainSplatMap(self.splat))
        return HeightmapTerrain(self.heights, config=self.config, materials=materials)

    def runtime_streaming_settings(self):
        runtime = self.to_runtime()
        return runtime.large_world_settings(
            active_radius_chunks=self.streaming.active_radius_chunks,
            preload_radius_chunks=self.streaming.preload_radius_chunks,
            retention_radius_chunks=self.streaming.retention_radius_chunks,
            max_activations_per_update=self.streaming.max_activations_per_update,
        )

    def canonical_json(self) -> str:
        payload = {
            "format": self.FORMAT,
            "version": self.VERSION,
            "config": {
                "cell_size": self.config.cell_size,
                "height_scale": self.config.height_scale,
                "chunk_cells": self.config.chunk_cells,
                "lod_steps": list(self.config.lod_steps),
                "lod_distances": list(self.config.lod_distances),
                "mesh_cache_size": self.config.mesh_cache_size,
            },
            "heights": self.heights.tolist(),
            "layers": [
                {
                    "name": item.name,
                    "albedo": item.albedo,
                    "normal": item.normal,
                    "uv_scale": item.uv_scale,
                    "roughness": item.roughness,
                    "metallic": item.metallic,
                }
                for item in self.layers
            ],
            "splat": None if self.splat is None else self.splat.tolist(),
            "foliage": [
                {
                    "asset": item.asset,
                    "x": item.x,
                    "z": item.z,
                    "yaw": item.yaw,
                    "scale": item.scale,
                }
                for item in self.foliage
            ],
            "streaming": {
                "active_radius_chunks": self.streaming.active_radius_chunks,
                "preload_radius_chunks": self.streaming.preload_radius_chunks,
                "retention_radius_chunks": self.streaming.retention_radius_chunks,
                "max_activations_per_update": self.streaming.max_activations_per_update,
            },
        }
        return json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n"

    def _normalize_splat(self) -> None:
        assert self.splat is not None
        totals = self.splat.sum(axis=2, keepdims=True)
        empty = totals[:, :, 0] <= 1e-8
        if np.any(empty):
            self.splat[empty] = 0.0
            self.splat[:, :, 0][empty] = 1.0
            totals = self.splat.sum(axis=2, keepdims=True)
        self.splat /= totals

    def _mark_dirty(self, samples) -> None:
        chunk = self.config.chunk_cells
        max_x = (self.heights.shape[1] - 2) // chunk
        max_z = (self.heights.shape[0] - 2) // chunk
        for row, col in samples:
            self._dirty.add(DirtyTerrainChunk(min(max_x, col // chunk), min(max_z, row // chunk)))


class TerrainAuthoringSession:
    def __init__(self, asset: TerrainAuthoringAsset, *, history_limit: int = 128) -> None:
        if history_limit < 1:
            raise ValueError("history_limit must be positive")
        self.asset = asset
        self.history_limit = history_limit
        self._undo: list[TerrainStroke] = []
        self._redo: list[TerrainStroke] = []

    def sculpt(self, **kwargs) -> TerrainStroke:
        stroke = self.asset.sculpt(**kwargs)
        if stroke.samples:
            self._undo.append(stroke)
            self._undo = self._undo[-self.history_limit :]
            self._redo.clear()
        return stroke

    def undo(self) -> bool:
        if not self._undo:
            return False
        stroke = self._undo.pop()
        self.asset.apply_stroke(stroke, reverse=True)
        self._redo.append(stroke)
        return True

    def redo(self) -> bool:
        if not self._redo:
            return False
        stroke = self._redo.pop()
        self.asset.apply_stroke(stroke)
        self._undo.append(stroke)
        return True
