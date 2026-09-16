from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass
from math import ceil, floor, sqrt

import numpy as np

from .graphics.material import Material3D
from .graphics.mesh import Mesh3D, MeshData
from .large_world import ChunkContent, ChunkDefinition, ChunkKey, LargeWorldSettings
from .math.types import Vec3


@dataclass(frozen=True, order=True, slots=True)
class TerrainChunkKey:
    """Integer X/Z address of one heightmap terrain chunk."""

    x: int
    z: int


@dataclass(frozen=True, slots=True)
class TerrainConfig:
    """Heightmap scale, chunking and distance-LOD policy."""

    cell_size: float = 1.0
    height_scale: float = 1.0
    chunk_cells: int = 32
    lod_steps: tuple[int, ...] = (1, 2, 4, 8)
    lod_distances: tuple[float, ...] = (96.0, 192.0, 384.0)
    mesh_cache_size: int = 128

    def __post_init__(self) -> None:
        if self.cell_size <= 0.0:
            raise ValueError("cell_size must be greater than zero")
        if self.height_scale <= 0.0:
            raise ValueError("height_scale must be greater than zero")
        if self.chunk_cells < 1:
            raise ValueError("chunk_cells must be >= 1")
        if not self.lod_steps or self.lod_steps[0] != 1:
            raise ValueError("lod_steps must start at 1")
        if any(step < 1 for step in self.lod_steps):
            raise ValueError("lod_steps must contain positive integers")
        if tuple(sorted(set(self.lod_steps))) != self.lod_steps:
            raise ValueError("lod_steps must be unique and strictly increasing")
        if len(self.lod_distances) != len(self.lod_steps) - 1:
            raise ValueError("lod_distances must contain one threshold between each LOD")
        if tuple(sorted(self.lod_distances)) != self.lod_distances:
            raise ValueError("lod_distances must be sorted ascending")
        if any(distance <= 0.0 for distance in self.lod_distances):
            raise ValueError("lod_distances must be positive")
        if self.mesh_cache_size < 1:
            raise ValueError("mesh_cache_size must be >= 1")


@dataclass(frozen=True, slots=True)
class TerrainMaterialLayer:
    """One creator-facing terrain material layer used by a splat map."""

    name: str
    albedo: str | None = None
    normal: str | None = None
    uv_scale: float = 1.0
    roughness: float = 1.0
    metallic: float = 0.0

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("terrain material layer name cannot be empty")
        if self.uv_scale <= 0.0:
            raise ValueError("uv_scale must be greater than zero")
        if not 0.0 <= self.roughness <= 1.0:
            raise ValueError("roughness must be between 0 and 1")
        if not 0.0 <= self.metallic <= 1.0:
            raise ValueError("metallic must be between 0 and 1")


@dataclass(frozen=True, slots=True)
class TerrainSplatMap:
    """Normalized HxWxL terrain blend weights with bilinear sampling."""

    weights: np.ndarray

    def __post_init__(self) -> None:
        values = np.asarray(self.weights, dtype="f4")
        if values.ndim != 3 or values.shape[2] < 1:
            raise ValueError("terrain splat weights must have shape (H, W, layers)")
        if values.shape[0] < 2 or values.shape[1] < 2:
            raise ValueError("terrain splat map must be at least 2x2")
        if np.any(values < 0.0):
            raise ValueError("terrain splat weights cannot be negative")
        totals = values.sum(axis=2, keepdims=True)
        zero = totals <= 1e-8
        if np.any(zero):
            values = values.copy()
            values[zero.repeat(values.shape[2], axis=2)] = 0.0
            values[:, :, 0][zero[:, :, 0]] = 1.0
            totals = values.sum(axis=2, keepdims=True)
        normalized = np.ascontiguousarray(values / totals, dtype="f4")
        normalized.setflags(write=False)
        object.__setattr__(self, "weights", normalized)

    @property
    def layer_count(self) -> int:
        return int(self.weights.shape[2])

    def sample_uv(self, u: float, v: float) -> np.ndarray:
        """Bilinearly sample normalized layer weights at clamped UV coordinates."""
        u = min(1.0, max(0.0, float(u)))
        v = min(1.0, max(0.0, float(v)))
        height, width, _ = self.weights.shape
        x = u * (width - 1)
        z = v * (height - 1)
        x0 = floor(x)
        z0 = floor(z)
        x1 = min(x0 + 1, width - 1)
        z1 = min(z0 + 1, height - 1)
        tx = x - x0
        tz = z - z0
        top = self.weights[z0, x0] * (1.0 - tx) + self.weights[z0, x1] * tx
        bottom = self.weights[z1, x0] * (1.0 - tx) + self.weights[z1, x1] * tx
        result = np.asarray(top * (1.0 - tz) + bottom * tz, dtype="f4")
        total = float(result.sum())
        if total > 0.0:
            result /= total
        return result


