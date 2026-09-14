from dataclasses import dataclass

from swirengine.core.scene import Scene
from swirengine.ecs import ECSWorld
from swirengine.prefab import Prefab


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


def test_scene_mount_unloads_grouped_objects_and_entities_once():
    scene = Scene()
    first = LifecycleObject("first")
    second = LifecycleObject("second")
    entity = scene.compose_entity(Position(1.0), name="enemy")
    mount = scene.mount(first, second, entities=(entity,))
    assert len(scene) == 2
    assert scene.entities == (entity,)
    assert mount.unmount() == (2, 1)
    assert mount.unmount() == (0, 0)
    assert len(scene) == 0
    assert scene.entities == ()


def test_compose_entity_rolls_back_when_component_bundle_is_invalid():
    world = ECSWorld()
    try:
        world.compose_entity(Position(1.0), Position(2.0), name="invalid")
    except ValueError:
        pass
    else:
        raise AssertionError("duplicate component type should fail")
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
