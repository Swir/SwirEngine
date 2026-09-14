from dataclasses import dataclass

import pytest

from swirengine import ECSDiagnostics, ECSWorld, Prefab, Scene, SceneDiagnostics, SceneMount


@dataclass
class Position:
    x: float


@dataclass
class Velocity:
    x: float


class SpecialPosition(Position):
    pass


class LifecycleObject:
    def __init__(self, name: str):
        self.name = name
        self.events = []

    def on_added_to_scene(self, scene):
        self.events.append(("added", scene))

    def on_start(self, scene):
        self.events.append(("start", scene))

    def update(self, dt):
        self.events.append(("update", dt))

    def on_stop(self, scene):
        self.events.append(("stop", scene))

    def on_removed_from_scene(self, scene):
        self.events.append(("removed", scene))


def test_new_creator_types_are_available_from_stable_top_level_api():
    assert ECSDiagnostics().query_calls == 0
    assert SceneDiagnostics().snapshot_rebuilds == 0
    assert SceneMount


def test_scene_lifecycle_runs_once_and_cached_snapshot_rebuilds_only_on_mutation():
    scene = Scene()
    obj = scene.add(LifecycleObject("hero"))
    scene.update(0.1)
    scene.update(0.2)
    assert [event[0] for event in obj.events] == ["added", "start", "update", "update"]
    assert scene.diagnostics.snapshot_rebuilds == 1
    assert scene.diagnostics.object_updates == 2

    extra = scene.add(LifecycleObject("extra"))
    scene.update(0.3)
    assert scene.diagnostics.snapshot_rebuilds == 2
    assert scene.remove(extra)
    assert [event[0] for event in extra.events][-2:] == ["stop", "removed"]
    assert scene.remove(obj)
    assert [event[0] for event in obj.events][-2:] == ["stop", "removed"]


def test_scene_mount_takes_ownership_of_existing_and_new_grouped_content_once():
    scene = Scene()
    existing = scene.add(LifecycleObject("existing"))
    new = LifecycleObject("new")
    entity = scene.compose_entity(Position(1.0), name="enemy")
    mount = scene.mount(existing, new, entities=(entity,))
    assert len(scene) == 2
    assert scene.entities == (entity,)
    assert mount.unmount() == (2, 1)
    assert mount.unmount() == (0, 0)
    assert len(scene) == 0
    assert scene.entities == ()


def test_scene_mount_validates_entities_before_adding_objects():
    scene = Scene()
    foreign = Scene().create_entity(name="foreign")
    obj = LifecycleObject("room")
    with pytest.raises(ValueError):
        scene.mount(obj, entities=(foreign,))
    assert obj not in scene


def test_compose_entity_rolls_back_when_component_bundle_is_invalid():
    world = ECSWorld()
    with pytest.raises(ValueError):
        world.compose_entity(Position(1.0), Position(2.0), name="invalid")
    assert world.entities == ()


def test_indexed_query_preserves_subclass_semantics_and_limits_candidates():
    world = ECSWorld()
    for index in range(1000):
        world.compose_entity(Position(float(index)), name=f"static-{index}")
    moving = world.compose_entity(SpecialPosition(1.0), Velocity(2.0), name="moving")
    world.diagnostics.reset()

    assert world.query(Position, Velocity) == (moving,)
    assert world.diagnostics.query_calls == 1
    assert world.diagnostics.query_candidates == 1
    assert world.diagnostics.query_matches == 1

    moving.remove(Velocity)
    world.diagnostics.reset()
    assert world.query(Position, Velocity) == ()
    assert world.diagnostics.query_candidates == 0


def test_indexed_query_preserves_entity_insertion_order_with_restored_ids():
    world = ECSWorld()
    first = world.create_entity(entity_id=50)
    first.add(Position(1.0))
    first.add(Velocity(1.0))
    second = world.create_entity(entity_id=2)
    second.add(Position(2.0))
    second.add(Velocity(2.0))
    assert world.query(Position, Velocity) == (first, second)


def test_system_order_cache_and_world_lifecycle_hooks_are_deterministic():
    world = ECSWorld()
    events = []

    class System:
        def on_added_to_world(self, current):
            events.append(("added", current))

        def update(self, current, dt):
            events.append(("update", current, dt))

        def on_removed_from_world(self, current):
            events.append(("removed", current))

    system = world.add_system(System(), priority=4)
    world.update(0.25)
    world.update(0.5)
    assert world.diagnostics.system_updates == 2
    assert world.remove_system(system)
    assert [event[0] for event in events] == ["added", "update", "update", "removed"]


def test_prefab_batch_instances_are_independent_and_registered_in_spawn_order():
    source = LifecycleObject("enemy")
    source.hp = 10
    prefab = Prefab(source, name="enemy")
    scene = Scene()
    instances = prefab.instantiate_many(
        3,
        scene,
        overrides=(
            {"enemy": {"hp": 11}},
            {"enemy": {"hp": 12}},
            {"enemy": {"hp": 13}},
        ),
    )
    assert tuple(instance.root.hp for instance in instances) == (11, 12, 13)
    assert scene.objects == tuple(instance.root for instance in instances)
    instances[0].root.hp = 99
    assert instances[1].root.hp == 12
