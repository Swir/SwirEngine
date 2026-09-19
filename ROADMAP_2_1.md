# SwirEngine 2.1 — SwirEditor & Creator Workflow Roadmap

<img width="100%" src="assets/readme/progress-2-1-mini.svg" alt="SwirEngine 2.1 SwirEditor roadmap progress" />

SwirEngine 2.1 develops the creator-facing desktop workflow in parallel with the maintained SwirEngine 2.0 post-release audit. It does not rewrite the published 2.0.0 release or its historical roadmap.

Current verified progress: 3/10 milestones = 30.0%.

## Milestones

- [x] **1. Project-backed SwirEditor session and desktop launcher.** Open a manifest-driven project, load/save a portable editor scene, persist `.swir/editor.json`, browse project assets, expose diagnostics/profiling models, provide a real desktop launcher and verify headless CI behavior. Verified on implementation head `be5d17ff64f2ae74bb8d96812b4dc2512f52defb` after the cross-platform CI, packaging, Ruff and compatibility checks passed.
- [x] **2. Project Hub and unified CLI entry.** Add New/Open/Recent project flows, creator templates and the `swirengine editor` command while preserving the standalone editor entry point for desktop packaging. Verified on implementation head `be5d17ff64f2ae74bb8d96812b4dc2512f52defb` with hub/CLI regression coverage included in the green CI matrix.
- [x] **3. Scene authoring workflow.** Create/open/save multiple scenes, add/remove/duplicate/reparent objects and entities, scene tabs, unsaved-change protection and deterministic recovery. Verified on implementation head `be5d17ff64f2ae74bb8d96812b4dc2512f52defb` with dedicated scene-authoring and recovery tests included in the green CI matrix.
- [ ] **4. Inspector, components and prefabs.** Creator-friendly typed editors, multi-selection, component add/remove, prefab create/instantiate/apply/revert and safe asset-property assignment.
- [ ] **5. Production 2D/3D viewport.** Picking, camera navigation, transform gizmos, snapping, overlays, grid controls and reliable live viewport rendering in both engine modes.
- [ ] **6. Asset import and content pipeline UX.** Import/reimport, drag/drop, previews, dependency visibility, background processing and actionable validation without duplicating runtime asset logic.
- [ ] **7. Play/debug/profiling loop.** Integrated Play/Pause/Stop/Step, isolated edit/runtime state, console navigation, profiler views, diagnostics and failure-safe recovery.
- [ ] **8. Gameplay tooling.** Input/rebinding, settings, animation, physics/collision, navigation/AI, audio, UI/HUD and save/profile editors built on the high-level runtime APIs.
- [ ] **9. Build/export wizard.** Profile-aware staging, host-native build/export, icon/metadata configuration, diagnostics, artifact inspection and truthful platform gating.
- [ ] **10. Real-game editor gate and 2.1 release readiness.** Drive maintained 2D, 3D and multiplayer fixtures from project creation through authoring, run, diagnostics and shipping; complete docs, migration, compatibility, packaging, performance and supported-platform CI before any 2.1 publication decision.

## Completion policy

`10/10 = 100%` means the named SwirEngine 2.1 creator/editor scope has verified acceptance evidence. It does not mean literal software perfection. No milestone closes from scaffolding, screenshots or cosmetic work alone; relevant implementation, tests and CI/runtime evidence must exist.

## Parallel 2.0 maintenance

The authoritative SwirEngine 2.0 post-release audit remains in [`docs/SWIRENGINE_2_0_POST_RELEASE_AUDIT.md`](docs/SWIRENGINE_2_0_POST_RELEASE_AUDIT.md). Findings that affect the stable public 2.0 line continue to be hardened independently while 2.1 editor development proceeds on feature branches.
