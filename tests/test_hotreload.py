from __future__ import annotations

from dataclasses import dataclass, field
from types import ModuleType

import pytest

from swirengine import (
    HotReloadStateError,
    HotReloadStateRegistry,
    PluginError,
    PluginManager,
    Rectangle2D,
    Scene,
)


@dataclass
class ReloadablePlugin:
    name: str = "demo"
    version: str = "1.0"
    fail_enable: bool = False
    events: list[str] = field(default_factory=list)

    def on_load(self, manager: PluginManager) -> None:
        self.events.append("load")

    def on_enable(self, manager: PluginManager) -> None:
        self.events.append("enable")
        if self.fail_enable:
            raise RuntimeError("replacement refused enable")

    def on_disable(self, manager: PluginManager) -> None:
        self.events.append("disable")

    def on_unload(self, manager: PluginManager) -> None:
        self.events.append("unload")


def test_state_registry_is_ordered_and_supports_partial_snapshots() -> None:
    state = {"a": 1, "b": 2}
    restored: list[tuple[str, int]] = []
    registry = HotReloadStateRegistry()
    registry.register("a", lambda: state["a"], lambda value: restored.append(("a", int(value))))
    registry.register("b", lambda: state["b"], lambda value: restored.append(("b", int(value))))

    snapshot = registry.capture(("b", "a", "b"))

    assert snapshot.names == ("b", "a")
    assert snapshot.get("a") == 1
    assert snapshot.get("missing", 9) == 9
    registry.restore(snapshot)
    assert restored == [("b", 2), ("a", 1)]


def test_state_registry_validates_provider_failures_and_missing_names() -> None:
    registry = HotReloadStateRegistry()
    registry.register(
        "bad",
        lambda: (_ for _ in ()).throw(RuntimeError("capture boom")),
        lambda _: None,
    )

    with pytest.raises(HotReloadStateError, match="failed to capture state 'bad'"):
        registry.capture()
    with pytest.raises(HotReloadStateError, match="not registered"):
        registry.capture(("missing",))
    with pytest.raises(TypeError, match="HotReloadSnapshot"):
        registry.restore(object())  # type: ignore[arg-type]


def test_scene_provider_restores_same_scene_instance() -> None:
    scene = Scene()
    scene.add(Rectangle2D(10, 20, 30, 40, name="player"))
    registry = HotReloadStateRegistry()
    registry.register_scene("scene", scene)
    snapshot = registry.capture()

    scene.clear()
    scene.add(Rectangle2D(0, 0, 1, 1, name="temporary"))
    registry.restore(snapshot)

    assert len(scene.objects) == 1
    restored = scene.find("player")
    assert isinstance(restored, Rectangle2D)
    assert (restored.x, restored.y, restored.width, restored.height) == (10, 20, 30, 40)


def _patch_reload_module(
    monkeypatch: pytest.MonkeyPatch,
    module: ModuleType,
) -> None:
    # Patch reload first: replacing importlib.import_module also changes the shared stdlib module,
    # which pytest itself uses to resolve string-based monkeypatch targets.
    monkeypatch.setattr("swirengine.plugins.importlib.reload", lambda _: module)
    monkeypatch.setattr("swirengine.plugins.importlib.import_module", lambda _: module)


def test_plugin_reload_preserves_registered_runtime_state(monkeypatch: pytest.MonkeyPatch) -> None:
    manager = PluginManager()
    original = ReloadablePlugin()
    replacement = ReloadablePlugin(version="2.0")
    manager.register(original, module_name="demo_plugin")
    manager.enable("demo")

    runtime = {"score": 42}
    restores: list[int] = []
    manager.state.register(
        "runtime",
        lambda: dict(runtime),
        lambda value: (runtime.clear(), runtime.update(value), restores.append(runtime["score"])),
    )

    module = ModuleType("demo_plugin")
    module.create_plugin = lambda: replacement  # type: ignore[attr-defined]
    _patch_reload_module(monkeypatch, module)

    runtime["score"] = 99
    result = manager.reload("demo")

    assert result is replacement
    assert manager.plugin("demo") is replacement
    assert manager.info("demo").version == "2.0"
    assert manager.enabled == ("demo",)
    assert restores == [99]
    assert original.events[-2:] == ["disable", "unload"]
    assert replacement.events == ["load", "enable"]


def test_plugin_reload_rolls_back_plugin_and_state_on_replacement_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manager = PluginManager()
    original = ReloadablePlugin()
    replacement = ReloadablePlugin(version="2.0", fail_enable=True)
    manager.register(original, module_name="demo_plugin")
    manager.enable("demo")

    runtime = {"value": "stable"}
    manager.state.register(
        "runtime",
        lambda: dict(runtime),
        lambda value: (runtime.clear(), runtime.update(value)),
    )

    module = ModuleType("demo_plugin")
    module.create_plugin = lambda: replacement  # type: ignore[attr-defined]
    _patch_reload_module(monkeypatch, module)

    runtime["value"] = "before-reload"
    with pytest.raises(PluginError, match="reload lifecycle/state failed"):
        manager.reload("demo")

    assert manager.plugin("demo") is original
    assert manager.enabled == ("demo",)
    assert runtime == {"value": "before-reload"}
    assert replacement.events[-1] == "unload"
    assert original.events[-2:] == ["load", "enable"]


def test_reload_can_explicitly_skip_state_preservation(monkeypatch: pytest.MonkeyPatch) -> None:
    manager = PluginManager()
    original = ReloadablePlugin()
    replacement = ReloadablePlugin(version="2.0")
    manager.register(original, module_name="demo_plugin")

    captures = 0

    def capture() -> object:
        nonlocal captures
        captures += 1
        return "state"

    manager.state.register("runtime", capture, lambda _: None)
    module = ModuleType("demo_plugin")
    module.create_plugin = lambda: replacement  # type: ignore[attr-defined]
    _patch_reload_module(monkeypatch, module)

    manager.reload("demo", preserve_state=False)

    assert captures == 0
    assert manager.plugin("demo") is replacement
