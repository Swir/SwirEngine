# SwirEngine 1.7 Roadmap — Parallel Runtime & Asset Throughput

SwirEngine 1.6 is complete as a verified source-development checkpoint. SwirEngine 1.7 continues the additive 1.x development line toward 2.0 without changing the published 1.5.0 package version or rewriting any released tag.

**Source-checkpoint candidate progress: 10/10 milestones = 100.0%.**

The 10/10 marker is valid for the final candidate only after the exact commit passes the complete source-checkpoint gate and is merged to `main`. Until that gate is green, the last verified `main` percentage remains authoritative.

A milestone is checked only when its implementation, focused tests, documentation, creator example and dedicated validation contract exist on the candidate. Final checkpoint acceptance additionally requires all repository-wide gates on that exact head. Scaffolding or documentation alone never counts as completion.

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

- [x] **2. Async Asset Decode/Cook Pipeline**
  - background-safe file/decode/cook stages on top of the job scheduler;
  - main-thread-only GPU/audio finalization contracts;
  - dependency-aware derived artifact production and cancellation;
  - exact cache/diagnostic accounting without blocking the game loop.

- [x] **3. Shared Resource Budget Broker**
  - explicit memory/count/work budgets shared by streaming-capable subsystems;
  - deterministic priority and eviction/admission contracts;
  - pressure diagnostics and creator-defined reservation classes;
  - stable behavior when one subsystem exhausts its allocation.

- [x] **4. Streaming Work Graph 3.0**
  - staged world/content work expressed as bounded dependency graphs;
  - prefetch, decode, instantiate and unload phases with cancellation;
  - creator-visible progress and fault isolation;
  - no renderer/window mutation from background workers.

- [x] **5. Scene Build & Activation Staging**
  - background-safe immutable scene preparation;
  - bounded main-thread activation slices;
  - transactional rollback when activation fails;
  - compatibility with existing Scene, prefab, ECS and world-streaming APIs.

- [x] **6. Background Save & Serialization I/O**
  - snapshot-first save preparation with explicit ownership boundaries;
  - asynchronous file writing and verification;
  - cancellation-safe atomic promotion;
  - integration with stable Save/Profile 2.0 recovery semantics.

- [x] **7. Shader & Material Preparation Cache**
  - deterministic source fingerprints and derived shader/material preparation;
  - background-safe preprocessing where possible;
  - owning-thread compile/finalization boundary;
  - cache invalidation and diagnostics without changing stable material APIs.

- [x] **8. Frame-time Budget Controller**
  - creator-defined per-frame finalize/work budgets;
  - deterministic bounded draining for async/streaming subsystems;
  - over-budget diagnostics and graceful deferral rather than unbounded stalls;
  - integration hooks for runtime diagnostics/profiling.

- [x] **9. Parallel Runtime Showcase & Soak Gate**
  - source-only showcase integrating all verified 1.7 systems;
  - deterministic aggregate stress workload plus retained cancellation/failure-injection coverage;
  - Windows/Linux source validation without a separate demo release;
  - regression checks proving stable 1.x behavior remains unchanged.

- [x] **10. 1.7 Hardening & Source Checkpoint Gate**
  - full locked 1.3/1.4/1.5 compatibility re-check plus strict 1.6 source-contract regression;
  - full supported-Python matrix, runtime, packaging and clean-install checks;
  - checkpoint auditor that refuses completion below exactly 10/10 or when release/version invariants drift;
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

Milestone 1 was implemented and merged as `3fc63010da56634ee7e5f416a88e7f6c6245b1c7` after the exact candidate passed its dedicated cross-version and repository compatibility gates.

## Milestone 2 verification contract

Milestone 2 is complete only when the exact implementation head satisfies all of the following:

1. `swirengine.assets17` is additive and leaves stable `AssetManager`, `AssetPreloader`, `AssetPipeline`, root imports and published 1.5.0 package metadata unchanged.
2. Asset requests perform bounded scheduler admission while file hashing, dependency discovery, decode and cook work execute through background jobs.
3. GPU/audio/thread-affine finalizers execute only from explicit bounded owning-thread `poll(...)` calls.
4. Request dependencies use verified job dependency gates; failed/cancelled dependencies never execute blocked derived workers.
5. Exact source/dependency fingerprints prevent stale cache reuse and mutation during build is rejected before finalization/cache commit.
6. Cancellation between worker completion and finalization discards the product safely and cooperative worker cancellation remains supported.
7. CPU-side cache entries are scoped deterministically and support explicit invalidation.
8. Worker/finalizer failures are isolated and diagnostics expose counters without asset payloads.
9. Focused regressions, strict Ruff, compile, demo and deterministic workload remain inside the documented CI budget.
10. Python 3.10/3.13/3.14 and repository compatibility workflows pass on the exact candidate; Release/PyPI remain frozen until 2.0.

Milestone 2 candidate `078ca08e65724f9c47160402cf06415e50ed1ece` was merged as `31ffeaefbe7f24f454b784fc2af6b208651d4f74` after the exact-head gate passed.

