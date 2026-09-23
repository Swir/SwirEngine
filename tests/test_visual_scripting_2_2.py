from __future__ import annotations

from pathlib import Path

import pytest

from swirengine.cli import new_project
from swirengine.editor_integrated_session21 import EditorIntegratedProjectSession21
from swirengine.editor_visual_scripting22 import (
    EditorVisualScriptingError22,
    EditorVisualScriptingTooling22,
)
from swirengine.visual_scripting22 import (
    GraphExecutionContext22,
    NodeGraphAsset22,
    NodeGraphLink22,
    VisualScriptValidationError22,
    compile_node_graph22,
    dumps_node_graph22,
    graph_node22,
    loads_node_graph22,
)


def _runtime_graph() -> NodeGraphAsset22:
    nodes = (
        graph_node22("start", "event.start"),
        graph_node22("left", "value.float", parameters={"value": 2.5}),
        graph_node22("right", "value.float", parameters={"value": 7.5}),
        graph_node22("add", "math.add"),
        graph_node22("set", "variable.set", parameters={"name": "score"}),
        graph_node22("get", "variable.get", parameters={"name": "score"}),
        graph_node22("emit", "event.emit", parameters={"name": "score_changed"}),
        graph_node22("end", "flow.end"),
    )
    links = (
        NodeGraphLink22("start", "flow", "set", "flow_in"),
        NodeGraphLink22("left", "value", "add", "a"),
        NodeGraphLink22("right", "value", "add", "b"),
        NodeGraphLink22("add", "value", "set", "value"),
        NodeGraphLink22("set", "flow", "emit", "flow_in"),
        NodeGraphLink22("get", "value", "emit", "value"),
        NodeGraphLink22("emit", "flow", "end", "flow_in"),
    )
    return NodeGraphAsset22("score_logic", nodes, links)


def test_node_graph_round_trips_deterministically() -> None:
    graph = _runtime_graph()
    first = dumps_node_graph22(graph)
    reopened = loads_node_graph22(first)

    assert dumps_node_graph22(reopened) == first
    assert reopened.fingerprint == graph.fingerprint
    assert '"format": "swirengine.node-graph"' in first
    assert '"version": 1' in first


def test_typed_pin_validation_rejects_incompatible_connections() -> None:
    graph = NodeGraphAsset22(
        "invalid",
        (
            graph_node22("start", "event.start"),
            graph_node22("text", "value.string", parameters={"value": "bad"}),
            graph_node22("number", "value.float", parameters={"value": 1.0}),
            graph_node22("add", "math.add"),
            graph_node22("end", "flow.end"),
        ),
        (
            NodeGraphLink22("start", "flow", "end", "flow_in"),
            NodeGraphLink22("text", "value", "add", "a"),
            NodeGraphLink22("number", "value", "add", "b"),
        ),
    )
    with pytest.raises(VisualScriptValidationError22) as exc_info:
        compile_node_graph22(graph)
    assert any(issue.code == "link.type" for issue in exc_info.value.issues)


def test_compiled_graph_executes_runtime_logic_and_python_handler() -> None:
    received: list[object] = []
    context = GraphExecutionContext22(handlers={"score_changed": received.append})

    result = compile_node_graph22(_runtime_graph()).execute(context)

    assert result.steps == 4
    assert result.variables == (("score", 10.0),)
    assert result.emitted == (("score_changed", 10.0),)
    assert received == [10.0]


def test_branch_executes_only_selected_flow() -> None:
    graph = NodeGraphAsset22(
        "branching",
        (
            graph_node22("start", "event.start"),
            graph_node22("condition", "value.bool", parameters={"value": True}),
            graph_node22("branch", "logic.branch"),
            graph_node22("yes", "event.emit", parameters={"name": "yes"}),
            graph_node22("no", "event.emit", parameters={"name": "no"}),
            graph_node22("end_yes", "flow.end"),
            graph_node22("end_no", "flow.end"),
        ),
        (
            NodeGraphLink22("start", "flow", "branch", "flow_in"),
            NodeGraphLink22("condition", "value", "branch", "condition"),
            NodeGraphLink22("branch", "true", "yes", "flow_in"),
            NodeGraphLink22("branch", "false", "no", "flow_in"),
            NodeGraphLink22("yes", "flow", "end_yes", "flow_in"),
            NodeGraphLink22("no", "flow", "end_no", "flow_in"),
        ),
    )
    assert compile_node_graph22(graph).execute().emitted == (("yes", None),)


def test_editor_tooling_saves_reopens_and_compiles_graph_assets(tmp_path: Path) -> None:
    tooling = EditorVisualScriptingTooling22(tmp_path)
    tooling.create_graph("gameplay")
    source = _runtime_graph()
    for node in source.nodes:
        tooling.add_node(
            "gameplay",
            node.node_id,
            node.kind,
            x=node.x,
            y=node.y,
            parameters=dict(node.parameters),
        )
    for link in source.links:
        tooling.connect("gameplay", link.from_node, link.from_pin, link.to_node, link.to_pin)

    assert tooling.dirty is True
    assert tooling.execute("gameplay").emitted == (("score_changed", 10.0),)
    tooling.save()
    path = tmp_path / "assets" / "graphs" / "gameplay.swirgraph"
    first = path.read_text(encoding="utf-8")
    assert tooling.dirty is False

    reopened = EditorVisualScriptingTooling22(tmp_path)
    assert reopened.execute("gameplay").emitted == (("score_changed", 10.0),)
    reopened.save()
    assert path.read_text(encoding="utf-8") == first


def test_editor_tooling_blocks_graph_directory_escape(tmp_path: Path) -> None:
    with pytest.raises(EditorVisualScriptingError22, match="project-relative"):
        EditorVisualScriptingTooling22(tmp_path, relative_dir="../graphs")


def test_editor_tooling_blocks_symlinked_graph_directory(tmp_path: Path) -> None:
    project = tmp_path / "project"
    outside = tmp_path / "outside"
    (project / "assets").mkdir(parents=True)
    outside.mkdir()
    try:
        (project / "assets" / "graphs").symlink_to(outside, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("directory symlinks are unavailable on this runner")
    with pytest.raises(EditorVisualScriptingError22, match="inside project root"):
        EditorVisualScriptingTooling22(project)


def test_integrated_session_marks_visual_scripts_dirty_and_reopens(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    root = new_project("VisualScriptSession", "3d")
    session = EditorIntegratedProjectSession21.open(root)
    session.visual_scripts.create_graph("main_logic")
    session.visual_scripts.add_node("main_logic", "start", "event.start")
    session.visual_scripts.add_node("main_logic", "end", "flow.end", x=250)
    session.visual_scripts.connect("main_logic", "start", "flow", "end", "flow_in")

    assert session.summary().dirty is True
    session.save()
    assert session.summary().dirty is False

    reopened = EditorIntegratedProjectSession21.open(root)
    assert tuple(graph.name for graph in reopened.visual_scripts.snapshot().graphs) == (
        "main_logic",
    )
    assert reopened.visual_scripts.execute("main_logic").steps == 2
    assert reopened.summary().dirty is False
