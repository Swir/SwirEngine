<!-- SWIR-PROGRESS-SVG-PRO:v1 -->

# SwirEngine 1.9 Roadmap — Production Workflow & Game Shipping

SwirEngine 1.8 is a completed source-only rendering checkpoint. SwirEngine 1.9 turns the mature
runtime systems into a coherent production path for building, validating, packaging and shipping
complete games while preserving stable 1.x behavior.

**Current verified progress: 3/10 milestones = 30.0%.**

<img width="100%" src="assets/readme/progress-mini.svg" alt="SwirEngine 1.9 verified roadmap progress: 3 of 10 milestones, 30.0%, in progress" />

**Verified active scope:** 3/10 milestones = 30.0% — IN PROGRESS.  
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

- [x] **2. Unified Run & Development Session Workflow**
  - manifest-driven project run command with explicit entrypoint and environment handling;
  - deterministic development configuration and actionable startup diagnostics;
  - safe argument/config forwarding without hidden global state;
  - creator workflow usable by both 2D and 3D projects.

- [x] **3. Input, UI & Settings Shipping Contract**
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
under the documented 5.0-second ceiling. The roadmap-marked PR head re-passed its triggered gates
before merge.

## Milestone 2 verification contract

Milestone 2 is complete only when the exact final implementation candidate satisfies all of the following:

1. Existing manifests without `[run]` retain a safe project-entrypoint/default-working-directory run contract.
2. `[run]` can select a project-contained entrypoint, working directory, bounded arguments and child-process
   environment without mutating parent process state.
3. Absolute/traversal paths and symlink-resolved escapes cannot start outside the project root.
4. `swirengine run` works for both generated 2D and 3D projects and provides a deterministic `--dry-run` plan.
5. Creator arguments after `--` are forwarded consistently on supported Python versions, including Python 3.10.
6. Environment overrides are validated, duplicate override names fail explicitly and `--clean-env` is opt-in.
7. Process launch never uses a shell; startup failures and child exit codes are surfaced without being hidden.
8. Portable run-plan fingerprints are checkout-independent and change when effective run configuration changes.
9. A deterministic 5,000-plan workload remains below the documented 5.0-second Python 3.13 CI ceiling
   without making runtime/FPS claims.
10. Focused tests, progress-asset checks, Ruff, compile and the dedicated Python 3.10/3.13/3.14 workflow pass,
    followed by the repository compatibility/regression gates before the roadmap checkbox is marked complete.

Verified implementation head `e18aa3777598a47c64bcb400946227e6d14583ff` passed the dedicated
Python 3.10/3.13/3.14 Run Sessions + Progress gate and all triggered compatibility/regression workflows,
including CI, Desktop Export, source checkpoints 1.6/1.7/1.8, game-demo validation, locked 1.4/1.5
hardening, real OpenGL source demos, clean-wheel probes and Windows one-file 2D/3D runtime probes.
Python 3.13 ran 45 focused project/run/export/progress tests, Ruff and compile successfully; the
5,000-plan workload completed in 0.8142 seconds under the documented 5.0-second ceiling. The
roadmap-marked PR head must re-pass its triggered gates before merge.

## Milestone 3 verification contract

Milestone 3 is complete only when the exact final implementation candidate satisfies all of the following:

1. Production action maps remain additive over existing `InputActions`/`InputManager` APIs and require a
   shipping-safe semantic menu navigation surface without changing stable 1.x input behavior.
2. Keyboard, mouse and standardized gamepad bindings are canonical, bounded and validated before a profile
   is accepted; unknown gamepad controls and unsafe numeric values fail explicitly.
3. Player overrides persist only actions that differ from project defaults so new default actions can flow
   through later game builds without erasing intentional user rebinding.
4. Binding conflicts are reported deterministically rather than silently rewritten, while intentional shared
   controls remain possible.
5. `FocusActionRouter` drives retained UI focus from semantic keyboard, d-pad and analog-stick action state
   with bounded edge behavior instead of per-frame repeat.
6. Display and accessibility settings use bounded validated schemas, atomic persistence and project defaults
   as fallback; malformed, unknown or non-finite values fail explicitly.
7. Display application stays backend-neutral through explicit callbacks and reports unsupported capabilities
   instead of guessing or mutating hidden backend state.
8. Project configuration paths reject absolute, Windows-drive, traversal and symlink-resolved escapes, and
   configuration payloads are bounded before parsing/writing.
9. The creator production-flow example proves title/settings/gameplay routing, rebinding, settings persistence
   and deterministic fingerprints, while the 5,000-cycle configuration workload remains below the documented
   5.0-second Python 3.13 ceiling without making input-latency/FPS claims.
10. Focused tests, existing input/gamepad regressions, Ruff, compile and the dedicated Python 3.10/3.13/3.14
    workflow pass, followed by the full repository compatibility/runtime/packaging matrix on the exact head.

Verified implementation head `3593f54bc7438b92a1dbb75819624cd4d00bf412` passed the dedicated
Python 3.10/3.13/3.14 Input UI Settings gate and all triggered compatibility/regression workflows,
including CI, Desktop Export, source checkpoints 1.6/1.7/1.8, game-demo validation and locked 1.4/1.5
hardening. Python 3.13 ran 35 focused shipping tests plus 12 existing input/gamepad regressions, Ruff
and compile successfully; the 5,000-cycle parse/fingerprint workload completed in 1.2300 seconds under
the documented 5.0-second ceiling. A missing `libx11-dev` prerequisite for CPython 3.14 source builds
was diagnosed and fixed in the dedicated workflow before this verification passed. The roadmap-marked
PR head must re-pass its triggered gates before merge.

`Release/PyPI: frozen until SwirEngine 2.0`.
