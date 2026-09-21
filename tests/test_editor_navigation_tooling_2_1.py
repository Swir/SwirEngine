from __future__ import annotations

import json

import pytest

from swirengine.editor_navigation_tooling21 import (
    EditorNavigationTooling21,
    EditorNavigationToolingError,
)
from swirengine.navigation15 import NavPoint


def _seed(tool: EditorNavigationTooling21) -> None:
    tool.create_node("spawn", (0.0, 0.0, 0.0))
    tool.create_node("mid", (2.0, 0.0, 0.0))
    tool.create_node("goal", (4.0, 0.0, 0.0))
    tool.create_edge("spawn-mid", "spawn", "mid", area="road")
    tool.create_edge("mid-goal", "mid", "goal", area="road")
    tool.create_agent("enemy", (0.0, 0.0, 0.0), max_speed=2.0)


def test_navigation_authoring_round_trips_deterministically(tmp_path) -> None:
    tool = EditorNavigationTooling21(tmp_path)
    _seed(tool)
    assert tool.dirty
    saved = tool.save()
    first = tool.target.read_bytes()
    assert not saved.dirty

    loaded = EditorNavigationTooling21(tmp_path)
    snapshot = loaded.snapshot()
    assert snapshot.nodes == saved.nodes
    assert snapshot.edges == saved.edges
    assert snapshot.agents == saved.agents
    assert not snapshot.dirty
    loaded.save()
    assert loaded.target.read_bytes() == first


def test_navigation_authoring_builds_shipping_runtime(tmp_path) -> None:
    tool = EditorNavigationTooling21(tmp_path)
    _seed(tool)
    runtime = tool.build_runtime()
    assert tuple(runtime.agents) == ("enemy",)
    result = runtime.set_target("enemy", (4.0, 0.0, 0.0))
    assert result.path is not None
    assert result.path.node_ids == ("spawn", "mid", "goal")
    for _ in range(180):
        runtime.step(1.0 / 60.0)
    assert runtime.agent("enemy").arrived
    assert runtime.agent("enemy").position == NavPoint(4.0, 0.0, 0.0)


def test_preview_uses_runtime_query_filters(tmp_path) -> None:
    tool = EditorNavigationTooling21(tmp_path)
    tool.create_node("a", (0.0, 0.0, 0.0))
    tool.create_node("b", (1.0, 0.0, 0.0))
    tool.create_node("c", (0.0, 0.0, 2.0))
    tool.create_node("d", (2.0, 0.0, 0.0))
    tool.create_edge("mud-1", "a", "b", area="mud")
    tool.create_edge("mud-2", "b", "d", area="mud")
    tool.create_edge("road-1", "a", "c", area="road")
    tool.create_edge("road-2", "c", "d", area="road")

    direct = tool.preview_path((0.0, 0.0, 0.0), (2.0, 0.0, 0.0))
    rerouted = tool.preview_path(
        (0.0, 0.0, 0.0),
        (2.0, 0.0, 0.0),
        area_costs=(("mud", 10.0),),
    )
    assert direct.path is not None and rerouted.path is not None
    assert direct.path.node_ids == ("a", "b", "d")
    assert rerouted.path.node_ids == ("a", "c", "d")


def test_rename_node_rewrites_connected_edges(tmp_path) -> None:
    tool = EditorNavigationTooling21(tmp_path)
    tool.create_node("a", (0.0, 0.0, 0.0))
    tool.create_node("b", (1.0, 0.0, 0.0))
    tool.create_edge("edge", "a", "b")
    snapshot = tool.rename_node("b", "exit")
    assert snapshot.edges[0].target == "exit"
    result = tool.preview_path((0.0, 0.0, 0.0), (1.0, 0.0, 0.0))
    assert result.path is not None
    assert result.path.node_ids == ("a", "exit")


def test_connected_node_requires_explicit_edge_removal(tmp_path) -> None:
    tool = EditorNavigationTooling21(tmp_path)
    tool.create_node("a", (0.0, 0.0, 0.0))
    tool.create_node("b", (1.0, 0.0, 0.0))
    tool.create_edge("edge", "a", "b")
    with pytest.raises(EditorNavigationToolingError, match="remove connected"):
        tool.remove_node("a")


def test_invalid_references_and_runtime_values_are_rejected(tmp_path) -> None:
    tool = EditorNavigationTooling21(tmp_path)
    tool.create_node("a", (0.0, 0.0, 0.0))
    with pytest.raises(EditorNavigationToolingError, match="unknown navigation node"):
        tool.create_edge("bad", "a", "missing")
    with pytest.raises(ValueError):
        tool.create_agent("bad", (0.0, 0.0, 0.0), max_speed=-1.0)
    with pytest.raises(EditorNavigationToolingError):
        tool.create_node("nan", (float("nan"), 0.0, 0.0))


def test_navigation_path_must_stay_inside_project(tmp_path) -> None:
    with pytest.raises(EditorNavigationToolingError, match="project-relative"):
        EditorNavigationTooling21(tmp_path, path="../escape.json")
    with pytest.raises(EditorNavigationToolingError, match="project-relative"):
        EditorNavigationTooling21(tmp_path, path="C:\\escape.json")


def test_symlink_escape_is_rejected_on_disk_access(tmp_path) -> None:
    outside = tmp_path.parent / f"{tmp_path.name}-outside"
    outside.mkdir()
    (tmp_path / "config").symlink_to(outside, target_is_directory=True)
    with pytest.raises(EditorNavigationToolingError, match="escapes the project root"):
        EditorNavigationTooling21(tmp_path)


def test_unknown_json_fields_and_duplicate_names_are_rejected(tmp_path) -> None:
    target = tmp_path / "config" / "navigation.json"
    target.parent.mkdir()
    target.write_text(
        json.dumps(
            {
                "format": "swirengine.navigation-profile",
                "version": 1,
                "nodes": [
                    {"name": "same", "position": [0, 0, 0]},
                    {"name": "same", "position": [1, 0, 0]},
                ],
                "edges": [],
                "agents": [],
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(EditorNavigationToolingError, match="duplicate navigation node"):
        EditorNavigationTooling21(tmp_path)

    target.write_text(
        json.dumps(
            {
                "format": "swirengine.navigation-profile",
                "version": 1,
                "nodes": [],
                "edges": [],
                "agents": [],
                "unexpected": True,
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(EditorNavigationToolingError, match="fields do not match schema"):
        EditorNavigationTooling21(tmp_path)
