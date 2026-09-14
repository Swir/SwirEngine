# Renderer / VFX performance pass — SwirEngine 1.2

SwirEngine 1.2 reduces steady-state Python work in the 2D renderer and particle/VFX hot paths without changing the public gameplay API or claiming an unmeasured FPS uplift.

## 2D render-run streaming

`graphics.batching.build_render_runs()` remains a sequence-compatible render-run view: existing code can iterate it, call `len()` and index it. When the input is repeatable (the renderer's normal sorted scene list), iteration now streams directly through `iter_render_runs()` instead of first building a second frame-sized outer list/tuple.

Only the currently pending compatible sprite group is retained. One-shot iterators are materialized once so sequence operations remain deterministic.

## Cached sprite state keys

Sprite batching previously allocated a new immutable `SpriteBatchKey` for every visible sprite every frame. The normalized texture/layer/screen-space combination is now held in a bounded 8192-entry cache. Stable sprites therefore reuse the same state-key object across frames, while the existing 4096-entry canonical texture-path cache continues to keep filesystem normalization out of steady-state work.

This does not reorder transparent sprites: only adjacent compatible sprites are merged, preserving visible draw order.

## Allocation-free clamped-color fast path

`Color` is immutable. When all four channels are already in the legal `[0, 1]` range, `Color.clamped()` now returns the same object rather than constructing an equivalent `Color`. Out-of-range values still produce a correctly clamped new color.

This benefits sprite tint, rectangle/text color and several 3D/VFX code paths that validate colors every frame.

## Particle emission hot path

Particle range sampling no longer calls `sorted()` for each sampled lifetime/speed/angle/size/rotation value. Two-value ranges are ordered with scalar comparisons, preserving reversed-range behavior without allocating a temporary list for every sample.

The existing sparse active-particle update remains intact: inactive pool slots are not visited every frame.

## Regression gates

`tests/test_renderer_vfx_performance.py` guards the optimization contracts:

- a 512-sprite repeatable scene can be fully iterated without materializing an outer render-run cache;
- one-shot generators retain deterministic sequence behavior;
- 1000 repeated sprite state-key lookups produce one cache miss and 1000 hits and reuse object identity;
- 1000 in-range `Color.clamped()` calls reuse the original immutable object;
- reversed particle ranges remain deterministic and behavior-compatible.

For local measurements, run:

```bash
python tools/benchmark_renderer_vfx_framework.py
```

The benchmark reports streamed versus materialized render-run peak Python memory/time, state-key and color identity reuse, and particle emission time. Timing numbers are diagnostic rather than a fixed CI threshold because they depend on host hardware; deterministic behavior/allocation contracts are enforced by tests instead.

## Compatibility

No rendering primitive, particle constructor or game-facing 1.x method was removed. Batch order and sprite blending semantics remain unchanged. The optimization is deliberately CPU-side and does not claim a specific FPS increase without a representative GPU/runtime benchmark on the target machine.
