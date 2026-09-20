from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from swirengine import Scene
from swirengine.editor_project_authoring21 import EditorProjectAuthoring21
from swirengine.editor_workspace import EditorWorkspace
from swirengine.serialization import SceneCodecRegistry, SceneSerializer


@dataclass
class Actor:
    name: str
    health: int = 100
    texture: Path = Path("textures/default.png")


@dataclass
class Health:
    value: int = 100


def _serializer() -> SceneSerializer:
    registry = SceneCodecRegistry.default()
    registry.register(Actor)
    return SceneSerializer(registry)


def test_project_bridge_exposes_mixed_typed_editing_and_grouped_history(tmp_path) -> None:
    scene = Scene()
    first = scene.add(Actor("One", health=100))
    second = scene.add(Actor("Two", health=75))
    workspace = EditorWorkspace(scene, scene_id="scenes/main.json", project_name="Game")
    authoring = EditorProjectAuthoring21(
        workspace,
        serializer=_serializer(),
        asset_root=tmp_path / "assets",
    )

    selection = authoring.select_many((first, second))
    assert selection.count == 2
    fields = {field.name: field for field in authoring.frame().fields}
    assert fields["health"].kind == "number"
    assert fields["health"].mixed

    authoring.set_typed_property("health", "42")
    assert first.health == 42
    assert second.health == 42

    authoring.undo()
    assert first.health == 100
    assert second.health == 75

    authoring.redo()
    assert first.health == 42
    assert second.health == 42


def test_project_bridge_routes_component_authoring_through_same_creator_history(tmp_path) -> None:
    scene = Scene()
    first = scene.create_entity(name="One")
    second = scene.create_entity(name="Two")
    workspace = EditorWorkspace(scene, scene_id="scenes/main.json")
    authoring = EditorProjectAuthoring21(workspace, asset_root=tmp_path / "assets")
    authoring.select_many((first, second))

    result = authoring.add_component(Health(80))
    assert result.target_keys == (f"entity:{first.id}", f"entity:{second.id}")
    assert first.require(Health).value == 80
    assert second.require(Health).value == 80

    authoring.undo()
    assert first.get(Health) is None
    assert second.get(Health) is None

    authoring.redo()
    assert first.require(Health).value == 80
    assert second.require(Health).value == 80


def test_persisted_prefab_catalog_rebinds_safely_after_workspace_scene_switch(tmp_path) -> None:
    serializer = _serializer()
    main = Scene()
    first = main.add(Actor("One", health=80))
    second = main.add(Actor("Two", health=60))
    workspace = EditorWorkspace(main, scene_id="scenes/main.json")
    authoring = EditorProjectAuthoring21(
        workspace,
        serializer=serializer,
        asset_root=tmp_path / "assets",
    )
    authoring.select_many((first, second))
    asset = authoring.create_prefab(
        "enemy_pair",
        relative_path="prefabs/enemy_pair.json",
    )
    assert asset.relative_path == "prefabs/enemy_pair.json"
    assert (tmp_path / "assets/prefabs/enemy_pair.json").is_file()

    main_spawn = authoring.instantiate_prefab("enemy_pair")
    assert len(main_spawn.instance.objects) == 2
    assert len(authoring.frame().prefab_bindings) == 1

    other = Scene()
    workspace.switch_scene("scenes/other.json", other)
    rebound = authoring.frame()
    assert rebound.scene_id == "scenes/other.json"
    assert rebound.selection.count == 0
    assert [item.asset_id for item in rebound.prefab_assets] == ["enemy_pair"]
    assert rebound.prefab_bindings == ()

    other_spawn = authoring.instantiate_prefab("enemy_pair")
    assert [item.name for item in other_spawn.instance.objects] == ["One", "Two"]
    assert [item.health for item in other_spawn.instance.objects] == [80, 60]
    assert len(other.objects) == 2


def test_in_memory_prefabs_remain_scene_local_across_rebind(tmp_path) -> None:
    scene = Scene()
    actor = scene.add(Actor("One"))
    workspace = EditorWorkspace(scene, scene_id="scenes/main.json")
    authoring = EditorProjectAuthoring21(
        workspace,
        serializer=_serializer(),
        asset_root=tmp_path / "assets",
    )
    authoring.select(actor)
    authoring.create_prefab("temporary")
    assert [item.asset_id for item in authoring.frame().prefab_assets] == ["temporary"]

    workspace.switch_scene("scenes/other.json", Scene())
    assert authoring.frame().prefab_assets == ()


def test_bridge_rebind_preserves_primary_workspace_selection(tmp_path) -> None:
    first_scene = Scene()
    first = first_scene.add(Actor("First"))
    workspace = EditorWorkspace(first_scene, scene_id="scenes/first.json")
    authoring = EditorProjectAuthoring21(workspace, asset_root=tmp_path / "assets")
    authoring.select(first)

    second_scene = Scene()
    second = second_scene.add(Actor("Second"))
    workspace.switch_scene("scenes/second.json", second_scene)
    workspace.select(second)

    rebound = authoring.frame()
    assert rebound.selection.count == 1
    assert rebound.selection.primary_key == workspace.inspector.key_for(second)
    assert {field.name for field in rebound.fields} >= {"name", "health", "texture"}
