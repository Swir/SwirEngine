# SwirEngine 2.0 Runtime Scalability & Resource Lifecycle

This document records the production contract being validated for SwirEngine 2.0 Milestone 4. It does not declare the milestone complete by itself; the exact implementation head and the later roadmap-marked closeout head must pass the required CI matrix.

## Goals

Milestone 4 treats asset residency and transient renderer resources as owned runtime lifecycles rather than unbounded caches. The contract also locks representative 2D and 3D scale invariants that can be reproduced deterministically without turning shared-runner wall-clock timings into marketing claims.

### Asset streaming

`AssetStreamingManager` now exposes explicit lifecycle and pressure diagnostics:

- deterministic LRU residency remains bounded by byte and asset-count budgets when unpinned resources are available;
- pinned resources are never silently evicted, but unresolved pressure is visible through `over_budget` and `budget_pressure_events`;
- peak resident asset count is tracked alongside peak resident bytes;
- cancelled background operations are separated from loader failures;
- exceptional custom/shared preloader futures become normal failed streaming results instead of escaping `pump()` and leaving sticky pending records;
- `release_all()` provides an explicit project/session teardown path while preserving pins unless the caller requests `force=True`;
- `shutdown(release_resident=True)` can close a session and invalidate all resources owned by its residency set;
- a closed manager rejects new staging or mutation work rather than accidentally reusing a shut-down worker pool.

For stable 1.x compatibility, ordinary `shutdown()` still preserves resident `AssetManager` cache entries unless explicit release is requested. An externally supplied `AssetPreloader` remains externally owned: shutdown never closes that shared pool. When explicit residency release is requested, the manager waits only for futures it already scheduled, invalidates their cache entries after completion, and then returns while the shared preloader remains usable by its owner and other consumers.

### Transient renderer resources

SwirEngine already has the bounded `TransientRenderResourcePool` from the 1.8 rendering work. Milestone 4 locks its production behavior together with streaming instead of adding a competing resource abstraction:

- exact-descriptor resources are reused rather than re-created every frame;
- resource and byte ceilings stay explicit;
- stale handles and capacity failures remain diagnosed;
- `close()` destroys owned backend resources and returns residency to zero.

### Representative 2D scale

The deterministic workload exercises two existing production paths rather than creating a synthetic renderer benchmark:

- a **128 × 128 tilemap (16,384 cells)** must keep viewport visibility work local instead of walking the whole world; the verifier rejects candidate counts above 500 or one-sixteenth of the map;
- a stable **4,096-sprite batch** is staged repeatedly after preallocation and must not trigger CPU staging-buffer reallocations.

These are algorithmic/work-allocation contracts. They do not claim a specific FPS because CI runner speed is not stable evidence for end-user hardware performance.

### Representative 3D scale

The 3D workload inserts **4,096 sparse scene objects** into the existing `SceneVisibilityIndex3D` BVH and queries a small frustum. The contract requires:

- the full inventory to remain represented correctly;
- exactly the local visible object for the fixed fixture;
- fewer than 128 leaf/object candidates for the query;
- more than 96% object-test reduction relative to walking the whole source set.

This locks scene-query scalability while keeping the existing lower-level visibility/index APIs available to advanced users.

### Existing budget broker

The 1.7 `ResourceBudgetBroker` remains the lower-level admission/eviction coordinator for subsystems that need shared memory/count/work-unit limits. Milestone 4 keeps this lower-level control available while strengthening the creator-facing streaming lifecycle.

## Deterministic verification

Run the focused contract:

```bash
python -m pytest -q \
  tests/test_asset_streaming.py \
  tests/test_runtime_scalability_2_0.py \
  tests/test_render_resources_1_8.py \
  tests/test_render_resources_hardening_1_8.py \
  tests/test_resource_budget_1_7.py \
  tests/test_renderer2d_power.py \
  tests/test_scene_visibility_1_4.py \
  tests/test_scene_acceleration_1_4.py
python tools/verify_runtime_scalability_2_0.py
```

The deterministic verifier repeatedly cycles a bounded asset set through streaming residency, performs 5,000 transient render-resource acquire/release operations, validates a 16,384-cell 2D tilemap plus a 4,096-sprite staging workload, and queries a 4,096-object sparse 3D BVH. It validates bounded counts, balanced teardown, reuse and pruning invariants. It intentionally does **not** turn wall-clock timing from a shared CI runner into an FPS or performance marketing claim.

The dedicated `Runtime Scalability 2.0` workflow runs the contract on Python 3.10, 3.13 and 3.14. Full repository compatibility workflows remain required before the roadmap checkbox can move from 3/10 to 4/10.

## Failure semantics

Pinned assets can legitimately make residency exceed its configured budget. This is a creator decision, not a reason to evict pinned content behind the application's back. The manager therefore records pressure and stays over-budget until content is unpinned or explicitly released.

Unexpected worker exceptions and cancellations are drained from the pending queue and surfaced in diagnostics. Shutdown is idempotent. Explicit teardown is deterministic and does not require garbage collection to recover asset or transient render residency.

## Compatibility and release policy

This source work is additive hardening on the road to SwirEngine 2.0. Published 1.4.0 and 1.5.0 release history is unchanged. No intermediate 1.6–1.9 release, tag or PyPI package is created.

`Release/PyPI: frozen until SwirEngine 2.0`
