from __future__ import annotations

import math
from collections.abc import Callable, Iterable
from dataclasses import dataclass

import numpy as np

from .graphics.instancing import Frustum3D
from .graphics.mesh import Mesh3D
from .graphics.primitives import Cube3D
from .math.types import Vec3


@dataclass(frozen=True, slots=True)
class VisibilityAABB3D:
    """Conservative world-space axis-aligned bounds used by scene visibility queries."""

    minimum: Vec3
    maximum: Vec3

    def __post_init__(self) -> None:
        if (
            float(self.minimum.x) > float(self.maximum.x)
            or float(self.minimum.y) > float(self.maximum.y)
            or float(self.minimum.z) > float(self.maximum.z)
        ):
            raise ValueError("visibility AABB minimum must not exceed maximum")

    @classmethod
    def from_center_extent(cls, center: Vec3, extent: Vec3) -> VisibilityAABB3D:
        ex = max(0.0, float(extent.x))
        ey = max(0.0, float(extent.y))
        ez = max(0.0, float(extent.z))
        return cls(
            Vec3(float(center.x) - ex, float(center.y) - ey, float(center.z) - ez),
            Vec3(float(center.x) + ex, float(center.y) + ey, float(center.z) + ez),
        )

    @property
    def center(self) -> Vec3:
        return Vec3(
            (float(self.minimum.x) + float(self.maximum.x)) * 0.5,
            (float(self.minimum.y) + float(self.maximum.y)) * 0.5,
            (float(self.minimum.z) + float(self.maximum.z)) * 0.5,
        )

    @property
    def extent(self) -> Vec3:
        return Vec3(
            (float(self.maximum.x) - float(self.minimum.x)) * 0.5,
            (float(self.maximum.y) - float(self.minimum.y)) * 0.5,
            (float(self.maximum.z) - float(self.minimum.z)) * 0.5,
        )

    @property
    def surface_area(self) -> float:
        dx = max(0.0, float(self.maximum.x) - float(self.minimum.x))
        dy = max(0.0, float(self.maximum.y) - float(self.minimum.y))
        dz = max(0.0, float(self.maximum.z) - float(self.minimum.z))
        return 2.0 * (dx * dy + dx * dz + dy * dz)

    def union(self, other: VisibilityAABB3D) -> VisibilityAABB3D:
        return VisibilityAABB3D(
            Vec3(
                min(float(self.minimum.x), float(other.minimum.x)),
                min(float(self.minimum.y), float(other.minimum.y)),
                min(float(self.minimum.z), float(other.minimum.z)),
            ),
            Vec3(
                max(float(self.maximum.x), float(other.maximum.x)),
                max(float(self.maximum.y), float(other.maximum.y)),
                max(float(self.maximum.z), float(other.maximum.z)),
            ),
        )

    def intersects_frustum(self, frustum: Frustum3D) -> bool:
        """Conservative AABB/frustum plane test using the positive vertex."""
        for plane in frustum.planes:
            px = float(self.maximum.x) if plane.x >= 0.0 else float(self.minimum.x)
            py = float(self.maximum.y) if plane.y >= 0.0 else float(self.minimum.y)
            pz = float(self.maximum.z) if plane.z >= 0.0 else float(self.minimum.z)
            if plane.x * px + plane.y * py + plane.z * pz + plane.w < 0.0:
                return False
        return True


@dataclass(slots=True)
class VisibilityEntry3D:
    """One indexed scene object and its conservative visibility bounds."""

    item: object
    bounds: VisibilityAABB3D
    registration_order: int = 0
    dynamic: bool = False
    enabled: bool = True


@dataclass(frozen=True, slots=True)
class VisibilityQueryDiagnostics3D:
    source_entries: int = 0
    static_entries: int = 0
    dynamic_entries: int = 0
    bvh_nodes: int = 0
    node_tests: int = 0
    leaf_tests: int = 0
    frustum_rejected: int = 0
    occlusion_tests: int = 0
    occlusion_rejected: int = 0
    visible_entries: int = 0

    @property
    def object_test_reduction(self) -> float:
        if self.source_entries <= 0:
            return 0.0
        tested = min(self.source_entries, self.leaf_tests)
        return max(0.0, 1.0 - tested / self.source_entries)


@dataclass(frozen=True, slots=True)
class VisibilityQueryResult3D:
    visible: tuple[object, ...]
    diagnostics: VisibilityQueryDiagnostics3D


@dataclass(slots=True)
class _BVHNode3D:
    bounds: VisibilityAABB3D
    entries: tuple[VisibilityEntry3D, ...] = ()
    left: _BVHNode3D | None = None
    right: _BVHNode3D | None = None

    @property
    def leaf(self) -> bool:
        return self.left is None and self.right is None


