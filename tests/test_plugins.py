from __future__ import annotations

from dataclasses import dataclass, field

import pytest

from swirengine import PluginError, PluginManager


@dataclass
class DemoPlugin:
    name: str
    version: str = "1.0"
    requires: tuple[str, ...] = ()
    events: list[str] = field(default_factory=list)

    def on_load(self, manager: PluginManager) -> None:
        self.events.append("load")

    def on_enable(self, manager: PluginManager) -> None:
        self.events.append("enable")

    def on_disable(self, manager: PluginManager) -> None:
        self.events.append("disable")

    def on_unload(self, manager: PluginManager) -> None:
        self.events.append("unload")


def test_register_enable_disable_and_unload_lifecycle() -> None:
    manager = PluginManager()
    plugin = DemoPlugin("demo")

    assert manager.register(plugin) is plugin
    assert manager.info("demo").version == "1.0"
    assert plugin.events == ["load"]

    manager.enable("demo")
    assert manager.enabled == ("demo",)
    assert plugin.events == ["load", "enable"]

    manager.disable("demo")
    manager.unload("demo")
    assert plugin.events == ["load", "enable", "disable", "unload"]
    assert manager.plugins == ()


def test_dependencies_enable_first_and_protect_required_plugins() -> None:
    manager = PluginManager()
    core = DemoPlugin("core")
    tools = DemoPlugin("tools", requires=("core",))
    manager.register(core)
    manager.register(tools)

    manager.enable("tools")
    assert manager.enabled == ("core", "tools")
    assert core.events == ["load", "enable"]
    assert tools.events == ["load", "enable"]

    with pytest.raises(PluginError, match="required by enabled plugins"):
        manager.disable("core")

    manager.disable("core", cascade=True)
    assert manager.enabled == ()
    assert tools.events[-1] == "disable"
    assert core.events[-1] == "disable"


def test_missing_dependency_and_dependency_cycle_are_reported() -> None:
    manager = PluginManager()
    manager.register(DemoPlugin("broken", requires=("missing",)))
    with pytest.raises(PluginError, match="missing plugin"):
        manager.enable("broken")

    manager = PluginManager()
    manager.register(DemoPlugin("a", requires=("b",)))
    manager.register(DemoPlugin("b", requires=("a",)))
    with pytest.raises(PluginError, match="dependency cycle"):
        manager.enable("a")


def test_services_are_shared_without_plugin_import_coupling() -> None:
    manager = PluginManager()
    renderer_service = object()

    assert manager.provide("renderer", renderer_service) is renderer_service
    assert manager.require_service("renderer") is renderer_service
    assert manager.service("missing", "fallback") == "fallback"

    with pytest.raises(PluginError, match="already provided"):
        manager.provide("renderer", object())
    with pytest.raises(PluginError, match="not available"):
        manager.require_service("audio")

    replacement = object()
    manager.provide("renderer", replacement, replace=True)
    assert manager.remove_service("renderer") is replacement


def test_shutdown_uses_reverse_dependency_order_and_clears_services() -> None:
    events: list[str] = []

    @dataclass
    class RecordingPlugin:
        name: str
        requires: tuple[str, ...] = ()

        def on_load(self, manager: PluginManager) -> None:
            events.append(f"load:{self.name}")

        def on_enable(self, manager: PluginManager) -> None:
            events.append(f"enable:{self.name}")

        def on_disable(self, manager: PluginManager) -> None:
            events.append(f"disable:{self.name}")

        def on_unload(self, manager: PluginManager) -> None:
            events.append(f"unload:{self.name}")

    manager = PluginManager()
    manager.register(RecordingPlugin("base"))
    manager.register(RecordingPlugin("editor", requires=("base",)))
    manager.enable("editor")
    manager.provide("workspace", object())

    manager.shutdown()

    assert events[-4:] == [
        "disable:editor",
        "unload:editor",
        "disable:base",
        "unload:base",
    ]
    assert manager.plugins == ()
    assert manager.service("workspace") is None


def test_duplicate_names_self_dependency_and_non_module_reload_are_rejected() -> None:
    manager = PluginManager()
    manager.register(DemoPlugin("demo"))

    with pytest.raises(PluginError, match="already registered"):
        manager.register(DemoPlugin("demo"))
    with pytest.raises(PluginError, match="cannot depend on itself"):
        manager.register(DemoPlugin("self", requires=("self",)))
    with pytest.raises(PluginError, match="not loaded from a module"):
        manager.reload("demo")
