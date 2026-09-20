from __future__ import annotations

from dataclasses import dataclass

import pytest

from swirengine import Scene
from swirengine.editor import SceneInspector
from swirengine.editor_component_authoring import EditorComponentAuthoringSession
from swirengine.editor_prefab_authoring import EditorPrefabAuthoring
from swirengine.editor_typed_inspector import EditorTypedInspector
from swirengine.serialization import SceneCodecRegistry, SceneSerializer


@dataclass
class PrefabActor:
    name: str
    health: int = 100
    speed: float = 3.0


def _workflow(tmp_path):
    registry = SceneCodecRegistry.default()
    registry.register(PrefabActor)
    serializer = SceneSerializer(registry)
    scene = Scene()
    first = scene.add(PrefabActor("One", health=80))
    second = scene.add(PrefabActor("Two", health=60))
    session = EditorComponentAuthoringSession(SceneInspector(scene))
    session.select(first)
    session.select(second, mode="add")
    prefabs = EditorPrefabAuthoring(
        session,
        serializer=serializer,
        asset_root=tmp_path / "assets",
    )
    return scene, first, second, session, prefabs


def test_create_persist_instantiate_apply_revert_and_reinstantiate(tmp_path) -> None:
    scene, first, second, session, prefabs = _workflow(tmp_path)
    asset = prefabs.create_from_selection(
        "enemy_pair",
        name="Enemy Pair",
        relative_path="prefabs/enemy_pair.json",
    )
    assert asset.revision == 1
    assert (tmp_path / "assets/prefabs/enemy_pair.json").is_file()

    spawned = prefabs.instantiate("enemy_pair")
    assert len(spawned.instance.objects) == 2
    assert len(scene.objects) == 4
    clone_one, clone_two = spawned.instance.objects
    assert clone_one is not first and clone_two is not second
    assert session.selection_snapshot.keys == spawned.binding.target_keys

    typed = EditorTypedInspector(session)
    typed.set("health", "40")
    assert clone_one.health == 40 and clone_two.health == 40

    applied = prefabs.apply(spawned.binding.binding_id)
    assert applied.revision == 2
    assert prefabs.binding(spawned.binding.binding_id).asset_revision == 2

    typed.set("health", "5")
    assert clone_one.health == 5 and clone_two.health == 5
    revert_transaction = prefabs.revert(spawned.binding.binding_id)
    assert revert_transaction.edit_count == 2
    assert clone_one.health == 40 and clone_two.health == 40

    session.undo()
    assert clone_one.health == 5 and clone_two.health == 5
    session.redo()
    assert clone_one.health == 40 and clone_two.health == 40

    fresh = prefabs.instantiate("enemy_pair", select_instance=False)
    fresh_one, fresh_two = fresh.instance.objects
    assert fresh_one.health == 40 and fresh_two.health == 40


def test_load_asset_round_trip_uses_registered_serializer(tmp_path) -> None:
    _scene, _first, _second, _session, prefabs = _workflow(tmp_path)
    prefabs.create_from_selection("saved", relative_path="prefabs/saved.json")

    registry = SceneCodecRegistry.default()
    registry.register(PrefabActor)
    other_scene = Scene()
    other_session = EditorComponentAuthoringSession(SceneInspector(other_scene))
    loaded = EditorPrefabAuthoring(
        other_session,
        serializer=SceneSerializer(registry),
        asset_root=tmp_path / "assets",
    )
    asset = loaded.load_asset("saved", "prefabs/saved.json")
    spawned = loaded.instantiate(asset.asset_id)

    assert [actor.name for actor in spawned.instance.objects] == ["One", "Two"]
    assert [actor.health for actor in spawned.instance.objects] == [80, 60]


def test_prefab_paths_reject_absolute_drive_and_parent_traversal(tmp_path) -> None:
    _scene, _first, _second, _session, prefabs = _workflow(tmp_path)

    for unsafe in ("../escape.json", "/tmp/escape.json", "C:\\escape.json"):
        with pytest.raises(ValueError):
            prefabs.create_from_selection(
                f"bad-{len(unsafe)}",
                relative_path=unsafe,
            )


def test_prefab_creation_rejects_ecs_entity_selection(tmp_path) -> None:
    scene = Scene()
    entity = scene.create_entity(name="Entity")
    session = EditorComponentAuthoringSession(SceneInspector(scene))
    session.select(entity)
    prefabs = EditorPrefabAuthoring(session, asset_root=tmp_path)

    with pytest.raises(TypeError):
        prefabs.create_from_selection("entity-prefab")


def test_missing_instance_target_blocks_apply_and_revert_without_partial_work(tmp_path) -> None:
    scene, _first, _second, _session, prefabs = _workflow(tmp_path)
    prefabs.create_from_selection("enemy_pair")
    spawned = prefabs.instantiate("enemy_pair", select_instance=False)
    first_clone = spawned.instance.objects[0]
    scene.remove(first_clone)

    with pytest.raises(LookupError):
        prefabs.apply(spawned.binding.binding_id)
    with pytest.raises(LookupError):
        prefabs.revert(spawned.binding.binding_id)
