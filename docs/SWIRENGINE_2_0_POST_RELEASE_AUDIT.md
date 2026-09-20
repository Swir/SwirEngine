# SwirEngine 2.0 — Archived Post-Release Audit Snapshot

This document preserves the verified SwirEngine 2.0 post-release audit evidence accumulated after the public 2.0.0 release. It is no longer an active progress scope. Active development is tracked in [`../ROADMAP_2_1.md`](../ROADMAP_2_1.md); stable 2.0 maintenance is reopened only when a concrete regression, compatibility failure, security/safety issue or release-blocking defect is discovered.

Archived verified snapshot: 5/10 domains = 50.0%.

## Verified release snapshot

- Public version: **2.0.0**
- Git tag: **`v2.0.0`**
- Release publication: **2026-09-19**
- Release-source commit: **`3fe0ff11e09ca0b4a9abcb2b757c12514100bc59`**
- Public installation evidence: the guarded release workflow installed only `swirengine==2.0.0` from public PyPI and ran maintained quick-start/2D/3D smoke checks.
- Release workflow evidence also rebuilt the exact tagged wheel/sdist, verified isolated artifact installs, rebuilt the Windows CPython 3.14 native wheel, re-ran the 2.0 final contract, API floor, platform identity, representative real-game shipping, performance evidence, and release-safety checks before publication.

## Audit domains at archival

- [x] **1. Public release provenance and clean public installation.** The GitHub Release exists as `v2.0.0`; the release workflow rebuilt the exact tagged artifacts, published to PyPI and completed fresh public-PyPI installation plus maintained smoke checks.
- [x] **2. API, migration and backwards-compatibility release floor.** The exact tagged release re-ran the complete 2.0 release contract and the published 1.5 compatibility/migration floor before distribution.
- [x] **3. Supported Python/platform and packaging identity.** Exact-source wheel/sdist metadata, isolated installs, tag/package/runtime version identity, and the Windows CPython 3.14 native wheel path were verified during the public release workflow. Support claims remain limited to the architectures documented in `SUPPORT_MATRIX_2_0.md`.
- [x] **4. Export/build integrity, diagnostics and release-safety publication gate.** The exact release re-ran export/build integrity and release-safety verification before publication. Privacy-safe support-bundle and deterministic build-identity contracts remain part of the maintained gate.
- [x] **5. Runtime stability and resource-lifecycle deep audit.** The post-release lifecycle harness covers bounded asset-streaming/cache pressure, owned worker teardown, successful/failed/cancelled async-asset work and dependency-safe reclamation. `AsyncAssetPipeline.forget()` plus bounded `prune_finalized()` remove finalized pipeline/scheduler bookkeeping without invalidating retained dependency graphs. The exact implementation head `0d1c2b65f305ed8b8619dc56fa56435daa4f897a` passed all 13 required pull-request workflows before PR #167 merged to `main` as `cc28b8803138d7ab5f4a7af88ab343de45c85970`. Evidence is recorded in [`SWIRENGINE_2_0_RUNTIME_LIFECYCLE_AUDIT.md`](SWIRENGINE_2_0_RUNTIME_LIFECYCLE_AUDIT.md).
- [ ] **6. Rendering, assets and world-production deep audit.** Not completed before the standalone audit was archived.
- [ ] **7. Gameplay systems deep audit.** Not completed before the standalone audit was archived.
- [ ] **8. Networking and dedicated-server post-release audit.** Not completed before the standalone audit was archived.
- [ ] **9. Creator/editor/export and complete real-game usability audit.** Not completed before the standalone audit was archived.
- [ ] **10. Documentation, CI, security boundaries and closeout audit.** Not completed before the standalone audit was archived.

## Archival policy

The 5/10 value above is a historical snapshot, not a current application-progress meter and not a claim that SwirEngine 2.0 is partially released. SwirEngine 2.0.0 remains a published stable release. The unfinished historical domains are preserved for evidence and traceability rather than continued percentage tracking; concrete stable-line defects are handled as focused maintenance and regression work.
