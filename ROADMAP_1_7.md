# SwirEngine 1.7 Roadmap — Parallel Runtime & Asset Throughput

SwirEngine 1.6 is complete as a verified source-development checkpoint. SwirEngine 1.7 continues the additive 1.x development line toward 2.0 without changing the published 1.5.0 package version or rewriting any released tag.

**Current verified progress: 0/10 milestones = 0.0%.**

A milestone is checked only after its implementation, focused tests, documentation, creator example and dedicated validation gate pass on the exact commit merged to `main`. Scaffolding or documentation alone never counts as completion.

## Release policy

- Keep `v1.5.0` and earlier published releases immutable.
- SwirEngine 1.6 and 1.7 are source-development checkpoints only.
- Do not create a `v1.7.0` tag, GitHub Release or PyPI publication.
- Keep new 1.7 systems additive or opt-in so published stable 1.x projects remain compatible.
- The next public GitHub Release and next PyPI publication after 1.5.0 are reserved for **SwirEngine 2.0**.
- When 1.7 reaches verified 10/10, run the full source-checkpoint gate and continue toward the next planned source-development stage without publishing.

## Milestones

- [ ] **1. Background Jobs & Main-thread Handoff**
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

Progress is based on milestone completion, not file count or commit count. Each milestone is worth 10 percentage points.
