<!-- SWIR-PROGRESS-SVG-PRO:v1 -->

# SwirEngine 2.0 Roadmap — Release-Quality Python-First Game Production

<img width="100%" src="assets/readme/progress-mini.svg" alt="SwirEngine 2.0 verified roadmap progress: 4 of 10 milestones, 40.0%, in progress" />

**Current verified progress: 4/10 milestones = 40.0%.**

`Release/PyPI: frozen until SwirEngine 2.0`

This roadmap is the authoritative active development scope after the completed source-only 1.9 checkpoint.
SwirEngine 2.0 is not release-ready merely because a subsystem exists or a historical 1.x roadmap is
complete. Every milestone below requires implementation, integration, regression coverage and exact-head
verification before its checkbox may be marked complete.

The public package remains **SwirEngine 1.5.0** until all ten 2.0 milestones are verified and the final
release gate succeeds. Source-only 1.6–1.9 checkpoints remain historical engineering evidence and are not
retroactively published.

## Release gate principles

- Preserve the stable 1.x compatibility floor unless a deliberate 2.0 migration is documented, tested and justified.
- Prefer creator-facing end-to-end workflows over disconnected subsystem demos.
- Keep representative 2D, 3D and multiplayer games as integration fixtures, not separate releases.
- Require reproducible evidence for performance or competitive comparisons; do not make unsupported superiority claims.
- Validate shipping on each claimed host platform. Unsupported cross-compilation remains explicit rather than implied.
- Keep release readiness separate from roadmap progress. A partial 2.0 percentage never means beta-ready or release-ready.
- No GitHub Release, release tag or PyPI publication is permitted until Milestone 10 completes public-install verification.

## Milestones

- [x] **1. Public API & Migration Contract**
  - freeze a machine-verifiable compatibility floor from the actual published `v1.5.0` root API;
  - document the 1.5.0 → 2.0 migration policy and migration ledger;
  - prove every published 1.5.0 root export remains present while allowing additive 2.0 exports;
  - keep package/module version metadata frozen at 1.5.0 until the final 2.0 release gate;
  - require future breaking changes to update migration evidence, tests and release notes together.

- [x] **2. Creator Workflow & Integrated Tooling**
  - make project creation, validation, run sessions, scene/prefab editing, settings, save data and export coherent;
  - remove avoidable manual file surgery from representative projects;
  - add actionable diagnostics for malformed projects, missing assets and invalid shipping configuration;
  - prove the workflow through maintained 2D and 3D fixtures.

- [x] **3. Multiplayer & Dedicated Server Production Contract**
  - harden replication/session lifecycle, reconnect/failure handling and deterministic compatibility checks;
  - provide a documented headless/dedicated-server path where technically supported;
  - separate authoritative server state from player-local settings/save data;
  - exercise the contract with the multiplayer fixture and failure-path tests.

- [x] **4. Renderer, Runtime Scalability & Resource Lifecycle**
  - audit scene/render workload scaling, streaming, asset lifetime, memory/resource release and diagnostics;
  - fix high-impact stalls, leaks or unbounded caches found by reproducible workloads;
  - validate 2D and 3D runtime paths under representative production-sized workloads;
  - preserve lower-level control without making the high-level creator API harder to use.

- [ ] **5. Final Python & Platform Support Matrix**
  - define the exact Python/OS matrix that 2.0 will publicly claim;
  - run supported combinations through unit, runtime, packaging and platform-specific probes;
  - document unsupported combinations and architecture constraints precisely;
  - remove stale support claims from docs and metadata.

- [ ] **6. Representative Real-Game Shipping Gate**
  - drive polished 2D, 3D and multiplayer fixtures through input/UI, settings, save/profile, scenes, assets, diagnostics and export;
  - run source and staged/shipped entrypoints, including failure-path checks;
  - verify game-local and player-local data boundaries;
  - treat fixture failures as engine integration failures rather than demo-only issues.

- [ ] **7. Packaging, Clean Install & Native Desktop Shipping**
  - build wheel and sdist from the exact candidate source;
  - verify clean installation and import/runtime smoke tests from built artifacts;
  - build and validate host-native Windows, Linux and macOS game packages for claimed targets;
  - verify artifact inventories, manifests and launch behavior without relying on the development checkout.

- [ ] **8. Performance Evidence & Competitive Quality Audit**
  - establish deterministic performance workloads with regression thresholds;
  - publish only technically comparable benchmark evidence with commands, hardware/runtime context and limitations;
  - compare creator productivity and shipping workflows where objective reproduction is possible;
  - fix material regressions before release rather than hiding them behind documentation.

- [ ] **9. Export/Build Integrity, Diagnostics & Release Safety**
  - harden content completeness, build identity, crash/support diagnostics and failure reporting;
  - verify required scene/asset/generated content cannot be silently omitted from a successful build;
  - audit privacy/safety boundaries for logs and support bundles;
  - re-run locked historical compatibility/source-checkpoint contracts needed to protect the candidate.

