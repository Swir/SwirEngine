# SwirEngine 1.8 Roadmap — Render Graph & GPU Delivery

SwirEngine 1.7 is a completed source-only checkpoint. SwirEngine 1.8 continues the path toward 2.0
with additive rendering scalability systems while preserving stable 1.x behavior.

**Current verified progress: 10/10 milestones = 100.0%.**

A milestone is checked only after implementation, focused tests, documentation, its dedicated gate,
and the repository's required compatibility/regression gates pass on the exact implementation head.
The final roadmap-marked PR head must pass the required gates again before merge to `main`.

## Release policy

- Keep published `v1.4.0` and `v1.5.0` history immutable.
- SwirEngine 1.8 is source-only: **do not create `v1.8.0`, a GitHub Release, or a PyPI publish**.
- Keep all 1.8 systems additive or opt-in where they could change stable 1.x behavior.
- After this roadmap reaches verified 10/10 and its source checkpoint gate is green, continue the
  next source-only development stage toward 2.0.
- The next public GitHub Release and PyPI publication remains SwirEngine 2.0 only.

## Milestones

- [x] **1. Render Graph 3.0 Planner**
  - bounded renderer-independent pass/resource authoring model;
  - implicit/explicit dependencies with deterministic topological scheduling;
  - output/side-effect rooted culling and strict graph validation;
  - transient lifetime analysis, deterministic alias slots and memory diagnostics;
  - portable snapshots/fingerprints, creator docs/demo, focused benchmark and Python 3.10/3.13/3.14 gate.

- [x] **2. Transient GPU Resource Pool & Attachment Reuse**
  - backend-facing pool contract consuming verified render-graph lifetimes;
  - bounded texture/buffer attachment reuse with generation-safe handles;
  - deterministic acquire/release/trim diagnostics and failure containment;
  - stable renderer behavior retained when the pool is not enabled.

- [x] **3. Batched Upload, Staging & Texture Residency**
  - bounded upload queues and staging budgets;
  - deterministic texture residency/eviction priorities;
  - duplicate upload suppression and explicit back-pressure;
  - renderer-safe diagnostics and workload regression coverage.

- [x] **4. Material Submission & Pipeline State Cache**
  - stable material/draw submission keys;
  - deterministic state sorting without changing visual order where ordering is required;
  - bounded pipeline/program state cache with invalidation diagnostics;
  - measurable draw/state-change workload contracts.

- [x] **5. Visibility & LOD Submission 3.0**
  - deterministic visibility submission contracts for 2D/3D scenes;
  - bounded spatial candidate filtering and creator-owned LOD policy hooks;
  - stable ordering, hysteresis and portable diagnostics;
  - no mandatory behavior change for existing scenes.

- [x] **6. GPU Timing & Frame Capture Integration**
  - backend timing-provider abstraction with safe unavailable/failure modes;
  - render-pass timing integration with existing performance diagnostics;
  - bounded capture/export metadata and creator-readable hotspots;
  - no forced GPU synchronization in default runtime paths.

- [x] **7. Dynamic Resolution & Quality Budget Controller**
  - opt-in deterministic quality budget policy;
  - bounded resolution/quality steps with hysteresis and recovery rules;
  - integration with frame pacing/diagnostics without changing simulation truth;
  - creator override and reproducible workload validation.

- [x] **8. Renderer2 Integration & Compatibility Bridge**
  - opt-in graph-backed submission path for existing renderer capabilities;
  - compatibility bridge preserving stable root/public renderer behavior;
  - integration tests covering textures, text, batching, instancing and common 2D/3D paths;
  - explicit fallback when a backend capability is unavailable.

- [x] **9. Render Showcase, Soak & Failure Injection**
  - source-only 2D/3D render showcase using verified 1.8 systems;
  - deterministic long-run workload and resource churn gate;
  - allocation/upload/backend failure injection with bounded recovery;
  - Linux OpenGL and Windows source/showcase coverage without a separate demo release.

- [x] **10. 1.8 Source Checkpoint & Roadmap Closeout**
  - full supported CI matrix plus locked 1.4/1.5/1.6/1.7 contracts;
  - package build/install and source showcase validation;
  - source-checkpoint auditor refusing completion below 10/10;
  - documentation/changelog closeout with no tag, GitHub Release or PyPI publication.

## Milestone 1 verification contract

