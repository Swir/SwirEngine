<!-- SWIR-PROGRESS-SVG-PRO:v1 -->

# SwirEngine 2.1 — SwirEditor & Creator Workflow Roadmap

<img width="100%" src="assets/readme/progress-mini.svg" alt="SwirEngine 2.1 SwirEditor roadmap progress" />

SwirEngine 2.1 develops the creator-facing desktop workflow after the public SwirEngine 2.0.0 release. Historical 2.0 release and audit evidence remain preserved, but active progress now tracks 2.1 only unless a concrete stable-line regression requires maintenance.

Current verified progress: 5/10 milestones = 50.0%.

## Milestones

- [x] **1. Project-backed SwirEditor session and desktop launcher.** Open a manifest-driven project, load/save a portable editor scene, persist `.swir/editor.json`, browse project assets, expose diagnostics/profiling models, provide a real desktop launcher and verify headless CI behavior. Verified on implementation head `be5d17ff64f2ae74bb8d96812b4dc2512f52defb` after the cross-platform CI, packaging, Ruff and compatibility checks passed.
- [x] **2. Project Hub and unified CLI entry.** Add New/Open/Recent project flows, creator templates and the `swirengine editor` command while preserving the standalone editor entry point for desktop packaging. Verified on implementation head `be5d17ff64f2ae74bb8d96812b4dc2512f52defb` with hub/CLI regression coverage included in the green CI matrix.
- [x] **3. Scene authoring workflow.** Create/open/save multiple scenes, add/remove/duplicate/reparent objects and entities, scene tabs, unsaved-change protection and deterministic recovery. Verified on implementation head `be5d17ff64f2ae74bb8d96812b4dc2512f52defb` with dedicated scene-authoring and recovery tests included in the green CI matrix.
- [x] **4. Inspector, components and prefabs.** Creator-friendly typed editors, multi-selection, component add/remove, prefab create/instantiate/apply/revert and safe asset-property assignment. Verified on exact implementation head `f580a432ac3c463027d721ebde3fec46d47d6f86`: all 13 required pull-request workflows passed, including the full repository suite (`1655 passed, 4 skipped` on the Python 3.13 compatibility job), strict Ruff, compilation, packaging, compatibility checkpoints, desktop export, demos and the 2.0 final release gate. The accepted implementation was squash-merged to `main` as `edcd9e25c961c41804a8c083d58fff73625fe0f8`.
- [x] **5. Production 2D/3D viewport.** Picking, camera navigation, transform gizmos, snapping, overlays, grid controls and reliable live viewport rendering in both engine modes. Interaction tooling landed through PR #178; the live renderer/framebuffer integration then passed all 14 required exact-head workflows on `5577281f98efab64688bbdf4566f1d6bff90e5e4`, including real Linux Mesa/Xvfb and macOS live-render probes plus the Windows CPython 3.14 packaged-runtime probe, before PR #179 squash-merged to `main` as `e5bec2bb4b91ca910880dc94feb36bb58edd8560`.
- [ ] **6. Asset import and content pipeline UX.** Import/reimport, drag/drop, previews, dependency visibility, background processing and actionable validation without duplicating runtime asset logic.
- [ ] **7. Play/debug/profiling loop.** Integrated Play/Pause/Stop/Step, isolated edit/runtime state, console navigation, profiler views, diagnostics and failure-safe recovery.
- [ ] **8. Gameplay tooling.** Input/rebinding, settings, animation, physics/collision, navigation/AI, audio, UI/HUD and save/profile editors built on the high-level runtime APIs.
- [ ] **9. Build/export wizard.** Profile-aware staging, host-native build/export, icon/metadata configuration, diagnostics, artifact inspection and truthful platform gating.
- [ ] **10. Real-game editor gate and 2.1 release readiness.** Drive maintained 2D, 3D and multiplayer fixtures from project creation through authoring, run, diagnostics and shipping; complete docs, migration, compatibility, packaging, performance and supported-platform CI before any 2.1 publication decision.

## Completion policy

`10/10 = 100%` means the named SwirEngine 2.1 creator/editor scope has verified acceptance evidence. It does not mean literal software perfection. No milestone closes from scaffolding, screenshots or cosmetic work alone; relevant implementation, tests and CI/runtime evidence must exist.

## Stable 2.0 maintenance policy

The former post-release audit in [`docs/SWIRENGINE_2_0_POST_RELEASE_AUDIT.md`](docs/SWIRENGINE_2_0_POST_RELEASE_AUDIT.md) is retained as a historical verification snapshot rather than an active progress scope. Stable 2.0 maintenance is reopened only for concrete regressions, compatibility failures, security/safety issues or other release-blocking defects discovered while 2.1 development continues.