@dataclass(frozen=True, slots=True)
class TerrainMaterialSet:
    layers: tuple[TerrainMaterialLayer, ...]
    splat: TerrainSplatMap

    def __post_init__(self) -> None:
        if not self.layers:
            raise ValueError("terrain material set must contain at least one layer")
        if len(self.layers) != self.splat.layer_count:
            raise ValueError("terrain material layer count must match splat-map channels")


@dataclass(frozen=True, slots=True)
class TerrainChunkMesh:
    key: TerrainChunkKey
    lod: int
    step: int
    mesh: MeshData
    origin: Vec3
    world_width: float
    world_depth: float

    @property
    def triangle_count(self) -> int:
        return self.mesh.triangle_count

    def to_object(self, *, material: Material3D | None = None, name: str = "") -> Mesh3D:
        return Mesh3D(
            mesh=self.mesh,
            position=Vec3(self.origin.x, self.origin.y, self.origin.z),
            material=material,
            name=name or f"Terrain[{self.key.x},{self.key.z}] LOD{self.lod}",
            tags={"terrain", f"terrain-lod-{self.lod}"},
        )


@dataclass(frozen=True, slots=True)
class TerrainSelection:
    key: TerrainChunkKey
    lod: int
    distance: float


@dataclass(frozen=True, slots=True)
class TerrainDiagnostics:
    mesh_builds: int = 0
    cache_hits: int = 0
    cache_misses: int = 0
    cached_meshes: int = 0
    selected_chunks: int = 0
    selected_triangles: int = 0


@dataclass(frozen=True, slots=True)
class TerrainHit3D:
    point: Vec3
    normal: Vec3
    distance: float