Milestone 1 is complete only when the exact implementation candidate satisfies all of the following:

1. `swirengine.render_graph18` is additive and leaves stable 1.x root renderer imports unchanged.
2. Pass/resource registries enforce deterministic hard bounds and stable validation errors.
3. Data dependencies and explicit dependencies produce a deterministic topological order in which
   creator priority can break ties but can never violate dependency order.
4. Missing dependencies, dependency cycles, multiple writers, internal reads without writers,
   uninitialized internal outputs and in-place read/write ambiguity fail before a plan is accepted.
5. Marked outputs and side-effect roots retain their complete upstream dependency closure and cull
   unrelated work; rootless authoring retains all passes.
6. Resource lifetimes are calculated only from active passes and same-pass lifetimes never alias.
7. Transient alias assignment is deterministic and reports unaliased, reserved, savings and
   peak-live byte diagnostics without claiming physical GPU allocation.
8. Portable plans have deterministic SHA-256 fingerprints and contain no callbacks/backend objects.
9. A 1,200-pass deterministic planner workload remains below the documented 5.0-second CI budget
   without making an FPS claim.
10. Focused tests, Ruff, compile, creator demo and the dedicated Python 3.10/3.13/3.14 workflow pass,
    followed by the repository's required compatibility/regression workflows on the implementation head.

Verified implementation head `e99a413e054bdfdbebcddc0a42223be65ed7780b` passed the dedicated
Python 3.10/3.13/3.14 Render Graph gate, the full repository CI, Desktop Export, game-demo validation,
locked 1.4/1.5 hardening, and 1.6/1.7 source-checkpoint regressions. The Python 3.13 focused gate ran
21 tests successfully and compiled the 1,200-pass workload in 0.0135 seconds under the documented
5.0-second regression ceiling. The roadmap-marked PR head re-passed its triggered gates before merge.

## Milestone 2 verification contract

Milestone 2 is complete only when the exact implementation candidate satisfies all of the following:

1. `swirengine.render_resources18` is additive and leaves stable 1.x root renderer/resource APIs
   unchanged; opting out keeps existing renderer behavior identical.
2. Backend object creation/destruction stays behind explicit creator/backend callbacks, and the pool
   never claims ownership of external/persistent graph resources or silently executes GPU work.
3. Immutable descriptors conservatively key compatible kind/format/dimensions/layers/samples/usage
   and byte-size properties so incompatible textures/buffers are never reused as one another.
4. Resident object count and declared byte residency have independent hard bounds; pressure may
   reclaim only idle allocations and fails explicitly when all reclaimable capacity is leased.
5. Resource leases use monotonically increasing generations, so a stale handle cannot release or
   resolve a slot after that physical allocation has been leased again.
6. `RenderPlanResourceSchedule` consumes only active transient lifetimes from a verified
   `RenderGraphPlan`, requires explicit descriptors, and creates deterministic acquire/release events.
7. `RenderPlanPoolSession` enforces strict pass order, keeps same-pass/overlapping lifetimes live, and
   rolls back every acquisition made for a pass if a later backend allocation in that pass fails.
8. Deterministic reuse/eviction/trim/close accounting remains coherent after creator/backend failures,
   and portable diagnostics contain counters/limits only rather than backend resource payloads.
9. A 100-frame × 512-pass workload (51,200 logical acquisitions) stabilizes at two compatible
   physical allocations and remains under the documented generous 5.0-second Python 3.13 CI budget
   without making an FPS or GPU-throughput claim.
10. Focused pool/render-graph/stable-renderer regressions, Ruff, compile, creator demo and the dedicated
    Python 3.10/3.13/3.14 workflow pass, followed by the repository's required compatibility/regression
    workflows on the exact final milestone head.

Verified implementation head `7b0bd23cd70c8858836ab908bbde782169e7bfe4` passed the dedicated
Python 3.10/3.13/3.14 transient-resource workflow, the full repository CI, Desktop Export, game-demo
validation, locked 1.4/1.5 hardening, and 1.6/1.7 source-checkpoint regressions. The roadmap-marked PR
head must re-pass its triggered gates before merge. Release/PyPI remain frozen until SwirEngine 2.0.

## Milestone 3 verification contract

Milestone 3 is complete only when the exact implementation candidate satisfies all of the following:

1. `swirengine.render_uploads18` is additive, renderer-independent and leaves stable 1.x texture and
   renderer APIs unchanged unless creators explicitly instantiate the new queue.
2. Enqueued bytes-like payloads are snapshotted immutably, full and rectangular layer-region uploads
   validate their resource/geometry contracts, and the backend remains responsible for format-specific
   payload interpretation rather than the queue guessing texel layout.
3. Pending request count, pending payload bytes, per-flush request count and per-flush byte work each
   have independent hard bounds; a single request that cannot fit the flush contract fails explicitly
   instead of starving FIFO work forever.
4. Backend submission is deterministic FIFO; work outside the current flush budget remains queued and
   observable instead of being silently dropped or reordered.
5. SHA-256 duplicate suppression becomes authoritative only after a successful backend submission;
   failed uploads remain retryable, full writes invalidate prior region assumptions and partial writes
   invalidate full/overlapping-region assumptions.
6. Successful uploads establish deterministic logical residency with independent texture-count and
   byte budgets, creator priority/pinning/use controls, and eviction ordering by lowest priority,
   oldest use and stable texture-id tie breaking.
7. Pinned or otherwise unreclaimable pressure fails with a stable error while preserving queued work;
   backend upload/eviction failures are contained without corrupting residency, digest or submitted
   accounting.
8. Portable diagnostics expose staging, duplicate, residency, eviction, deferral, pressure and failure
   counters without callbacks/backend payloads, and deterministic state fingerprints omit raw upload
   bytes while retaining content identity through digests.
9. A 7,680-operation / 64-texture deterministic workload remains below the documented generous
   5.0-second Python 3.13 CI budget without making an FPS or physical GPU-throughput claim.
10. Focused upload/resource-pool/render-graph/stable-renderer regressions, Ruff, compile, creator demo
    and the dedicated Python 3.10/3.13/3.14 workflow pass, followed by the repository's required
    compatibility/regression workflows on the exact final milestone head.

Verified implementation head `c78a58beebea6601dfd5964487856beeaab4f549` passed the dedicated
Python 3.10/3.13/3.14 texture-upload gate, full repository CI, Desktop Export, game-demo validation,
locked 1.4/1.5 hardening, Render Graph and Transient Render Resources 1.8 gates, and 1.6/1.7
source-checkpoint regressions. The Python 3.13 gate's earlier implementation run executed 65
focused/regression tests successfully and completed the 7,680-operation workload in 0.0743 seconds,
with 3,840 backend submissions and 3,840 verified duplicate skips. This roadmap-marked PR head must
re-pass its triggered gates before merge. Release/PyPI remain frozen until SwirEngine 2.0.

## Milestone 4 verification contract

Milestone 4 is complete only when the exact implementation candidate satisfies all of the following:

1. `swirengine.render_submission18` is additive and renderer-independent and leaves stable 1.x root
   renderer/material APIs unchanged unless creators or backends explicitly instantiate the new systems.
2. `PipelineStateKey` is immutable, normalized and deterministically fingerprints shader, vertex
   layout, blend/depth/cull state, primitive topology, render-target signature, sample count and sorted
   compile-time variants so incompatible pipeline states cannot share one cache entry.
3. `MaterialKey` provides deterministic static material/resource identity while deliberately excluding
   fast-changing runtime uniform values that would create a new material identity every frame.
4. `MaterialSubmissionQueue` has a hard draw bound and sorts only contiguous reorderable runs; an
   explicit `preserve_order=True` draw is a hard barrier that remains at its authored position and
   prevents work from crossing it in either direction.
5. Compiled ordering is deterministic and portable diagnostics accurately report authored/compiled
   draw counts, sortable segments, pipeline/material switches and state-switch savings.
6. `PipelineStateCache` has a hard resident-entry bound and deterministic LRU selection, while backend
   object creation/destruction stays behind explicit callbacks and the cache never submits GPU commands.
7. Backend create, eviction, invalidation, clear and close failures are contained with stable error
   codes; failed resident states remain observable/retryable and an untracked candidate is destroyed
   during eviction rollback before failure is returned.
8. Shader-specific invalidation and cache/plan fingerprints are deterministic and portable while
   excluding backend pipeline payloads/callbacks from serialized logical state.
9. A 20-frame × 4,096-draw workload (81,920 draws) remains below the documented generous 5.0-second
   Python 3.13 CI budget while validating substantial switch reduction and exact cache accounting,
   without making an FPS or physical GPU-throughput claim.
