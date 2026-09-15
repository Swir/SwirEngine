from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from math import floor, inf, isfinite, sqrt
from typing import Any, cast

from ..math.types import Vec3


@dataclass(frozen=True, slots=True)
class AABB3D:
    """Center-based 3D axis-aligned bounds used by broad-phase queries."""

    x: float
    y: float
    z: float
    width: float
    height: float
    depth: float

    def __post_init__(self) -> None:
        if self.width < 0 or self.height < 0 or self.depth < 0:
            raise ValueError("AABB3D width, height and depth must be non-negative")

    @property
    def left(self) -> float:
        return self.x - self.width / 2.0

    @property
    def right(self) -> float:
        return self.x + self.width / 2.0

    @property
    def bottom(self) -> float:
        return self.y - self.height / 2.0

    @property
    def top(self) -> float:
        return self.y + self.height / 2.0

    @property
    def back(self) -> float:
        return self.z - self.depth / 2.0

    @property
    def front(self) -> float:
        return self.z + self.depth / 2.0

    def intersects(self, other: AABB3D) -> bool:
        return not (
            self.right < other.left
            or self.left > other.right
            or self.top < other.bottom
            or self.bottom > other.top
            or self.front < other.back
            or self.back > other.front
        )

    def contains(self, x: float, y: float, z: float) -> bool:
        return (
            self.left <= x <= self.right
            and self.bottom <= y <= self.top
            and self.back <= z <= self.front
        )


@dataclass(frozen=True, slots=True)
class SphereBounds3D:
    """Center/radius bounds used by sphere queries and sphere colliders."""

    x: float
    y: float
    z: float
    radius: float

    def __post_init__(self) -> None:
        if self.radius < 0:
            raise ValueError("sphere radius must be non-negative")

    @property
    def aabb(self) -> AABB3D:
        diameter = self.radius * 2.0
        return AABB3D(self.x, self.y, self.z, diameter, diameter, diameter)

    def contains(self, x: float, y: float, z: float) -> bool:
        dx = x - self.x
        dy = y - self.y
        dz = z - self.z
        return dx * dx + dy * dy + dz * dz <= self.radius * self.radius


@dataclass(frozen=True, slots=True)
class CollisionDiagnostics3D:
    """Diagnostics from the most recent 3D broad/narrow-phase operation."""

    collider_count: int = 0
    occupied_cells: int = 0
    candidate_count: int = 0
    narrow_phase_tests: int = 0
    hits: int = 0


@dataclass(frozen=True, slots=True)
class RaycastHit3D:
    """One deterministic 3D ray hit sorted by distance from the origin."""

    collider: Collider3D
    distance: float
    point: Vec3
    normal: Vec3


def _target_position(target: object) -> tuple[float, float, float]:
    value = getattr(target, "position", None)
    if value is not None:
        try:
            return float(value.x), float(value.y), float(value.z)
        except AttributeError as exc:
            raise TypeError("target.position must expose x, y and z attributes") from exc

    raw = cast(Any, target)
    try:
        return float(raw.x), float(raw.y), float(raw.z)
    except AttributeError as exc:
        raise TypeError("3D collider target must expose position.x/y/z or x/y/z") from exc


def _target_box_size(
    target: object,
    width: float | None,
    height: float | None,
    depth: float | None,
) -> tuple[float, float, float]:
    raw = cast(Any, target)
    if width is not None and height is not None and depth is not None:
        values = float(width), float(height), float(depth)
        if min(values) < 0:
            raise ValueError("3D box collider dimensions must be non-negative")
        return values

    resolved_width = width
    resolved_height = height
    resolved_depth = depth

    if resolved_width is None:
        resolved_width = getattr(raw, "width", None)
    if resolved_height is None:
        resolved_height = getattr(raw, "height", None)
    if resolved_depth is None:
        resolved_depth = getattr(raw, "depth", None)

    size = getattr(raw, "size", None)
    if size is not None and isinstance(size, (int, float)):
        resolved_width = float(size) if resolved_width is None else resolved_width
        resolved_height = float(size) if resolved_height is None else resolved_height
        resolved_depth = float(size) if resolved_depth is None else resolved_depth

    scale = getattr(raw, "scale", None)
    if scale is not None:
        try:
            resolved_width = abs(float(scale.x)) if resolved_width is None else resolved_width
            resolved_height = abs(float(scale.y)) if resolved_height is None else resolved_height
            resolved_depth = abs(float(scale.z)) if resolved_depth is None else resolved_depth
        except AttributeError as exc:
            raise TypeError("target.scale must expose x, y and z attributes") from exc

    if resolved_width is None or resolved_height is None or resolved_depth is None:
        raise ValueError(
            "3D box collider size is unknown; set width/height/depth or use a target with size/scale"
        )

    values = float(resolved_width), float(resolved_height), float(resolved_depth)
    if min(values) < 0:
        raise ValueError("3D box collider dimensions must be non-negative")
    return values


