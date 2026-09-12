from __future__ import annotations

import json
from dataclasses import dataclass

import pytest

from swirengine import (
    Prefab,
    Rectangle2D,
    Scene,
    SceneCodecRegistry,
    SceneSerializationError,
    SceneSerializer,
)
from swirengine.ecs import ECSWorld


@dataclass(slots=True)
class Position:
    x: float
    y: float


@dataclass(slots=True)
class Target:
    value: object


def serializer_with_components() -> SceneSerializer:
    registry = SceneCodecRegistry.default()
    registry.register(Position, name="tests.Position")
    registry.register(Target, name="tests.Target")
    return SceneSerializer(registry)


def test_world_can_restore_stable_ids_and_allocator_moves_forward() -> None:
    world = ECSWorld()
    restored = world.create_entity(entity_id=42, name="restored")

    assert restored.id == 42
    assert world.create_entity().id == 43

    with pytest.raises(ValueError, match="already exists"):
        world.create_entity(entity_id=42)
    with pytest.raises(ValueError, match=">= 1"):
        world.create_entity(entity_id=0)


def test_scene_round_trip_persists_ecs_metadata_components_and_scene_refs() -> None:
    serializer = serializer_with_components()
    scene = Scene()
    target = scene.add(Rectangle2D(1, 2, 3, 4, name="target"))
    entity = scene.ecs.create_entity(
        entity_id=17,
        name="enemy",
        enabled=False,
        tags={"flying", "enemy"},
    )
    entity.add(Position(10.0, 20.0))
    entity.add(Target(target))

    text = serializer.dumps_scene(scene)
    document = json.loads(text)
    restored = serializer.loads_scene(text)

    assert document["version"] == 2
    assert len(restored.entities) == 1
    restored_entity = restored.entities[0]
    assert restored_entity.id == 17
    assert restored_entity.name == "enemy"
    assert not restored_entity.enabled
    assert restored_entity.tags == {"flying", "enemy"}
    assert restored_entity.require(Position) == Position(10.0, 20.0)
    assert restored_entity.require(Target).value is restored.objects[0]
    assert restored.ecs.create_entity().id == 18


def test_version_one_scene_and_prefab_documents_migrate_automatically() -> None:
    serializer = serializer_with_components()
    old_scene = {"format": "swirengine.scene", "version": 1, "objects": []}
    restored_scene = serializer.loads_scene(json.dumps(old_scene))
    assert restored_scene.entities == ()

    prefab = Prefab(Rectangle2D(0, 0, 1, 1, name="crate"), name="crate")
    old_prefab = json.loads(serializer.dumps_prefab(prefab))
    old_prefab["version"] = 1
    restored_prefab = serializer.loads_prefab(json.dumps(old_prefab))
    assert restored_prefab.name == "crate"


def test_duplicate_or_conflicting_persisted_entity_ids_are_rejected() -> None:
    serializer = serializer_with_components()
    duplicate = {
        "format": "swirengine.scene",
        "version": 2,
        "objects": [],
        "ecs": [
            {"id": 1, "name": "a", "enabled": True, "tags": [], "components": []},
            {"id": 1, "name": "b", "enabled": True, "tags": [], "components": []},
        ],
    }
    with pytest.raises(SceneSerializationError, match="duplicate ECS entity id"):
        serializer.loads_scene(json.dumps(duplicate))

    target = Scene()
    target.ecs.create_entity(entity_id=1)
    one = {
        "format": "swirengine.scene",
        "version": 2,
        "objects": [],
        "ecs": [{"id": 1, "name": "saved", "enabled": True, "tags": [], "components": []}],
    }
    with pytest.raises(SceneSerializationError, match="already exists"):
        serializer.loads_scene(json.dumps(one), scene=target)


def test_clear_load_replaces_existing_ecs_state_without_id_conflict() -> None:
    serializer = serializer_with_components()
    source = Scene()
    source.ecs.create_entity(entity_id=3, name="saved").add(Position(1.0, 2.0))

    target = Scene()
    target.ecs.create_entity(entity_id=3, name="old")
    restored = serializer.loads_scene(serializer.dumps_scene(source), scene=target, clear=True)

    assert restored is target
    assert len(target.entities) == 1
    assert target.entities[0].name == "saved"
    assert target.entities[0].require(Position) == Position(1.0, 2.0)
