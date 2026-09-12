from dataclasses import dataclass

import pytest

from swirengine import Scene
from swirengine.editor_workspace import (
    EDITOR_PROJECT_FORMAT,
    EditorPanelState,
    EditorProjectState,
    EditorViewportState,
    EditorWorkspace,
    default_editor_panels,
)


@dataclass
class Actor:
    name: str
    enabled: bool = True
    tags: set[str] | None = None
    health: int = 100

    def __post_init__(self) -> None:
        if self.tags is None:
            self.tags = set()


def test_project_state_round_trips_json_and_disk(tmp_path):
    scene = Scene()
    root = scene.add(Actor("Root"))
    child = scene.add(Actor("Child"))
    workspace = EditorWorkspace(scene, scene_id="levels/main", project_name="Demo")
    workspace.inspector.set_parent(child, root)
    workspace.select(child)
    workspace.configure_panel("profiler", visible=True, region="right", order=1)
    workspace.configure_viewport(mode="2d", gizmo="scale", snap_enabled=True)

    state = workspace.capture_project()
    payload = state.to_dict()
    decoded = EditorProjectState.loads(state.dumps())
    path = tmp_path / ".swir" / "editor.json"
    state.save(path)

    assert payload["format"] == EDITOR_PROJECT_FORMAT
    assert decoded == state
    assert EditorProjectState.load(path) == state
    assert decoded.active_scene_id == "levels/main"
    assert decoded.scenes[0].viewport.mode == "2d"
    assert next(panel for panel in decoded.panels if panel.panel_id == "profiler").visible


def test_workspace_frame_combines_hierarchy_inspector_layout_and_history():
    scene = Scene()
    player = scene.add(Actor("Player", tags={"gameplay"}))
    scene.add(Actor("Decoration", enabled=False, tags={"art"}))
    workspace = EditorWorkspace(scene, project_name="Frame Test")
    workspace.select(player)
    workspace.inspector.set_property("health", 75)
    workspace.set_hierarchy_filter("play", tag="gameplay", include_disabled=False)

    frame = workspace.frame()

    assert frame.project_name == "Frame Test"
    assert [row.label for row in frame.hierarchy] == ["Player"]
    assert frame.inspector is not None
    assert frame.inspector.key == workspace.inspector.key_for(player)
    assert frame.can_undo
    assert not frame.can_redo
    assert frame.hierarchy_query == "play"
    assert {panel.panel_id for panel in frame.panels} >= {
        "hierarchy",
        "viewport",
        "inspector",
        "assets",
        "console",
    }


def test_workspace_scene_switch_stashes_and_restores_per_scene_editor_state():
    first_scene = Scene()
    first_root = first_scene.add(Actor("First root"))
    first_child = first_scene.add(Actor("First child"))
    workspace = EditorWorkspace(first_scene, scene_id="first")
    workspace.inspector.set_parent(first_child, first_root)
    workspace.select(first_child)
    workspace.configure_viewport(mode="2d", gizmo="translate", translation_snap=8.0)

    second_scene = Scene()
    second = second_scene.add(Actor("Second"))
    workspace.switch_scene("second", second_scene)
    workspace.select(second)
    workspace.configure_viewport(mode="3d", gizmo="rotate", rotation_snap=5.0)

    replacement_first = Scene()
    replacement_root = replacement_first.add(Actor("First root"))
    replacement_child = replacement_first.add(Actor("First child"))
    workspace.switch_scene("first", replacement_first)

    assert workspace.scene is replacement_first
    assert workspace.inspector.parent(replacement_child) is replacement_root
    assert workspace.inspector.selected_target is replacement_child
    assert workspace.viewport.mode == "2d"
    assert workspace.viewport.translation_snap == 8.0
    project = workspace.capture_project()
    assert {state.scene_id for state in project.scenes} == {"first", "second"}


def test_restore_project_is_transactional_for_invalid_scene_references():
    source_scene = Scene()
    source_scene.add(Actor("Only object"))
    source = EditorWorkspace(source_scene, scene_id="main", project_name="Source")
    state = source.capture_project()

    live_scene = Scene()
    original = live_scene.add(Actor("Keep me"))
    target = EditorWorkspace(live_scene, scene_id="live", project_name="Live")
    target.select(original)

    empty_scene = Scene()
    with pytest.raises(LookupError):
        target.restore_project(state, empty_scene)

    assert target.project_name == "Live"
    assert target.scene_id == "live"
    assert target.scene is live_scene
    assert target.inspector.selected_target is original


def test_panel_and_viewport_configuration_validate_frontend_contract():
    scene = Scene()
    workspace = EditorWorkspace(scene)

    panel = workspace.configure_panel(
        "assets", visible=False, region="left", order=4, weight=0.5
    )
    viewport = workspace.configure_viewport(
        mode="2d",
        gizmo="none",
        grid_visible=False,
        snap_enabled=True,
        translation_snap=16.0,
        rotation_snap=45.0,
        scale_snap=0.25,
    )

    assert panel == EditorPanelState("assets", "Assets", "left", False, 4, 0.5)
    assert viewport == EditorViewportState("2d", "none", False, True, 16.0, 45.0, 0.25)
    with pytest.raises(KeyError, match="unknown editor panel"):
        workspace.configure_panel("missing", visible=True)
    with pytest.raises(ValueError, match="viewport mode"):
        workspace.configure_viewport(mode="vr")
    with pytest.raises(ValueError, match="panel region"):
        workspace.configure_panel("assets", region="somewhere")


def test_project_state_rejects_duplicate_panels_scenes_and_unknown_active_scene():
    scene = Scene()
    workspace = EditorWorkspace(scene, scene_id="main")
    valid = workspace.capture_project()
    panel = default_editor_panels()[0]

    with pytest.raises(ValueError, match="duplicate panel"):
        EditorProjectState(
            valid.project_name,
            valid.asset_root,
            valid.scenes,
            valid.active_scene_id,
            (panel, panel),
        )

    with pytest.raises(ValueError, match="duplicate scene"):
        EditorProjectState(
            valid.project_name,
            valid.asset_root,
            (valid.scenes[0], valid.scenes[0]),
            valid.active_scene_id,
            valid.panels,
        )

    with pytest.raises(ValueError, match="active_scene_id"):
        EditorProjectState(
            valid.project_name,
            valid.asset_root,
            valid.scenes,
            "missing",
            valid.panels,
        )
