from dataclasses import dataclass

import pytest

from swirengine import ECSWorld
from swirengine.core.scene import Scene


@dataclass
class Position:
    x: float
    y: float


@dataclass
class Velocity:
    x: float
    y: float


class SpecialPosition(Position):
    pass


def test_entity_component_lifecycle_and_base_type_lookup():
    world = ECSWorld()
    entity = world.create_entity(name="hero", tags={"player"})
    component = entity.add(SpecialPosition(2.0, 3.0))
    assert entity.get(Position) is component
    assert entity.require(Position) is component
    assert entity.has(Position)
    with pytest.raises(ValueError):
        entity.add(SpecialPosition(4.0, 5.0))
    replacement = entity.set(SpecialPosition(6.0, 7.0))
    assert entity.remove(Position) is replacement
    with pytest.raises(KeyError):
        entity.require(Position)


def test_world_ids_find_destroy_and_clear_detach_entities():
    world = ECSWorld()
    first = world.create_entity(name="first")
    second = world.create_entity(name="second")
    assert (first.id, second.id) == (1, 2)
    assert world.entity(second.id) is second
    assert world.find("first") is first
    assert first.destroy()
    assert not first.destroy()
    world.clear()
    assert world.entities == ()
    assert not second.destroy()


def test_query_filters_components_enabled_state_and_tags():
    world = ECSWorld()
    moving = world.create_entity(tags={"enemy", "flying"})
    moving.add(Position(0.0, 0.0))
    moving.add(Velocity(1.0, 2.0))
    sleeping = world.create_entity(enabled=False, tags={"enemy"})
    sleeping.add(Position(3.0, 4.0))
    assert world.query(Position, Velocity) == (moving,)
    assert world.query(Position, tags={"enemy"}) == (moving,)
    assert world.query(Position, enabled_only=False) == (moving, sleeping)
    assert world.query(Position, tags={"flying"}) == (moving,)


def test_rows_return_entity_and_components_in_requested_order():
    world = ECSWorld()
    entity = world.create_entity()
    position = entity.add(Position(1.0, 2.0))
    velocity = entity.add(Velocity(3.0, 4.0))
    assert world.rows(Velocity, Position) == ((entity, velocity, position),)


def test_systems_run_by_priority_then_registration_order_and_respect_enabled():
    world = ECSWorld()
    calls = []

    def late(current, dt):
        calls.append(("late", current is world, dt))

    class System:
        enabled = True

        def __init__(self, name):
            self.name = name

        def update(self, current, dt):
            calls.append((self.name, current is world, dt))

    first = System("first")
    disabled = System("disabled")
    disabled.enabled = False
    world.add_system(late, priority=10)
    world.add_system(first, priority=-5)
    world.add_system(disabled, priority=-10)
    assert world.systems == (disabled, first, late)
    world.update(0.25)
    assert calls == [("first", True, 0.25), ("late", True, 0.25)]


def test_system_validation_duplicate_and_negative_dt():
    world = ECSWorld()
    system = lambda _world, _dt: None
    world.add_system(system)
    with pytest.raises(ValueError):
        world.add_system(system)
    with pytest.raises(TypeError):
        world.add_system(object())
    with pytest.raises(ValueError):
        world.update(-0.01)


def test_scene_owns_ecs_world_and_updates_it_after_scene_objects():
    scene = Scene()
    calls = []

    class Object:
        def update(self, dt):
            calls.append(("object", dt))

    entity = scene.create_entity(name="hero", tags={"player"})
    entity.add(Position(1.0, 2.0))
    scene.add(Object())
    scene.ecs.add_system(lambda _world, dt: calls.append(("ecs", dt)))
    assert scene.entities == (entity,)
    assert scene.query_entities(Position, tags={"player"}) == (entity,)
    scene.update(0.5)
    assert calls == [("object", 0.5), ("ecs", 0.5)]
    scene.clear(clear_entities=False)
    assert scene.entities == (entity,)
    scene.clear()
    assert scene.entities == ()
