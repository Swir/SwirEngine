# SwirEngine 2.0 Roadmap — Release-Quality Python-First Game Production

<img width="100%" src="assets/readme/progress-mini.svg" alt="SwirEngine 2.0 verified roadmap progress" />

**Current verified progress: 0/10 milestones = 0.0%.**

`Release/PyPI: frozen until SwirEngine 2.0`

This roadmap is the authoritative active development scope after the completed source-only 1.9 checkpoint. SwirEngine 2.0 is not release-ready merely because a subsystem exists or a historical 1.x roadmap is complete. Every milestone below requires implementation, integration, regression coverage and exact-head verification before its checkbox may be marked complete.

The public package remains **SwirEngine 1.5.0** until all ten 2.0 milestones are verified and the final release gate succeeds. Source-only 1.6–1.9 checkpoints remain historical engineering evidence and are not retroactively published.

## Release gate principles

- Preserve the stable 1.x compatibility floor unless a deliberate 2.0 migration is documented, tested and justified.
- Prefer creator-facing end-to-end workflows over disconnected subsystem demos.
- Keep representative 2D, 3D and multiplayer games as integration fixtures, not separate releases.
- Require reproducible evidence for performance or competitive comparisons; do not make unsupported superiority claims.
- Validate shipping on each claimed host platform. Unsupported cross-compilation remains explicit rather than implied.
- Keep release readiness separate from roadmap progress. A partial 2.0 roadmap percentage never means beta-ready or release-ready.
- No GitHub Release, release tag or PyPI publication is permitted until Milestone 10 completes its public-install verification.

## Milestones

- [ ] **1. Public API & Migration Contract**
  - Freeze a machine-readable compatibility floor from the published 1.5.0 root API.
  - Document the 1.5.0 → 2.0 migration policy and migration ledger.
  - Add deterministic verification that public root exports cannot silently disappear or drift from the contract.
  - Keep the repository package version frozen at 1.5.0 until the final 2.0 release gate.
  - Require future breaking changes to update the compatibility manifest, migration guide, tests and changelog together.

- [ ] **2. Creator Workflow & Integrated Tooling**
  - Make project creation, validation, run sessions, scene/prefab editing, settings, save data and export coherent from one creator workflow.
  - Remove avoidable manual file surgery from representative projects.
  - Add actionable diagnostics for malformed projects, missing assets and invalid shipping configuration.
  - Prove the workflow through maintained 2D and 3D fixtures.

- [ ] **3. Multiplayer & Dedicated Server Production Contract**
  - Harden replication/session lifecycle, reconnect/failure handling and deterministic compatibility checks.
  - Provide a documented headless/dedicated-server path where technically supported.
  - Separate authoritative server state from player-local settings/save data.
  - Exercise the contract with the multiplayer integration fixture and failure-path tests.

- [ ] **4. Renderer, Runtime Scalability & Resource Lifecycle**
  - Audit scene/render workload scaling, streaming, asset lifetime, memory/resource release and diagnostics.
  - Fix high-impact stalls, leaks or unbounded caches found by reproducible workloads.
  - Validate 2D and 3D runtime paths under representative production-sized workloads.
  - Keep advanced controls available without making the high-level creator API harder to use.

- [ ] **5. Final Python & Platform Support Matrix**
  - Define the exact Python/OS matrix that 2.0 will publicly claim.
  - Run supported combinations through unit, runtime, packaging and platform-specific probes.
  - Document unsupported combinations and architecture constraints precisely.
  - Remove stale support claims from docs and metadata.

- [ ] **6. Representative Real-Game Shipping Gate**
  - Drive polished 2D, 3D and multiplayer fixtures through input/UI, settings, save/profile, scenes, assets, diagnostics and export.
  - Run source and staged/shipped entrypoints, including failure-path checks.
  - Verify game-local and player-local data boundaries.
  - Treat failures in these fixtures as engine integration failures rather than demo-only issues.

- [ ] **7. Packaging, Clean Install & Native Desktop Shipping**
  - Build wheel and sdist from the exact candidate source.
  - Verify clean installation and import/runtime smoke tests from built artifacts.
  - Build and validate host-native Windows, Linux and macOS game packages for claimed targets.
  - Verify artifact inventories, manifests and launch behavior without relying on the development checkout.

- [ ] **8. Performance Evidence & Competitive Quality Audit**
  - Establish deterministic performance workloads with regression thresholds.
  - Publish only technically comparable benchmark evidence with commands, hardware/runtime context and limitations.
  - Compare creator productivity and shipping workflows where objective reproduction is possible.
  - Fix material regressions before release rather than hiding them behind documentation.

- [ ] **9. Export/Build Integrity, Diagnostics & Release Safety**
  - Harden content completeness, build identity, crash/support diagnostics and failure reporting.
  - Verify no required scene/asset/generated content can be silently omitted from a successful build.
  - Audit privacy/safety boundaries for logs and support bundles.
  - Re-run locked historical compatibility/source-checkpoint contracts needed to protect the 2.0 candidate.

- [ ] **10. SwirEngine 2.0 Final Release Gate & Public Verification**
  - Complete compatibility/migration validation, supported CI/runtime matrix and documentation accuracy audit.
  - Pass clean wheel/sdist install, representative real-game workflows, performance regressions and export/build validation on the exact release candidate.
  - Set package/version metadata to 2.0 only at the verified release step and create the public GitHub Release/PyPI publication through the repository workflow.
  - Confirm a fresh public `pip install` from PyPI and execute documented smoke/quick-start validation outside the source checkout.
  - Begin the dedicated post-release audit immediately after publication; roadmap completion alone is not a claim of literal perfection.

## Historical handoff

SwirEngine 1.9 completed its source-only production/shipping checkpoint at 10/10. Its evidence remains in [`ROADMAP_1_9.md`](ROADMAP_1_9.md) and [`docs/SWIRENGINE_2_0_READINESS_AUDIT.md`](docs/SWIRENGINE_2_0_READINESS_AUDIT.md). This 2.0 roadmap supersedes 1.9 only as the **active development measurement**, not as a rewrite of historical evidence.