- [ ] **10. SwirEngine 2.0 Final Release Gate & Public Verification**
  - complete compatibility/migration validation, supported CI/runtime matrix and documentation accuracy audit;
  - pass clean wheel/sdist install, representative real-game workflows, performance regressions and export/build validation;
  - set package/version metadata to 2.0 only at the verified release step and publish through the repository workflow;
  - confirm a fresh public `pip install` from PyPI and execute documented smoke/quick-start validation outside the checkout;
  - begin the dedicated post-release audit immediately after publication.

## Milestone 1 verification contract

Milestone 1 may be checked only after the exact final implementation head proves all of the following:

1. `docs/public_api_2_0.json` is anchored to the actual published `v1.5.0` tag and root-module blob.
2. The tagged `swirengine.__all__` count and deterministic digest match the committed baseline evidence.
3. Every tagged 1.5.0 root export remains present in the current source; additive 2.0 exports remain allowed.
4. `pyproject.toml` and `swirengine.__version__` stay at 1.5.0 until the Milestone 10 release step.
5. `docs/MIGRATING_TO_2_0.md` is the explicit migration ledger and does not invent unsupported breakage.
6. `docs/API_STABILITY.md` points to the same compatibility contract and distinguishes import compatibility from behavior stability.
7. The verifier operates without importing optional engine/runtime dependencies.
8. The contract runs on Python 3.10, 3.13 and 3.14 from a full Git checkout containing the published tag.
9. Progress assets are regenerated from this active roadmap and legacy ASCII/Unicode progress meters stay blocked.
10. Focused tests, Ruff, compile and the repository compatibility/regression workflows pass on the exact final head.

## Milestone 1 verified evidence

Implementation head `967f3d3e08ee67e0bf5701ca3a685a4d251dfa1b` passed the complete triggered matrix before this
closeout was marked. The dedicated Public API 2.0 workflow passed Python 3.10, 3.13 and 3.14 with the
published `v1.5.0` tag available from a full checkout. The contract verified the tagged root-module blob,
271 published root exports, their deterministic digest, preserved current imports, frozen 1.5.0 package
metadata, the migration ledger, API stability policy, generated SVG checks, Ruff and bytecode compilation.

Repository-wide CI, locked 1.4/1.5 hardening, source checkpoints 1.6–1.9, desktop export/shipping and the
representative real-game production gates also passed on that implementation head. The first hosted-runner
attempt of the unchanged 1.5 save/profile workload exceeded its 5.0 s budget during runner contention;
a retry passed without changing production code, the benchmark or its threshold. Milestone 1 is therefore
verified at **1/10 = 10.0%**. Release readiness remains a separate final gate.

## Milestone 2 verification contract

Milestone 2 is complete only when the exact implementation head proves all of the following:

1. New 2D and 3D projects expose one coherent creator layout and editable shipping defaults without manual setup.
2. `swirengine workflow` validates the manifest, deterministic run plan, scene packages, content graph, shipping defaults, creator directories and save/profile policy through one creator-facing command.
3. `--prepare` is additive and idempotent: it creates only missing creator directories/defaults and never overwrites existing project configuration.
4. Human diagnostics include actionable next steps for malformed projects, missing entrypoints/assets and invalid scene/content declarations.
5. `--json` returns deterministic machine-readable workflow evidence suitable for CI and higher-level tooling.
6. Equivalent checkouts produce the same workflow fingerprint; absolute checkout and player-data paths are not encoded into portable evidence.
7. Inspection does not execute the game, export a package or create player save/profile data.
8. Maintained 2D and 3D real-game fixtures pass the integrated workflow with scene packages, content graphs and editable defaults present.
9. The dedicated workflow passes on Python 3.10, 3.13 and 3.14 with focused tests, Ruff and bytecode compilation.
10. Full repository CI, historical compatibility/source checkpoints, desktop export and representative demo/runtime gates remain green.

## Milestone 2 verified evidence

Implementation head `79a1a8302a96cb82f49b2b5f368618397b2f5724` passed every triggered workflow before this closeout
was marked. The dedicated Creator Workflow 2.0 gate passed on Python 3.10, 3.13 and 3.14, including focused
creator tests, maintained 2D/3D fixture verification, strict Ruff and bytecode compilation. The exact head
also passed full repository CI, where Python 3.13 completed **1532 tests with 4 skipped**, plus locked
1.4/1.5 hardening, source checkpoints 1.6–1.9, project-production regression checks, game demos, Neon Snake
3D, desktop export and the clean-wheel/native runtime checks exercised by the locked 1.5/1.9 gates.

The integrated workflow is additive over existing project/run/editor/scene/content/settings/save/export
contracts and the public package/module version remains 1.5.0. Milestone 2 is therefore verified at
**2/10 = 20.0%**. Release readiness remains separate; this closeout head must re-pass its triggered matrix
before merge.

## Milestone 3 verification contract

Milestone 3 is complete only when the exact implementation head proves all of the following:

1. Client and server compatibility fingerprints cover project, protocol, build, replication schema and content identity.
2. Compatibility mismatches are rejected before join/resume mutates authoritative session state.
3. Disconnect/resume rotates the single-use resume token and forces a full replication resynchronization when authoritative history exists.
4. Authoritative gameplay state explicitly rejects settings, display, accessibility, controls/input bindings, profile and save data.
5. Authoritative player-state payloads are bounded, portable and returned as defensive snapshots so caller mutation cannot rewrite stored authoritative state.
6. The dedicated-server adapter runs through the existing fixed-tick headless runtime and validates startup before execution.
7. Dedicated-server snapshots preserve the authoritative server tick and fail deterministically on mismatch.
8. The maintained multiplayer real-game fixture exercises join, authoritative/local state separation, match start, disconnect/resume and full resynchronization without public sockets.
9. The dedicated workflow passes on Python 3.10, 3.13 and 3.14 with focused multiplayer/session/replication/server tests, snapshot-isolation regressions, Ruff and bytecode compilation.
10. Full repository CI, locked 1.4/1.5 hardening, source checkpoints 1.6–1.9, desktop export and representative game/runtime gates remain green.

## Milestone 3 verified evidence

Hardened implementation head `419368d6aa910b211a1f71ebdc458ed4b3882d2d` passed every triggered workflow before this closeout
was marked. The dedicated Multiplayer Production 2.0 gate passed on Python 3.10, 3.13 and 3.14, including
focused multiplayer production tests, the existing replication/prediction/session/dedicated-server regression
suites, the representative multiplayer fixture, defensive snapshot-isolation regressions, strict Ruff and
bytecode compilation. The same exact head also passed full repository CI, locked 1.4/1.5 hardening, source
checkpoints 1.6–1.9, Game Demos, Demo Game 3D, Neon Snake 3D, Desktop Export and Real-Game Production 1.9.

The new production layer is additive over the established session, replication, networking and headless-server
APIs; the public package/module version remains 1.5.0 and the fixture opens no public sockets. Milestone 3 is
therefore verified at **3/10 = 30.0%**. Release readiness remains separate; this closeout head must re-pass
its triggered matrix before merge.

## Milestone 4 verification contract

Milestone 4 is complete only when the exact implementation head proves all of the following:

1. Asset streaming residency remains explicitly bounded by byte and asset-count budgets when unpinned eviction is possible.
2. Pinned over-budget pressure is surfaced in diagnostics instead of silently evicting protected resources.
3. Streaming teardown drains or detaches owned pending work deterministically and can release all session-owned residency without worker repopulation races.
4. Externally supplied preloaders remain externally owned and usable after a streaming session shuts down.
5. External cache invalidation reconciles stale residency and re-enters background loading without synchronous decode/file work on the caller thread.
6. Null-like cached values and creator size-estimator failures participate in deterministic invalidation/accounting instead of leaving hidden residency divergence.
7. Transient render resources reuse exact descriptors under explicit bounds and return owned residency to zero on close.
8. Representative 2D workloads retain viewport-local tile visibility and stable 4,096-sprite CPU staging without reallocations.
9. A 4,096-object sparse 3D scene workload retains BVH pruning with fewer than 128 object tests and more than 96% object-test reduction.
10. The dedicated Python 3.10/3.13/3.14 workflow plus full repository compatibility, checkpoint, demo and export gates pass on the exact implementation head.

## Milestone 4 verified evidence

Hardened implementation head `7c690970d614d26af07458eecaf9c425ad65e1ab` passed every triggered workflow before this closeout
was marked. The dedicated Runtime Scalability 2.0 workflow passed on Python 3.10, 3.13 and 3.14, including
focused asset-streaming, resource-pool, renderer, visibility and acceleration regressions, deterministic
production-sized workload verification, strict Ruff and bytecode compilation. The same exact head also
passed full repository CI, Asset Pipeline 2.0/1.4, Large World 1.3, locked 1.4/1.5 hardening, source
checkpoints 1.6–1.9, Game Demos, Demo Game 3D, Neon Snake 3D, Content Build 1.9 and Desktop Export.

The runtime hardening remains additive over stable 1.x behavior: ordinary shutdown preserves cache residency
unless explicit release is requested, shared preloaders stay externally owned, and no benchmark is converted
into an unsupported FPS claim. Milestone 4 is therefore verified at **4/10 = 40.0%**. Release readiness
remains separate; this closeout head must re-pass its triggered matrix before merge.

## Historical handoff

SwirEngine 1.9 completed its source-only production/shipping checkpoint at 10/10. Its archived evidence
remains in [`ROADMAP_1_9.md`](ROADMAP_1_9.md) and
[`docs/SWIRENGINE_2_0_READINESS_AUDIT.md`](docs/SWIRENGINE_2_0_READINESS_AUDIT.md). This 2.0 roadmap
supersedes 1.9 only as the **active development measurement**, not as a rewrite of historical evidence.
