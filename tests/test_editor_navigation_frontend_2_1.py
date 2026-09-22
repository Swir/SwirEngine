from __future__ import annotations

from pathlib import Path

import pytest

from swirengine.cli import new_project
from swirengine.editor_app21 import EditorProjectSession
from swirengine.editor_navigation_frontend21 import (
    EditorNavigationPanelController21,
    TkNavigationEditorApp21,
    parse_navigation_point21,
)
from swirengine.editor_navigation_tooling21 import EditorNavigationTooling21
from swirengine.editor_physics_frontend21 import TkPhysicsEditorApp21


def _seed_controller(controller: EditorNavigationPanelController21) -> None:
    controller.create_node("spawn", (0.0, 0.0, 0.0))
    controller.create_node("mid", (2.0, 0.0, 0.0))
    controller.create_node("goal", (4.0, 0.0, 0.0))
    controller.create_edge("spawn-mid", "spawn", "mid", area="road")
    controller.create_edge("mid-goal", "mid", "goal", area="road")
    controller.create_agent("enemy", (0.0, 0.0, 0.0), max_speed=2.0)


def test_navigation_panel_authors_and_previews_shipping_runtime(tmp_path: Path) -> None:
    controller = EditorNavigationPanelController21(EditorNavigationTooling21(tmp_path))
    _seed_controller(controller)

    frame, result = controller.preview_nodes("spawn", "goal")

    assert result.path is not None
    assert result.path.node_ids == ("spawn", "mid", "goal")
    assert frame.preview_start == "spawn"
    assert frame.preview_goal == "goal"
    assert frame.preview_node_ids == ("spawn", "mid", "goal")
    assert frame.dirty is True
    assert tuple(row.name for row in frame.agents) == ("enemy",)


def test_navigation_panel_round_trips_and_clears_preview_on_graph_change(tmp_path: Path) -> None:
    controller = EditorNavigationPanelController21(EditorNavigationTooling21(tmp_path))
    _seed_controller(controller)
    controller.preview_nodes("spawn", "goal")

    frame = controller.rename_node("mid", "junction")
    assert frame.preview_node_ids == ()
    assert tuple(row.name for row in frame.nodes) == ("goal", "junction", "spawn")
    assert {row.name: (row.source, row.target) for row in frame.edges} == {
        "mid-goal": ("junction", "goal"),
        "spawn-mid": ("spawn", "junction"),
    }

    saved = controller.save()
    assert saved.dirty is False
    reopened = EditorNavigationPanelController21(EditorNavigationTooling21(tmp_path))
    assert reopened.frame().nodes == saved.nodes
    assert reopened.frame().edges == saved.edges
    assert reopened.frame().agents == saved.agents


def test_navigation_point_parser_requires_exact_xyz() -> None:
    assert parse_navigation_point21("1, 2.5, -3") == (1.0, 2.5, -3.0)

    with pytest.raises(ValueError, match="exactly three"):
        parse_navigation_point21("1, 2")
    with pytest.raises(ValueError, match="exactly three"):
        parse_navigation_point21("1, nope, 3")


def test_project_session_tracks_and_saves_navigation_authoring(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    root = new_project("NavigationPanel", "3d")
    session = EditorProjectSession.open(root)

    session.navigation.create_node("spawn", (0.0, 0.0, 0.0))
    session.navigation.create_node("goal", (5.0, 0.0, 0.0))
    session.navigation.create_edge("route", "spawn", "goal", area="walkable")
    session.navigation.create_agent("enemy", (0.0, 0.0, 0.0), max_speed=3.0)
    assert session.summary().dirty is True

    session.save()
    assert session.summary().dirty is False
    assert (root / "config" / "navigation.json").is_file()

    reopened = EditorProjectSession.open(root)
    result = reopened.navigation.preview_path((0.0, 0.0, 0.0), (5.0, 0.0, 0.0))
    assert result.path is not None
    assert result.path.node_ids == ("spawn", "goal")
    runtime = reopened.navigation.build_runtime()
    assert tuple(runtime.agents) == ("enemy",)


def test_navigation_shell_preserves_physics_editor_capability() -> None:
    assert issubclass(TkNavigationEditorApp21, TkPhysicsEditorApp21)
