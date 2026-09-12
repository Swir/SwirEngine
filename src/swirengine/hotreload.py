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
    domain: str


class HotReloadStateDomain:
    """Scoped view over one editor/game-owned hot-reload state domain.

    Domains do not change provider names or snapshot formats, so existing state APIs remain
    compatible. They add explicit ownership and selective capture, which lets an editor keep
    scene, viewport, selection and tool state independent without maintaining parallel registries.
    """

    def __init__(self, registry: HotReloadStateRegistry, name: str) -> None:
        self._registry = registry
        self.name = registry._normalize_domain(name)

    @property
    def names(self) -> tuple[str, ...]:
        return self._registry.names_for_domain(self.name)

    def register(
        self,
        name: str,
        capture: Callable[[], object],
        restore: Callable[[object], None],
        *,
        replace: bool = False,
    ) -> None:
        self._registry.register(
            name,
            capture,
            restore,
            replace=replace,
            domain=self.name,
        )

    def register_scene(
        self,
        name: str,
        scene: Scene,
        *,
        serializer: SceneSerializer | None = None,
        replace: bool = False,
    ) -> SceneSerializer:
        return self._registry.register_scene(
            name,
            scene,
            serializer=serializer,
            replace=replace,
            domain=self.name,
        )

    def remove(self, name: str) -> bool:
        key = str(name)
        if self._registry.domain_of(key) != self.name:
            return False
        return self._registry.remove(key)

    def clear(self) -> int:
        return self._registry.remove_domain(self.name)

    def capture(self, names: Iterable[str] | None = None) -> HotReloadSnapshot:
        if names is None:
            return self._registry.capture(domains=(self.name,))
        selected = tuple(dict.fromkeys(map(str, names)))
        outside = tuple(name for name in selected if self._registry.domain_of(name) != self.name)
        if outside:
            raise HotReloadStateError(
                f"state provider {outside[0]!r} does not belong to domain {self.name!r}"
            )
        return self._registry.capture(selected)

    def restore(self, snapshot: HotReloadSnapshot, *, strict: bool = True) -> None:
        self._validate_snapshot(snapshot, strict=strict)
        self._registry.restore(snapshot, strict=strict)

    def restore_atomic(self, snapshot: HotReloadSnapshot, *, strict: bool = True) -> None:
        """Restore this domain as an all-or-nothing transaction.

        Before mutating any provider, the registry captures rollback values for every target.
        If one restore callback fails, every provider touched by the transaction is restored to
        its pre-transaction value in reverse order.
        """
        self._validate_snapshot(snapshot, strict=strict)
        self._registry.restore_atomic(snapshot, strict=strict)

    def _validate_snapshot(self, snapshot: HotReloadSnapshot, *, strict: bool) -> None:
        if not isinstance(snapshot, HotReloadSnapshot):
            raise TypeError("snapshot must be HotReloadSnapshot")
        for name in snapshot.names:
            provider_domain = self._registry.domain_of(name)
            if provider_domain is None and not strict:
                continue
            if provider_domain != self.name:
                raise HotReloadStateError(
                    f"state provider {name!r} does not belong to domain {self.name!r}"
                )


