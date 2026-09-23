from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from math import floor, isfinite, sqrt
from pathlib import Path, PurePosixPath
from typing import Any, Literal

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
        self.layers = tuple(self.layers)
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

    @classmethod
    def from_swirterrain_bytes(cls, data: bytes | str) -> TerrainAuthoringAsset:
        try:
            text = data.decode("utf-8") if isinstance(data, bytes) else data
            payload = json.loads(text)
            if not isinstance(payload, Mapping):
                raise ValueError("terrain payload root must be an object")
            if payload.get("format") != cls.FORMAT:
                raise ValueError("unsupported terrain asset format")
            if payload.get("version") != cls.VERSION:
                raise ValueError("unsupported terrain asset version")

            config_data = cls._mapping(payload, "config")
            config = TerrainConfig(
                cell_size=float(config_data["cell_size"]),
                height_scale=float(config_data["height_scale"]),
                chunk_cells=int(config_data["chunk_cells"]),
                lod_steps=tuple(int(value) for value in config_data["lod_steps"]),
                lod_distances=tuple(float(value) for value in config_data["lod_distances"]),
                mesh_cache_size=int(config_data["mesh_cache_size"]),
            )
            layers_data = payload.get("layers")
            if not isinstance(layers_data, list):
                raise ValueError("terrain layers must be an array")
            layers = tuple(
                TerrainMaterialLayer(
                    name=str(cls._mapping_value(item, "name")),
                    albedo=cls._optional_string(item, "albedo"),
                    normal=cls._optional_string(item, "normal"),
                    uv_scale=float(cls._mapping_value(item, "uv_scale")),
                    roughness=float(cls._mapping_value(item, "roughness")),
                    metallic=float(cls._mapping_value(item, "metallic")),
                )
                for item in layers_data
            )
            foliage_data = payload.get("foliage")
            if not isinstance(foliage_data, list):
                raise ValueError("terrain foliage must be an array")
            foliage = [
                FoliagePlacement(
                    asset=str(cls._mapping_value(item, "asset")),
                    x=float(cls._mapping_value(item, "x")),
                    z=float(cls._mapping_value(item, "z")),
                    yaw=float(cls._mapping_value(item, "yaw")),
                    scale=float(cls._mapping_value(item, "scale")),
                )
                for item in foliage_data
            ]
            streaming_data = cls._mapping(payload, "streaming")
            streaming = WorldStreamingAuthoring(
                active_radius_chunks=int(streaming_data["active_radius_chunks"]),
                preload_radius_chunks=int(streaming_data["preload_radius_chunks"]),
                retention_radius_chunks=int(streaming_data["retention_radius_chunks"]),
                max_activations_per_update=int(streaming_data["max_activations_per_update"]),
            )
            heights = np.asarray(payload["heights"], dtype="f4")
            splat_payload = payload.get("splat")
            splat = None if splat_payload is None else np.asarray(splat_payload, dtype="f4")
            return cls(
                heights,
                config=config,
                layers=layers,
                splat=splat,
                foliage=foliage,
                streaming=streaming,
            )
        except (KeyError, TypeError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError("invalid .swirterrain payload") from exc

    @staticmethod
    def _mapping(payload: Mapping[str, Any], key: str) -> Mapping[str, Any]:
        value = payload[key]
        if not isinstance(value, Mapping):
            raise ValueError(f"terrain {key} must be an object")
        return value

    @staticmethod
    def _mapping_value(payload: object, key: str) -> Any:
        if not isinstance(payload, Mapping):
            raise ValueError("terrain list entries must be objects")
        return payload[key]

    @classmethod
    def _optional_string(cls, payload: object, key: str) -> str | None:
        value = cls._mapping_value(payload, key)
        if value is None:
            return None
        if not isinstance(value, str):
            raise ValueError(f"terrain {key} must be a string or null")
        return value

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

    def to_swirterrain_bytes(self) -> bytes:
        return self.canonical_json().encode("utf-8")

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


class TerrainProjectStore:
    """Project-scoped deterministic storage for ``assets/terrain/*.swirterrain`` assets."""

    ASSET_ROOT = PurePosixPath("assets/terrain")

    def __init__(self, project_root: str | Path) -> None:
        self.project_root = Path(project_root).expanduser().resolve()
        self.asset_root = (self.project_root / "assets" / "terrain").resolve()

    def resolve(self, asset_path: str | Path) -> Path:
        raw = str(asset_path).replace("\\", "/")
        relative = PurePosixPath(raw)
        if not raw or relative.is_absolute() or ".." in relative.parts:
            raise ValueError("terrain asset path must be project-relative")
        if relative.parts[:2] == self.ASSET_ROOT.parts:
            relative = PurePosixPath(*relative.parts[2:])
        if not relative.parts or relative.suffix != ".swirterrain":
            raise ValueError("terrain asset path must end with .swirterrain")
        target = (self.asset_root / Path(*relative.parts)).resolve()
        try:
            target.relative_to(self.asset_root)
        except ValueError as exc:
            raise ValueError("terrain asset path escapes project assets/terrain") from exc
        return target

    def save(self, asset_path: str | Path, asset: TerrainAuthoringAsset) -> Path:
        target = self.resolve(asset_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_name(f".{target.name}.tmp")
        try:
            temporary.write_bytes(asset.to_swirterrain_bytes())
            temporary.replace(target)
        finally:
            if temporary.exists():
                temporary.unlink()
        return target

    def load(self, asset_path: str | Path) -> TerrainAuthoringAsset:
        target = self.resolve(asset_path)
        if not target.is_file():
            raise FileNotFoundError(target)
        return TerrainAuthoringAsset.from_swirterrain_bytes(target.read_bytes())


class TerrainEditorSession:
    """Creator-facing terrain document session backed by project storage and runtime preview."""

    def __init__(
        self,
        store: TerrainProjectStore,
        asset_path: str | Path,
        asset: TerrainAuthoringAsset,
        *,
        history_limit: int = 128,
        saved: bool = False,
    ) -> None:
        self.store = store
        self.asset_path = str(asset_path).replace("\\", "/")
        self.asset = asset
        self.history_limit = history_limit
        self._history = TerrainAuthoringSession(asset, history_limit=history_limit)
        self._saved_bytes: bytes | None = asset.to_swirterrain_bytes() if saved else None
        self.store.resolve(self.asset_path)

    @classmethod
    def create(
        cls,
        store: TerrainProjectStore,
        asset_path: str | Path,
        asset: TerrainAuthoringAsset,
        *,
        history_limit: int = 128,
    ) -> TerrainEditorSession:
        return cls(store, asset_path, asset, history_limit=history_limit, saved=False)

    @classmethod
    def open(
        cls,
        store: TerrainProjectStore,
        asset_path: str | Path,
        *,
        history_limit: int = 128,
    ) -> TerrainEditorSession:
        return cls(
            store,
            asset_path,
            store.load(asset_path),
            history_limit=history_limit,
            saved=True,
        )

    @property
    def dirty(self) -> bool:
        return self._saved_bytes != self.asset.to_swirterrain_bytes()

    @property
    def project_path(self) -> Path:
        return self.store.resolve(self.asset_path)

    def sculpt(self, **kwargs) -> TerrainStroke:
        return self._history.sculpt(**kwargs)

    def paint(self, layer: int, **kwargs) -> int:
        return self.asset.paint(layer, **kwargs)

    def add_foliage(self, placement: FoliagePlacement) -> None:
        self.asset.add_foliage(placement)

    def undo(self) -> bool:
        return self._history.undo()

    def redo(self) -> bool:
        return self._history.redo()

    def runtime_preview(self) -> HeightmapTerrain:
        return self.asset.to_runtime()

    def save(self) -> Path:
        target = self.store.save(self.asset_path, self.asset)
        self._saved_bytes = self.asset.to_swirterrain_bytes()
        return target

    def reload(self) -> None:
        self.asset = self.store.load(self.asset_path)
        self._history = TerrainAuthoringSession(self.asset, history_limit=self.history_limit)
        self._saved_bytes = self.asset.to_swirterrain_bytes()
