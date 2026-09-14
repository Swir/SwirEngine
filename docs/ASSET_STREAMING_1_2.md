# Asset Streaming — SwirEngine 1.2

SwirEngine 1.2 adds a budgeted asset-streaming layer on top of `AssetManager` and `AssetPreloader`.

## Goals

- keep file/decode work off the gameplay thread;
- let the game loop decide how many completed loads are finalized per frame;
- cap resident assets by both count and estimated bytes;
- use deterministic LRU eviction rather than unbounded cache growth;
- allow critical assets to be pinned;
- expose deterministic counters for staged/completed/failed loads, evictions, residency and finalize hitches.

## Runtime model

```python
from swirengine.asset_streaming import AssetStreamingBudget, AssetStreamingManager

budget = AssetStreamingBudget(
    max_resident_bytes=256 * 1024 * 1024,
    max_resident_assets=512,
    hitch_threshold_ms=4.0,
)

with AssetStreamingManager(assets, budget=budget) as streaming:
    streaming.stage_many(["world/terrain.bin", "characters/hero.bin"])

    # call once per game-loop iteration; unfinished work is never awaited here
    completed = streaming.pump(max_completions=2)
    diagnostics = streaming.diagnostics()
```

`stage()` shares duplicate in-flight requests through the existing preloader. `pump()` inspects only futures that are already complete and therefore does not deliberately wait for background decode/file work. Finalized assets enter a deterministic LRU residency set.

## Residency and eviction

The runtime enforces both `max_resident_assets` and `max_resident_bytes`. When either limit is exceeded, the least-recently-used unpinned asset is removed from residency and invalidated from `AssetManager`'s cache. `touch()` refreshes recency. `pin()` and `unpin()` let games protect assets such as the current player, UI atlas or active level core.

The default byte estimate uses the source file size. Games that decode compressed files into much larger runtime objects can provide a `size_estimator(path, value)` callback with a more realistic estimate.

## Hitch diagnostics

`AssetStreamingDiagnostics` reports:

- staged / completed / failed requests;
- current pending count;
- resident asset count and estimated bytes;
- peak resident bytes;
- eviction count;
- finalize hitch count and maximum finalize duration.

The hitch threshold applies to the game-thread `pump()` finalization path. These counters intentionally describe streaming work only and do not claim a frame-rate improvement.

## GPU resources

Background threads must not perform renderer-context operations that require the owning graphics thread. Load/decode data in the background and perform GPU upload/finalization from the render/game thread as appropriate for the active backend.
