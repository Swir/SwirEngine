from __future__ import annotations

from dataclasses import dataclass

import pytest

from swirengine.core.scene import Scene
from swirengine.large_world import ChunkContent, ChunkKey
from swirengine.world_streaming15 import (
    WorldPartitionCell,
    WorldPartitionRegistry,
    WorldStreamingRuntime,
    WorldStreamingSettings,
)
from swirengine.world_streaming_easy15 import WorldStream, chunk_content, world_stream


@dataclass
class Marker:
    name: str
    added: int = 0
    removed: int = 0

    def on_added_to_scene(self, _scene: Scene) -> None:
        self.added += 1

    def on_removed_from_scene(self, _scene: Scene) -> None:
        self.removed += 1


def empty_cell(cell_id: str, key: ChunkKey, **kwargs: object) -> WorldPartitionCell:
    return WorldPartitionCell(
        cell_id,
        key,
        lambda _ctx: ChunkContent(),
        **kwargs,
    )


def test_registry_fingerprint_is_order_independent_and_validates_dependencies() -> None:
    first = WorldPartitionRegistry(
        (
            empty_cell("root", ChunkKey(0, 0, 0)),
            empty_cell("child", ChunkKey(1, 0, 0), dependencies=("root",)),
        )
    )
    second = WorldPartitionRegistry(
        (
            empty_cell("child", ChunkKey(1, 0, 0), dependencies=("root",)),
            empty_cell("root", ChunkKey(0, 0, 0)),
        )
    )
    first.validate()
    second.validate()
    assert first.fingerprint() == second.fingerprint()

    missing = WorldPartitionRegistry(
        (empty_cell("child", ChunkKey(0, 0, 0), dependencies=("missing",)),)
    )
    with pytest.raises(KeyError):
        missing.validate()


def test_dependency_cycle_is_rejected() -> None:
    registry = WorldPartitionRegistry(
        (
            empty_cell("a", ChunkKey(0, 0, 0), dependencies=("b",)),
            empty_cell("b", ChunkKey(0, 0, 0), dependencies=("a",)),
        )
    )
    with pytest.raises(ValueError):
        registry.validate()


def test_runtime_respects_activation_budget_and_dependency_order() -> None:
    scene = Scene()
    registry = WorldPartitionRegistry(
        (
            empty_cell("base", ChunkKey(0, 0, 0), priority=5),
            empty_cell("dependent", ChunkKey(0, 0, 0), dependencies=("base",)),
            empty_cell("extra", ChunkKey(0, 0, 0)),
        )
    )
    runtime = WorldStreamingRuntime(
        scene,
        registry,
        settings=WorldStreamingSettings(
            dimensions=2,
            active_radius_chunks=0,
            max_active_cost=3,
            max_activations_per_update=1,
            max_deactivations_per_update=3,
            retention_updates=0,
        ),
    )

    first = runtime.update((0.0, 0.0))
    assert first.activated == ("base",)
    second = runtime.update((0.0, 0.0))
    assert second.activated in (("dependent",), ("extra",))
    for _ in range(3):
        runtime.update((0.0, 0.0))
    assert set(runtime.active_ids) == {"base", "dependent", "extra"}


def test_active_cost_budget_blocks_lower_ranked_cells() -> None:
    scene = Scene()
    registry = WorldPartitionRegistry(
        (
            empty_cell("important", ChunkKey(0, 0, 0), cost=2, priority=10),
            empty_cell("other", ChunkKey(0, 0, 0), cost=2),
        )
    )
    runtime = WorldStreamingRuntime(
        scene,
        registry,
        settings=WorldStreamingSettings(
            dimensions=2,
            active_radius_chunks=0,
            max_active_cost=2,
            max_activations_per_update=4,
            max_deactivations_per_update=4,
            retention_updates=0,
        ),
    )
    update = runtime.update((0.0, 0.0))
    assert runtime.active_ids == ("important",)
    assert "other" in update.blocked
    assert update.diagnostics.active_cost == 2


def test_retention_prevents_immediate_thrashing() -> None:
    scene = Scene()
    registry = WorldPartitionRegistry((empty_cell("origin", ChunkKey(0, 0, 0)),))
    runtime = WorldStreamingRuntime(
        scene,
        registry,
        settings=WorldStreamingSettings(
            dimensions=2,
            chunk_size=10,
            active_radius_chunks=0,
            max_active_cost=1,
            max_activations_per_update=1,
            max_deactivations_per_update=1,
            retention_updates=1,
        ),
    )
    runtime.update((1.0, 1.0))
    assert runtime.active_ids == ("origin",)
    runtime.update((11.0, 1.0))
    assert runtime.active_ids == ("origin",)
    runtime.update((11.0, 1.0))
    assert runtime.active_ids == ()


def test_factory_failure_is_isolated_and_retryable() -> None:
    scene = Scene()
    attempts = 0

    def factory(_ctx):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise RuntimeError("temporary")
        return ChunkContent()

    runtime = WorldStreamingRuntime(
        scene,
        WorldPartitionRegistry((WorldPartitionCell("fragile", ChunkKey(0, 0, 0), factory),)),
        settings=WorldStreamingSettings(
            dimensions=2,
            active_radius_chunks=0,
            max_active_cost=1,
            max_activations_per_update=1,
            max_deactivations_per_update=1,
            retention_updates=0,
        ),
    )
    first = runtime.update((0.0, 0.0))
    assert first.failed
    assert runtime.active_ids == ()
    assert runtime.retry("fragile")
    second = runtime.update((0.0, 0.0))
    assert second.activated == ("fragile",)
    assert runtime.active_ids == ("fragile",)


