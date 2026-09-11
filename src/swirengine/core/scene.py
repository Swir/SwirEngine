from __future__ import annotations

from collections.abc import Iterator
from typing import TypeVar

T = TypeVar("T")


class Scene:
    def __init__(self) -> None:
        self._objects: list[object] = []

    @property
    def objects(self) -> tuple[object, ...]:
        return tuple(self._objects)

    def __iter__(self) -> Iterator[object]:
        return iter(tuple(self._objects))

    def __len__(self) -> int:
        return len(self._objects)

    def __contains__(self, obj: object) -> bool:
        return any(existing is obj for existing in self._objects)

    def add(self, obj: T) -> T:
        # Scene membership is based on object identity, not dataclass value equality.
        # Games routinely contain many separate entities with identical values.
        if not any(existing is obj for existing in self._objects):
            self._objects.append(obj)
        return obj

    def add_many(self, *objects: object) -> tuple[object, ...]:
        for obj in objects:
            self.add(obj)
        return objects

    def remove(self, obj: object) -> bool:
        for index, existing in enumerate(self._objects):
            if existing is obj:
                del self._objects[index]
                return True
        return False

    def clear(self) -> None:
        self._objects.clear()

    def update(self, dt: float) -> None:
        for obj in tuple(self._objects):
            if not getattr(obj, "enabled", True):
                continue
            update = getattr(obj, "update", None)
            if callable(update):
                update(dt)

    def by_type(self, cls: type[T]) -> tuple[T, ...]:
        return tuple(obj for obj in self._objects if isinstance(obj, cls))

    def find(self, name: str) -> object | None:
        return next((obj for obj in self._objects if getattr(obj, "name", None) == name), None)

    def find_all(self, name: str) -> tuple[object, ...]:
        return tuple(obj for obj in self._objects if getattr(obj, "name", None) == name)

    def tagged(self, tag: str) -> tuple[object, ...]:
        return tuple(obj for obj in self._objects if tag in getattr(obj, "tags", set()))
