from __future__ import annotations

import importlib
from collections.abc import Iterable
from contextlib import suppress
from dataclasses import dataclass
from types import ModuleType
from typing import Any

from .hotreload import HotReloadSnapshot, HotReloadStateError, HotReloadStateRegistry


class PluginError(RuntimeError):
    """Raised when a plugin cannot be registered, activated or reloaded safely."""


@dataclass(frozen=True, slots=True)
class PluginInfo:
    """Stable metadata snapshot for one registered plugin."""

    name: str
    version: str
    requires: tuple[str, ...]
    enabled: bool
    module: str | None


@dataclass(slots=True)
class _PluginEntry:
    name: str
    plugin: object
    version: str
    requires: tuple[str, ...]
    module_name: str | None = None
    enabled: bool = False


class PluginManager:
    """Deterministic plugin lifecycle, services, dependencies and development hot reload.

    Plugins are ordinary Python objects. Optional hooks are invoked when present::

        on_load(manager)
        on_enable(manager)
        on_disable(manager)
        on_unload(manager)

    ``load_module()`` accepts modules exposing either ``create_plugin()`` or ``plugin``.
    Dependencies are declared through a plugin ``requires`` iterable or ``register(...,
    requires=...)``. Enabling a plugin enables its dependencies first.

    ``state`` is a :class:`HotReloadStateRegistry`. Registered state providers are captured
    automatically before a module-backed plugin is reloaded and restored after the new plugin
    has completed its load/enable lifecycle. This lets a game or editor preserve scene/ECS and
    tool state while Python code changes underneath it.
    """

    def __init__(self) -> None:
        self._plugins: dict[str, _PluginEntry] = {}
        self._services: dict[str, object] = {}
        self.state = HotReloadStateRegistry()

    @property
    def plugins(self) -> tuple[PluginInfo, ...]:
        return tuple(self.info(name) for name in self._plugins)

    @property
    def enabled(self) -> tuple[str, ...]:
        return tuple(entry.name for entry in self._plugins.values() if entry.enabled)

    def info(self, name: str) -> PluginInfo:
        entry = self._entry(name)
        return PluginInfo(
            name=entry.name,
            version=entry.version,
            requires=entry.requires,
            enabled=entry.enabled,
            module=entry.module_name,
        )

    def plugin(self, name: str) -> object:
        return self._entry(name).plugin

    def register(
        self,
        plugin: object,
        *,
        name: str | None = None,
        version: str | None = None,
        requires: Iterable[str] | None = None,
        module_name: str | None = None,
    ) -> object:
        resolved_name = str(name or getattr(plugin, "name", type(plugin).__name__)).strip()
        if not resolved_name:
            raise PluginError("plugin name cannot be empty")
        if resolved_name in self._plugins:
            raise PluginError(f"plugin {resolved_name!r} is already registered")

        resolved_version = str(version or getattr(plugin, "version", "0"))
        raw_requires = requires if requires is not None else getattr(plugin, "requires", ())
        try:
            resolved_requires = tuple(dict.fromkeys(str(item) for item in raw_requires))
        except TypeError as exc:
            raise PluginError("plugin requires must be an iterable of plugin names") from exc
        if resolved_name in resolved_requires:
            raise PluginError(f"plugin {resolved_name!r} cannot depend on itself")
        if any(not dependency for dependency in resolved_requires):
            raise PluginError("plugin dependency names cannot be empty")

        entry = _PluginEntry(
            name=resolved_name,
            plugin=plugin,
            version=resolved_version,
            requires=resolved_requires,
            module_name=module_name,
        )
        self._plugins[resolved_name] = entry
        try:
            self._call(plugin, "on_load")
        except Exception:
            del self._plugins[resolved_name]
            raise
        return plugin

    def load_module(self, module_name: str, *, enable: bool = False) -> object:
        """Import and register a plugin module using its explicit plugin entrypoint."""
        module = importlib.import_module(module_name)
        plugin = self._plugin_from_module(module)
        self.register(plugin, module_name=module.__name__)
        name = self._name_for_plugin(plugin)
        if enable:
            self.enable(name)
        return plugin

    def enable(self, name: str) -> object:
        """Enable a plugin and all of its dependencies in deterministic order."""
        self._enable(name, stack=[])
        return self._entry(name).plugin

    def _enable(self, name: str, stack: list[str]) -> None:
        entry = self._entry(name)
        if entry.enabled:
            return
        if name in stack:
            cycle = " -> ".join((*stack, name))
            raise PluginError(f"plugin dependency cycle detected: {cycle}")
        stack.append(name)
        try:
            for dependency in entry.requires:
                if dependency not in self._plugins:
                    raise PluginError(
                        f"plugin {entry.name!r} requires missing plugin {dependency!r}"
                    )
                self._enable(dependency, stack)
            self._call(entry.plugin, "on_enable")
            entry.enabled = True
        finally:
            stack.pop()

    def disable(self, name: str, *, cascade: bool = False) -> object:
        """Disable a plugin, optionally disabling enabled dependants first."""
        entry = self._entry(name)
        dependants = self._enabled_dependants(name)
        if dependants and not cascade:
            joined = ", ".join(dependants)
            raise PluginError(f"plugin {name!r} is required by enabled plugins: {joined}")
        if cascade:
            for dependant in reversed(dependants):
                self.disable(dependant, cascade=True)
        if entry.enabled:
            self._call(entry.plugin, "on_disable")
            entry.enabled = False
        return entry.plugin

    def unload(self, name: str, *, cascade: bool = False) -> object:
        """Disable and unregister a plugin after invoking ``on_unload``."""
        entry = self._entry(name)
        self.disable(name, cascade=cascade)
        dependants = self._registered_dependants(name)
        if dependants:
            joined = ", ".join(dependants)
            raise PluginError(f"plugin {name!r} is required by registered plugins: {joined}")
        self._call(entry.plugin, "on_unload")
        del self._plugins[name]
        return entry.plugin

    def reload(
        self,
        name: str,
        *,
        preserve_state: bool = True,
        state_domains: Iterable[str] | None = None,
    ) -> object:
        """Hot-reload a module-backed plugin while preserving activation/runtime state.

        When ``preserve_state`` is true (the default), registered providers are captured before
        old lifecycle hooks run and restored only after the replacement plugin has loaded and
        re-enabled successfully. ``state_domains`` optionally limits preservation to selected
        state domains, which is useful when an editor owns state independently from the game.
        Lifecycle/state failures attempt a full rollback to the previous plugin and snapshot.
        """
        if not preserve_state and state_domains is not None:
            raise ValueError("state_domains requires preserve_state=True")

        entry = self._entry(name)
        if entry.module_name is None:
            raise PluginError(f"plugin {name!r} was not loaded from a module")
        dependants = self._enabled_dependants(name)
        if dependants:
            joined = ", ".join(dependants)
            raise PluginError(
                f"cannot hot-reload plugin {name!r} while enabled dependants exist: {joined}"
            )

        snapshot = (
            self._capture_reload_state(name, state_domains)
            if preserve_state
            else HotReloadSnapshot()
        )
        module = importlib.import_module(entry.module_name)
        try:
            reloaded = importlib.reload(module)
            replacement = self._plugin_from_module(reloaded)
        except Exception as exc:
            raise PluginError(f"failed to reload plugin {name!r}: {exc}") from exc

        replacement_name = self._name_for_plugin(replacement)
        if replacement_name != name:
            raise PluginError(
                f"reloaded plugin changed name from {name!r} to {replacement_name!r}"
            )

        was_enabled = entry.enabled
        old_plugin = entry.plugin
        old_version = entry.version
        old_requires = entry.requires
        if was_enabled:
            self._call(old_plugin, "on_disable")
            entry.enabled = False
        self._call(old_plugin, "on_unload")

        try:
            new_requires = self._resolved_requires(replacement, name)
            entry.plugin = replacement
            entry.version = str(getattr(replacement, "version", old_version))
            entry.requires = new_requires
            self._call(replacement, "on_load")
            if was_enabled:
                self.enable(name)
            if preserve_state:
                self.state.restore_atomic(snapshot)
        except Exception as exc:
            self._cleanup_failed_replacement(entry)
            entry.plugin = old_plugin
            entry.version = old_version
            entry.requires = old_requires
            entry.enabled = False
            try:
                self._call(old_plugin, "on_load")
                if was_enabled:
                    self.enable(name)
                if preserve_state:
                    self.state.restore_atomic(snapshot)
            except Exception as rollback_exc:  # noqa: BLE001 - plugin hooks are arbitrary code.
                raise PluginError(
                    f"plugin {name!r} reload failed and rollback also failed: {rollback_exc}"
                ) from exc
            raise PluginError(f"plugin {name!r} reload lifecycle/state failed: {exc}") from exc
        return replacement

    def provide(self, name: str, service: object, *, replace: bool = False) -> object:
        """Publish a named service that plugins can share without direct imports."""
        key = str(name).strip()
        if not key:
            raise PluginError("service name cannot be empty")
        if key in self._services and not replace:
            raise PluginError(f"service {key!r} is already provided")
        self._services[key] = service
        return service

    def service(self, name: str, default: Any = None) -> Any:
        return self._services.get(str(name), default)

    def require_service(self, name: str) -> object:
        try:
            return self._services[str(name)]
        except KeyError as exc:
            raise PluginError(f"required service {name!r} is not available") from exc

    def remove_service(self, name: str) -> object | None:
        return self._services.pop(str(name), None)

    def shutdown(self) -> None:
        """Disable and unload every plugin in reverse dependency-safe order."""
        for name in reversed(self._topological_names()):
            entry = self._plugins.get(name)
            if entry is None:
                continue
            if entry.enabled:
                self._call(entry.plugin, "on_disable")
                entry.enabled = False
            self._call(entry.plugin, "on_unload")
            del self._plugins[name]
        self._services.clear()
        self.state.clear()

    def _capture_reload_state(
        self,
        name: str,
        domains: Iterable[str] | None = None,
    ) -> HotReloadSnapshot:
        try:
            return self.state.capture(domains=domains)
        except HotReloadStateError as exc:
            raise PluginError(
                f"failed to capture runtime state before reloading {name!r}: {exc}"
            ) from exc

    def _cleanup_failed_replacement(self, entry: _PluginEntry) -> None:
        if entry.enabled:
            with suppress(Exception):
                self._call(entry.plugin, "on_disable")
            entry.enabled = False
        with suppress(Exception):
            self._call(entry.plugin, "on_unload")

    @staticmethod
    def _resolved_requires(plugin: object, name: str) -> tuple[str, ...]:
        raw_requires = getattr(plugin, "requires", ())
        try:
            resolved = tuple(dict.fromkeys(str(item) for item in raw_requires))
        except TypeError as exc:
            raise PluginError("plugin requires must be an iterable of plugin names") from exc
        if name in resolved:
            raise PluginError(f"plugin {name!r} cannot depend on itself")
        if any(not dependency for dependency in resolved):
            raise PluginError("plugin dependency names cannot be empty")
        return resolved

    def _topological_names(self) -> tuple[str, ...]:
        result: list[str] = []
        visiting: set[str] = set()
        visited: set[str] = set()

        def visit(name: str) -> None:
            if name in visited:
                return
            if name in visiting:
                raise PluginError(f"plugin dependency cycle detected at {name!r}")
            visiting.add(name)
            entry = self._entry(name)
            for dependency in entry.requires:
                if dependency not in self._plugins:
                    raise PluginError(
                        f"plugin {entry.name!r} requires missing plugin {dependency!r}"
                    )
                visit(dependency)
            visiting.remove(name)
            visited.add(name)
            result.append(name)

        for name in self._plugins:
            visit(name)
        return tuple(result)

    def _enabled_dependants(self, name: str) -> tuple[str, ...]:
        return tuple(
            entry.name
            for entry in self._plugins.values()
            if entry.enabled and name in entry.requires
        )

    def _registered_dependants(self, name: str) -> tuple[str, ...]:
        return tuple(entry.name for entry in self._plugins.values() if name in entry.requires)

    def _entry(self, name: str) -> _PluginEntry:
        try:
            return self._plugins[str(name)]
        except KeyError as exc:
            raise PluginError(f"plugin {name!r} is not registered") from exc

    def _name_for_plugin(self, plugin: object) -> str:
        return str(getattr(plugin, "name", type(plugin).__name__)).strip()

    def _plugin_from_module(self, module: ModuleType) -> object:
        factory = getattr(module, "create_plugin", None)
        if callable(factory):
            plugin = factory()
        elif hasattr(module, "plugin"):
            plugin = module.plugin
        else:
            raise PluginError(
                f"plugin module {module.__name__!r} must expose create_plugin() or plugin"
            )
        if plugin is None:
            raise PluginError(f"plugin module {module.__name__!r} produced no plugin")
        return plugin

    def _call(self, plugin: object, hook_name: str) -> None:
        hook = getattr(plugin, hook_name, None)
        if hook is not None:
            if not callable(hook):
                raise PluginError(f"plugin hook {hook_name} must be callable")
            hook(self)