## Milestone 3 verification contract

Milestone 3 is complete only when the exact candidate satisfies all of the following:

1. `swirengine.resource_budget17` is additive and does not change stable resource/asset/streaming/renderer APIs.
2. Memory, resident-count and abstract work-unit budgets are accounted atomically across subsystems.
3. Reservation floors protect owned capacity while safely permitting unused capacity borrowing.
4. Optional subsystem limits remain independently valid against current/global usage.
5. Eviction/admission ordering is deterministic and protected allocations are never silently evicted.
6. Rejections expose stable structured reasons rather than partial mutations.
7. Planned admissions use revision checks and reject stale plans before mutation.
8. Release/eviction keep global and per-class accounting exact; diagnostics remain payload-free.
9. Focused regressions, strict Ruff, compile, demo and the deterministic pressure workload remain within the CI contract.
10. Python 3.10/3.13/3.14 and repository compatibility gates pass on the exact candidate; Release/PyPI remain frozen until 2.0.

Milestone 3 candidate `ac1293401e5a7a6781fbc5c4bc306ad36d25b17e` was merged as `fed23138faaa0b4713df75127f04fb2f5d599999` after its exact-head gate passed.

## Milestone 4 verification contract

Milestone 4 is complete only when the exact candidate satisfies all of the following:

1. `swirengine.work_graph17` remains additive.
2. Graph construction is bounded and rejects duplicate/missing/self dependencies atomically.
3. Background-safe phases execute through bounded workers; instantiate/unload callbacks execute only on explicit owner-thread polling.
4. Successful dependency values flow read-only and failed/cancelled dependencies block dependents.
5. Ready work uses deterministic priority plus immutable submission ordering.
6. Worker admission and owner-thread drain limits are independently bounded.
7. Failures remain isolated to dependent subgraphs while independent branches continue.
8. Cascade/non-cascade cancellation has deterministic semantics and diagnostics expose no result payloads.
9. Focused regressions, strict Ruff, compile, demo and deterministic graph workload remain inside the CI budget.
10. Python 3.10/3.13/3.14 and repository compatibility gates pass on the exact candidate; Release/PyPI remain frozen until 2.0.

Milestone 4 candidate `2e77f5db7e24d2353a654c4c17d68b75ae2d3b76` was merged as `909d570e5512b330778266ed1cf32489edc5d695` after its exact-head gate passed.

## Milestone 5 verification contract

Milestone 5 is complete only when the exact candidate satisfies all of the following:

1. `swirengine.scene_staging17` is additive and preserves stable Scene/Prefab/ECS/world-streaming behavior.
2. Background preparation never receives a live mutable Scene and returns validated immutable plans.
3. Live scene mutation occurs only from explicit owning-thread polling.
4. Activation order follows immutable submission order even when preparation completes out of order.
5. Worker, pending, retained-request and activation/rollback work each have hard bounds.
6. Activation failure/cancellation rolls successful steps back in reverse order.
7. Stable Scene/Prefab/ECS/chunk adapters remain transactional and clean partial mutations.
8. Preparation/callback failures are isolated and terminal state is explicitly manageable.
9. Focused stable/runtime regressions, strict Ruff, compile, demo and deterministic staging workload stay within the CI contract.
10. Python 3.10/3.13/3.14 and repository compatibility gates pass on the exact candidate; Release/PyPI remain frozen until 2.0.

Milestone 5 candidate `1478368cb5ffcde60ca115f8cedaf0a271f4b14c` was merged as `d64ee3fde14a540eca63c7d024402770a1b1c963` after its exact-head gate passed.

## Milestone 6 verification contract

Milestone 6 is complete only when the exact candidate satisfies all of the following:

1. `swirengine.background_save17` is additive and composes stable Save/Profile 2.0 rather than replacing its public contract.
2. Creator state is snapshotted before background work so worker serialization never races live mutable game state.
3. Serialization/file verification executes off the owner thread while final promotion remains atomic and bounded.
4. Cancellation before promotion leaves the prior trustworthy save untouched and cleans temporary output safely.
5. Written data is verified before promotion and a failed verification cannot replace the prior primary/backup state.
6. Stable backup/recovery semantics remain available after background writes.
7. Queue/worker/result retention are bounded and failures remain isolated per request.
8. Diagnostics expose state/counters without save payload contents.
9. Focused save/profile/job regressions, strict Ruff, compile, creator demo and deterministic workload pass their documented gate.
10. Python 3.10/3.13/3.14 plus repository compatibility workflows pass on the exact candidate.

Milestone 6 candidate `cff0d71ecc13e175f756b49a59d3b6b971cae4db` was merged as `a11a4abceec1eec1a9d8822c85c1f7d0fef02a89` after its exact-head gate passed.

## Milestone 7 verification contract

Milestone 7 is complete only when the exact candidate satisfies all of the following:

