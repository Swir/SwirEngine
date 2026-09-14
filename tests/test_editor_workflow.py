from pathlib import Path

import pytest

from swirengine.core.scene import Scene
from swirengine.editor_workflow import EditorProjectLayout, EditorWorkflow
from swirengine.graphics.primitives import Rectangle2D
from swirengine.input.actions import InputActions, InputBinding


class _InputStub:
    pass


def test_project_layout_creates_creator_directories(tmp_path: Path) -> None:
    layout = EditorProjectLayout.at(tmp_path / "game").ensure()
    assert layout.scenes_dir.is_dir()
    assert layout.prefabs_dir.is_dir()
    assert layout.settings_dir.is_dir()


def test_scene_save_load_and_discovery(tmp_path: Path) -> None:
    scene = Scene()
    scene.add(Rectangle2D(1, 2, 30, 40, name="player"))
    workflow = EditorWorkflow(tmp_path, scene)

    path = workflow.save_scene("level_one")
    assert path.name == "level_one.scene.json"
    assert workflow.list_scenes() == ("level_one",)

    scene.clear()
    assert not scene.objects
    workflow.load_scene("level_one")
    assert len(scene.objects) == 1
    assert scene.objects[0].name == "player"


def test_prefab_authoring_and_instantiation_with_overrides(tmp_path: Path) -> None:
    scene = Scene()
    source = scene.add(Rectangle2D(0, 0, 16, 16, name="enemy"))
    workflow = EditorWorkflow(tmp_path, scene)

    workflow.save_prefab("enemy", source)
    assert workflow.list_prefabs() == ("enemy",)

    instance = workflow.instantiate_prefab("enemy", overrides={"enemy": {"x": 96}})
    assert len(instance) == 1
    assert instance.root is not source
    assert instance.root.x == 96
    assert len(scene.objects) == 2


def test_input_profile_setup_persists_with_project(tmp_path: Path) -> None:
    actions = InputActions(_InputStub())  # type: ignore[arg-type]
    workflow = EditorWorkflow(tmp_path, Scene(), input_actions=actions)
    workflow.bind_input("jump", InputBinding("key", "SPACE"))
    workflow.bind_input("jump", InputBinding("gamepad_button", "A"))

    target = workflow.save_input_profile()
    assert target == workflow.layout.input_profile

    actions.clear()
    workflow.load_input_profile()
    assert actions.bindings("jump") == (
        InputBinding("key", "SPACE"),
        InputBinding("gamepad_button", "A"),
    )


def test_playtest_restores_scene_and_input_authoring_state(tmp_path: Path) -> None:
    scene = Scene()
    player = scene.add(Rectangle2D(10, 20, 32, 32, name="player"))
    actions = InputActions(_InputStub())  # type: ignore[arg-type]
    actions.key("jump", "SPACE")
    workflow = EditorWorkflow(tmp_path, scene, input_actions=actions)

    workflow.begin_playtest()
    assert workflow.playtesting
    player.x = 999
    actions.key("jump", "J", replace=True)
    scene.add(Rectangle2D(0, 0, 8, 8, name="runtime_spawn"))
    workflow.end_playtest()

    assert not workflow.playtesting
    assert len(scene.objects) == 1
    assert scene.objects[0].name == "player"
    assert scene.objects[0].x == 10
    assert actions.bindings("jump") == (InputBinding("key", "SPACE"),)


def test_playtest_can_keep_runtime_changes(tmp_path: Path) -> None:
    scene = Scene()
    player = scene.add(Rectangle2D(10, 20, 32, 32, name="player"))
    workflow = EditorWorkflow(tmp_path, scene)
    workflow.begin_playtest()
    player.x = 55
    workflow.keep_playtest_changes()
    assert scene.objects[0].x == 55


def test_nested_playtest_and_unsafe_names_are_rejected(tmp_path: Path) -> None:
    workflow = EditorWorkflow(tmp_path, Scene())
    with pytest.raises(ValueError):
        workflow.scene_path("../outside")

    workflow.begin_playtest()
    with pytest.raises(RuntimeError):
        workflow.begin_playtest()
    workflow.cancel_playtest()