10. Focused submission/cache/hardening and stable-renderer regressions, Ruff, compile, creator demo and
    the dedicated Python 3.10/3.13/3.14 workflow pass, followed by the full required repository
    compatibility/regression workflows on the exact implementation head.

Verified implementation head `568abc01e05dc1c33650774434304899acc3b775` passed the dedicated
Python 3.10/3.13/3.14 Material Pipeline Cache gate, full repository CI, Desktop Export, game-demo
validation, locked 1.4/1.5 hardening, and 1.6/1.7 source-checkpoint regressions. The Python 3.13 gate
ran 79 focused/regression tests successfully and completed the 81,920-draw workload in 1.2949 seconds,
saving 71,397 pipeline switches with 81,888 cache hits and 32 pipeline creations. The implementation
head also passed clean-wheel/source-demo validation and Windows one-file 2D/3D runtime probes through
the locked 1.5 hardening gate. This roadmap-marked PR head must re-pass its triggered gates before
merge. Release/PyPI remain frozen until SwirEngine 2.0.

## Milestone 5 verification contract

Milestone 5 is complete only when the exact implementation candidate satisfies all of the following:

1. `swirengine.visibility18` is additive and renderer-independent, leaves stable 1.x renderer/scene
   behavior untouched by default, and models 2D and 3D candidates with finite validated `AABB3` bounds.
2. `VisibilityIndex` enforces independent hard limits for indexed items, global cells, cells per item,
   query cells and unique candidates; register/replace capacity failures leave the previous index state
   intact and return stable creator-facing error codes.
3. Candidate collection uses deterministic uniform-grid buckets, suppresses duplicate bucket hits,
   refines conservatively collected candidates with exact AABB overlap and emits stable ordered results.
4. Optional tag filtering and creator/backend visibility predicates support stricter frustum, portal,
   room, occlusion-result or gameplay culling without coupling the core index to a GPU backend; callback
   failures and invalid callback results fail explicitly before LOD state is committed.
5. Creator-authored distance LOD bands are deterministic, `VisibilitySession` provides bounded
   cross-frame hysteresis, and transitions may cross multiple bands without oscillating at thresholds.
6. Optional creator-owned LOD policy callbacks receive the item, distance, previous LOD and default LOD;
   invalid ranges/results and callback failures are contained with stable errors and no partial commit.
7. Item replacement/removal, tag ordering, candidate deduplication and bounded-session reuse are covered
   by hardening regressions so spatial bookkeeping and creator-facing state remain coherent under churn.
8. Item/index/session/query fingerprints and portable diagnostics remain deterministic and exclude
   creator callbacks/backend payloads while retaining enough logical state to reproduce planning results.
9. A deterministic workload indexing 12,000 items and executing 120 moving camera queries stays below
   the documented generous 5.0-second Python 3.13 CI ceiling while exercising candidate reduction and
   LOD transitions; it is explicitly a CPU-side workload contract, not an FPS/GPU-throughput claim.
10. Focused visibility/render regressions, Ruff, compile, creator demo and the dedicated Python
    3.10/3.13/3.14 workflow pass, followed by the repository-wide compatibility/regression workflows on
    the exact implementation head.

Verified implementation head `19679c7f25a3574caab72502ff593ef93fb5aa3c` passed the dedicated
Python 3.10/3.13/3.14 Visibility LOD gate plus the full required pull-request compatibility/regression
suite. The Python 3.13 gate ran 99 focused/render regressions in 1.05 seconds; the 12,000-item / 120-query
workload processed 69,120 unique candidates, produced 60,750 visible submissions, tracked 5,925 LOD
states, observed 7,198 transitions and completed in 0.8542 seconds under the documented 5.0-second
ceiling. This roadmap-marked PR head must now re-pass its triggered gates before merge. Release/PyPI
remain frozen until SwirEngine 2.0.

## Milestone 6 verification contract

Milestone 6 is complete only when the exact implementation candidate satisfies all of the following:

1. `swirengine.render_timing18` is additive and renderer-independent and leaves stable 1.x renderer
   behavior unchanged unless a creator/backend explicitly opts into GPU timing capture.
2. `GpuTimingProvider` owns opaque backend timestamp-query objects behind `begin`, `end` and non-blocking
   `poll` calls; recorder state never serializes provider tokens or requires a specific graphics API.
