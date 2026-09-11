from __future__ import annotations


class Scene:
    def __init__(self) -> None:
        self._objects: list[object] = []

    @property
    def objects(self) -> tuple[object, ...]:
        return tuple(self._objects)

    def add(self, obj: object) -> object:
        if obj not in self._objects:
            self._objects.append(obj)
        return obj

    def remove(self, obj: object) -> None:
        if obj in self._objects:
            self._objects.remove(obj)

    def clear(self) -> None:
        self._objects.clear()

    def update(self, dt: float) -> None:
        for obj in tuple(self._objects):
            if not getattr(obj, "enabled", True):
                continue
            update = getattr(obj, "update", None)
            if callable(update):
                update(dt)

    def by_type(self, cls: type):
        return tuple(obj for obj in self._objects if isinstance(obj, cls))
