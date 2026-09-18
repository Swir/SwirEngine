<!-- SWIR-PROGRESS-SVG-PRO:v1 -->

# SwirEngine 2.0 Roadmap — Release-Quality Python-First Game Production

<img width="100%" src="assets/readme/progress-mini.svg" alt="SwirEngine 2.0 verified roadmap progress: 1 of 10 milestones, 10.0%, in progress" />

**Current verified progress: 1/10 milestones = 10.0%.**

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

- [ ] **2. Creator Workflow & Integrated Tooling**
  - make project creation, validation, run sessions, scene/prefab editing, settings, save data and export coherent;
  - remove avoidable manual file surgery from representative projects;
  - add actionable diagnostics for malformed projects, missing assets and invalid shipping configuration;
  - prove the workflow through maintained 2D and 3D fixtures.

- [ ] **3. Multiplayer & Dedicated Server Production Contract**
  - harden replication/session lifecycle, reconnect/failure handling and deterministic compatibility checks;
  - provide a documented headless/dedicated-server path where technically supported;
  - separate authoritative server state from player-local settings/save data;
  - exercise the contract with the multiplayer fixture and failure-path tests.

- [ ] **4. Renderer, Runtime Scalability & Resource Lifecycle**
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

## Historical handoff

SwirEngine 1.9 completed its source-only production/shipping checkpoint at 10/10. Its archived evidence
remains in [`ROADMAP_1_9.md`](ROADMAP_1_9.md) and
[`docs/SWIRENGINE_2_0_READINESS_AUDIT.md`](docs/SWIRENGINE_2_0_READINESS_AUDIT.md). This 2.0 roadmap
supersedes 1.9 only as the **active development measurement**, not as a rewrite of historical evidence.