class HotReloadStateRegistry:
    """Deterministic capture/restore registry for development hot reload.

    Providers are intentionally runtime-only. A provider decides how to serialize its state,
    while the registry guarantees stable registration order and gives plugin reload a single
    transaction-like snapshot to restore after code changes. Providers may additionally belong
    to named domains so an editor can preserve only the state it owns for a given reload.
    """

    DEFAULT_DOMAIN = "runtime"

    def __init__(self) -> None:
        self._providers: dict[str, _StateProvider] = {}

    @property
    def names(self) -> tuple[str, ...]:
        return tuple(self._providers)

    @property
    def domains(self) -> tuple[str, ...]:
        return tuple(dict.fromkeys(provider.domain for provider in self._providers.values()))

    def domain(self, name: str) -> HotReloadStateDomain:
        """Return a lightweight scoped facade for registering/capturing one state domain."""
        return HotReloadStateDomain(self, name)

    def domain_of(self, name: str) -> str | None:
        provider = self._providers.get(str(name))
        return None if provider is None else provider.domain

    def names_for_domain(self, domain: str) -> tuple[str, ...]:
        key = self._normalize_domain(domain)
        return tuple(name for name, provider in self._providers.items() if provider.domain == key)

    def register(
        self,
        name: str,
        capture: Callable[[], object],
        restore: Callable[[object], None],
        *,
        replace: bool = False,
        domain: str = DEFAULT_DOMAIN,
    ) -> None:
        key = str(name).strip()
        if not key:
            raise HotReloadStateError("state provider name cannot be empty")
        if not callable(capture) or not callable(restore):
            raise TypeError("state capture and restore callbacks must be callable")
        if key in self._providers and not replace:
            raise HotReloadStateError(f"state provider {key!r} is already registered")
        self._providers[key] = _StateProvider(capture, restore, self._normalize_domain(domain))

    def register_scene(
        self,
        name: str,
        scene: Scene,
        *,
        serializer: SceneSerializer | None = None,
        replace: bool = False,
        domain: str = DEFAULT_DOMAIN,
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

        self.register(name, capture, restore, replace=replace, domain=domain)
        return codec

    def remove(self, name: str) -> bool:
        return self._providers.pop(str(name), None) is not None

    def remove_domain(self, domain: str) -> int:
        key = self._normalize_domain(domain)
        names = self.names_for_domain(key)
        for name in names:
            del self._providers[name]
        return len(names)

    def clear(self) -> None:
        self._providers.clear()

    def capture(
        self,
        names: Iterable[str] | None = None,
        *,
        domains: Iterable[str] | None = None,
    ) -> HotReloadSnapshot:
        if names is not None and domains is not None:
            raise ValueError("capture accepts either names or domains, not both")
        if domains is not None:
            selected_domains = tuple(
                dict.fromkeys(self._normalize_domain(domain) for domain in domains)
            )
            known_domains = set(self.domains)
            for domain in selected_domains:
                if domain not in known_domains:
                    raise HotReloadStateError(f"state domain {domain!r} is not registered")
            selected = tuple(
                name
                for name, provider in self._providers.items()
                if provider.domain in selected_domains
            )
        else:
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

    def restore_atomic(self, snapshot: HotReloadSnapshot, *, strict: bool = True) -> None:
        """Restore a snapshot transactionally across providers and domains.

        The method first captures the current value of every provider that will participate.
        Only after all rollback values are available does it begin applying the requested
        snapshot. A failing callback triggers reverse-order restoration of every provider that
        may already have been mutated, including the failing provider itself.

        The existing :meth:`restore` method intentionally keeps its original best-effort
        semantics for compatibility. Hot-reload transactions should prefer this method.
        """
        if not isinstance(snapshot, HotReloadSnapshot):
            raise TypeError("snapshot must be HotReloadSnapshot")

        targets: list[tuple[str, _StateProvider, object]] = []
        for name, value in snapshot.values:
            provider = self._providers.get(name)
            if provider is None:
                if strict:
                    raise HotReloadStateError(f"state provider {name!r} is not registered")
                continue
            targets.append((name, provider, value))

        rollback_values: list[tuple[str, _StateProvider, object]] = []
        for name, provider, _ in targets:
            try:
                current = provider.capture()
            except Exception as exc:
                raise HotReloadStateError(
                    f"failed to capture rollback state {name!r}: {exc}"
                ) from exc
            rollback_values.append((name, provider, current))

        for index, (name, provider, value) in enumerate(targets):
            try:
                provider.restore(value)
            except Exception as exc:
                rollback_errors: list[str] = []
                for rollback_name, rollback_provider, rollback_value in reversed(
                    rollback_values[: index + 1]
                ):
                    try:
                        rollback_provider.restore(rollback_value)
                    except Exception as rollback_exc:  # noqa: BLE001 - callbacks are user code.
                        rollback_errors.append(f"{rollback_name!r}: {rollback_exc}")
                if rollback_errors:
                    details = "; ".join(rollback_errors)
                    raise HotReloadStateError(
                        f"failed to restore state {name!r}: {exc}; rollback failed for {details}"
                    ) from exc
                raise HotReloadStateError(
                    f"failed to restore state {name!r}: {exc}; transaction rolled back"
                ) from exc

    @classmethod
    def _normalize_domain(cls, domain: str) -> str:
        key = str(domain).strip()
        if not key:
            raise HotReloadStateError("state domain name cannot be empty")
        return key