1. `swirengine.shader_cache17` is additive and leaves stable material/shader APIs unchanged.
2. Source/material preparation keys use deterministic fingerprints rather than object identity.
3. Background-safe preprocessing is separated from owner-thread compile/finalization.
4. Cache entries have explicit bounded retention/invalidation behavior.
5. Source/configuration changes cannot silently reuse stale prepared output.
6. Finalizer failures do not poison unrelated cache entries or future retries.
7. Thread-affine compilation is never invoked from background workers.
8. Diagnostics expose hit/miss/preparation/finalization state without shader payloads.
9. Focused renderer/material/job regressions, strict Ruff, compile, creator demo and deterministic workload pass their documented gate.
10. Python 3.10/3.13/3.14 plus repository compatibility workflows pass on the exact candidate.

Milestone 7 candidate `b864b987f813b5f9de982ac3feee3441978f58aa` was merged as `a0c40ed04600d44aae5a35d6b8a84f90785e3b98` after its exact-head gate passed.

## Milestone 8 verification contract

Milestone 8 is complete only when the exact candidate satisfies all of the following:

1. `swirengine.frame_budget17` is additive and does not silently alter stable subsystem update behavior.
2. Creators can define positive per-frame time, item and drain-call bounds for owner-thread work.
3. Registered drains execute only on the owning thread.
4. Drain selection is deterministic and prevents permanent starvation under repeated budget pressure.
5. Exhausted time/item/call budgets defer remaining work instead of performing an unbounded drain.
6. A failing drain is isolated and reported without corrupting the controller's remaining schedule.
7. Runtime diagnostics integrate budget/deferral/overrun counters without exposing subsystem payloads.
8. Queue and controller state remain bounded under long-running pressure.
9. Focused parallel-runtime/performance regressions, strict Ruff, compile, creator demo and workload contract pass.
10. Python 3.10/3.13/3.14 plus repository compatibility workflows pass on the exact candidate.

Milestone 8 candidate `36ed81710a01c0eb7e1b09842130b4ea3ccb9af4` was merged as `230243cd71282a8d62b4c5f255be2424a7841410` after Frame Budget 1.7 and the full required compatibility/runtime gates passed.

## Milestone 9 verification contract

Milestone 9 is complete only when the exact candidate satisfies all of the following:

1. `examples/demo_parallel_runtime_showcase_1_7.py` executes all eight verified 1.7 creator examples in one interpreter.
2. The integrated showcase fails clearly if a required verified component is absent.
3. `tools/soak_parallel_runtime_1_7.py` runs all eight deterministic component workloads with explicit per-stage and aggregate timeouts.
4. A failing workload reports the component plus captured stdout/stderr and cannot be silently skipped.
5. The complete focused 1.7 test surface preserves cancellation, rollback, stale-input, back-pressure and failure-isolation coverage.
6. The integration surfaces pass strict Ruff and compile checks.
7. The source showcase runs successfully on Linux and Windows with Python 3.13.
8. The focused parallel-runtime surface passes on Python 3.10, 3.13 and 3.14.
9. Normal CI, Desktop Export, 1.4/1.5 hardening and strict 1.6 source-checkpoint regressions remain green on the exact candidate.
10. No separate showcase release/tag/PyPI path is created.

Milestone 9 candidate `0ffd4c4b561fbbe696977acce1ecb9750c020e9b` was merged as `5b6f97e74e2e359aaeacd61365ee34c8af56c5d0` after all triggered exact-head gates completed successfully.

## Milestone 10 verification contract

Milestone 10 is complete only when the exact final candidate satisfies all of the following:

1. `tools/verify_1_7_source_checkpoint.py --require-complete` refuses any roadmap below exactly 10/10, version drift away from public 1.5.0, missing checkpoint surfaces, incomplete locked roadmaps or a forbidden 1.7 publication path.
2. `tests/test_source_checkpoint_1_7.py` covers milestone parsing, strict repository validation, required-file uniqueness/existence, publication freeze and locked prior-roadmap invariants.
3. The complete focused 1.7 contract suite passes on Python 3.10, 3.13 and 3.14.
4. The exact candidate re-runs the strict 1.6 source checkpoint and locked 1.3/1.4/1.5 compatibility/release auditors.
5. Python 3.13 runs the full repository pytest suite, strict Ruff and compile validation.
6. The aggregate 1.7 soak and integrated source showcase pass again on the final candidate.
7. The integrated source showcase runs on Linux and Windows, and source-only 2D/3D game demos pass the checkpoint's headless probes.
8. Wheel/sdist build, `twine check`, clean virtual-environment wheel installation and installed-version/module probes pass while the public version remains 1.5.0.
9. Repository-wide normal CI, Desktop Export and locked 1.4/1.5 hardening remain green on the exact candidate, including their supported-platform/native-wheel/demo packaging coverage.
10. The checkpoint contains no tag/release/PyPI publication action; once the exact candidate is green and merged, 1.7 is closed as a source checkpoint and development continues toward SwirEngine 2.0.

The final checkpoint candidate is accepted only after the complete `Source Checkpoint 1.7` workflow and repository-wide required gates are green on the same head. Until then the previously verified `main` progress remains authoritative.

Progress is based on milestone completion, not file count or commit count. Each milestone is worth 10 percentage points.
