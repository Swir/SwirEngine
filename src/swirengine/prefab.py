from __future__ import annotations

import copy
from collections.abc import Callable, Iterator, Mapping, Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, TypeAlias

if TYPE_CHECKING:
    from .core.scene import Scene

PrefabSelector: TypeAlias = int | str
PrefabOverrides: TypeAlias = Mapping[PrefabSelector, Mapping[str, object]]


@dataclass(frozen=True, slots=True)
class PrefabInstance:
    """A concrete set of objects cloned from a :class:`Prefab`."""

    objects: tuple[object, ...]
    prefab_name: str = ""

    def __iter__(self) -> Iterator[object]:
        return iter(self.objects)

    def __len__(self) -> int:
        return len(self.objects)

    @property
    def root(self) -> object | None:
        return self.objects[0] if self.objects else None

    def find(self, name: str) -> object | None:
        return next((obj for obj in self.objects if getattr(obj, "name", None) == name), None)

    def tagged(self, tag: str) -> tuple[object, ...]:
        return tuple(obj for obj in self.objects if tag in getattr(obj, "tags", set()))

    def remove_from(self, scene: Scene) -> int:
        """Remove every object in this instance from ``scene`` and return the count removed."""
        return len(scene.remove_many(*self.objects))


class Prefab:
    """Reusable deep-copy blueprint for a graph of scene objects.

    The complete object tuple is deep-copied as one graph. This is important for creator
    objects that reference one another: references between prefab members remain internal to
    each spawned instance instead of pointing back to the source objects or another spawn.
    """

    def __init__(self, *objects: object, name: str = "") -> None:
        if not objects:
            raise ValueError("a prefab requires at least one object")
        self.name = str(name)
        self._templates = copy.deepcopy(tuple(objects))

    @classmethod
    def from_scene(
        cls,
        scene: Scene,
        *,
        name: str = "",
        predicate: Callable[[object], bool] | None = None,
    ) -> Prefab:
        objects = tuple(
            obj for obj in scene.objects if predicate is None or bool(predicate(obj))
        )
        if not objects:
            raise ValueError("scene selection produced an empty prefab")
        return cls(*objects, name=name)

    @property
    def size(self) -> int:
        return len(self._templates)

    def templates(self) -> tuple[object, ...]:
        """Return safe copies of the stored templates for inspection."""
        return copy.deepcopy(self._templates)

    @staticmethod
    def _resolve_selector(objects: tuple[object, ...], selector: PrefabSelector) -> object:
        if isinstance(selector, int):
            try:
                return objects[selector]
            except IndexError as exc:
                raise KeyError(f"prefab object index {selector} is out of range") from exc

        matches = tuple(obj for obj in objects if getattr(obj, "name", None) == selector)
        if not matches:
            raise KeyError(f"prefab has no object named {selector!r}")
        if len(matches) > 1:
            raise KeyError(f"prefab object name {selector!r} is ambiguous")
        return matches[0]

    @classmethod
    def _apply_overrides(
        cls,
        objects: tuple[object, ...],
        overrides: PrefabOverrides,
    ) -> None:
        for selector, values in overrides.items():
            target = cls._resolve_selector(objects, selector)
            for attribute, value in values.items():
                if not hasattr(target, attribute):
                    raise AttributeError(
                        f"{type(target).__name__} has no prefab-overridable attribute {attribute!r}"
                    )
                setattr(target, attribute, copy.deepcopy(value))

    def instantiate(
        self,
        scene: Scene | None = None,
        *,
        overrides: PrefabOverrides | None = None,
    ) -> PrefabInstance:
        """Clone the prefab and optionally register the new objects with ``scene``.

        ``overrides`` can target an object by zero-based index or by its unique ``name``.
        Attribute values are deep-copied so mutable override data is never shared between
        the caller and the spawned instance.
        """
        objects = copy.deepcopy(self._templates)
        if overrides:
            self._apply_overrides(objects, overrides)
        if scene is not None:
            scene.add_many(*objects)
        return PrefabInstance(objects=objects, prefab_name=self.name)

    def instantiate_many(
        self,
        count: int,
        scene: Scene | None = None,
        *,
        overrides: Sequence[PrefabOverrides | None] | None = None,
    ) -> tuple[PrefabInstance, ...]:
        """Instantiate a deterministic prefab batch for rooms, waves and world chunks.

        ``overrides`` may provide one override mapping per instance. All instances remain
        independent deep-copied graphs and are registered in spawn order.
        """
        resolved_count = int(count)
        if resolved_count < 0:
            raise ValueError("count must be >= 0")
        if overrides is not None and len(overrides) != resolved_count:
            raise ValueError("overrides length must match count")
        instances: list[PrefabInstance] = []
        for index in range(resolved_count):
            instance_overrides = None if overrides is None else overrides[index]
            instances.append(self.instantiate(scene, overrides=instance_overrides))
        return tuple(instances)
