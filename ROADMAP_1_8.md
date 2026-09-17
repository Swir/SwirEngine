# SwirEngine 1.8 Roadmap — Render Graph & GPU Delivery

SwirEngine 1.7 is a completed source-only checkpoint. SwirEngine 1.8 continues the path toward 2.0
with additive rendering scalability systems while preserving stable 1.x behavior.

**Current verified progress: 1/10 milestones = 10.0%.**

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

- [ ] **2. Transient GPU Resource Pool & Attachment Reuse**
  - backend-facing pool contract consuming verified render-graph lifetimes;
  - bounded texture/buffer attachment reuse with generation-safe handles;
  - deterministic acquire/release/trim diagnostics and failure containment;
  - stable renderer behavior retained when the pool is not enabled.

- [ ] **3. Batched Upload, Staging & Texture Residency**
  - bounded upload queues and staging budgets;
  - deterministic texture residency/eviction priorities;
  - duplicate upload suppression and explicit back-pressure;
  - renderer-safe diagnostics and workload regression coverage.

- [ ] **4. Material Submission & Pipeline State Cache**
  - stable material/draw submission keys;
  - deterministic state sorting without changing visual order where ordering is required;
  - bounded pipeline/program state cache with invalidation diagnostics;
  - measurable draw/state-change workload contracts.

- [ ] **5. Visibility & LOD Submission 3.0**
  - deterministic visibility submission contracts for 2D/3D scenes;
  - bounded spatial candidate filtering and creator-owned LOD policy hooks;
  - stable ordering, hysteresis and portable diagnostics;
  - no mandatory behavior change for existing scenes.

- [ ] **6. GPU Timing & Frame Capture Integration**
  - backend timing-provider abstraction with safe unavailable/failure modes;
  - render-pass timing integration with existing performance diagnostics;
  - bounded capture/export metadata and creator-readable hotspots;
  - no forced GPU synchronization in default runtime paths.

- [ ] **7. Dynamic Resolution & Quality Budget Controller**
  - opt-in deterministic quality budget policy;
  - bounded resolution/quality steps with hysteresis and recovery rules;
  - integration with frame pacing/diagnostics without changing simulation truth;
  - creator override and reproducible workload validation.

- [ ] **8. Renderer2 Integration & Compatibility Bridge**
  - opt-in graph-backed submission path for existing renderer capabilities;
  - compatibility bridge preserving stable root/public renderer behavior;
  - integration tests covering textures, text, batching, instancing and common 2D/3D paths;
  - explicit fallback when a backend capability is unavailable.

- [ ] **9. Render Showcase, Soak & Failure Injection**
  - source-only 2D/3D render showcase using verified 1.8 systems;
  - deterministic long-run workload and resource churn gate;
  - allocation/upload/backend failure injection with bounded recovery;
  - Linux OpenGL and Windows source/showcase coverage without a separate demo release.

- [ ] **10. 1.8 Source Checkpoint & Roadmap Closeout**
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
5.0-second regression ceiling. The roadmap-marked PR head is still required to re-pass its triggered
gates before merge.
