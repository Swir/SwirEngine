from dataclasses import dataclass

import pytest

from swirengine import Scene
from swirengine.editor_frontend import EditorFrontendController, parse_editor_value
from swirengine.editor_workspace import EditorWorkspace


@dataclass
class Actor:
    name: str
    enabled: bool = True
    health: int = 100
    speed: float = 3.5
    label: str = "hero"


def test_frontend_controller_builds_interactive_hierarchy_and_inspector_frame():
    scene = Scene()
    parent = scene.add(Actor("Parent"))
    child = scene.add(Actor("Child"))
    workspace = EditorWorkspace(scene, project_name="Frontend")
    workspace.inspector.set_parent(child, parent)
    workspace.select(child)
    controller = EditorFrontendController(workspace)

    frame = controller.frame()

    assert frame.shell.project_name == "Frontend"
    assert [row.label for row in frame.hierarchy] == ["Parent", "Child"]
    assert frame.hierarchy[1].depth == 1
    assert frame.hierarchy[1].selected
    assert {field.name for field in frame.inspector_fields} >= {"name", "health", "speed"}
    assert frame.status == "Ready"


def test_frontend_controller_edits_properties_and_routes_undo_redo():
    scene = Scene()
    actor = scene.add(Actor("Player"))
    workspace = EditorWorkspace(scene)
    workspace.select(actor)
    controller = EditorFrontendController(workspace)

    assert controller.edit_property("health", "0x40") == 64
    assert actor.health == 64
    assert controller.undo()
    assert actor.health == 100
    assert controller.redo()
    assert actor.health == 64
    assert controller.status == "Redo"


def test_frontend_controller_controls_filter_gizmo_snap_and_panels():
    scene = Scene()
    scene.add(Actor("Player"))
    scene.add(Actor("Decoration"))
    controller = EditorFrontendController(EditorWorkspace(scene))

    controller.set_hierarchy_query("play")
    controller.set_gizmo("rotate")
    controller.set_snap(True)
    panel = controller.set_panel_visible("profiler", True)
    frame = controller.frame()

    assert [row.label for row in frame.hierarchy] == ["Player"]
    assert frame.shell.viewport.gizmo == "rotate"
    assert frame.shell.viewport.snap_enabled
    assert panel.visible
    assert next(item for item in frame.shell.panels if item.panel_id == "profiler").visible


def test_frontend_controller_reports_missing_selection_and_fields():
    controller = EditorFrontendController(EditorWorkspace(Scene()))

    with pytest.raises(RuntimeError, match="no scene object"):
        controller.edit_property("health", "10")

    scene = Scene()
    actor = scene.add(Actor("Player"))
    workspace = EditorWorkspace(scene)
    workspace.select(actor)
    controller = EditorFrontendController(workspace)
    with pytest.raises(KeyError, match="unknown inspector field"):
        controller.edit_property("missing", "10")


def test_parse_editor_value_is_safe_and_type_aware():
    assert parse_editor_value("plain text", "old") == "plain text"
    assert parse_editor_value("yes", False) is True
    assert parse_editor_value("off", True) is False
    assert parse_editor_value("0xff", 0) == 255
    assert parse_editor_value("2.75", 0.0) == pytest.approx(2.75)
    assert parse_editor_value("[1, 2]", [0]) == [1, 2]
    assert parse_editor_value("None", None) is None

    with pytest.raises(ValueError, match="boolean"):
        parse_editor_value("maybe", False)
    with pytest.raises(TypeError, match="expected list"):
        parse_editor_value("(1, 2)", [0])
    with pytest.raises((ValueError, SyntaxError)):
        parse_editor_value("__import__('os').system('echo nope')", [])


def test_frontend_optional_models_are_absent_without_forcing_dependencies():
    controller = EditorFrontendController(EditorWorkspace(Scene()))
    frame = controller.frame()

    assert frame.assets is None
    assert frame.console is None
    assert frame.profiler is None
