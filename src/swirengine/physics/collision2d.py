from __future__ import annotations

from dataclasses import dataclass
from math import floor, inf, sqrt
from typing import Any, cast


@dataclass(frozen=True, slots=True)
class AABB:
    """Axis-aligned rectangle using the same center-based coordinates as 2D sprites."""

    x: float
    y: float
    width: float
    height: float

    def __post_init__(self) -> None:
        if self.width < 0 or self.height < 0:
            raise ValueError("AABB width and height must be non-negative")

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

    def intersects(self, other: AABB) -> bool:
        return not (
            self.right < other.left
            or self.left > other.right
            or self.top < other.bottom
            or self.bottom > other.top
        )

    def contains(self, x: float, y: float) -> bool:
        return self.left <= x <= self.right and self.bottom <= y <= self.top


@dataclass(frozen=True, slots=True)
class CollisionDiagnostics:
    """Diagnostics from the most recent broad/narrow-phase operation."""

    collider_count: int = 0
    occupied_cells: int = 0
    candidate_count: int = 0
    narrow_phase_tests: int = 0
    hits: int = 0


@dataclass(frozen=True, slots=True)
class RaycastHit2D:
    """A deterministic 2D ray/segment hit sorted by distance from the origin."""

    collider: BoxCollider2D
    distance: float
    x: float
    y: float
    normal_x: float
    normal_y: float


class BoxCollider2D:
    """A lightweight box collider attached to an object exposing ``x`` and ``y``."""

    def __init__(
        self,
        target: object,
        *,
        width: float | None = None,
        height: float | None = None,
        offset_x: float = 0.0,
        offset_y: float = 0.0,
        enabled: bool = True,
        layer: int = 1,
        mask: int = 0xFFFFFFFF,
        tag: str = "",
    ) -> None:
        self.target = target
        self.width = width
        self.height = height
        self.offset_x = float(offset_x)
        self.offset_y = float(offset_y)
        self.enabled = bool(enabled)
        self.layer = int(layer)
        self.mask = int(mask)
        self.tag = tag

    @property
    def bounds(self) -> AABB:
        target = cast(Any, self.target)
        try:
            x = float(target.x)
            y = float(target.y)
        except AttributeError as exc:
            raise TypeError("collider target must expose x and y attributes") from exc

        width = self.width
        height = self.height
        if width is None:
            try:
                width = target.width
            except AttributeError:
                width = None
        if height is None:
            try:
                height = target.height
            except AttributeError:
                height = None
        if width is None or height is None:
            raise ValueError(
                "collider size is unknown; set collider width/height or target width/height"
            )

        return AABB(
            x=x + self.offset_x,
            y=y + self.offset_y,
            width=float(width),
            height=float(height),
        )

    def can_collide_with(self, other: BoxCollider2D) -> bool:
        return bool(
            self.enabled
            and other.enabled
            and self.mask & other.layer
            and other.mask & self.layer
        )

    def collides_with(self, other: BoxCollider2D) -> bool:
        return self.can_collide_with(other) and self.bounds.intersects(other.bounds)


