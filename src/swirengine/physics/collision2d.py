from __future__ import annotations

from dataclasses import dataclass
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
    """Small collision registry suitable for arcade games and early prototypes."""

    def __init__(self) -> None:
        self._colliders: list[BoxCollider2D] = []

    @property
    def colliders(self) -> tuple[BoxCollider2D, ...]:
        return tuple(self._colliders)

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

    def query(
        self, collider: BoxCollider2D, *, tag: str | None = None
    ) -> tuple[BoxCollider2D, ...]:
        hits: list[BoxCollider2D] = []
        for other in self._colliders:
            if other is collider:
                continue
            if tag is not None and other.tag != tag:
                continue
            if collider.collides_with(other):
                hits.append(other)
        return tuple(hits)

    def pairs(self) -> tuple[tuple[BoxCollider2D, BoxCollider2D], ...]:
        hits: list[tuple[BoxCollider2D, BoxCollider2D]] = []
        for index, collider in enumerate(self._colliders):
            for other in self._colliders[index + 1 :]:
                if collider.collides_with(other):
                    hits.append((collider, other))
        return tuple(hits)
