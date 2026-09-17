<!-- SWIR-PROGRESS-SVG-PRO:v1 -->

# SwirEngine 1.9 Roadmap — Production Workflow & Game Shipping

SwirEngine 1.8 is a completed source-only rendering checkpoint. SwirEngine 1.9 turns the mature
runtime systems into a coherent production path for building, validating, packaging and shipping
complete games while preserving stable 1.x behavior.

**Current verified progress: 1/10 milestones = 10.0%.**

<img width="100%" src="assets/readme/progress-mini.svg" alt="SwirEngine 1.9 verified roadmap progress: 1 of 10 milestones, 10.0%, in progress" />

**Verified active scope:** 1/10 milestones = 10.0% — IN PROGRESS.  
**Release readiness:** frozen; the next public GitHub Release and PyPI publication remains SwirEngine 2.0.

A milestone is checked only after implementation, focused tests, creator documentation, its dedicated
gate and the repository's required compatibility/regression gates pass on the exact final head.

## Release policy

- Keep published `v1.4.0` and `v1.5.0` history immutable.
- SwirEngine 1.9 is source-only: **do not create `v1.9.0`, a GitHub Release, a release tag or a PyPI publish**.
- Keep new 1.9 systems additive or opt-in where they could change stable 1.x behavior.
- When this roadmap reaches verified 10/10, run the full source-checkpoint gate and continue toward 2.0.
- The next public GitHub Release and PyPI publication remains SwirEngine 2.0 only.

## Milestones

- [x] **1. Project Manifest & Production Profiles**
  - validated `swirproject.toml` loader with legacy-manifest compatibility;
  - deterministic project fingerprint and safe project-relative path contracts;
  - named desktop/export profiles mapped onto the existing `PackagingProfile` contract;
  - `swirengine doctor` plus profile-driven `swirengine export` without breaking legacy CLI use;
  - Python 3.10/3.13/3.14 gate, focused regression coverage and creator documentation.

- [ ] **2. Unified Run & Development Session Workflow**
  - manifest-driven project run command with explicit entrypoint and environment handling;
  - deterministic development configuration and actionable startup diagnostics;
  - safe argument/config forwarding without hidden global state;
  - creator workflow usable by both 2D and 3D projects.

- [ ] **3. Input, UI & Settings Shipping Contract**
  - project-level action-map and controller/rebinding integration;
  - menu/focus/accessibility defaults suitable for keyboard and gamepad shipping;
  - settings persistence and resolution/display configuration bridge;
  - source examples covering a complete title/menu/settings/gameplay flow.

- [ ] **4. Save, Profile & Game-State Production Integration**
  - project lifecycle integration for save/profile/config systems;
  - bounded autosave/manual-save orchestration and migration diagnostics;
  - portable user-data location policy by supported desktop platform;
  - failure-safe recovery and representative game integration coverage.

- [ ] **5. Scene, Prefab & Level Package Workflow**
  - explicit boot scene and packaged scene registry;
  - deterministic scene/prefab dependency validation before export;
  - creator-facing level transition/loading contracts;
  - compatibility bridge for existing scene APIs and demos.

- [ ] **6. Content Build Graph & Shipping Asset Preparation**
  - deterministic content dependency graph for assets, scenes, shaders and generated data;
  - preload/warmup/streaming plans connected to existing asset/runtime systems;
  - duplicate/missing content detection and bounded build diagnostics;
  - measurable content-build regression workload.

- [ ] **7. Runtime Diagnostics, Crash Reports & Support Bundles**
  - opt-in structured crash/runtime report capture with privacy-safe defaults;
  - bounded logs, engine/project/build identifiers and diagnostic snapshots;
  - creator-generated support bundle without secrets or arbitrary user files;
  - failure-injection and corrupted-report hardening coverage.

- [ ] **8. Desktop Shipping Matrix & Reproducible Build Plans**
  - canonical Windows/Linux/macOS build profiles where each platform is actually verified;
  - deterministic staging/build manifests, checksums and artifact inventory;
  - clean-environment install/export/build verification;
  - no unsupported cross-compilation claims.

- [ ] **9. Real-Game Production Gate**
  - polished source-only 2D integration game through the production workflow;
  - polished source-only 3D integration game through the production workflow;
  - multiplayer integration fixture with packaging/runtime validation;
  - end-to-end menu/settings/save/input/assets/scenes/export regression coverage.

- [ ] **10. 1.9 Source Checkpoint & 2.0 Readiness Audit**
  - full supported CI/runtime/packaging matrix plus locked 1.4–1.8 contracts;
  - clean source/package install and representative game shipping validation;
  - 2.0 gap audit based on measured real-game blockers rather than feature counting;
  - documentation/changelog closeout with no tag, GitHub Release or PyPI publication.

## Milestone 1 verification contract

Milestone 1 is complete only when the exact final implementation head satisfies all of the following:

1. Existing minimal root-key `swirproject.toml` files remain loadable.
2. Rich manifests may define project metadata, content roots and named packaging profiles.
3. Manifest paths reject absolute paths, traversal and platform-drive escapes before export.
4. Profile values map deterministically onto the existing `PackagingProfile` API.
5. Project fingerprints are deterministic and independent of checkout location.
6. `swirengine new` produces a manifest that passes `swirengine doctor` immediately.
7. `swirengine doctor` returns actionable errors for missing entrypoints/icons and warnings for optional
   content roots without mutating the project.
8. `swirengine export --profile <name>` uses the manifest profile while legacy explicit-target export
   remains supported.
9. A deterministic 2,000-cycle parse/profile/fingerprint workload remains below the documented
   5.0-second Python 3.13 CI ceiling without making runtime/FPS claims.
10. Focused tests, Ruff, compile and the dedicated Python 3.10/3.13/3.14 workflow pass, followed by
    repository compatibility/regression gates before the roadmap checkbox is marked complete.

Verified implementation head `d9e4b5fcc98d64847d75ae3e02c9910d56dcf2f6` passed the dedicated
Python 3.10/3.13/3.14 Project Production gate and all triggered compatibility/regression workflows,
including CI, Desktop Export, source checkpoints 1.6/1.7/1.8, game-demo validation, locked 1.4/1.5
hardening and real packaged-game probes. Python 3.13 ran 23 focused CLI/export/manifest tests, Ruff and
compile successfully; the 2,000-cycle parse/profile/fingerprint workload completed in 1.1970 seconds
under the documented 5.0-second ceiling. The roadmap-marked PR head must re-pass its triggered gates
before merge.

`Release/PyPI: frozen until SwirEngine 2.0`.