3. The recorder has no wait/finish/synchronization path: unresolved query results remain pending and
   `poll_ready()` processes only an explicit bounded amount of work per call.
4. History frames, pending frames, passes per frame, pending queries and poll work are independently
   hard-bounded; reaching capacity returns stable creator-facing errors instead of allocating forever.
5. Render Graph integration verifies active pass membership and execution order, stores the plan
   fingerprint in captures and refuses invalid/misordered timing scopes before corrupting frame state.
6. Provider unavailability, invalid results and backend begin/end/poll failures are contained in safe
   unavailable/failed samples by default, with explicit strict-provider behavior for backend development.
7. Resolved timings integrate explicitly with `PerformanceDiagnostics2` as `gpu.<pass>` timings plus
   bounded counters, without coupling normal CPU frame diagnostics to GPU query polling.
8. Portable frame/capture data, metadata, hotspot aggregation, deterministic fingerprints and atomic
   JSON export exclude backend objects/callbacks and preserve creator-readable pass-level evidence.
9. A deterministic 500-frame × 128-pass workload (64,000 timestamp queries) remains below the documented
   generous 5.0-second Python 3.13 CI ceiling without making an FPS or hardware-GPU-throughput claim.
10. Focused timing/hardening/render regressions, Ruff, compile, creator demo and the dedicated Python
    3.10/3.13/3.14 workflow pass, followed by the repository-wide compatibility/regression workflows on
    the exact implementation head.

Verified implementation head `0338d9f5b69ff17d3156a2c87638879004459222` passed the dedicated
Python 3.10/3.13/3.14 GPU Timing Capture gate plus CI, Desktop Export, game-demo validation, locked
1.4/1.5 hardening and 1.6/1.7 source-checkpoint regressions. The Python 3.13 gate ran 113 focused/render
regressions in 0.75 seconds and completed the 64,000-query workload in 0.2587 seconds with 500 retained
frames and zero pending queries. This roadmap-marked PR head must re-pass its triggered gates before
merge. Release/PyPI remain frozen until SwirEngine 2.0.

## Milestone 7 verification contract

Milestone 7 is complete only when the exact implementation candidate satisfies all of the following:

1. `swirengine.render_quality18` is additive and renderer-independent; stable 1.x renderer behavior is
   unchanged unless a creator explicitly instantiates and wires the dynamic-quality controller.
2. Creator-authored quality steps have hard count/name/value bounds and must be monotonically ordered so
   degradation cannot silently increase resolution or generic quality scale.
3. Timing input is finite and atomic, with deterministic selection of CPU frame time, resolved GPU frame
   time, or their maximum; missing GPU timing falls back safely without changing simulation timing.
4. Rolling timing evidence, asymmetric degrade/recover thresholds, streak requirements and transition
   cooldown provide deterministic hysteresis and prevent one-frame spikes from causing quality thrash.
5. Adaptation moves at most one authored quality step per transition, respects authored upper/lower
   bounds and preserves fixed-step, physics, gameplay and other simulation truth.
6. Creator manual baseline changes and persistent overrides are explicit, bounded and observable; an
   override pins the requested tier until cleared without being misreported as adaptive degradation.
7. `PerformanceDiagnostics2` integration exposes numeric quality state and consumes the explicit
   `gpu.frame_ms` counter from GPU Timing Capture 1.8 without forcing GPU synchronization.
8. Portable diagnostics/state and deterministic SHA-256 fingerprints contain logical evidence only and
   exclude renderer/backend objects; invalid samples fail before mutating controller state.
9. A deterministic 200,000-frame workload remains below the documented generous 5.0-second Python 3.13
   CI ceiling while exercising thousands of transitions, without making an FPS/GPU-throughput claim.
10. Focused quality/timing/render regressions, Ruff, compile, creator demo and the dedicated Python
    3.10/3.13/3.14 workflow pass, followed by CI, Desktop Export, game-demo validation, locked 1.4/1.5
    hardening and 1.6/1.7 source-checkpoint regressions on the exact implementation head.

