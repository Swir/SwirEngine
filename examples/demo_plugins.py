from __future__ import annotations

from swirengine import PluginManager


class AnalyticsPlugin:
    name = "analytics"
    version = "1.0"

    def on_load(self, manager: PluginManager) -> None:
        manager.provide("analytics.ready", True)

    def on_enable(self, manager: PluginManager) -> None:
        print("analytics enabled")

    def on_disable(self, manager: PluginManager) -> None:
        print("analytics disabled")


class GameplayToolsPlugin:
    name = "gameplay-tools"
    version = "1.0"
    requires = ("analytics",)

    def on_enable(self, manager: PluginManager) -> None:
        print("tools enabled; analytics =", manager.require_service("analytics.ready"))


plugins = PluginManager()
plugins.register(AnalyticsPlugin())
plugins.register(GameplayToolsPlugin())
plugins.enable("gameplay-tools")

print(plugins.plugins)
plugins.shutdown()