class CollisionWorld2D:
    """2D collision registry with a spatial-hash broad phase and creator queries.

    The spatial index is rebuilt from live collider bounds before every public query. This keeps
    moving targets correct without requiring users to manually synchronize transforms while still
    replacing all-pairs narrow-phase work with local-cell candidate generation.
    """

    def __init__(self, *, cell_size: float = 128.0) -> None:
        if cell_size <= 0:
            raise ValueError("cell_size must be greater than zero")
        self.cell_size = float(cell_size)
        self._colliders: list[BoxCollider2D] = []
        self._grid: dict[tuple[int, int], list[int]] = {}
        self._bounds: list[AABB] = []
        self._diagnostics = CollisionDiagnostics()

    @property
    def colliders(self) -> tuple[BoxCollider2D, ...]:
        return tuple(self._colliders)

    @property
    def diagnostics(self) -> CollisionDiagnostics:
        return self._diagnostics

    def add(self, collider: BoxCollider2D) -> BoxCollider2D:
        if not any(existing is collider for existing in self._colliders):
            self._colliders.append(collider)
        return collider

    def remove(self, collider: BoxCollider2D) -> bool:
        for index, existing in enumerate(self._colliders):
            if existing is collider:
                del self._colliders[index]
                return True
        return False

    def clear(self) -> None:
        self._colliders.clear()
        self._grid.clear()
        self._bounds.clear()
        self._diagnostics = CollisionDiagnostics()

    def _cells_for(self, bounds: AABB) -> tuple[tuple[int, int], ...]:
        left = floor(bounds.left / self.cell_size)
        right = floor(bounds.right / self.cell_size)
        bottom = floor(bounds.bottom / self.cell_size)
        top = floor(bounds.top / self.cell_size)
        return tuple(
            (cell_x, cell_y)
            for cell_y in range(bottom, top + 1)
            for cell_x in range(left, right + 1)
        )

    def _rebuild_index(self) -> None:
        self._grid = {}
        self._bounds = []
        for index, collider in enumerate(self._colliders):
            bounds = collider.bounds
            self._bounds.append(bounds)
            if not collider.enabled:
                continue
            for cell in self._cells_for(bounds):
                self._grid.setdefault(cell, []).append(index)

    def _candidate_indexes(self, bounds: AABB) -> list[int]:
        indexes: set[int] = set()
        for cell in self._cells_for(bounds):
            indexes.update(self._grid.get(cell, ()))
        return sorted(indexes)

    def _set_diagnostics(self, candidates: int, tests: int, hits: int) -> None:
        self._diagnostics = CollisionDiagnostics(
            collider_count=len(self._colliders),
            occupied_cells=len(self._grid),
            candidate_count=candidates,
            narrow_phase_tests=tests,
            hits=hits,
        )

    def query(
        self, collider: BoxCollider2D, *, tag: str | None = None
    ) -> tuple[BoxCollider2D, ...]:
        self._rebuild_index()
        bounds = collider.bounds
        candidates = self._candidate_indexes(bounds)
        hits: list[BoxCollider2D] = []
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
            if bounds.intersects(self._bounds[index]):
                hits.append(other)
        self._set_diagnostics(len(candidates), tests, len(hits))
        return tuple(hits)

    def overlap_aabb(
        self,
        bounds: AABB,
        *,
        layer_mask: int = 0xFFFFFFFF,
        tag: str | None = None,
    ) -> tuple[BoxCollider2D, ...]:
        """Return enabled colliders overlapping ``bounds`` in registry order."""
        self._rebuild_index()
        candidates = self._candidate_indexes(bounds)
        hits: list[BoxCollider2D] = []
        tests = 0
        for index in candidates:
            collider = self._colliders[index]
            if not collider.enabled or not collider.layer & layer_mask:
                continue
            if tag is not None and collider.tag != tag:
                continue
            tests += 1
            if bounds.intersects(self._bounds[index]):
                hits.append(collider)
        self._set_diagnostics(len(candidates), tests, len(hits))
        return tuple(hits)

    def query_point(
        self,
        x: float,
        y: float,
        *,
        layer_mask: int = 0xFFFFFFFF,
        tag: str | None = None,
    ) -> tuple[BoxCollider2D, ...]:
        """Return colliders containing a world-space point."""
        point = AABB(float(x), float(y), 0.0, 0.0)
        return tuple(
            collider
            for collider in self.overlap_aabb(point, layer_mask=layer_mask, tag=tag)
            if collider.bounds.contains(x, y)
        )

    def raycast(
        self,
        origin_x: float,
        origin_y: float,
        direction_x: float,
        direction_y: float,
        *,
        max_distance: float = inf,
        layer_mask: int = 0xFFFFFFFF,
        tag: str | None = None,
    ) -> tuple[RaycastHit2D, ...]:
        """Cast a normalized-by-the-engine 2D ray and return distance-sorted AABB hits."""
        length = sqrt(direction_x * direction_x + direction_y * direction_y)
        if length == 0:
            raise ValueError("ray direction must be non-zero")
        if max_distance < 0:
            raise ValueError("max_distance must be non-negative")
        dx = direction_x / length
        dy = direction_y / length

        self._rebuild_index()
        hits: list[RaycastHit2D] = []
        tests = 0
        candidates = 0
        for index, collider in enumerate(self._colliders):
            if not collider.enabled or not collider.layer & layer_mask:
                continue
            if tag is not None and collider.tag != tag:
                continue
            candidates += 1
            tests += 1
            hit = self._ray_aabb(origin_x, origin_y, dx, dy, self._bounds[index], max_distance)
            if hit is not None:
                distance, normal_x, normal_y = hit
                hits.append(
                    RaycastHit2D(
                        collider=collider,
                        distance=distance,
                        x=origin_x + dx * distance,
                        y=origin_y + dy * distance,
                        normal_x=normal_x,
                        normal_y=normal_y,
                    )
                )
        hits.sort(key=lambda hit: hit.distance)
        self._set_diagnostics(candidates, tests, len(hits))
        return tuple(hits)

    @staticmethod
    def _ray_aabb(
        origin_x: float,
        origin_y: float,
        dx: float,
        dy: float,
        bounds: AABB,
        max_distance: float,
    ) -> tuple[float, float, float] | None:
        near = -inf
        far = inf
        normal_x = 0.0
        normal_y = 0.0

        for origin, direction, minimum, maximum, axis in (
            (origin_x, dx, bounds.left, bounds.right, 0),
            (origin_y, dy, bounds.bottom, bounds.top, 1),
        ):
            if direction == 0.0:
                if origin < minimum or origin > maximum:
                    return None
                continue
            first = (minimum - origin) / direction
            second = (maximum - origin) / direction
            sign = -1.0
            if first > second:
                first, second = second, first
                sign = 1.0
            if first > near:
                near = first
                if axis == 0:
                    normal_x, normal_y = sign, 0.0
                else:
                    normal_x, normal_y = 0.0, sign
            far = min(far, second)
            if near > far:
                return None

        distance = max(near, 0.0)
        if far < 0.0 or distance > max_distance:
            return None
        return distance, normal_x, normal_y

    def pairs(self) -> tuple[tuple[BoxCollider2D, BoxCollider2D], ...]:
        self._rebuild_index()
        candidate_pairs: set[tuple[int, int]] = set()
        for indexes in self._grid.values():
            for offset, first in enumerate(indexes):
                for second in indexes[offset + 1 :]:
                    if first != second:
                        candidate_pairs.add((min(first, second), max(first, second)))

        hits: list[tuple[BoxCollider2D, BoxCollider2D]] = []
        tests = 0
        for first, second in sorted(candidate_pairs):
            collider = self._colliders[first]
            other = self._colliders[second]
            if not collider.can_collide_with(other):
                continue
            tests += 1
            if self._bounds[first].intersects(self._bounds[second]):
                hits.append((collider, other))
        self._set_diagnostics(len(candidate_pairs), tests, len(hits))
        return tuple(hits)