Verified implementation head `d44a8d0d6e9a7dd2f96340cc1b4326d41617e0fc` passed the dedicated
Python 3.10/3.13/3.14 Dynamic Quality gate plus the full required repository compatibility/regression
suite: CI, Desktop Export, Demo Game 3D, Game Demos, Neon Snake 3D, locked 1.4/1.5 hardening and the
1.6/1.7 source checkpoints. The Python 3.13 dedicated gate ran 81 focused/regression tests in 1.06
seconds, Ruff and compile checks passed, and the 200,000-frame workload completed in 0.7995 seconds
with 3,335 deterministic transitions and final authored tier `low`. This roadmap-marked PR head must
re-pass its triggered gates before merge. Release/PyPI remain frozen until SwirEngine 2.0.

## Milestone 8 verification contract

Milestone 8 is complete only when the exact implementation candidate satisfies all of the following:

1. `swirengine.renderer2_bridge18` is additive and opt-in and does not replace, monkey-patch or change
   stable 1.x root/public renderer behavior when the bridge is not explicitly constructed.
2. Stable 2D scene submission reuses the existing layer ordering and sprite-run batching contract while
   representing rectangles, text and sprite batches in a bounded deterministic graph-backed frame plan.
3. 3D preparation reuses the existing backend-independent `Renderer2Planner` pass schedule without
   requiring a GPU context, and common Renderer2 pass ordering remains covered by compatibility tests.
4. Active `InstancedMesh3D` batches and visible instances are accounted for explicitly, while a backend
   is never reported as native graph-capable unless it actually exposes the `render_graph18` hook.
5. The active Dynamic Quality 1.8 tier is carried as portable frame metadata without mutating legacy
   framebuffer dimensions, fixed-step timing, physics or other simulation truth.
6. Native graph execution, graph-validated legacy compatibility execution and explicit fallback are
   distinct observable paths; compatibility execution invokes the historical renderer exactly once.
7. Preparation/capability failures are contained before backend submission and creators can require
   strict behavior by disabling preparation fallback or compatibility execution.
8. Graph/run counts are hard-bounded and portable SHA-256 frame fingerprints retain hashed submission
   identity while excluding raw texture paths, text payloads and backend objects from portable output.
9. A deterministic 500-frame × 128-run workload (64,000 logical runs) remains below the documented
   generous 5.0-second Python 3.13 CI ceiling without making an FPS or GPU-throughput claim.
10. Focused bridge/Renderer2/batching/text/instancing/render regressions, Ruff, compile and creator demo
    pass on Python 3.10/3.13/3.14, followed by the full required repository compatibility/regression
    suite on the exact implementation head.

Verified implementation head `68ac179cff1f43681203a9819e7bb012194ed54e` passed the dedicated
Python 3.10/3.13/3.14 Renderer2 Bridge gate plus CI, Desktop Export, Demo Game 3D, Game Demos,
Neon Snake 3D, locked 1.4/1.5 hardening and the 1.6/1.7 source checkpoints. The Python 3.13 dedicated
gate ran 128 focused/render regressions in 0.99 seconds, Ruff and compile checks passed, and the
64,000-logical-run workload completed in 1.1937 seconds. A transient locked-1.5 save/profile workload
run exceeded its historical ceiling on a shared runner; the failed job was re-run rather than bypassed
and then passed. This roadmap-marked PR head must re-pass its triggered gates before merge. Release/PyPI
remain frozen until SwirEngine 2.0.

## Milestone 9 verification contract

Milestone 9 is complete only when the exact implementation candidate satisfies all of the following:

1. `swirengine.render_showcase18` is source-only validation infrastructure layered over the opt-in 1.8
   rendering stack and does not alter stable 1.x runtime behavior or create a separately released demo.
2. The soak runner has explicit frame, failure-history and consecutive-failure bounds and performs no
   recursive retry loop or unbounded failure accumulation.
3. Transient resource churn uses generation-safe pool leases and always attempts to release every
   successfully acquired lease, including partial-allocation failure paths.
4. Repeated texture staging uses the verified bounded upload queue and reports real duplicate suppression,
   submission, residency and failure diagnostics rather than synthetic GPU-throughput claims.
5. Allocation, upload and render/backend failures are contained at frame boundaries, recovery is
   observable on later clean frames and exceeding the configured consecutive-failure budget fails hard.
6. The 2D and 3D source showcases exercise real Renderer2 bridge planning paths and retain deterministic
   portable workload fingerprints without serializing backend objects or raw content payloads.
7. Failure injection covers allocation, upload and backend-render errors with regressions for cleanup,
   bounded history, deterministic recovery and stable creator-facing error codes.