OcclusionPredicate3D = Callable[[object, VisibilityAABB3D], bool]
BoundsProvider3D = Callable[[object], VisibilityAABB3D]


def visibility_bounds_for(item: object) -> VisibilityAABB3D:
    """Return conservative built-in bounds, or honor a creator-provided ``visibility_bounds``."""
    custom = getattr(item, "visibility_bounds", None)
    if custom is not None:
        value = custom() if callable(custom) else custom
        if not isinstance(value, VisibilityAABB3D):
            raise TypeError("visibility_bounds must be VisibilityAABB3D or return one")
        return value

    if isinstance(item, Cube3D):
        radius = abs(float(item.size)) * math.sqrt(3.0) * 0.5
        return VisibilityAABB3D.from_center_extent(item.position, Vec3(radius, radius, radius))

    if isinstance(item, Mesh3D):
        vertices = np.asarray(item.mesh.vertices, dtype="f4")
        radius = float(np.linalg.norm(vertices, axis=1).max(initial=0.0))
        scale = item.scale
        radius *= max(abs(float(scale.x)), abs(float(scale.y)), abs(float(scale.z)))
        return VisibilityAABB3D.from_center_extent(item.position, Vec3(radius, radius, radius))

    raise TypeError(
        "scene visibility bounds are not known for this object; provide a VisibilityAABB3D "
        "through a visibility_bounds attribute/property"
    )


def _combined_bounds(entries: Iterable[VisibilityEntry3D]) -> VisibilityAABB3D:
    iterator = iter(entries)
    try:
        first = next(iterator)
    except StopIteration as exc:
        raise ValueError("cannot build visibility bounds from an empty entry set") from exc
    bounds = first.bounds
    for entry in iterator:
        bounds = bounds.union(entry.bounds)
    return bounds


def _axis_value(bounds: VisibilityAABB3D, axis: int) -> float:
    center = bounds.center
    if axis == 0:
        return float(center.x)
    if axis == 1:
        return float(center.y)
    return float(center.z)


def _widest_axis(bounds: VisibilityAABB3D) -> int:
    extent = bounds.extent
    values = (float(extent.x), float(extent.y), float(extent.z))
    return max(range(3), key=values.__getitem__)