def test_creator_facade_normalizes_objects_and_entities_and_unloads_cleanly() -> None:
    scene = Scene()
    marker = Marker("spawn")
    created_entity = None
    world = WorldStream(
        scene,
        dimensions=2,
        chunk_size=10,
        radius=0,
        budget=2,
        loads_per_update=2,
        unloads_per_update=2,
        retention_updates=0,
    )

    @world.chunk("spawn", (0, 0))
    def build(ctx):
        nonlocal created_entity
        created_entity = ctx.scene.create_entity(name="streamed-entity")
        return [marker, created_entity]

    update = world.update((1.0, 1.0))
    assert update.activated == ("spawn",)
    assert marker in scene
    assert marker.added == 1
    assert created_entity is not None
    assert scene.ecs.entity(created_entity.id) is created_entity

    world.update((20.0, 0.0))
    assert marker not in scene
    assert marker.removed == 1
    assert scene.ecs.entity(created_entity.id) is None


def test_creator_facade_accepts_single_object_none_and_explicit_content() -> None:
    scene = Scene()
    single = Marker("single")
    explicit = Marker("explicit")
    world = WorldStream(
        scene,
        dimensions=2,
        radius=0,
        budget=3,
        loads_per_update=3,
        retention_updates=0,
    )
    world.add_chunk("single", (0, 0), lambda _ctx: single)
    world.add_chunk("empty", (0, 0), lambda _ctx: None)
    world.add_chunk("explicit", (0, 0), lambda _ctx: chunk_content(explicit))
    world.warmup((0.0, 0.0), max_updates=4)
    assert set(world.active) == {"single", "empty", "explicit"}
    assert single in scene
    assert explicit in scene


def test_warmup_respects_runtime_budget_but_resolves_multiple_updates() -> None:
    scene = Scene()
    world = WorldStream(
        scene,
        dimensions=2,
        radius=0,
        budget=3,
        loads_per_update=1,
        retention_updates=0,
    )
    for index in range(3):
        world.add_chunk(f"cell-{index}", (0, 0), lambda _ctx: None)
    result = world.warmup((0.0, 0.0), max_updates=5)
    assert len(world.active) == 3
    assert result.activated == ()
    assert result.deactivated == ()


def test_creator_introspection_does_not_start_or_seal_registration() -> None:
    world = WorldStream(Scene(), dimensions=2, radius=0)
    assert not world.started
    assert world.active == ()
    assert world.active_cost == 0
    assert world.diagnostics is None
    assert world.failures == ()
    assert not world.started
    world.add_chunk("still-open", (0, 0), lambda _ctx: None)
    assert not world.started


def test_context_and_retry_before_start_keep_registration_open() -> None:
    world = WorldStream(Scene(), dimensions=2, chunk_size=10.0, radius=0)
    world.add_chunk("probe", (2, 3), lambda _ctx: None)

    context = world.context("probe")
    assert (context.origin.x, context.origin.y, context.origin.z) == (20.0, 30.0, 0.0)
    assert (context.center.x, context.center.y, context.center.z) == (25.0, 35.0, 0.0)
    assert context.update_index == 0
    assert not world.started
    assert not world.retry("probe")
    assert not world.started

    world.add_chunk("still-open", (4, 3), lambda _ctx: None)
    assert not world.started


def test_dependency_string_is_rejected_instead_of_becoming_character_ids() -> None:
    world = WorldStream(Scene(), dimensions=2, radius=0)
    with pytest.raises(TypeError):
        world.add_chunk("child", (0, 0), lambda _ctx: None, dependencies="base")


def test_registration_closes_after_streaming_starts() -> None:
    world = WorldStream(Scene(), dimensions=2, radius=0)
    world.add_chunk("first", (0, 0), lambda _ctx: None)
    world.update((0.0, 0.0))
    with pytest.raises(RuntimeError):
        world.add_chunk("late", (1, 0), lambda _ctx: None)


def test_world_stream_helper_accepts_game_like_owner_and_context_manager_unloads() -> None:
    class Owner:
        def __init__(self) -> None:
            self.scene = Scene()

    owner = Owner()
    marker = Marker("owned")
    with world_stream(
        owner,
        dimensions=2,
        radius=0,
        budget=1,
        retention_updates=0,
    ) as world:
        world.add_chunk("owned", (0, 0), lambda _ctx: marker)
        world.update((0.0, 0.0))
        assert marker in owner.scene
    assert marker not in owner.scene


def test_state_fingerprint_is_reproducible() -> None:
    def build(order: tuple[str, ...]) -> WorldStreamingRuntime:
        scene = Scene()
        cells = {
            "a": empty_cell("a", ChunkKey(0, 0, 0)),
            "b": empty_cell("b", ChunkKey(1, 0, 0)),
            "c": empty_cell("c", ChunkKey(0, 1, 0)),
        }
        runtime = WorldStreamingRuntime(
            scene,
            WorldPartitionRegistry(cells[name] for name in order),
            settings=WorldStreamingSettings(
                dimensions=2,
                active_radius_chunks=1,
                max_active_cost=3,
                max_activations_per_update=3,
                max_deactivations_per_update=3,
                retention_updates=0,
            ),
        )
        runtime.update((0.0, 0.0))
        return runtime

    first = build(("a", "b", "c"))
    second = build(("c", "b", "a"))
    assert first.state_fingerprint() == second.state_fingerprint()


def test_2d_key_validation_rejects_3d_coordinates() -> None:
    world = WorldStream(Scene(), dimensions=2)
    with pytest.raises(ValueError):
        world.add_chunk("wrong", ChunkKey(0, 0, 1), lambda _ctx: None)
    with pytest.raises(ValueError):
        world.add_chunk("wrong-len", (0, 0, 0), lambda _ctx: None)
