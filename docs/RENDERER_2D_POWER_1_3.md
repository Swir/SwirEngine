# 2D Renderer Power Pass — SwirEngine 1.3

SwirEngine 1.3 milestone 7 focuses on reducing CPU work that scaled with the full 2D world even when only a small camera viewport was visible.

## What changes

### Tilemaps become aggregate render/update roots

`Game.tilemap(...)` still creates the same fixed `Sprite2D` child pool and still registers those children in the scene for compatibility with existing 1.x code. The children remain available through `tilemap.children`.

The 1.3 scene fast path now recognizes those sprites as parent-managed. They no longer enter the scene-wide update snapshot or render-root sort individually. The tilemap itself owns their transform synchronization and renderer submission.

This preserves the public object model while removing the dominant per-frame cost of walking thousands of no-op child sprites.

### Dirty transform synchronization

A tilemap stores its last `(x, y, layer, enabled, visible)` state. If that state does not change, `TileMap2D.update()` performs zero child transform visits.

When the aggregate transform/state changes, one full pool synchronization occurs and the new state becomes the baseline for subsequent frames.

### Viewport-local tile submission

The renderer converts the camera viewport directly into clamped tile-cell bounds. Only cells overlapping those bounds are visited for submission. The number of visibility candidates therefore depends on viewport size, tile size and camera zoom rather than total map dimensions.

For example, a 640×360 viewport over 16×16 tiles considers roughly 40×23 cells even when the authored map contains tens of thousands of cells.

### Conservative object culling

World-space `Rectangle2D` objects and `Sprite2D` objects with explicit width/height use a conservative radius derived from their rectangle diagonal. Objects fully outside the camera viewport are rejected before draw preparation. Screen-space objects are never camera-culled by this path.

Sprites without explicit dimensions are retained because their final dimensions depend on the loaded texture.

### Reusable sprite staging

The production 2D path owns a geometrically grown NumPy float32 staging buffer for batched sprite vertices. Stable-size workloads reuse the same buffer across frames instead of building a new Python float list plus a new NumPy array for each sprite batch.

GPU uploads use the array's buffer protocol through `memoryview`, avoiding the previous explicit `tobytes()` allocation in this power path.

## Diagnostics

`RendererStats` adds:

- `render_roots_2d`
- `objects_culled_2d`
- `tilemap_cells_considered`
- `tilemap_cells_visible`

`TileMap2D.diagnostics` exposes:

- `transform_syncs`
- `transform_sprite_visits`
- `visibility_queries`
- `last_visibility_candidates`
- `last_visible_sprites`

These counters are intended for creator tooling and regression tests rather than synthetic FPS claims.

## Measurable regression contracts

The milestone locks several concrete properties:

- a tilemap with 64 child sprites remains 65 registered scene objects including its root, while one scene update executes only the tilemap root update;
- 120 unchanged tilemap updates perform exactly zero child transform visits;
- changing one aggregate transform performs exactly one full-pool synchronization, and the following unchanged update performs none;
- a 128×128 fully populated map viewed through a 320×180 viewport over 16×16 cells considers no more than 240 local cells rather than all 16,384 cells;
- sprite CPU staging retains object identity until capacity must grow, then grows geometrically and remains stable again.

`tools/benchmark_renderer2d_power.py` runs a larger repeated CPU/locality workload and reports timing only as a diagnostic. It does not translate host-specific timings into an FPS claim.

## Production validation

`tools/verify_renderer2d_power_opengl.py` generates a temporary atlas, builds a 96×96 tilemap through the normal `Game.tilemap(...)` API, moves the camera for five frames and renders through the production OpenGL/post-process renderer under Xvfb/software Mesa in CI.

This specifically validates the aggregate tilemap expansion, batched sprite staging, buffer-protocol VBO upload and production renderer delegation rather than a fake backend.

## Compatibility boundary

This milestone intentionally keeps the fixed child pool and scene registration semantics of `Game.tilemap(...)`. It improves per-frame CPU/render work, not tilemap construction memory. Direct mutation of pooled tile child transforms is not treated as an independent rendering contract: the tilemap owns child transform/layer/visibility synchronization, as it already did through `TileMap2D.update()`.

The power pass is additive to existing post-processing, UI, text, sprites and 3D rendering. It does not change stable 1.x package versioning or trigger an intermediate 1.3 release.
