from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Any

from .core.scene import Scene
from .serialization import SceneSerializer


class HotReloadStateError(RuntimeError):
    """Raised when registered runtime state cannot be captured or restored safely."""


@dataclass(frozen=True, slots=True)
class HotReloadSnapshot:
    """Immutable, ordered snapshot produced by :class:`HotReloadStateRegistry`."""

    values: tuple[tuple[str, object], ...] = ()

    @property
    def names(self) -> tuple[str, ...]:
        return tuple(name for name, _ in self.values)

    def get(self, name: str, default: Any = None) -> Any:
        key = str(name)
        for item_name, value in self.values:
            if item_name == key:
                return value
        return default


@dataclass(frozen=True, slots=True)
class _StateProvider:
    capture: Callable[[], object]
    restore: Callable[[object], None]


class HotReloadStateRegistry:
    """Deterministic capture/restore registry for development hot reload.

    Providers are intentionally runtime-only. A provider decides how to serialize its state,
    while the registry guarantees stable registration order and gives plugin reload a single
    transaction-like snapshot to restore after code changes.
    """

    def __init__(self) -> None:
        self._providers: dict[str, _StateProvider] = {}

    @property
    def names(self) -> tuple[str, ...]:
        return tuple(self._providers)

    def register(
        self,
        name: str,
        capture: Callable[[], object],
        restore: Callable[[object], None],
        *,
        replace: bool = False,
    ) -> None:
        key = str(name).strip()
        if not key:
            raise HotReloadStateError("state provider name cannot be empty")
        if not callable(capture) or not callable(restore):
            raise TypeError("state capture and restore callbacks must be callable")
        if key in self._providers and not replace:
            raise HotReloadStateError(f"state provider {key!r} is already registered")
        self._providers[key] = _StateProvider(capture, restore)

    def register_scene(
        self,
        name: str,
        scene: Scene,
        *,
        serializer: SceneSerializer | None = None,
        replace: bool = False,
    ) -> SceneSerializer:
        """Register a scene/ECS graph as a hot-reload state provider.

        Passing a custom serializer is useful when game/plugin dataclasses have been added to
        its codec registry. Restore mutates the same ``Scene`` instance so references held by a
        game/editor shell remain valid.
        """
        codec = serializer or SceneSerializer()

        def capture() -> object:
            return codec.dumps_scene(scene, indent=None)

        def restore(value: object) -> None:
            if not isinstance(value, str):
                raise HotReloadStateError("captured scene state must be JSON text")
            codec.loads_scene(value, scene=scene, clear=True)

        self.register(name, capture, restore, replace=replace)
        return codec

    def remove(self, name: str) -> bool:
        return self._providers.pop(str(name), None) is not None

    def clear(self) -> None:
        self._providers.clear()

    def capture(self, names: Iterable[str] | None = None) -> HotReloadSnapshot:
        selected = (
            tuple(self._providers)
            if names is None
            else tuple(dict.fromkeys(map(str, names)))
        )
        values: list[tuple[str, object]] = []
        for name in selected:
            provider = self._providers.get(name)
            if provider is None:
                raise HotReloadStateError(f"state provider {name!r} is not registered")
            try:
                value = provider.capture()
            except Exception as exc:
                raise HotReloadStateError(f"failed to capture state {name!r}: {exc}") from exc
            values.append((name, value))
        return HotReloadSnapshot(tuple(values))

    def restore(self, snapshot: HotReloadSnapshot, *, strict: bool = True) -> None:
        if not isinstance(snapshot, HotReloadSnapshot):
            raise TypeError("snapshot must be HotReloadSnapshot")
        for name, value in snapshot.values:
            provider = self._providers.get(name)
            if provider is None:
                if strict:
                    raise HotReloadStateError(f"state provider {name!r} is not registered")
                continue
            try:
                provider.restore(value)
            except Exception as exc:
                raise HotReloadStateError(f"failed to restore state {name!r}: {exc}") from exc
