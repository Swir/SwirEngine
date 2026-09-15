from __future__ import annotations

from dataclasses import dataclass

from swirengine.core.scene import Scene
from swirengine.editor_frontend import EditorFrontendController
from swirengine.editor_systems import CreatorEditorIntegration, EditorSystemRegistry
from swirengine.editor_workspace import EditorWorkspace
from swirengine.gameplay import Scheduler


@dataclass(slots=True)
class _Diagnostics:
    active: int = 3
    cache_hits: int = 17
    latency_ms: float = 1.25


class _Subsystem:
    def __init__(self) -> None:
        self.diagnostics = _Diagnostics()


def test_registry_captures_real_scheduler_diagnostics() -> None:
    scheduler = Scheduler()
    scheduler.call_later(2.0, lambda: None)
    registry = EditorSystemRegistry()
    registry.register("gameplay", scheduler, category="gameplay", title="Gameplay Runtime")

    frame = registry.frame()

    assert frame.total_systems == 1
    assert frame.categories == ("gameplay",)
    snapshot = frame.systems[0]
    assert snapshot.system_id == "gameplay"
    values = {metric.name: metric.value for metric in snapshot.metrics}
    assert values["scheduled"] == 1
    assert values["live_timers"] == 1
    assert values["heap_pops"] == 0


def test_registry_orders_and_filters_before_provider_capture() -> None:
    calls = {"renderer": 0, "world": 0, "gameplay": 0}
    registry = EditorSystemRegistry()

    def provider(name: str):
        def capture() -> _Diagnostics:
            calls[name] += 1
            return _Diagnostics()

        return capture

    registry.register("world", title="Large World", category="world", provider=provider("world"))
    registry.register(
        "renderer",
        title="2D Renderer",
        category="rendering",
        provider=provider("renderer"),
    )
    registry.register(
        "gameplay",
        title="Gameplay Runtime",
        category="gameplay",
        provider=provider("gameplay"),
    )

    assert calls == {"renderer": 0, "world": 0, "gameplay": 0}
    frame = registry.frame(category="rendering")

    assert [item.system_id for item in frame.systems] == ["renderer"]
    assert calls == {"renderer": 1, "world": 0, "gameplay": 0}

    frame = registry.frame(query="large")
    assert [item.system_id for item in frame.systems] == ["world"]
    assert calls == {"renderer": 1, "world": 1, "gameplay": 0}


def test_registry_supports_dataclass_mapping_and_plain_public_attributes() -> None:
    class Plain:
        def __init__(self) -> None:
            self.visible = 4
            self._private = 99

    registry = EditorSystemRegistry()
    registry.register("dataclass", _Subsystem(), category="test")
    registry.register("mapping", {"b": 2, "a": 1}, category="test")
    registry.register("plain", Plain(), category="test")

    frame = registry.frame(category="test")
    snapshots = {item.system_id: item for item in frame.systems}

    assert [metric.name for metric in snapshots["mapping"].metrics] == ["a", "b"]
    assert {metric.name for metric in snapshots["plain"].metrics} == {"visible"}
    assert snapshots["dataclass"].metrics[0].name == "active"


def test_creator_bridge_preserves_existing_editor_frontend() -> None:
    workspace = EditorWorkspace(Scene(), project_name="Creator 1.3")
    controller = EditorFrontendController(workspace)
    registry = EditorSystemRegistry()
    registry.register("gameplay", _Subsystem(), category="gameplay")
    bridge = CreatorEditorIntegration(controller, systems=registry)

    frame = bridge.frame()

    assert frame.frontend.shell.project_name == "Creator 1.3"
    assert frame.frontend.shell.scene_id == "main"
    assert frame.systems.total_systems == 1
    assert frame.systems.systems[0].system_id == "gameplay"


def test_creator_bridge_filter_is_additive_and_does_not_mutate_workspace() -> None:
    workspace = EditorWorkspace(Scene(), project_name="Filter Test")
    controller = EditorFrontendController(workspace)
    registry = EditorSystemRegistry()
    registry.register("renderer", _Subsystem(), category="rendering")
    registry.register("gameplay", _Subsystem(), category="gameplay")
    bridge = CreatorEditorIntegration(controller, systems=registry)

    original = workspace.frame()
    bridge.set_system_filter(category="rendering")
    filtered = bridge.frame()
    after = workspace.frame()

    assert [item.system_id for item in filtered.systems.systems] == ["renderer"]
    assert original.project_name == after.project_name
    assert original.scene_id == after.scene_id
    assert original.viewport == after.viewport


def test_register_replaces_same_id_and_unregister_is_explicit() -> None:
    registry = EditorSystemRegistry()
    registry.register("runtime", {"value": 1})
    registry.register("runtime", {"value": 2}, title="Updated Runtime")

    frame = registry.frame()
    assert frame.total_systems == 1
    assert frame.systems[0].title == "Updated Runtime"
    assert frame.systems[0].metrics[0].value == 2
    assert registry.unregister("runtime") is True
    assert registry.unregister("runtime") is False
    assert registry.frame().total_systems == 0
