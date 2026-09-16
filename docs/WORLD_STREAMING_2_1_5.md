# SwirEngine 1.5 — World Streaming 2.0

World Streaming 2.0 lets a game keep a large authored world split into small scene-owned cells and
activate only the nearby content. The system is additive to the released 1.x API: existing
`LargeWorldStreamer`, `Scene`, `SceneMount`, asset streaming and normal game code remain valid.

The design has two layers:

- `swirengine.world_streaming15` — strict deterministic runtime for engine/game-framework code;
- `swirengine.world_streaming_easy15` — creator-first facade for normal game code.

The facade exists so a beginner does not need to understand registries, mount ownership or strict
`ChunkContent` construction before making a world.

## Smallest useful example

```python
from swirengine.world_streaming_easy15 import world_stream

world = world_stream(
    game,
    dimensions=2,
    chunk_size=512,
    radius=1,
    budget=12,
    loads_per_update=2,
)

@world.chunk("village", (0, 0))
def village(ctx):
    return [
        Sprite2D("house.png", x=ctx.center.x, y=ctx.center.y),
        Sprite2D("tree.png", x=ctx.center.x + 120, y=ctx.center.y),
    ]

@world.chunk("forest", (1, 0), cost=2)
def forest(ctx):
    return build_forest(ctx.origin)

@game.update
def update(_dt):
    world.update((player.x, player.y))
```

A creator factory may return:

- one scene object;
- a list/tuple/generator of scene objects;
- ECS entities;
- a mixture of objects and entities;
- explicit `ChunkContent`;
- `None` for a logical/lifecycle-only cell.

The facade converts all of those forms into the strict runtime contract.

## Loading-screen warmup

Runtime work budgets are deliberately bounded so normal frames cannot suddenly activate a huge
number of cells. For a spawn/loading screen, use `warmup()` instead of temporarily changing those
budgets:

```python
world.warmup(player_spawn, max_updates=64)
```

`warmup()` performs multiple ordinary deterministic streaming updates until residency settles or
the safety limit is reached. This preserves exactly the same activation rules used during gameplay.

## Dependencies

A cell can require another cell to be resident first:

```python
@world.chunk("castle-interior", (5, 2), dependencies=("castle-shell",))
def castle_interior(ctx):
    return build_interior(ctx)
```

Dependencies are validated before runtime start. Missing dependencies and dependency cycles fail
with clear errors instead of becoming intermittent runtime bugs. Activation happens dependency
first; deactivation happens in the safe reverse order.

## Budgets and priority

Each cell has a small creator-defined integer `cost` (default `1`). Cost is intentionally a coarse
content weight, not fake measured bytes. The runtime admits cells until `budget` /
`max_active_cost` is reached.

```python
@world.chunk("boss-arena", (8, 4), cost=4, priority=20)
def boss_arena(ctx):
    return build_boss_arena(ctx)
```

Priority only affects deterministic admission order when desired cells compete for the same hard
budget. Distance and stable cell IDs provide deterministic tie breaking.

Per-update activation and deactivation limits bound the amount of scene churn in one frame.
`retention_updates` adds a short hysteresis period so movement around a cell border does not cause
constant load/unload thrashing.

## Lifecycle hooks

For systems that need explicit transition work, cells may define `on_activate` and
`on_deactivate` hooks. Scene objects still receive the normal `Scene` lifecycle (`on_added_to_scene`,
`on_start`, `on_stop`, `on_removed_from_scene`) because residency uses `Scene.mount(...)` instead of
inventing a second object-lifecycle system.

```python
def on_town_open(ctx, content):
    music.enter_region("town")


def on_town_close(ctx, content):
    music.leave_region("town")

world.add_chunk(
    "town",
    (0, 0),
    build_town,
    on_activate=on_town_open,
    on_deactivate=on_town_close,
)
```

## Failure isolation and retry

A creator factory failure does not leave a half-mounted cell behind. The runtime records the
failure and skips repeated activation attempts until the creator explicitly retries it:

```python
for failure in world.runtime.failures():
    print(failure.cell_id, failure.message)

world.retry("forest")
```

If an activation hook fails after content was mounted, the mount is rolled back before the failure
is recorded.

## Diagnostics

`world.diagnostics` exposes bounded, portable counters:

- current focus key;
- local keys inspected;
- desired/target/active cells;
- active cost;
- cells blocked by the hard budget;
- failed cells;
- total activations/deactivations.

The strict runtime also provides `state_fingerprint()` for regression tests, replay/server
verification and deterministic diagnostics.

```python
print(world.active)
print(world.diagnostics.active_cost)
print(world.state_fingerprint())
```

## Explicit content helper

Most factories can simply return objects. When a creator wants to be explicit:

```python
from swirengine.world_streaming_easy15 import chunk_content

@world.chunk("dungeon", (3, 1))
def dungeon(ctx):
    trigger = ctx.scene.create_entity(name="dungeon-trigger")
    return chunk_content(
        build_floor(ctx),
        build_walls(ctx),
        entities=(trigger,),
    )
```

## Strict runtime

Framework/game-tooling code can use the lower-level API directly:

```python
from swirengine.large_world import ChunkContent, ChunkKey
from swirengine.world_streaming15 import (
    WorldPartitionCell,
    WorldPartitionRegistry,
    WorldStreamingRuntime,
    WorldStreamingSettings,
)

registry = WorldPartitionRegistry([
    WorldPartitionCell(
        "spawn",
        ChunkKey(0, 0, 0),
        lambda ctx: ChunkContent(objects=(build_spawn(ctx),)),
    ),
])

runtime = WorldStreamingRuntime(
    game.scene,
    registry,
    settings=WorldStreamingSettings(dimensions=3),
)
runtime.update(player.position)
```

The strict layer provides dependency validation, deterministic target selection, active-cost
admission, bounded activation/deactivation, retention, lifecycle rollback, failure tracking,
portable diagnostics and deterministic fingerprints.

## Performance contract

The registry keeps O(1) cell-id lookup and O(1) chunk-key buckets. An update enumerates only the
fixed local chunk window around the current focus; it does not scan the complete authored world.
The dedicated benchmark registers 10,000 cells and repeatedly moves the focus while enforcing a
generous regression budget in CI.

## Compatibility rule

World Streaming 2.0 intentionally lives in 1.5 additive modules. It does not replace the stable
root imports, `Scene`, `LargeWorldStreamer`, `ChunkRegistry`, or existing asset-streaming behavior.
The creator facade is convenience on top of the strict runtime, not a second streaming engine.
