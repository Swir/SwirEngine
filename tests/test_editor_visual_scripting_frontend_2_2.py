from __future__ import annotations

from pathlib import Path

import pytest

from swirengine.editor_visual_scripting22 import EditorVisualScriptingTooling22
from swirengine.editor_visual_scripting_frontend22 import EditorVisualScriptPanelController22


def test_visual_script_controller_authors_compiles_and_runs_graph(tmp_path: Path) -> None:
    controller = EditorVisualScriptPanelController22(EditorVisualScriptingTooling22(tmp_path))

    controller.create("door_logic")
    controller.add_node("enabled", "value.bool", parameters={"value": True})
    controller.add_node("branch", "logic.branch", x=280, y=100)
    controller.add_node(
        "open", "event.emit", x=520, y=60, parameters={"name": "open_door"}
    )
    controller.add_node(
        "closed", "event.emit", x=520, y=220, parameters={"name": "locked"}
    )
    controller.add_node("done_open", "flow.end", x=760, y=60)
    controller.add_node("done_closed", "flow.end", x=760, y=220)
    controller.connect("start", "flow", "branch", "flow_in")
    controller.connect("enabled", "value", "branch", "condition")
    controller.connect("branch", "true", "open", "flow_in")
    controller.connect("branch", "false", "closed", "flow_in")
    controller.connect("open", "flow", "done_open", "flow_in")
    controller.connect("closed", "flow", "done_closed", "flow_in")

    frame = controller.compile()
    result = controller.run_preview()

    assert frame.diagnostics == ()
    assert frame.node_count == 7
    assert frame.link_count == 6
    assert result.emitted == (("open_door", None),)
    assert "Preview executed" in controller.status


def test_visual_script_controller_surfaces_incomplete_graph_diagnostics(
    tmp_path: Path,
) -> None:
    controller = EditorVisualScriptPanelController22(EditorVisualScriptingTooling22(tmp_path))
    controller.create("draft")
    controller.add_node("branch", "logic.branch")

    frame = controller.frame()

    assert frame.dirty is True
    assert any("required pin" in message for message in frame.diagnostics)
    with pytest.raises(ValueError, match="required pin"):
        controller.compile()


def test_visual_script_controller_saves_project_asset(tmp_path: Path) -> None:
    controller = EditorVisualScriptPanelController22(EditorVisualScriptingTooling22(tmp_path))
    controller.create("minimal")
    controller.add_node("end", "flow.end", x=260, y=100)
    controller.connect("start", "flow", "end", "flow_in")

    frame = controller.save()

    assert frame.dirty is False
    assert (tmp_path / "assets" / "graphs" / "minimal.swirgraph").is_file()
