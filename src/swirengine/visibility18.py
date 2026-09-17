from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from itertools import pairwise
from types import MappingProxyType

Cell = tuple[int, int, int]


def _token(value: str, *, label: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{label} must be a string")
    result = value.strip()
    if not result:
        raise ValueError(f"{label} must not be empty")
    if len(result) > 128:
        raise ValueError(f"{label} must contain at most 128 characters")
    return result


def _positive_int(value: int, *, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{label} must be an integer")
    if value < 1:
        raise ValueError(f"{label} must be >= 1")
    return value


def _integer(value: int, *, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{label} must be an integer")
    return value


def _number(value: float, *, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{label} must be a number")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{label} must be finite")
    return result


class VisibilityError(RuntimeError):
    """Stable creator-facing visibility/LOD failure."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


@dataclass(frozen=True, slots=True)
class AABB3:
    """Backend-neutral axis-aligned bounds usable by 2D and 3D scenes.

    A 2D object can use ``z_min == z_max == 0``. A 3D object supplies its full
    world-space extent. The class deliberately contains no renderer objects.
    """

    x_min: float
    y_min: float
    z_min: float
    x_max: float
    y_max: float
    z_max: float

    def __post_init__(self) -> None:
        for name in ("x_min", "y_min", "z_min", "x_max", "y_max", "z_max"):
            object.__setattr__(self, name, _number(getattr(self, name), label=name))
        if self.x_min > self.x_max:
            raise ValueError("x_min must be <= x_max")
        if self.y_min > self.y_max:
            raise ValueError("y_min must be <= y_max")
        if self.z_min > self.z_max:
            raise ValueError("z_min must be <= z_max")

    @property
    def center(self) -> tuple[float, float, float]:
        return (
            (self.x_min + self.x_max) * 0.5,
            (self.y_min + self.y_max) * 0.5,
            (self.z_min + self.z_max) * 0.5,
        )

    def intersects(self, other: AABB3) -> bool:
        if not isinstance(other, AABB3):
            raise TypeError("other must be an AABB3")
        return not (
            self.x_max < other.x_min
            or self.x_min > other.x_max
            or self.y_max < other.y_min
            or self.y_min > other.y_max
            or self.z_max < other.z_min
            or self.z_min > other.z_max
        )

    def portable(self) -> Mapping[str, float]:
        return MappingProxyType(
            {
                "x_min": self.x_min,
                "y_min": self.y_min,
                "z_min": self.z_min,
                "x_max": self.x_max,
                "y_max": self.y_max,
                "z_max": self.z_max,
            }
        )


@dataclass(frozen=True, slots=True)
class VisibilityItem:
    """One spatially indexed renderable candidate with creator-owned LOD bands."""

    item_id: str
    bounds: AABB3
    layer: int = 0
    priority: int = 0
    lod_thresholds: tuple[float, ...] = ()
    lod_hysteresis: float = 0.0
    tags: tuple[str, ...] = ()
    _fingerprint: str = field(init=False, repr=False, compare=False, hash=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "item_id", _token(self.item_id, label="item_id"))
        if not isinstance(self.bounds, AABB3):
            raise TypeError("bounds must be an AABB3")
        object.__setattr__(self, "layer", _integer(self.layer, label="layer"))
        object.__setattr__(self, "priority", _integer(self.priority, label="priority"))
        if isinstance(self.lod_thresholds, (str, bytes)):
            raise TypeError("lod_thresholds must be an iterable of distances")
        thresholds = tuple(
            _number(value, label="lod threshold") for value in self.lod_thresholds
        )
        if any(value < 0.0 for value in thresholds):
            raise ValueError("lod thresholds must be >= 0")
        if any(right <= left for left, right in pairwise(thresholds)):
            raise ValueError("lod thresholds must be strictly increasing")
        object.__setattr__(self, "lod_thresholds", thresholds)
        hysteresis = _number(self.lod_hysteresis, label="lod_hysteresis")
        if hysteresis < 0.0:
            raise ValueError("lod_hysteresis must be >= 0")
        object.__setattr__(self, "lod_hysteresis", hysteresis)
        if isinstance(self.tags, (str, bytes)):
            raise TypeError("tags must be an iterable of strings")
        tags = tuple(sorted({_token(tag, label="tag") for tag in self.tags}))
        object.__setattr__(self, "tags", tags)
        payload = self._portable_payload()
        object.__setattr__(
            self,
            "_fingerprint",
            hashlib.sha256(
                json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
            ).hexdigest(),
        )

    @property
    def max_lod(self) -> int:
        return len(self.lod_thresholds)

    @property
    def fingerprint(self) -> str:
        return self._fingerprint

    def _portable_payload(self) -> dict[str, object]:
        return {
            "item_id": self.item_id,
            "bounds": dict(self.bounds.portable()),
            "layer": self.layer,
            "priority": self.priority,
            "lod_thresholds": list(self.lod_thresholds),
            "lod_hysteresis": self.lod_hysteresis,
            "tags": list(self.tags),
        }

    def portable(self) -> Mapping[str, object]:
        return MappingProxyType(self._portable_payload())


@dataclass(frozen=True, slots=True)
class VisibleSubmission:
    item_id: str
    lod: int
    distance: float
    layer: int
    priority: int
    item_fingerprint: str

    def portable(self) -> Mapping[str, object]:
        return MappingProxyType(
            {
                "item_id": self.item_id,
                "lod": self.lod,
                "distance": self.distance,
                "layer": self.layer,
                "priority": self.priority,
                "item_fingerprint": self.item_fingerprint,
            }
        )


@dataclass(frozen=True, slots=True)
class VisibilityDiagnostics:
    indexed_items: int
    indexed_cells: int
    query_cells: int
    bucket_references: int
    unique_candidates: int
    duplicate_bucket_hits: int
    bounds_culled: int
    predicate_culled: int
    visible_items: int
    lod_transitions: int
    tracked_lods: int

    def portable(self) -> Mapping[str, int]:
        return MappingProxyType(
            {name: getattr(self, name) for name in self.__dataclass_fields__}
        )


@dataclass(frozen=True, slots=True)
class VisibilityPlan:
    submissions: tuple[VisibleSubmission, ...]
    diagnostics: VisibilityDiagnostics
    fingerprint: str

    def portable(self) -> Mapping[str, object]:
        return MappingProxyType(
            {
                "submissions": [dict(item.portable()) for item in self.submissions],
                "diagnostics": dict(self.diagnostics.portable()),
                "fingerprint": self.fingerprint,
            }
        )


class VisibilitySession:
    """Bounded cross-frame LOD state used only for deterministic hysteresis."""

    def __init__(self, *, max_tracked: int = 65_536) -> None:
        self.max_tracked = _positive_int(max_tracked, label="max_tracked")
        self._last_lod: dict[str, int] = {}

    @property
    def tracked(self) -> int:
        return len(self._last_lod)

    def last_lod(self, item_id: str) -> int | None:
        item_id = _token(item_id, label="item_id")
        return self._last_lod.get(item_id)

    def forget(self, item_id: str) -> bool:
        item_id = _token(item_id, label="item_id")
        return self._last_lod.pop(item_id, None) is not None

    def clear(self) -> None:
        self._last_lod.clear()

    def _commit(self, values: Mapping[str, int]) -> None:
        new_ids = sum(1 for item_id in values if item_id not in self._last_lod)
        if len(self._last_lod) + new_ids > self.max_tracked:
            raise VisibilityError(
                "lod-state-limit",
                "visibility LOD state limit would be exceeded",
            )
        self._last_lod.update(values)

    def state_fingerprint(self) -> str:
        payload = [[item_id, self._last_lod[item_id]] for item_id in sorted(self._last_lod)]
        return hashlib.sha256(
            json.dumps(payload, separators=(",", ":")).encode("utf-8")
        ).hexdigest()


class VisibilityIndex:
    """Bounded deterministic spatial candidate index for 2D and 3D scenes.

    The index is renderer-independent. It performs conservative uniform-grid candidate
    collection and exact AABB overlap. A creator/backend may provide a stricter predicate
    (for example a camera frustum or portal test) and a LOD policy callback without
    changing stable 1.x renderer behavior.
    """

    def __init__(
        self,
        *,
        cell_size: float = 32.0,
        max_items: int = 65_536,
        max_cells: int = 262_144,
        max_cells_per_item: int = 4_096,
        max_query_cells: int = 65_536,
        max_candidates: int = 65_536,
    ) -> None:
        self.cell_size = _number(cell_size, label="cell_size")
        if self.cell_size <= 0.0:
            raise ValueError("cell_size must be > 0")
        self.max_items = _positive_int(max_items, label="max_items")
        self.max_cells = _positive_int(max_cells, label="max_cells")
        self.max_cells_per_item = _positive_int(
            max_cells_per_item, label="max_cells_per_item"
        )
        self.max_query_cells = _positive_int(max_query_cells, label="max_query_cells")
        self.max_candidates = _positive_int(max_candidates, label="max_candidates")
        self._items: dict[str, VisibilityItem] = {}
        self._cells: dict[Cell, set[str]] = {}
        self._item_cells: dict[str, tuple[Cell, ...]] = {}

    @property
    def item_count(self) -> int:
        return len(self._items)

    @property
    def cell_count(self) -> int:
        return len(self._cells)

    def get(self, item_id: str) -> VisibilityItem | None:
        item_id = _token(item_id, label="item_id")
        return self._items.get(item_id)

    def register(self, item: VisibilityItem) -> None:
        if not isinstance(item, VisibilityItem):
            raise TypeError("item must be a VisibilityItem")
        if item.item_id in self._items:
            raise VisibilityError("duplicate-item", f"visibility item already exists: {item.item_id}")
        if len(self._items) >= self.max_items:
            raise VisibilityError("item-limit", "visibility item limit reached")
        cells = self._cells_for_bounds(
            item.bounds,
            limit=self.max_cells_per_item,
            error_code="item-cell-limit",
        )
        new_cells = sum(1 for cell in cells if cell not in self._cells)
        if len(self._cells) + new_cells > self.max_cells:
            raise VisibilityError("cell-limit", "visibility spatial cell limit would be exceeded")
        self._items[item.item_id] = item
        self._item_cells[item.item_id] = cells
        for cell in cells:
            self._cells.setdefault(cell, set()).add(item.item_id)

    def replace(self, item: VisibilityItem) -> None:
        if not isinstance(item, VisibilityItem):
            raise TypeError("item must be a VisibilityItem")
        if item.item_id not in self._items:
            raise VisibilityError("missing-item", f"visibility item does not exist: {item.item_id}")
        cells = self._cells_for_bounds(
            item.bounds,
            limit=self.max_cells_per_item,
            error_code="item-cell-limit",
        )
        old_cells = self._item_cells[item.item_id]
        cells_removed_entirely = {
            cell for cell in old_cells if self._cells[cell] == {item.item_id}
        }
        remaining_cells = len(self._cells) - len(cells_removed_entirely)
        new_cells = sum(
            1
            for cell in cells
            if cell not in self._cells or cell in cells_removed_entirely
        )
        if remaining_cells + new_cells > self.max_cells:
            raise VisibilityError("cell-limit", "visibility spatial cell limit would be exceeded")
        self._detach(item.item_id)
        self._items[item.item_id] = item
        self._item_cells[item.item_id] = cells
        for cell in cells:
            self._cells.setdefault(cell, set()).add(item.item_id)

    def remove(self, item_id: str) -> bool:
        item_id = _token(item_id, label="item_id")
        if item_id not in self._items:
            return False
        self._detach(item_id)
        del self._items[item_id]
        del self._item_cells[item_id]
        return True

    def query(
        self,
        bounds: AABB3,
        observer: tuple[float, float, float],
        *,
        session: VisibilitySession | None = None,
        predicate: Callable[[VisibilityItem], bool] | None = None,
        lod_policy: Callable[[VisibilityItem, float, int | None, int], int] | None = None,
        required_tags: Iterable[str] = (),
    ) -> VisibilityPlan:
        if not isinstance(bounds, AABB3):
            raise TypeError("bounds must be an AABB3")
        if not isinstance(observer, tuple) or len(observer) != 3:
            raise TypeError("observer must be a (x, y, z) tuple")
        observer_xyz = tuple(
            _number(value, label="observer coordinate") for value in observer
        )
        if session is None:
            session = VisibilitySession(max_tracked=self.max_items)
        elif not isinstance(session, VisibilitySession):
            raise TypeError("session must be a VisibilitySession")
        if predicate is not None and not callable(predicate):
            raise TypeError("predicate must be callable")
        if lod_policy is not None and not callable(lod_policy):
            raise TypeError("lod_policy must be callable")
        if isinstance(required_tags, (str, bytes)):
            raise TypeError("required_tags must be an iterable of strings")
        tag_filter = frozenset(_token(tag, label="required tag") for tag in required_tags)

        query_cells = self._cells_for_bounds(
            bounds,
            limit=self.max_query_cells,
            error_code="query-cell-limit",
        )
        candidate_ids: set[str] = set()
        bucket_references = 0
        for cell in query_cells:
            bucket = self._cells.get(cell)
            if not bucket:
                continue
            bucket_references += len(bucket)
            candidate_ids.update(bucket)
            if len(candidate_ids) > self.max_candidates:
                raise VisibilityError(
                    "candidate-limit",
                    "visibility candidate limit exceeded",
                )

        bounds_culled = 0
        predicate_culled = 0
        transitions = 0
        submissions: list[VisibleSubmission] = []
        pending_lods: dict[str, int] = {}
        for item_id in sorted(candidate_ids):
            item = self._items[item_id]
            if not item.bounds.intersects(bounds):
                bounds_culled += 1
                continue
            if tag_filter and not tag_filter.issubset(item.tags):
                predicate_culled += 1
                continue
            if predicate is not None:
                try:
                    accepted = predicate(item)
                except Exception as exc:
                    raise VisibilityError(
                        "predicate-failed",
                        f"visibility predicate failed for {item.item_id}: {exc}",
                    ) from exc
                if not isinstance(accepted, bool):
                    raise VisibilityError(
                        "predicate-result",
                        "visibility predicate must return bool",
                    )
                if not accepted:
                    predicate_culled += 1
                    continue
            distance = self._distance(item.bounds.center, observer_xyz)
            previous = session.last_lod(item.item_id)
            default_lod = self._default_lod(item, distance, previous)
            selected = default_lod
            if lod_policy is not None:
                try:
                    selected = lod_policy(item, distance, previous, default_lod)
                except Exception as exc:
                    raise VisibilityError(
                        "lod-policy-failed",
                        f"LOD policy failed for {item.item_id}: {exc}",
                    ) from exc
                if isinstance(selected, bool) or not isinstance(selected, int):
                    raise VisibilityError("lod-policy-result", "LOD policy must return an integer")
                if selected < 0 or selected > item.max_lod:
                    raise VisibilityError(
                        "lod-policy-range",
                        f"LOD policy returned {selected} outside 0..{item.max_lod}",
                    )
            if previous is not None and selected != previous:
                transitions += 1
            pending_lods[item.item_id] = selected
            submissions.append(
                VisibleSubmission(
                    item_id=item.item_id,
                    lod=selected,
                    distance=distance,
                    layer=item.layer,
                    priority=item.priority,
                    item_fingerprint=item.fingerprint,
                )
            )

        submissions.sort(
            key=lambda item: (
                item.layer,
                -item.priority,
                item.lod,
                item.distance,
                item.item_id,
            )
        )
        session._commit(pending_lods)
        diagnostics = VisibilityDiagnostics(
            indexed_items=len(self._items),
            indexed_cells=len(self._cells),
            query_cells=len(query_cells),
            bucket_references=bucket_references,
            unique_candidates=len(candidate_ids),
            duplicate_bucket_hits=max(0, bucket_references - len(candidate_ids)),
            bounds_culled=bounds_culled,
            predicate_culled=predicate_culled,
            visible_items=len(submissions),
            lod_transitions=transitions,
            tracked_lods=session.tracked,
        )
        payload = {
            "submissions": [dict(item.portable()) for item in submissions],
            "diagnostics": dict(diagnostics.portable()),
        }
        fingerprint = hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        return VisibilityPlan(tuple(submissions), diagnostics, fingerprint)

    def state_fingerprint(self) -> str:
        payload = {
            "cell_size": self.cell_size,
            "items": [
                dict(self._items[item_id].portable()) for item_id in sorted(self._items)
            ],
        }
        return hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()

    def _detach(self, item_id: str) -> None:
        for cell in self._item_cells[item_id]:
            bucket = self._cells[cell]
            bucket.remove(item_id)
            if not bucket:
                del self._cells[cell]

    def _cells_for_bounds(
        self,
        bounds: AABB3,
        *,
        limit: int,
        error_code: str,
    ) -> tuple[Cell, ...]:
        x0 = math.floor(bounds.x_min / self.cell_size)
        y0 = math.floor(bounds.y_min / self.cell_size)
        z0 = math.floor(bounds.z_min / self.cell_size)
        x1 = math.floor(bounds.x_max / self.cell_size)
        y1 = math.floor(bounds.y_max / self.cell_size)
        z1 = math.floor(bounds.z_max / self.cell_size)
        nx = x1 - x0 + 1
        ny = y1 - y0 + 1
        nz = z1 - z0 + 1
        count = nx * ny * nz
        if count > limit:
            raise VisibilityError(error_code, f"spatial bounds require {count} cells; limit is {limit}")
        return tuple(
            (x, y, z)
            for x in range(x0, x1 + 1)
            for y in range(y0, y1 + 1)
            for z in range(z0, z1 + 1)
        )

    @staticmethod
    def _distance(
        center: tuple[float, float, float],
        observer: tuple[float, float, float],
    ) -> float:
        dx = center[0] - observer[0]
        dy = center[1] - observer[1]
        dz = center[2] - observer[2]
        return math.sqrt(dx * dx + dy * dy + dz * dz)

    @staticmethod
    def _default_lod(item: VisibilityItem, distance: float, previous: int | None) -> int:
        if previous is None:
            lod = 0
            for threshold in item.lod_thresholds:
                if distance >= threshold:
                    lod += 1
                else:
                    break
            return lod

        lod = min(max(previous, 0), item.max_lod)
        hysteresis = item.lod_hysteresis
        while lod < item.max_lod and distance >= item.lod_thresholds[lod] + hysteresis:
            lod += 1
        while lod > 0 and distance < item.lod_thresholds[lod - 1] - hysteresis:
            lod -= 1
        return lod