8. The dedicated gate covers Python 3.10/3.13/3.14 source validation, Windows/Python 3.13 showcase
   execution and a real Linux Mesa OpenGL 3.3 Renderer2 smoke path.
9. A deterministic Python 3.13 long soak processes 2,400 total 2D/3D frames under the documented generous
   15-second CI ceiling while exercising resource reuse and duplicate upload suppression, without making
   an FPS or physical GPU-throughput claim.
10. Focused showcase/bridge/resource/upload/render regressions, Ruff, compile and creator showcase pass,
    followed by the full required repository compatibility/regression workflows on the exact head.

Verified implementation head `8f28a04c3e72e4ad0f7da4fa6c884b69ee114783` passed the dedicated
Render Showcase 1.8 workflow plus CI, Desktop Export, Demo Game 3D, Game Demos, Neon Snake 3D,
locked 1.4/1.5 hardening and 1.6/1.7 source checkpoints. The Python 3.13 dedicated gate ran 100
focused/integration tests in 1.08 seconds; Ruff and compile checks passed, and the deterministic soak
processed 2,400 total 2D/3D frames in 0.5934 seconds. Windows source-showcase coverage and the Linux
Mesa OpenGL 3.3 smoke path also passed. This roadmap-marked PR head must re-pass its triggered gates
before merge. Release/PyPI remain frozen until SwirEngine 2.0.

## Milestone 10 verification contract

Milestone 10 is complete only when the exact source-checkpoint candidate satisfies all of the following:

1. `tools/verify_1_8_source_checkpoint.py --require-complete` refuses every roadmap state below exactly
   10/10 = 100.0% and validates that declared progress matches the authoritative milestone checkboxes.
2. Public package metadata remains frozen at `1.5.0`, the 2.0-only release policy remains explicit and
   no dedicated 1.8 release, tag or PyPI publication workflow is introduced.
3. Every verified 1.8 rendering subsystem, dedicated workflow and closeout artifact is present, while
   the completed 1.4/1.5/1.6/1.7 compatibility and source-checkpoint contracts remain locked in place.
4. The dedicated source-checkpoint matrix passes on Python 3.10, 3.13 and 3.14 and re-runs the strict
   completed 1.7 checkpoint audit before accepting the 1.8 closeout candidate.
5. Focused 1.8 regressions plus the full Python 3.13 repository suite, Ruff and compile validation pass
   without weakening historical correctness or performance gates.
6. Wheel and sdist builds succeed, `twine check` validates distribution metadata and no intermediate
   publication occurs as part of packaging validation.
7. A clean wheel install retains public version `1.5.0`, imports every 1.8 subsystem from the installed
   artifact and executes the source-only 1.8 showcase plus headless 2D and 3D game workflows.
8. Linux and Windows source-showcase validation passes, while the existing desktop-export, real OpenGL,
   Windows one-file game probes and representative creator-facing runtime gates remain green.
9. Deterministic render-soak evidence remains part of the integrated checkpoint and transient shared-runner
   timing noise must be re-run and verified rather than bypassed or hidden by relaxing historical gates.
10. After the roadmap is marked 10/10, the exact roadmap-marked head must re-run the strict 1.8 auditor
    and all required repository compatibility/regression gates before merge to `main`.

Verified pre-roadmap checkpoint head `b9acf38e940bab7536753a096b1b732a0a95a173` passed the dedicated
Python 3.10/3.13/3.14 Source Checkpoint 1.8 gate, CI, Desktop Export, locked 1.4/1.5 hardening and the
1.6/1.7 source checkpoints. Python 3.13 ran 179 focused 1.8 tests in 1.47 seconds and 1,368 full
repository tests in 6.77 seconds; Ruff and compile validation passed. Wheel/sdist build, `twine check`,
clean-wheel installation, complete 1.8 imports, installed-artifact showcase/game probes, Ubuntu/Windows
source-showcase coverage and Windows one-file 2D/3D runtime probes passed. A shared-runner locked-1.5
save/profile workload initially exceeded its historical ceiling at 12.470769 seconds; the failed job was
re-run without changing the gate and passed. This 10/10 roadmap-marked head must now re-pass the strict
checkpoint and required gates before merge. No 1.8 release/tag/PyPI publication is permitted.

Release/PyPI remain frozen until SwirEngine 2.0.