class HeightmapTerrain:
    """Chunked heightmap terrain with bounded LOD mesh caching.

    The heightmap is copied into one immutable contiguous float32 array. Camera selection only scans
    a bounded local chunk window, and generated meshes are retained in an LRU cache so a stationary
    camera does not rebuild terrain every frame.
    """

    def __init__(
        self,
        heightmap: np.ndarray,
        *,
        config: TerrainConfig | None = None,
        origin: Vec3 | None = None,
        materials: TerrainMaterialSet | None = None,
    ) -> None:
        values = np.asarray(heightmap, dtype="f4")
        if values.ndim != 2 or values.shape[0] < 2 or values.shape[1] < 2:
            raise ValueError("heightmap must be a 2D array at least 2x2")
        values = np.ascontiguousarray(values.copy(), dtype="f4")
        values.setflags(write=False)
        self.heightmap = values
        self.config = config or TerrainConfig()
        self.origin = origin or Vec3()
        self.materials = materials
        self._mesh_cache: OrderedDict[tuple[TerrainChunkKey, int], TerrainChunkMesh] = OrderedDict()
        self._mesh_builds = 0
        self._cache_hits = 0
        self._cache_misses = 0
        self._selected_chunks = 0
        self._selected_triangles = 0

    @property
    def cells_x(self) -> int:
        return int(self.heightmap.shape[1] - 1)

    @property
    def cells_z(self) -> int:
        return int(self.heightmap.shape[0] - 1)

    @property
    def chunk_count_x(self) -> int:
        return ceil(self.cells_x / self.config.chunk_cells)

    @property
    def chunk_count_z(self) -> int:
        return ceil(self.cells_z / self.config.chunk_cells)

    @property
    def chunk_world_size(self) -> float:
        return self.config.chunk_cells * self.config.cell_size

    @property
    def world_width(self) -> float:
        return self.cells_x * self.config.cell_size

    @property
    def world_depth(self) -> float:
        return self.cells_z * self.config.cell_size

    @property
    def diagnostics(self) -> TerrainDiagnostics:
        return TerrainDiagnostics(
            mesh_builds=self._mesh_builds,
            cache_hits=self._cache_hits,
            cache_misses=self._cache_misses,
            cached_meshes=len(self._mesh_cache),
            selected_chunks=self._selected_chunks,
            selected_triangles=self._selected_triangles,
        )

    def contains(self, x: float, z: float) -> bool:
        local_x = float(x) - self.origin.x
        local_z = float(z) - self.origin.z
        return 0.0 <= local_x <= self.world_width and 0.0 <= local_z <= self.world_depth

    def sample_height(self, x: float, z: float, *, clamp: bool = False) -> float:
        """Bilinearly sample world-space terrain height."""
        local_x = float(x) - self.origin.x
        local_z = float(z) - self.origin.z
        if clamp:
            local_x = min(self.world_width, max(0.0, local_x))
            local_z = min(self.world_depth, max(0.0, local_z))
        elif not (0.0 <= local_x <= self.world_width and 0.0 <= local_z <= self.world_depth):
            raise ValueError("terrain sample lies outside the heightmap")

        gx = local_x / self.config.cell_size
        gz = local_z / self.config.cell_size
        x0 = min(floor(gx), self.cells_x)
        z0 = min(floor(gz), self.cells_z)
        x1 = min(x0 + 1, self.cells_x)
        z1 = min(z0 + 1, self.cells_z)
        tx = gx - x0
        tz = gz - z0
        top = float(self.heightmap[z0, x0]) * (1.0 - tx) + float(self.heightmap[z0, x1]) * tx
        bottom = float(self.heightmap[z1, x0]) * (1.0 - tx) + float(self.heightmap[z1, x1]) * tx
        return self.origin.y + (top * (1.0 - tz) + bottom * tz) * self.config.height_scale

    def sample_normal(self, x: float, z: float) -> Vec3:
        """Return an upward terrain normal using central height differences."""
        cell = self.config.cell_size
        left = self.sample_height(x - cell, z, clamp=True)
        right = self.sample_height(x + cell, z, clamp=True)
        back = self.sample_height(x, z - cell, clamp=True)
        front = self.sample_height(x, z + cell, clamp=True)
        dx = (right - left) / (2.0 * cell)
        dz = (front - back) / (2.0 * cell)
        return Vec3(-dx, 1.0, -dz).normalized()

    def sample_material_weights(self, x: float, z: float) -> np.ndarray:
        if self.materials is None:
            raise RuntimeError("terrain has no material/splat set")
        u = (float(x) - self.origin.x) / self.world_width
        v = (float(z) - self.origin.z) / self.world_depth
        return self.materials.splat.sample_uv(u, v)

    def has_chunk(self, key: TerrainChunkKey) -> bool:
        return 0 <= key.x < self.chunk_count_x and 0 <= key.z < self.chunk_count_z

    def iter_chunk_keys(self) -> tuple[TerrainChunkKey, ...]:
        return tuple(
            TerrainChunkKey(x, z)
            for z in range(self.chunk_count_z)
            for x in range(self.chunk_count_x)
        )

    def chunk_origin(self, key: TerrainChunkKey) -> Vec3:
        self._validate_chunk(key)
        size = self.chunk_world_size
        return Vec3(self.origin.x + key.x * size, self.origin.y, self.origin.z + key.z * size)

    def chunk_center(self, key: TerrainChunkKey) -> Vec3:
        start_x, end_x, start_z, end_z = self._chunk_cell_bounds(key)
        cell = self.config.cell_size
        return Vec3(
            self.origin.x + (start_x + end_x) * 0.5 * cell,
            self.origin.y,
            self.origin.z + (start_z + end_z) * 0.5 * cell,
        )

    def select_lod(self, key: TerrainChunkKey, focus_x: float, focus_z: float) -> int:
        center = self.chunk_center(key)
        distance = sqrt((center.x - focus_x) ** 2 + (center.z - focus_z) ** 2)
        for lod, threshold in enumerate(self.config.lod_distances):
            if distance < threshold:
                return lod
        return len(self.config.lod_steps) - 1

    def select_chunks(
        self,
        focus_x: float,
        focus_z: float,
        *,
        radius_chunks: int,
    ) -> tuple[TerrainSelection, ...]:
        """Select only the bounded chunk window around the focus point."""
        if radius_chunks < 0:
            raise ValueError("radius_chunks must be non-negative")
        size = self.chunk_world_size
        focus_chunk_x = floor((focus_x - self.origin.x) / size)
        focus_chunk_z = floor((focus_z - self.origin.z) / size)
        selections: list[TerrainSelection] = []
        total_triangles = 0
        for z in range(focus_chunk_z - radius_chunks, focus_chunk_z + radius_chunks + 1):
            for x in range(focus_chunk_x - radius_chunks, focus_chunk_x + radius_chunks + 1):
                key = TerrainChunkKey(x, z)
                if not self.has_chunk(key):
                    continue
                center = self.chunk_center(key)
                distance = sqrt((center.x - focus_x) ** 2 + (center.z - focus_z) ** 2)
                lod = self.select_lod(key, focus_x, focus_z)
                mesh = self.chunk_mesh(key, lod)
                total_triangles += mesh.triangle_count
                selections.append(TerrainSelection(key, lod, distance))
        selections.sort(key=lambda item: (item.distance, item.key))
        self._selected_chunks = len(selections)
        self._selected_triangles = total_triangles
        return tuple(selections)

    def chunk_mesh(self, key: TerrainChunkKey, lod: int = 0) -> TerrainChunkMesh:
        self._validate_chunk(key)
        if not 0 <= lod < len(self.config.lod_steps):
            raise ValueError("lod index is outside configured lod_steps")
        cache_key = (key, lod)
        cached = self._mesh_cache.get(cache_key)
        if cached is not None:
            self._cache_hits += 1
            self._mesh_cache.move_to_end(cache_key)
            return cached

        self._cache_misses += 1
        built = self._build_chunk_mesh(key, lod)
        self._mesh_builds += 1
        self._mesh_cache[cache_key] = built
        self._mesh_cache.move_to_end(cache_key)
        while len(self._mesh_cache) > self.config.mesh_cache_size:
            self._mesh_cache.popitem(last=False)
        return built

    def clear_mesh_cache(self) -> None:
        self._mesh_cache.clear()

    def large_world_settings(
        self,
        *,
        active_radius_chunks: int = 1,
        preload_radius_chunks: int = 2,
        retention_radius_chunks: int = 3,
        max_activations_per_update: int = 4,
    ) -> LargeWorldSettings:
        """Return settings aligned with terrain X/Z chunks using LargeWorld's 2D window."""
        return LargeWorldSettings(
            chunk_size=self.chunk_world_size,
            dimensions=2,
            active_radius_chunks=active_radius_chunks,
            preload_radius_chunks=preload_radius_chunks,
            retention_radius_chunks=retention_radius_chunks,
            max_activations_per_update=max_activations_per_update,
        )

    def large_world_provider(
        self,
        *,
        lod: int = 0,
        material: Material3D | None = None,
    ) -> TerrainChunkProvider:
        return TerrainChunkProvider(self, lod=lod, material=material)

    def _validate_chunk(self, key: TerrainChunkKey) -> None:
        if not self.has_chunk(key):
            raise KeyError(f"terrain chunk {key!r} is outside the heightmap")

    def _chunk_cell_bounds(self, key: TerrainChunkKey) -> tuple[int, int, int, int]:
        self._validate_chunk(key)
        start_x = key.x * self.config.chunk_cells
        start_z = key.z * self.config.chunk_cells
        end_x = min(start_x + self.config.chunk_cells, self.cells_x)
        end_z = min(start_z + self.config.chunk_cells, self.cells_z)
        return start_x, end_x, start_z, end_z

    @staticmethod
    def _axis_samples(start: int, end: int, step: int) -> list[int]:
        samples = list(range(start, end + 1, step))
        if samples[-1] != end:
            samples.append(end)
        return samples

    def _vertex(
        self,
        col: int,
        row: int,
        chunk_origin: Vec3,
    ) -> tuple[
        tuple[float, float, float],
        tuple[float, float, float],
        tuple[float, float],
    ]:
        world_x = self.origin.x + col * self.config.cell_size
        world_z = self.origin.z + row * self.config.cell_size
        world_y = self.origin.y + float(self.heightmap[row, col]) * self.config.height_scale
        normal = self.sample_normal(world_x, world_z)
        position = (
            world_x - chunk_origin.x,
            world_y - chunk_origin.y,
            world_z - chunk_origin.z,
        )
        uv = (col / self.cells_x, row / self.cells_z)
        return position, (normal.x, normal.y, normal.z), uv

    def _build_chunk_mesh(self, key: TerrainChunkKey, lod: int) -> TerrainChunkMesh:
        start_x, end_x, start_z, end_z = self._chunk_cell_bounds(key)
        step = self.config.lod_steps[lod]
        xs = self._axis_samples(start_x, end_x, step)
        zs = self._axis_samples(start_z, end_z, step)
        chunk_origin = self.chunk_origin(key)
        vertices: list[tuple[float, float, float]] = []
        normals: list[tuple[float, float, float]] = []
        uvs: list[tuple[float, float]] = []

        vertex_cache: dict[
            tuple[int, int],
            tuple[
                tuple[float, float, float],
                tuple[float, float, float],
                tuple[float, float],
            ],
        ] = {}

        def emit(col: int, row: int) -> None:
            sample_key = (col, row)
            value = vertex_cache.get(sample_key)
            if value is None:
                value = self._vertex(col, row, chunk_origin)
                vertex_cache[sample_key] = value
            position, normal, uv = value
            vertices.append(position)
            normals.append(normal)
            uvs.append(uv)

        for zi in range(len(zs) - 1):
            z0, z1 = zs[zi], zs[zi + 1]
            for xi in range(len(xs) - 1):
                x0, x1 = xs[xi], xs[xi + 1]
                emit(x0, z0)
                emit(x0, z1)
                emit(x1, z1)
                emit(x0, z0)
                emit(x1, z1)
                emit(x1, z0)

        mesh = MeshData(
            np.asarray(vertices, dtype="f4"),
            np.asarray(normals, dtype="f4"),
            np.asarray(uvs, dtype="f4"),
        )
        return TerrainChunkMesh(
            key=key,
            lod=lod,
            step=step,
            mesh=mesh,
            origin=chunk_origin,
            world_width=(end_x - start_x) * self.config.cell_size,
            world_depth=(end_z - start_z) * self.config.cell_size,
        )