class BoxCollider3D:
    """Axis-aligned box collider tracking a live 3D target transform."""

    def __init__(
        self,
        target: object,
        *,
        width: float | None = None,
        height: float | None = None,
        depth: float | None = None,
        offset: Vec3 | None = None,
        enabled: bool = True,
        layer: int = 1,
        mask: int = 0xFFFFFFFF,
        tag: str = "",
    ) -> None:
        self.target = target
        self.width = width
        self.height = height
        self.depth = depth
        self.offset = offset or Vec3()
        self.enabled = bool(enabled)
        self.layer = int(layer)
        self.mask = int(mask)
        self.tag = tag

    @property
    def bounds(self) -> AABB3D:
        x, y, z = _target_position(self.target)
        width, height, depth = _target_box_size(
            self.target,
            self.width,
            self.height,
            self.depth,
        )
        return AABB3D(
            x + float(self.offset.x),
            y + float(self.offset.y),
            z + float(self.offset.z),
            width,
            height,
            depth,
        )

    def can_collide_with(self, other: Collider3D) -> bool:
        return bool(
            self.enabled
            and other.enabled
            and self.mask & other.layer
            and other.mask & self.layer
        )

    def collides_with(self, other: Collider3D) -> bool:
        return self.can_collide_with(other) and _colliders_intersect(self, other)


class SphereCollider3D:
    """Sphere collider tracking a live 3D target position."""

    def __init__(
        self,
        target: object,
        *,
        radius: float | None = None,
        offset: Vec3 | None = None,
        enabled: bool = True,
        layer: int = 1,
        mask: int = 0xFFFFFFFF,
        tag: str = "",
    ) -> None:
        self.target = target
        self.radius = radius
        self.offset = offset or Vec3()
        self.enabled = bool(enabled)
        self.layer = int(layer)
        self.mask = int(mask)
        self.tag = tag

    @property
    def bounds(self) -> SphereBounds3D:
        x, y, z = _target_position(self.target)
        radius = self.radius
        if radius is None:
            radius = getattr(cast(Any, self.target), "radius", None)
        if radius is None:
            raise ValueError("sphere collider radius is unknown; set radius or target.radius")
        radius = float(radius)
        if radius < 0:
            raise ValueError("sphere collider radius must be non-negative")
        return SphereBounds3D(
            x + float(self.offset.x),
            y + float(self.offset.y),
            z + float(self.offset.z),
            radius,
        )

    def can_collide_with(self, other: Collider3D) -> bool:
        return bool(
            self.enabled
            and other.enabled
            and self.mask & other.layer
            and other.mask & self.layer
        )

    def collides_with(self, other: Collider3D) -> bool:
        return self.can_collide_with(other) and _colliders_intersect(self, other)


Collider3D = BoxCollider3D | SphereCollider3D


def _sphere_intersects_aabb(sphere: SphereBounds3D, box: AABB3D) -> bool:
    closest_x = min(max(sphere.x, box.left), box.right)
    closest_y = min(max(sphere.y, box.bottom), box.top)
    closest_z = min(max(sphere.z, box.back), box.front)
    dx = sphere.x - closest_x
    dy = sphere.y - closest_y
    dz = sphere.z - closest_z
    return dx * dx + dy * dy + dz * dz <= sphere.radius * sphere.radius


def _spheres_intersect(first: SphereBounds3D, second: SphereBounds3D) -> bool:
    dx = first.x - second.x
    dy = first.y - second.y
    dz = first.z - second.z
    radius = first.radius + second.radius
    return dx * dx + dy * dy + dz * dz <= radius * radius


