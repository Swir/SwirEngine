# Large World / Chunk Streaming — SwirEngine 1.3

SwirEngine 1.3 adds a deterministic chunk-residency layer for games whose authored or procedural
world is much larger than the portion that should be active at one time. The subsystem is additive
to the stable 1.x scene and asset APIs: it uses `SceneMount` for grouped lifetime and can use the
existing `AssetStreamingManager` for staged background asset residency.

## Core model

A world is addressed by integer `ChunkKey(x, y, z)` values. `LargeWorldSettings.dimensions` selects
2D or 3D addressing while keeping one API. World coordinates are converted to chunk keys with
floor-based division, including negative coordinates.

Each chunk is described by `ChunkDefinition`:

```python
from swirengine.large_world import ChunkContent, ChunkDefinition, ChunkKey


def provider(key: ChunkKey) -> ChunkDefinition:
    def build(context):
        # Create objects/entities only when this chunk actually activates.
        return ChunkContent(objects=())

    return ChunkDefinition(key, build)
```

`ChunkRegistry` is supplied for finite authored worlds. A callable provider can generate definitions
on demand for effectively unbounded/procedural worlds.

## Residency states

The runtime separates three kinds of work:

1. **Tracked/preloaded** — the chunk lies inside the local preload window and its definition has been
   resolved.
2. **Ready** — declared assets have completed staged loading, or the chunk has no asset dependencies.
3. **Active** — the chunk lies inside the active window, passes an optional visibility predicate and
   its activation budget slot was available. Its `ChunkContent` is mounted into the scene.

Leaving the active window unmounts scene objects/entities. A larger retention radius can keep the
chunk definition/assets warm for quick revisits. Once the focus moves beyond retention, inactive
state is dropped and asset references are released.

## Local-window performance contract

`LargeWorldStreamer.update()` does **not** iterate every authored chunk. It enumerates only the
preload window around the current focus key:

- 2D candidate bound: `(2 * preload_radius + 1)²`
- 3D candidate bound: `(2 * preload_radius + 1)³`

For example, preload radius 2 means exactly 25 local candidate keys in 2D or 125 in 3D, independent
of whether the conceptual world contains hundreds, millions or procedurally infinite chunks.
Tracked states outside the retention radius are removed rather than accumulated forever.

`tools/benchmark_large_world.py` exercises long-distance movement through a procedural world and
gates these local-window bounds. Its wall-clock output is diagnostic only and is deliberately not
converted into an FPS claim.

## Per-frame work budgets

`LargeWorldSettings` controls:

- `max_activations_per_update`
- `max_deactivations_per_update`
- `max_asset_completions_per_update`

Activation candidates are deterministic and nearest-first. These budgets prevent a camera/player
teleport from forcing every newly relevant chunk to instantiate scene content in one frame.

## Asset streaming integration

A `ChunkDefinition` may declare asset paths. When an `AssetStreamingManager` is supplied, those
assets are staged as soon as the chunk enters the preload window. Scene content is not created until
all declared futures succeed.

Chunk residency uses reference-counted pins on top of the existing asset streamer. If neighboring
chunks share one texture/model, releasing one chunk does not unpin the asset while another tracked
chunk still references it. When the last reference leaves, SwirEngine unpins the asset and lets the
existing deterministic LRU budget decide when to evict it; chunk streaming does not bypass or
replace asset-cache policy.

## Scene and ECS ownership

Chunk factories receive `ChunkBuildContext`, including the owning `Scene`, chunk origin/center and
chunk size. The returned `ChunkContent` can contain normal scene objects and ECS entities already
created in that same scene. Activation uses `Scene.mount(...)`; deactivation uses the mount's normal
lifecycle cleanup, so scene hooks and entity destruction stay consistent with the established API.

## Visibility hooks

`update(..., visibility=...)` can reject a ready chunk from activation while keeping it preloaded.
This is useful for creator-authored portals, vertical floors, indoor/outdoor sectors or a higher-level
visibility system. It is intentionally separate from renderer frustum culling: a chunk can be kept
active while individual renderables are culled by the renderer.

## Failure and retry behavior

Background asset failures and factory/activation exceptions become creator-visible `ChunkFailure`
entries instead of silently corrupting residency. `retry(key)` rebuilds only the failed chunk state
and leaves unrelated chunks untouched.

## Current 1.3 boundaries

This milestone provides chunk lifetime, locality, asset staging and scene activation. It does **not**
claim to be:

- a terrain LOD or geometry clipmap system,
- renderer occlusion culling,
- a world-file format or editor terrain authoring tool,
- network replication/interest management,
- a persistent procedural-world database.

Those systems can build on the chunk/provider contracts without forcing a breaking change to the
stable 1.x scene and asset APIs.

See `examples/demo_large_world_streaming.py` and `tests/test_large_world.py` for executable usage and
regression contracts.
