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

When created with `world_stream(game, ...)`, the facade also detects the owner's normal
`remove(...)` path. Streamed scene objects are routed through it during normal unload and during
activation-hook rollback before the Scene mount is released, so Game-managed resources such as
registered 2D physics/UI ownership do not get stranded. Owner cleanup is best-effort across the
whole chunk: if one `remove(...)` call raises, remaining objects are still offered to the owner,
the first cleanup error is then reported by the streaming failure record, and the Scene mount is
still released. Passing a raw `Scene` keeps pure scene ownership instead.

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
with clear errors instead of becoming intermittent runtime bugs. A plain string is rejected instead
of being interpreted as one dependency per character. Activation happens dependency first;
deactivation happens in the safe reverse order.

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
for failure in world.failures:
    print(failure.cell_id, failure.message)

world.retry("forest")
```

If an activation hook fails after content was mounted, the mount is rolled back before the failure
is recorded. With `world_stream(game, ...)`, owner-specific cleanup also runs during that rollback.

## Registration-safe inspection

Reading creator-facing state should not accidentally close world registration before gameplay
starts. Before the first `update()`/`warmup()` call:

- `world.active` is empty;
- `world.active_cost` is `0`;
- `world.diagnostics` is `None`;
- `world.failures` is empty;
- `world.context(cell_id)` returns the deterministic cell geometry without starting the runtime;
- `world.retry(cell_id)` validates the cell and returns `False` without starting the runtime.

Accessing `world.runtime` explicitly still constructs the strict runtime and therefore intentionally
freezes registration. This keeps the low-level escape hatch explicit.

## Diagnostics

The diagnostics record includes:

- current focus key;
- local keys inspected;
- desired/target/active cells;
- active cost;
- cells blocked by the hard budget;
- failed cells;
- total activations/deactivations.

`unload_all()` refreshes the diagnostic snapshot after cleanup, so active count/cost, target state,
failure count and total deactivations stay coherent with the runtime state and its fingerprint.

The strict runtime also provides `state_fingerprint()` for regression tests, replay/server
verification and deterministic diagnostics.

```python
print(world.active)
print(world.active_cost)
print(world.diagnostics)
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

`WorldStreamingSettings.dimensions` is an integer-only `2`/`3` contract. A 2D strict runtime rejects
cells with nonzero `ChunkKey.z`, matching the creator facade instead of leaving unreachable cells in
the registry. Focus coordinates are required to be finite for tuples/sequences and `Vec2`/`Vec3`
inputs before chunk addressing reaches `floor()`. In 2D, a supplied `Vec3` must also use `z=0`
instead of silently discarding a nonzero third coordinate. Rejected focus updates are validated
before the runtime update counter advances, so invalid input cannot perturb later deterministic
contexts, diagnostics or fingerprints.

## Performance contract

The registry keeps O(1) cell-id lookup and O(1) chunk-key buckets. Each runtime update enumerates
only the fixed local chunk window plus the small resident/failed sets; it does not scan the complete
authored world to discover active cells, failures or current budget usage. Active cost is maintained
incrementally in O(1).

The dedicated CI workload registers 10,000 cells and performs 1,200 focus updates while enforcing a
3.0-second regression budget. Its radius-2 2D window is bounded to 25 chunk keys per update. The
budget is deliberately a workload guard, not an FPS claim; it exists to catch accidental
O(total-world) hot paths behind the creator-friendly API.

## Compatibility rule

World Streaming 2.0 intentionally lives in 1.5 additive modules. It does not replace the stable
root imports, `Scene`, `LargeWorldStreamer`, `ChunkRegistry`, or existing asset-streaming behavior.
The creator facade is convenience on top of the strict runtime, not a second streaming engine.