def _collider_aabb(collider: Collider3D) -> AABB3D:
    if isinstance(collider, BoxCollider3D):
        return collider.bounds
    return collider.bounds.aabb


def _colliders_intersect(first: Collider3D, second: Collider3D) -> bool:
    if isinstance(first, BoxCollider3D):
        first_bounds = first.bounds
        if isinstance(second, BoxCollider3D):
            return first_bounds.intersects(second.bounds)
        return _sphere_intersects_aabb(second.bounds, first_bounds)

    first_sphere = first.bounds
    if isinstance(second, BoxCollider3D):
        return _sphere_intersects_aabb(first_sphere, second.bounds)
    return _spheres_intersect(first_sphere, second.bounds)


class CollisionWorld3D:
    """Dynamic 3D collision registry with deterministic spatial-hash broad phase."""

    def __init__(self, *, cell_size: float = 4.0) -> None:
        if cell_size <= 0:
            raise ValueError("cell_size must be greater than zero")
        self.cell_size = float(cell_size)
        self._colliders: list[Collider3D] = []
        self._grid: dict[tuple[int, int, int], list[int]] = {}
        self._bounds: list[AABB3D] = []
        self._diagnostics = CollisionDiagnostics3D()

    @property
    def colliders(self) -> tuple[Collider3D, ...]:
        return tuple(self._colliders)

    @property
    def diagnostics(self) -> CollisionDiagnostics3D:
        return self._diagnostics

    def add(self, collider: Collider3D) -> Collider3D:
        if not any(existing is collider for existing in self._colliders):
            self._colliders.append(collider)
        return collider

    def remove(self, collider: Collider3D) -> bool:
        for index, existing in enumerate(self._colliders):
            if existing is collider:
                del self._colliders[index]
                return True
        return False

    def clear(self) -> None:
        self._colliders.clear()
        self._grid.clear()
        self._bounds.clear()
        self._diagnostics = CollisionDiagnostics3D()

    def _iter_cells(self, bounds: AABB3D) -> Iterator[tuple[int, int, int]]:
        left = floor(bounds.left / self.cell_size)
        right = floor(bounds.right / self.cell_size)
        bottom = floor(bounds.bottom / self.cell_size)
        top = floor(bounds.top / self.cell_size)
        back = floor(bounds.back / self.cell_size)
        front = floor(bounds.front / self.cell_size)
        for cell_z in range(back, front + 1):
            for cell_y in range(bottom, top + 1):
                for cell_x in range(left, right + 1):
                    yield cell_x, cell_y, cell_z

    def _rebuild_index(self) -> None:
        self._grid.clear()
        self._bounds.clear()
        for index, collider in enumerate(self._colliders):
            bounds = _collider_aabb(collider)
            self._bounds.append(bounds)
            if not collider.enabled:
                continue
            for cell in self._iter_cells(bounds):
                self._grid.setdefault(cell, []).append(index)

    def _candidate_indexes(self, bounds: AABB3D) -> list[int]:
        indexes: set[int] = set()
        for cell in self._iter_cells(bounds):
            indexes.update(self._grid.get(cell, ()))
        return sorted(indexes)

    def _set_diagnostics(self, candidates: int, tests: int, hits: int) -> None:
        self._diagnostics = CollisionDiagnostics3D(
            collider_count=len(self._colliders),
            occupied_cells=len(self._grid),
            candidate_count=candidates,
            narrow_phase_tests=tests,
            hits=hits,
        )

    def query(self, collider: Collider3D, *, tag: str | None = None) -> tuple[Collider3D, ...]:
        self._rebuild_index()
        broad_bounds = _collider_aabb(collider)
        candidates = self._candidate_indexes(broad_bounds)
        hits: list[Collider3D] = []
        tests = 0
        for index in candidates:
            other = self._colliders[index]
            if other is collider:
                continue
            if tag is not None and other.tag != tag:
                continue
            if not collider.can_collide_with(other):
                continue
            tests += 1
            if _colliders_intersect(collider, other):
                hits.append(other)
        self._set_diagnostics(len(candidates), tests, len(hits))
        return tuple(hits)

    def overlap_box(
        self,
        bounds: AABB3D,
        *,
        layer_mask: int = 0xFFFFFFFF,
        tag: str | None = None,
    ) -> tuple[Collider3D, ...]:
        """Return enabled colliders intersecting an axis-aligned query box."""
        self._rebuild_index()
        candidates = self._candidate_indexes(bounds)
        hits: list[Collider3D] = []
        tests = 0
        for index in candidates:
            collider = self._colliders[index]
            if not collider.enabled or not collider.layer & layer_mask:
                continue
            if tag is not None and collider.tag != tag:
                continue
            tests += 1
            if isinstance(collider, BoxCollider3D):
                matched = bounds.intersects(collider.bounds)
            else:
                matched = _sphere_intersects_aabb(collider.bounds, bounds)
            if matched:
                hits.append(collider)
        self._set_diagnostics(len(candidates), tests, len(hits))
        return tuple(hits)

    def overlap_sphere(
        self,
        center: Vec3,
        radius: float,
        *,
        layer_mask: int = 0xFFFFFFFF,
        tag: str | None = None,
    ) -> tuple[Collider3D, ...]:
        """Return enabled colliders intersecting a world-space sphere."""
        query = SphereBounds3D(float(center.x), float(center.y), float(center.z), float(radius))
        self._rebuild_index()
        candidates = self._candidate_indexes(query.aabb)
        hits: list[Collider3D] = []
        tests = 0
        for index in candidates:
            collider = self._colliders[index]
            if not collider.enabled or not collider.layer & layer_mask:
                continue
            if tag is not None and collider.tag != tag:
                continue
            tests += 1
            if isinstance(collider, BoxCollider3D):
                matched = _sphere_intersects_aabb(query, collider.bounds)
            else:
                matched = _spheres_intersect(query, collider.bounds)
            if matched:
                hits.append(collider)
        self._set_diagnostics(len(candidates), tests, len(hits))
        return tuple(hits)

    def query_point(
        self,
        point: Vec3,
        *,
        layer_mask: int = 0xFFFFFFFF,
        tag: str | None = None,
    ) -> tuple[Collider3D, ...]:
        """Return colliders containing one world-space point."""
        point_bounds = AABB3D(float(point.x), float(point.y), float(point.z), 0.0, 0.0, 0.0)
        self._rebuild_index()
        candidates = self._candidate_indexes(point_bounds)
        hits: list[Collider3D] = []
        tests = 0
        for index in candidates:
            collider = self._colliders[index]
            if not collider.enabled or not collider.layer & layer_mask:
                continue
            if tag is not None and collider.tag != tag:
                continue
            tests += 1
            bounds = collider.bounds
            if bounds.contains(point.x, point.y, point.z):
                hits.append(collider)
        self._set_diagnostics(len(candidates), tests, len(hits))
        return tuple(hits)

    def raycast(
        self,
        origin: Vec3,
        direction: Vec3,
        *,
        max_distance: float = inf,
        layer_mask: int = 0xFFFFFFFF,
        tag: str | None = None,
    ) -> tuple[RaycastHit3D, ...]:
        """Cast a 3D ray and return deterministic distance-sorted hits."""
        length = direction.length
        if length == 0:
            raise ValueError("ray direction must be non-zero")
        if max_distance < 0:
            raise ValueError("max_distance must be non-negative")
        dx = float(direction.x) / length
        dy = float(direction.y) / length
        dz = float(direction.z) / length

        self._rebuild_index()
        if isfinite(max_distance):
            end_x = float(origin.x) + dx * max_distance
            end_y = float(origin.y) + dy * max_distance
            end_z = float(origin.z) + dz * max_distance
            broad = AABB3D(
                (float(origin.x) + end_x) / 2.0,
                (float(origin.y) + end_y) / 2.0,
                (float(origin.z) + end_z) / 2.0,
                abs(end_x - float(origin.x)),
                abs(end_y - float(origin.y)),
                abs(end_z - float(origin.z)),
            )
            candidates = self._candidate_indexes(broad)
        else:
            candidates = [
                index for index, collider in enumerate(self._colliders) if collider.enabled
            ]

        hits: list[RaycastHit3D] = []
        tests = 0
        for index in candidates:
            collider = self._colliders[index]
            if not collider.enabled or not collider.layer & layer_mask:
                continue
            if tag is not None and collider.tag != tag:
                continue
            tests += 1
            if isinstance(collider, BoxCollider3D):
                result = self._ray_aabb(origin, dx, dy, dz, collider.bounds, max_distance)
            else:
                result = self._ray_sphere(origin, dx, dy, dz, collider.bounds, max_distance)
            if result is None:
                continue
            distance, normal = result
            hits.append(
                RaycastHit3D(
                    collider=collider,
                    distance=distance,
                    point=Vec3(
                        float(origin.x) + dx * distance,
                        float(origin.y) + dy * distance,
                        float(origin.z) + dz * distance,
                    ),
                    normal=normal,
                )
            )
        hits.sort(key=lambda hit: hit.distance)
        self._set_diagnostics(len(candidates), tests, len(hits))
        return tuple(hits)

    @staticmethod
    def _ray_aabb(
        origin: Vec3,
        dx: float,
        dy: float,
        dz: float,
        bounds: AABB3D,
        max_distance: float,
    ) -> tuple[float, Vec3] | None:
        near = -inf
        far = inf
        normal = Vec3()
        axes = (
            (float(origin.x), dx, bounds.left, bounds.right, Vec3(-1.0, 0.0, 0.0)),
            (float(origin.y), dy, bounds.bottom, bounds.top, Vec3(0.0, -1.0, 0.0)),
            (float(origin.z), dz, bounds.back, bounds.front, Vec3(0.0, 0.0, -1.0)),
        )
        for value, component, minimum, maximum, negative_normal in axes:
            if component == 0.0:
                if value < minimum or value > maximum:
                    return None
                continue
            first = (minimum - value) / component
            second = (maximum - value) / component
            candidate_normal = negative_normal
            if first > second:
                first, second = second, first
                candidate_normal = Vec3(
                    -negative_normal.x,
                    -negative_normal.y,
                    -negative_normal.z,
                )
            if first > near:
                near = first
                normal = candidate_normal
            far = min(far, second)
            if near > far:
                return None

        distance = max(near, 0.0)
        if far < 0.0 or distance > max_distance:
            return None
        return distance, normal

    @staticmethod
    def _ray_sphere(
        origin: Vec3,
        dx: float,
        dy: float,
        dz: float,
        sphere: SphereBounds3D,
        max_distance: float,
    ) -> tuple[float, Vec3] | None:
        ox = float(origin.x) - sphere.x
        oy = float(origin.y) - sphere.y
        oz = float(origin.z) - sphere.z
        projection = ox * dx + oy * dy + oz * dz
        constant = ox * ox + oy * oy + oz * oz - sphere.radius * sphere.radius
        discriminant = projection * projection - constant
        if discriminant < 0:
            return None
        root = sqrt(discriminant)
        distance = -projection - root
        if distance < 0:
            distance = -projection + root
        if distance < 0 or distance > max_distance:
            return None
        hit_x = float(origin.x) + dx * distance
        hit_y = float(origin.y) + dy * distance
        hit_z = float(origin.z) + dz * distance
        normal = Vec3(hit_x - sphere.x, hit_y - sphere.y, hit_z - sphere.z).normalized()
        return distance, normal

    def pairs(self) -> tuple[tuple[Collider3D, Collider3D], ...]:
        """Return deterministic colliding pairs after spatial-hash candidate generation."""
        self._rebuild_index()
        candidate_pairs: set[tuple[int, int]] = set()
        for indexes in self._grid.values():
            for offset, first in enumerate(indexes):
                for second in indexes[offset + 1 :]:
                    if first != second:
                        candidate_pairs.add((min(first, second), max(first, second)))

        hits: list[tuple[Collider3D, Collider3D]] = []
        tests = 0
        for first, second in sorted(candidate_pairs):
            collider = self._colliders[first]
            other = self._colliders[second]
            if not collider.can_collide_with(other):
                continue
            tests += 1
            if _colliders_intersect(collider, other):
                hits.append((collider, other))
        self._set_diagnostics(len(candidate_pairs), tests, len(hits))
        return tuple(hits)