class TerrainCollider3D:
    """Heightfield collision adapter for grounded gameplay and downward ray tests."""

    def __init__(self, terrain: HeightmapTerrain) -> None:
        self.terrain = terrain

    def height_at(self, x: float, z: float) -> float | None:
        if not self.terrain.contains(x, z):
            return None
        return self.terrain.sample_height(x, z)

    def normal_at(self, x: float, z: float) -> Vec3 | None:
        if not self.terrain.contains(x, z):
            return None
        return self.terrain.sample_normal(x, z)

    def raycast_down(
        self,
        x: float,
        y: float,
        z: float,
        max_distance: float,
    ) -> TerrainHit3D | None:
        if max_distance < 0.0:
            raise ValueError("max_distance must be non-negative")
        height = self.height_at(x, z)
        if height is None or y < height:
            return None
        distance = y - height
        if distance > max_distance:
            return None
        normal = self.terrain.sample_normal(x, z)
        return TerrainHit3D(Vec3(float(x), height, float(z)), normal, distance)

    def snap_to_ground(self, point: Vec3, *, offset: float = 0.0) -> Vec3 | None:
        height = self.height_at(point.x, point.z)
        if height is None:
            return None
        return Vec3(point.x, height + float(offset), point.z)


class TerrainChunkProvider:
    """Adapter exposing terrain chunks to :class:`LargeWorldStreamer`.

    Use the streamer's 2D dimensions: ``ChunkKey.x`` maps to terrain X and ``ChunkKey.y`` maps to
    terrain Z. The produced scene object is an ordinary ``Mesh3D`` so existing renderer, scene and
    export paths remain unchanged.
    """

    def __init__(
        self,
        terrain: HeightmapTerrain,
        *,
        lod: int = 0,
        material: Material3D | None = None,
    ) -> None:
        if not 0 <= lod < len(terrain.config.lod_steps):
            raise ValueError("lod index is outside configured lod_steps")
        self.terrain = terrain
        self.lod = lod
        self.material = material

    def __call__(self, key: ChunkKey) -> ChunkDefinition | None:
        if key.z != 0:
            return None
        terrain_key = TerrainChunkKey(key.x, key.y)
        if not self.terrain.has_chunk(terrain_key):
            return None

        def factory(_context: object) -> ChunkContent:
            chunk = self.terrain.chunk_mesh(terrain_key, self.lod)
            return ChunkContent(objects=(chunk.to_object(material=self.material),))

        return ChunkDefinition(
            key=key,
            factory=factory,
            name=f"terrain:{terrain_key.x}:{terrain_key.z}:lod{self.lod}",
        )
