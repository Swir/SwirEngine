# SwirEngine 1.8 Visibility & LOD Submission 3.0

SwirEngine 1.8 Milestone 5 adds an **opt-in, renderer-independent visibility candidate index and LOD submission contract** for real 2D/3D game scenes. It is designed to avoid full-scene render submission scans while keeping culling policy and visual LOD decisions explicit and creator/backend controlled.

This system does **not** replace `Renderer2`, silently enable culling, or claim GPU/FPS gains by itself. Existing stable 1.x scenes behave exactly as before unless a creator/backend explicitly uses `swirengine.visibility18`.

## What it solves

Large levels often contain thousands of objects while only a small fraction matter to the current camera. A production renderer needs a bounded path that can:

- reduce a world-sized registry to nearby spatial candidates;
- perform an exact conservative bounds overlap before renderer-specific tests;
- let a backend add frustum, portal, occlusion, room or gameplay predicates;
- select deterministic LOD bands without rapid threshold flicker;
- keep ordering reproducible for later render submission;
- expose portable diagnostics and fingerprints for tests/profilers;
- fail explicitly when configured spatial/candidate budgets are exceeded instead of silently dropping work.

## Public module

```python
from swirengine.visibility18 import (
    AABB3,
    VisibilityIndex,
    VisibilityItem,
    VisibilitySession,
)
```

The API is additive and contains no OpenGL/backend objects.

## 2D and 3D bounds

`AABB3` is a small world-space axis-aligned bounds contract. A 2D game can use a flat Z extent:

```python
sprite_bounds = AABB3(10, 20, 0, 42, 52, 0)
```

A 3D game supplies the full extent:

```python
crate_bounds = AABB3(-1, 0, -1, 1, 2, 1)
```

All coordinates must be finite and min/max ordering is validated before the bounds are accepted.

## Registering visible objects

```python
index = VisibilityIndex(cell_size=32.0)
index.register(
    VisibilityItem(
        "oak-1042",
        AABB3(120, 80, 0, 126, 86, 18),
        priority=5,
        lod_thresholds=(30.0, 70.0, 140.0),
        lod_hysteresis=4.0,
        tags=("world", "tree"),
    )
)
```

The uniform-grid index is conservative and deterministic. An item may occupy several cells, but `max_cells_per_item`, global `max_cells`, and `max_items` are independent hard bounds. Oversized registrations fail before registry state changes.

`replace()` updates a moving/resized item's spatial occupancy atomically after all new capacity checks pass. `remove()` releases empty buckets. Item IDs are unique.

## Querying a camera region

```python
session = VisibilitySession()
plan = index.query(
    AABB3(0, 0, -20, 200, 120, 80),
    observer=(90.0, 60.0, 10.0),
    session=session,
)
```

A query performs these stages:

1. deterministically enumerate spatial cells intersecting the query bounds;
2. gather unique candidate IDs with an explicit `max_candidates` budget;
3. run exact AABB overlap to reject conservative cell false positives;
4. apply optional tag and creator/backend predicates;
5. calculate deterministic distance-based LOD with cross-frame hysteresis;
6. apply an optional creator LOD policy hook;
7. sort the portable submissions by layer, priority, LOD, distance and stable item ID.

The query itself never submits GPU commands.

## Renderer/backend visibility hook

The grid deliberately provides **candidates**, not a claim that every candidate is physically visible. A backend can add stricter camera logic:

```python
plan = index.query(
    camera_region,
    camera_position,
    predicate=lambda item: camera_frustum_intersects(item.bounds),
)
```

That hook is appropriate for frustum, portal, room, occlusion-result or gameplay-specific filtering. Predicate exceptions are contained and surfaced with the stable `predicate-failed` error code rather than leaving partial LOD state committed.

## LOD bands and hysteresis

`lod_thresholds=(30, 70, 140)` creates four logical LOD levels: `0..3`.

Without previous state, distance crossing each threshold selects the next level. With a `VisibilitySession`, `lod_hysteresis` creates a deterministic dead band around each threshold so an object hovering near a boundary does not flip LOD every frame.

The session is bounded by `max_tracked`. A query that would overflow it fails before committing any new LOD states.

## Creator-owned LOD policy

Creators can override the default LOD after SwirEngine computes it:

```python
def hero_policy(item, distance, previous, default_lod):
    if item.item_id == "hero":
        return 0
    return default_lod

plan = index.query(region, camera_position, lod_policy=hero_policy)
```

The hook must return an integer inside the item's valid `0..max_lod` range. Invalid results fail explicitly. This supports gameplay-important actors, platform/backend quality rules, accessibility choices, photo mode and future dynamic quality integration without hard-coding those policies into the spatial index.

## Stable ordering

Visible submissions are sorted by:

1. layer ascending;
2. priority descending;
3. selected LOD ascending;
4. distance ascending;
5. item ID.

This is a deterministic creator/backend hand-off order, not a replacement for the material ordering rules in `render_submission18`. A later Renderer2 compatibility bridge can consume both layers while preserving explicit transparency/UI ordering requirements.

## Diagnostics

Each plan reports:

- indexed item/cell counts;
- query cell count;
- raw bucket references and duplicate bucket hits;
- unique spatial candidate count;
- exact-bounds and predicate culls;
- visible submission count;
- LOD transition count;
- tracked cross-frame LOD state count.

These are CPU-side visibility submission diagnostics. They do not imply physical GPU throughput or an FPS improvement.

## Portable fingerprints

Items, the index's logical registry state, LOD session state and query plans expose deterministic SHA-256 fingerprints. Callbacks and renderer/backend objects are never serialized into those fingerprints.

This gives regression tests and future editor/profiler tooling a stable way to compare visibility decisions across runs.

## Bounded failure behavior

The system has separate limits for:

- registered items;
- globally occupied spatial cells;
- cells occupied by one item;
- cells enumerated by one query;
- unique candidates returned by spatial collection;
- LOD states retained by a session.

Exceeding a limit raises `VisibilityError` with a stable code. No candidate is silently discarded to make a budget fit.

## Workload regression gate

`tools/benchmark_visibility_lod_1_8.py` builds a deterministic **12,000-item** world and performs **120 moving camera-region queries** with LOD hysteresis. It verifies that the spatial candidate workload is substantially smaller than a full-registry scan, checks fingerprints/state bounds, and uses a generous **5.0-second Python 3.13 CI ceiling**.

The ceiling is a regression guard, not a published FPS benchmark.

## Creator demo

Run:

```bash
python examples/demo_visibility_lod_1_8.py
```

The demo registers player/world objects, queries a camera region, prints selected LODs and diagnostics, then demonstrates a stricter creator-owned tree predicate.

## Compatibility

- Stable 1.x root renderer/scene APIs are unchanged.
- The module is opt-in and renderer-independent.
- No GPU backend is selected or synchronized.
- No object is automatically hidden in existing games.
- SwirEngine 1.8 remains source-only; no 1.8 GitHub Release, tag or PyPI publication is created.

The next public release remains SwirEngine 2.0 after its dedicated roadmap and final release gate are fully verified.
