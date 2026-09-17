# SwirEngine 1.7 Roadmap — Parallel Runtime & Asset Throughput

SwirEngine 1.6 is complete as a verified source-development checkpoint. SwirEngine 1.7 continues the additive 1.x development line toward 2.0 without changing the published 1.5.0 package version or rewriting any released tag.

**Current verified progress: 1/10 milestones = 10.0%.**

A milestone is checked only after its implementation, focused tests, documentation, creator example and dedicated validation gate pass on the exact commit merged to `main`. Scaffolding or documentation alone never counts as completion.

## Release policy

- Keep `v1.5.0` and earlier published releases immutable.
- SwirEngine 1.6 and 1.7 are source-development checkpoints only.
- Do not create a `v1.7.0` tag, GitHub Release or PyPI publication.
- Keep new 1.7 systems additive or opt-in so published stable 1.x projects remain compatible.
- The next public GitHub Release and next PyPI publication after 1.5.0 are reserved for **SwirEngine 2.0**.
- When 1.7 reaches verified 10/10, run the full source-checkpoint gate and continue toward the next planned source-development stage without publishing.

## Milestones

- [x] **1. Background Jobs & Main-thread Handoff**
  - bounded worker concurrency and unfinished-job back-pressure;
  - deterministic priority/FIFO dispatch among ready work;
  - explicit dependency gating with failure/cancellation propagation;
  - cooperative cancellation and failure isolation;
  - bounded main-thread completion draining plus payload-free diagnostics;
  - creator documentation, example, workload benchmark and Python 3.10/3.13/3.14 validation.

- [ ] **2. Async Asset Decode/Cook Pipeline**
  - background-safe file/decode/cook stages on top of the job scheduler;
  - main-thread-only GPU/audio finalization contracts;
  - dependency-aware derived artifact production and cancellation;
  - exact cache/diagnostic accounting without blocking the game loop.

- [ ] **3. Shared Resource Budget Broker**
  - explicit memory/count/work budgets shared by streaming-capable subsystems;
  - deterministic priority and eviction/admission contracts;
  - pressure diagnostics and creator-defined reservation classes;
  - stable behavior when one subsystem exhausts its allocation.

- [ ] **4. Streaming Work Graph 3.0**
  - staged world/content work expressed as bounded dependency graphs;
  - prefetch, decode, instantiate and unload phases with cancellation;
  - creator-visible progress and fault isolation;
  - no renderer/window mutation from background workers.

- [ ] **5. Scene Build & Activation Staging**
  - background-safe immutable scene preparation;
  - bounded main-thread activation slices;
  - transactional rollback when activation fails;
  - compatibility with existing Scene, prefab, ECS and world-streaming APIs.

- [ ] **6. Background Save & Serialization I/O**
  - snapshot-first save preparation with explicit ownership boundaries;
  - asynchronous file writing and verification;
  - cancellation-safe atomic promotion;
  - integration with stable Save/Profile 2.0 recovery semantics.

- [ ] **7. Shader & Material Preparation Cache**
  - deterministic source fingerprints and derived shader/material preparation;
  - background-safe preprocessing where possible;
  - owning-thread compile/finalization boundary;
  - cache invalidation and diagnostics without changing stable material APIs.

- [ ] **8. Frame-time Budget Controller**
  - creator-defined per-frame finalize/work budgets;
  - deterministic bounded draining for async/streaming subsystems;
  - over-budget diagnostics and graceful deferral rather than unbounded stalls;
  - integration hooks for runtime diagnostics/profiling.

- [ ] **9. Parallel Runtime Showcase & Soak Gate**
  - source-only showcase integrating the verified 1.7 systems;
  - deterministic headless stress workload and cancellation/failure injection;
  - Windows/Linux source validation without a separate demo release;
  - regression checks proving stable 1.x behavior remains unchanged.

- [ ] **10. 1.7 Hardening & Source Checkpoint Gate**
  - full locked 1.3/1.4/1.5 compatibility re-check plus 1.6 source-contract regressions;
  - full supported-Python matrix, runtime, packaging and clean-install checks;
  - checkpoint auditor that refuses completion below exactly 10/10;
  - after the exact checkpoint is green, continue toward 2.0 with Release/PyPI still frozen.