class SceneVisibilityIndex3D:
    """Additive static-BVH + dynamic-refit visibility index for SwirEngine 1.4.

    Static entries are organized into a deterministic median-split BVH. Dynamic entries stay in a
    separate bounded list whose bounds can be refit without rebuilding the static hierarchy. This is
    intentional: large mostly-static scenes get broad visibility pruning while moving gameplay
    objects avoid forcing full BVH rebuilds every frame.

    ``occlusion`` is deliberately a predicate hook instead of a concrete GPU implementation. A
    later depth/Hi-Z backend can consume the same candidate set without changing the public index.
    The predicate returns ``True`` when an object should remain visible.
    """

    def __init__(self, *, leaf_size: int = 8, bounds_provider: BoundsProvider3D | None = None) -> None:
        size = int(leaf_size)
        if size < 1:
            raise ValueError("leaf_size must be at least 1")
        self.leaf_size = size
        self.bounds_provider = bounds_provider or visibility_bounds_for
        self._entries: dict[int, VisibilityEntry3D] = {}
        self._static_root: _BVHNode3D | None = None
        self._static_dirty = False
        self._static_count = 0
        self._dynamic_count = 0
        self._bvh_nodes = 0
        self._rebuilds = 0
        self._refits = 0
        self._next_registration_order = 0

    @property
    def rebuilds(self) -> int:
        return self._rebuilds

    @property
    def refits(self) -> int:
        return self._refits

    @property
    def entry_count(self) -> int:
        return len(self._entries)

    def add(
        self,
        item: object,
        *,
        bounds: VisibilityAABB3D | None = None,
        dynamic: bool = False,
    ) -> object:
        key = id(item)
        existing = self._entries.get(key)
        if existing is not None and existing.item is not item:
            raise RuntimeError("visibility index identity collision")
        resolved = bounds or self.bounds_provider(item)
        if existing is None:
            self._entries[key] = VisibilityEntry3D(
                item=item,
                bounds=resolved,
                registration_order=self._next_registration_order,
                dynamic=bool(dynamic),
            )
            self._next_registration_order += 1
        else:
            if existing.dynamic != bool(dynamic):
                self._static_dirty = True
            existing.bounds = resolved
            existing.dynamic = bool(dynamic)
            existing.enabled = True
        if not dynamic:
            self._static_dirty = True
        self._recount()
        return item

    def add_many(self, items: Iterable[object], *, dynamic: bool = False) -> tuple[object, ...]:
        values = tuple(items)
        for item in values:
            self.add(item, dynamic=dynamic)
        return values

    def remove(self, item: object) -> bool:
        entry = self._entries.get(id(item))
        if entry is None or entry.item is not item:
            return False
        self._entries.pop(id(item), None)
        if not entry.dynamic:
            self._static_dirty = True
        self._recount()
        return True

    def clear(self) -> None:
        self._entries.clear()
        self._static_root = None
        self._static_dirty = False
        self._static_count = 0
        self._dynamic_count = 0
        self._bvh_nodes = 0
        self._next_registration_order = 0

    def refit(self, item: object, bounds: VisibilityAABB3D | None = None) -> None:
        entry = self._entries.get(id(item))
        if entry is None or entry.item is not item:
            raise KeyError("object is not registered in the visibility index")
        resolved = bounds or self.bounds_provider(item)
        entry.bounds = resolved
        if entry.dynamic:
            self._refits += 1
        else:
            self._static_dirty = True

    def sync_dynamic(self) -> int:
        """Refresh bounds for all dynamic entries and return the number refit."""
        changed = 0
        for entry in self._entries.values():
            if not entry.dynamic:
                continue
            entry.bounds = self.bounds_provider(entry.item)
            changed += 1
        self._refits += changed
        return changed

    def rebuild(self) -> int:
        """Rebuild the static BVH and return the resulting node count."""
        static_entries = tuple(entry for entry in self._entries.values() if not entry.dynamic)
        self._bvh_nodes = 0
        self._static_root = self._build(static_entries) if static_entries else None
        self._static_dirty = False
        self._rebuilds += 1
        return self._bvh_nodes

    def query(
        self,
        frustum: Frustum3D,
        *,
        occlusion: OcclusionPredicate3D | None = None,
        refresh_dynamic: bool = True,
    ) -> VisibilityQueryResult3D:
        if refresh_dynamic:
            self.sync_dynamic()
        if self._static_dirty:
            self.rebuild()

        visible: list[object] = []
        node_tests = 0
        leaf_tests = 0
        frustum_rejected = 0
        occlusion_tests = 0
        occlusion_rejected = 0

        def accept(entry: VisibilityEntry3D) -> None:
            nonlocal leaf_tests, frustum_rejected, occlusion_tests, occlusion_rejected
            if not entry.enabled:
                return
            if not getattr(entry.item, "enabled", True) or not getattr(entry.item, "visible", True):
                return
            leaf_tests += 1
            if not entry.bounds.intersects_frustum(frustum):
                frustum_rejected += 1
                return
            if occlusion is not None:
                occlusion_tests += 1
                if not bool(occlusion(entry.item, entry.bounds)):
                    occlusion_rejected += 1
                    return
            visible.append(entry.item)

        stack: list[_BVHNode3D] = []
        if self._static_root is not None:
            stack.append(self._static_root)
        while stack:
            node = stack.pop()
            node_tests += 1
            if not node.bounds.intersects_frustum(frustum):
                continue
            if node.leaf:
                for entry in node.entries:
                    accept(entry)
            else:
                if node.right is not None:
                    stack.append(node.right)
                if node.left is not None:
                    stack.append(node.left)

        for entry in self._entries.values():
            if entry.dynamic:
                accept(entry)

        diagnostics = VisibilityQueryDiagnostics3D(
            source_entries=len(self._entries),
            static_entries=self._static_count,
            dynamic_entries=self._dynamic_count,
            bvh_nodes=self._bvh_nodes,
            node_tests=node_tests,
            leaf_tests=leaf_tests,
            frustum_rejected=frustum_rejected,
            occlusion_tests=occlusion_tests,
            occlusion_rejected=occlusion_rejected,
            visible_entries=len(visible),
        )
        return VisibilityQueryResult3D(tuple(visible), diagnostics)

    def _build(self, entries: tuple[VisibilityEntry3D, ...]) -> _BVHNode3D:
        bounds = _combined_bounds(entries)
        self._bvh_nodes += 1
        if len(entries) <= self.leaf_size:
            ordered = tuple(sorted(entries, key=lambda entry: entry.registration_order))
            return _BVHNode3D(bounds=bounds, entries=ordered)

        axis = _widest_axis(bounds)
        ordered = tuple(
            sorted(
                entries,
                key=lambda entry: (
                    _axis_value(entry.bounds, axis),
                    entry.registration_order,
                ),
            )
        )
        midpoint = len(ordered) // 2
        left = self._build(ordered[:midpoint])
        right = self._build(ordered[midpoint:])
        return _BVHNode3D(bounds=bounds, left=left, right=right)

    def _recount(self) -> None:
        self._static_count = sum(not entry.dynamic for entry in self._entries.values())
        self._dynamic_count = len(self._entries) - self._static_count