## Milestone 1 verification contract

Milestone 1 is complete only when the exact implementation head satisfies all of the following:

1. `swirengine.jobs17` is additive and does not change stable root imports, `Game`, renderer or published package metadata.
2. `JobScheduler` enforces positive worker/pending bounds and rejects duplicate ids, malformed dependencies and submissions after shutdown with stable error codes.
3. Ready work is dispatched by higher integer priority first, then immutable submission sequence, while running work never exceeds `max_workers`.
4. The unfinished-job budget produces atomic back-pressure: rejected work does not consume an id/sequence or partially enter dependency graphs.
5. Dependencies must already exist, execute only after every dependency succeeds, and propagate failed/cancelled/blocked states transitively without executing blocked work.
6. Queued/waiting cancellation is immediate and running cancellation is cooperative through `JobContext`; cancelled results discard worker return values.
7. Worker exceptions are isolated as failed outcomes and do not stop unrelated queued work or the scheduler.
8. `drain_completed(max_items=...)` provides an explicit bounded handoff surface for main-thread-owned engine changes; diagnostics expose only counts/budgets and never job result payloads.
9. Focused tests, strict Ruff, compile checks, creator demo and a 2,000-job workload remain within the documented generous 5.0-second CI budget without making an FPS claim.
10. The dedicated Python 3.10/3.13/3.14 workflow passes on the final milestone head before merge to `main`; Release/PyPI remain frozen until SwirEngine 2.0.

Milestone 1 was implemented and merged as `3fc63010da56634ee7e5f416a88e7f6c6245b1c7` after the exact candidate head passed Background Jobs 1.7 on Python 3.10/3.13/3.14 plus normal CI, Desktop Export, game-demo, 1.4/1.5 hardening and the 1.6 source-checkpoint regressions. The Python 3.13 gate completed 15 focused tests in 0.70 seconds and the 2,000-job workload in 0.2994 seconds against the 5.0-second budget.

## Milestone 2 verification contract

Milestone 2 is complete only when the exact implementation head satisfies all of the following:

1. `swirengine.assets17` is additive and leaves stable `AssetManager`, `AssetPreloader`, `AssetPipeline`, root imports and published 1.5.0 package metadata unchanged.
2. `AsyncAssetPipeline.submit()` performs only request validation/path resolution plus bounded scheduler admission; file hashing, dependency discovery, decode and cook work execute through `JobScheduler` workers.
3. GPU/audio/thread-affine finalizers execute only from explicit `poll(max_items=...)` calls, and each poll has a positive hard item budget so owning-thread handoff cannot become an unbounded per-frame drain.
4. Request dependencies use existing scheduler dependency gates and expose only successful CPU-side worker products to dependent builds; failed/cancelled scheduler dependencies never execute blocked derived workers.
5. File-dependency resolvers run on workers, exact SHA-256 source/dependency fingerprints guard CPU-product cache reuse, and any input mutation during decode/cook returns `STALE` without finalization or cache commit.
6. Worker-to-finalizer cancellation discards an already-computed product, skips finalization and does not populate the cache; cooperative worker cancellation remains available through `AssetBuildContext.raise_if_cancelled()`.
7. Cache entries contain CPU-side cooked products rather than owning-thread finalizer outputs, remain scoped by processor + canonical source path, and support explicit scoped/full invalidation.
8. Worker and finalizer exceptions remain isolated as request failures; diagnostics provide exact submitted/completed/failed/cancelled/stale/cache/finalizer counters without exposing asset payloads.
9. Focused tests, strict Ruff, compile checks, creator demo, stable asset/job regressions and a 512-asset cold + cached workload (1,024 requests) remain within the documented generous 5.0-second Python 3.13 CI budget without making an FPS claim.
10. The dedicated Python 3.10/3.13/3.14 Async Assets 1.7 workflow and repository compatibility workflows pass on the exact final milestone head before merge; Release/PyPI remain frozen until SwirEngine 2.0.

Progress is based on milestone completion, not file count or commit count. Each milestone is worth 10 percentage points.
