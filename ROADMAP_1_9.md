<!-- SWIR-PROGRESS-SVG-PRO:v1 -->

# SwirEngine 1.9 Roadmap — Production Workflow & Game Shipping

SwirEngine 1.8 is a completed source-only rendering checkpoint. SwirEngine 1.9 turns the mature
runtime systems into a coherent production path for building, validating, packaging and shipping
complete games while preserving stable 1.x behavior.

**Current verified progress: 9/10 milestones = 90.0%.**

<img width="100%" src="assets/readme/progress-mini.svg" alt="SwirEngine 1.9 verified roadmap progress: 9 of 10 milestones, 90.0%, in progress" />

**Verified active scope:** 9/10 milestones = 90.0% — IN PROGRESS.  
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

- [x] **4. Save, Profile & Game-State Production Integration**
  - project lifecycle integration for save/profile/config systems;
  - bounded autosave/manual-save orchestration and migration diagnostics;
  - portable user-data location policy by supported desktop platform;
  - failure-safe recovery and representative game integration coverage.

- [x] **5. Scene, Prefab & Level Package Workflow**
  - explicit boot scene and packaged scene registry;
  - deterministic scene/prefab dependency validation before export;
  - creator-facing level transition/loading contracts;
  - compatibility bridge for existing scene APIs and demos.

- [x] **6. Content Build Graph & Shipping Asset Preparation**
  - deterministic content dependency graph for assets, scenes, shaders and generated data;
  - preload/warmup/streaming plans connected to existing asset/runtime systems;
  - duplicate/missing content detection and bounded build diagnostics;
  - measurable content-build regression workload.

- [x] **7. Runtime Diagnostics, Crash Reports & Support Bundles**
  - opt-in structured crash/runtime report capture with privacy-safe defaults;
  - bounded logs, engine/project/build identifiers and diagnostic snapshots;
  - creator-generated support bundle without secrets or arbitrary user files;
  - failure-injection and corrupted-report hardening coverage.

- [x] **8. Desktop Shipping Matrix & Reproducible Build Plans**
  - canonical Windows/Linux/macOS build profiles where each platform is actually verified;
  - deterministic staging/build manifests, checksums and artifact inventory;
  - clean-environment install/export/build verification;
  - no unsupported cross-compilation claims.

- [x] **9. Real-Game Production Gate**
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

## Milestone 4 verification contract

Milestone 4 is complete only when the exact final implementation candidate satisfies all of the following:

1. `ProductionGameStateSession` remains additive over the stable save/profile and background-save systems and
   does not change the published 1.5.0 API contract.
2. Manual slots use validated bounded identifiers, reserve the autosave namespace and enforce a hard creator
   slot budget before background work is accepted.
3. Autosaves use deterministic rotating slots, monotonic generations, an interval gate and at most one active
   autosave request per production session.
4. Save snapshots are validated and size-bounded on the owner thread before background I/O begins; rejected
   snapshots never enter the background scheduler.
5. Completed background-save records are released after delivery so long-running play sessions do not retain
   one scheduler/request record per completed manual save or autosave.
6. User-data roots follow explicit Windows/macOS/Linux desktop policy and settings persist inside the same
   profile tree without claiming unsupported platforms.
7. Recovery reads can fall back through the stable primary/backup contract and migration counts are exposed in
   production diagnostics without hiding failures.
8. Existing Save/Profile 2.0 and Background Save 1.7 behavior remains unchanged and passes regression coverage.
9. The creator demo proves manual save, autosave, settings/profile co-location and load/recovery flow, while the
   deterministic workload completes verified writes plus a recovery read under the documented regression gate.
10. Focused tests, stable save/profile regressions, Ruff, compile and the dedicated Python 3.10/3.13/3.14
    workflow pass, followed by the repository compatibility/runtime/packaging matrix on the exact head.

Verified implementation head `0cdf57a11a5d3c6df9fc5f5285ae14ea96a04a02` passed the dedicated
Python 3.10/3.13/3.14 Game State Production gate and all triggered compatibility/regression workflows,
including CI, Desktop Export, source checkpoints 1.6/1.7/1.8, game-demo validation, locked 1.4/1.5
hardening, real OpenGL source demos and packaged 3D runtime validation. Python 3.13 ran 7 focused
production game-state tests plus 53 stable save/profile/background-save regressions; Ruff and compile
passed, the creator demo completed, and the 32-write plus recovery workload finished in 0.0396 seconds.
The roadmap-marked PR head must re-pass its triggered gates before merge.

## Milestone 5 verification contract

Milestone 5 is complete only when the exact final implementation candidate satisfies all of the following:

1. Scene shipping is opt-in: projects without `[scenes]` keep the established 1.x exporter and manifest behavior.
2. `[scenes]` declares an explicit boot scene plus a bounded registry of project-contained scene packages.
3. Scene dependencies are deterministic, cycle-safe and reject unknown/self dependencies before runtime loading.
4. Scene and prefab paths reject absolute paths, traversal, drive escapes and symlink-resolved project escapes.
5. `ScenePackageLoader` transitions into the existing runtime `Scene` object without replacing its identity and
   returns declared `Prefab` values without hidden auto-instantiation.
6. Full document validation remains explicit through the creator's `SceneSerializer`/codec registry, while
   generic export preflight performs safe structural/filesystem validation without dynamic imports.
7. `ProjectExporter` treats declared scene and prefab files as authoritative shipping content, stages them even
   outside broad include roots, and rejects export profiles that would silently exclude required scene content.
8. Stable `Scene`, `Prefab`, `SceneSerializer` behavior and legacy projects without `[scenes]` remain unchanged.
9. The creator demo proves boot/level transition plus explicit prefab instantiation, while the deterministic
   5,000 × 64-package planning workload remains under the documented regression ceiling without FPS claims.
10. Focused scene/export/serialization/manifest tests, Ruff, compile and the dedicated Python 3.10/3.13/3.14
    workflow pass, followed by the repository compatibility/runtime/packaging matrix on the exact head.

Verified implementation head `dc60b13dd1b317149d483a94ec4456ffdb3ac54d` passed the dedicated
Python 3.10/3.13/3.14 Scene Packages 1.9 gate and every triggered compatibility/regression workflow,
including CI, Desktop Export, source checkpoints 1.6/1.7/1.8, Game Demos Validation, Demo Game 3D
Validation, Neon Snake 3D Validation and locked 1.4/1.5 hardening. The final implementation includes
an exporter compatibility regression proving projects without `[scenes]` stay on the legacy path.
This roadmap-marked head must re-pass its triggered gates before merge.

## Milestone 6 verification contract

Milestone 6 is complete only when the exact final implementation candidate satisfies all of the following:

1. Production content planning is opt-in through a semantically parsed `[content.build]` TOML table; projects
   without it and malformed legacy manifests keep the established 1.x export path.
2. The graph is bounded to 1,024 nodes and 128 direct dependencies per node, with build diagnostics capped at
   64 entries so broken content cannot create unbounded validation output.
3. Target plans use an iterative deterministic dependency-first order, compute transitive closures without
   recursion-depth dependence and expose checkout-independent graph/plan fingerprints.
4. Duplicate node names, duplicate dependency entries, case-folded path collisions, unknown/self/cyclic
   dependencies and unsafe absolute/traversal/drive-prefixed paths fail explicitly before shipping.
5. Filesystem preflight rejects missing content, directories used as files and symlink-resolved project escapes;
   generated build outputs must already exist and are never silently invented or executed by the exporter.
6. Warmup, preload and stream groups bridge to the established asset/preload/streaming runtimes without moving
   renderer/GPU finalization onto worker threads or changing stable 1.x loading semantics.
7. `ProjectExporter` automatically stages required content-build files even outside broad include roots and
   rejects profiles that would silently exclude graph-declared shipping content.
8. Existing legacy export behavior, scene packages and stable asset/runtime systems remain additive and pass
   compatibility coverage when `[content.build]` is not enabled.
9. The creator demo proves deterministic shader warmup inputs, startup preload and stream-on-demand planning;
   the 256-node × 2,500-plan Python 3.13 workload remains below the documented 8.0-second ceiling.
10. Focused graph/export tests, creator demo, Ruff, compile and the dedicated Python 3.10/3.13/3.14 workflow
    pass, followed by the complete repository compatibility/runtime/packaging matrix on the exact head.

Verified implementation head `71d185b3b32299adfaeee772d27abb7105667614` passed the dedicated
Python 3.10/3.13/3.14 Content Build 1.9 gate and every triggered compatibility/regression workflow,
including CI, Desktop Export, source checkpoints 1.6/1.7/1.8, Game Demos Validation, Demo Game 3D
Validation, Neon Snake 3D Validation and locked 1.4/1.5 hardening. Python 3.13 ran 38 focused
content/export tests, the creator preload/stream flow, Ruff and compile successfully; the 256-node ×
2,500-plan workload completed in 1.2311 seconds under the documented 8.0-second ceiling. This
roadmap-marked head must re-pass its triggered gates before merge.

## Milestone 7 verification contract

Milestone 7 is complete only when the exact final implementation candidate satisfies all of the following:

1. Runtime crash capture is opt-in and does not automatically collect environment variables, command-line
   arguments, locals, arbitrary files or traceback source lines.
2. Reports carry bounded engine/project/build identity and a deterministic project fingerprint without
   depending on checkout location or hidden global state.
3. Structured logs are bounded, sequence-stable and redact sensitive-key fields before they enter a report.
4. Diagnostic and performance snapshots are explicitly supplied, size/depth bounded and reject non-finite or
   non-portable JSON values rather than silently serializing them.
5. Tracebacks expose project-relative paths when possible and external basenames otherwise, while report text
   scrubs known project/home paths and common inline credential forms.
6. Creator-generated support ZIPs contain only generated `bundle.json` and `report.json` entries with stable
   ordering/timestamps, report hashes and explicit privacy metadata; unrelated user files are never swept in.
7. Report loading rejects invalid UTF-8/JSON, unsupported schemas/versions and oversized payloads before a
   support bundle can be created from them.
8. Integration with existing project manifests and `PerformanceDiagnostics2` remains additive and does not
   change the published 1.5.0 runtime contract.
9. The creator demo proves crash capture → JSON round-trip → support ZIP without user-file capture; the
   deterministic 1,000-report Python 3.13 workload remains below the documented 8.0-second ceiling.
10. Focused tests, creator demo, workload, Ruff, compile and the dedicated Python 3.10/3.13/3.14 workflow pass,
    followed by the complete repository compatibility/runtime/packaging matrix on the exact head.

Verified implementation head `8546ccc0bf2d70575ab05628e8bf8d4aab4c6f0a` passed the dedicated
Python 3.10/3.13/3.14 Runtime Diagnostics 1.9 gate and every triggered compatibility/regression workflow,
including CI, Desktop Export, source checkpoints 1.6/1.7/1.8, Game Demos Validation, Demo Game 3D
Validation, Neon Snake 3D Validation, Project Production 1.9, GPU Timing Capture 1.8 and locked 1.4/1.5
hardening. Python 3.13 ran 14 focused runtime-diagnostics tests, the creator support-bundle flow, Ruff and
compile successfully; the 1,000-report workload completed in 0.2926 seconds (3,418.0 reports/s) under
the documented 8.0-second ceiling. This roadmap-marked head must re-pass its triggered gates before merge.

## Milestone 8 verification contract

Milestone 8 is complete only when the exact final implementation candidate satisfies all of the following:

1. Desktop shipping remains additive over the stable `ProjectExporter`/1.5.0 packaging contract and consumes
   explicit 1.9 production profiles rather than silently changing legacy export behavior.
2. A shipping plan accepts Windows, Linux or macOS only when the requested target matches the host platform;
   unsupported cross-compilation claims fail explicitly before a native build starts.
3. Source inventories are deterministic and checkout-independent, contain project-relative paths plus SHA-256
   content hashes, and reject unsafe/traversing/case-colliding inputs before packaging.
4. Shipping plans and artifact manifests are schema-versioned, bounded and fingerprinted so malformed,
   oversized or inconsistent metadata cannot be accepted as a valid build record.
5. Native build output is created outside project source, preserving the established exporter overlap-safety
   contract while still consuming the verified staged content produced by the existing export pipeline.
6. Artifact manifests inventory the exact packaged files and symlink targets with content hashes, target and
   plan identity; verification rejects missing, extra, modified or mismatched artifacts.
7. A clean wheel install can build and verify a host-native packaged smoke game and the produced executable
   must actually run and emit the expected runtime marker on every claimed desktop platform.
8. Dedicated native validation covers Windows, Linux and macOS on matching GitHub-hosted runners while the
   Python 3.10/3.13/3.14 contract matrix locks planning/export compatibility and no cross-build claim is made.
9. The deterministic 500-plan Python 3.13 workload remains below the documented 5.0-second ceiling without
   turning CI timing into an unsupported FPS or end-user build-speed claim.
10. Focused shipping/export tests, clean-wheel native runtime probes, Ruff, compile and the dedicated matrix
    pass, followed by the complete repository compatibility/runtime/packaging matrix on the exact head.

Verified implementation head `5da85ae39df0f55c3b1679eabf0cfddc3daef08a` passed the dedicated
Desktop Shipping 1.9 matrix and every triggered compatibility/regression workflow, including CI,
Desktop Export, source checkpoints 1.6/1.7/1.8, Game Demos Validation, Demo Game 3D Validation,
Neon Snake 3D Validation and locked 1.4/1.5 hardening. The dedicated contract matrix passed Python
3.10, 3.13 and 3.14; Python 3.13 ran 24 shipping/export tests plus 35 locked input/UI/settings tests,
Ruff and compile successfully, while the 500-plan workload completed in 2.0154 seconds under the
5.0-second ceiling. Clean-wheel host-native package/manifest/runtime probes passed on Windows, Linux
and macOS. This roadmap-marked head must re-pass its triggered gates before merge.

## Milestone 9 verification contract

Milestone 9 is complete only when the exact final implementation candidate satisfies all of the following:

1. The maintained 2D and 3D source games plus a dedicated multiplayer fixture remain source-only integration
   fixtures and do not create independent releases or bypass the engine production workflow.
2. Each fixture is copied into an isolated production project with an explicit manifest, title/gameplay scenes,
   shipping input/settings defaults and content-build declarations rather than relying on repository state.
3. Player rebinding, accessibility settings and save/profile data round-trip through the production APIs while
   remaining outside redistributable staged project content.
4. Scene packages, content dependencies and required shipping files are validated before export, and repeated
   export planning is deterministic.
5. Staged outputs contain the entrypoint, project manifest, project controls/settings, declared assets and scenes
   with deterministic SHA-256 inventory entries, while private user-data paths are rejected from shipping.
6. Runtime mode launches both copied source entrypoints and staged entrypoints for the 2D, 3D and multiplayer
   fixtures and requires successful completion rather than treating staging alone as runtime validation.
7. The multiplayer fixture exercises the established replication, prediction/reconciliation, session, QoS and
   profiler paths under seeded packet loss, duplication, reordering, latency and jitter with four clients.
8. The production contract runs on Python 3.10, 3.13 and 3.14, while deterministic staging runs independently on
   Windows, Linux and macOS without making unsupported cross-compilation claims.
9. The real-game gate stays separate from the native executable gate: Milestone 8 continues to own clean-wheel
   host-native executable creation, and both gates must remain green on the exact implementation head.
10. Focused production tests, runtime/staging validation, Ruff, compile, deterministic SVG checks and the full
    repository compatibility/runtime/packaging matrix pass before the milestone is marked complete.

Verified implementation head `ab44450e1d2ae9566967b0ec398b712cfe479c85` passed Real-Game Production
1.9 on Python 3.10, 3.13 and 3.14, including the source-to-staged runtime gate, and deterministic staging
passed on Windows, Linux and macOS. The same exact head passed CI, Desktop Export, source checkpoints
1.6/1.7/1.8, Game Demos Validation, Run Sessions + Progress 1.9, Frame Budget 1.7 and locked 1.4/1.5
hardening. A timing-sensitive frame-budget reentrancy regression was made deterministic with the existing
fake clock after macOS Python 3.10 exposed the test flake; the production frame-budget implementation was
unchanged and its Python 3.10/3.13/3.14 dedicated gate passed. This roadmap-marked closeout head must
re-pass its triggered gates before merge.

`Release/PyPI: frozen until SwirEngine 2.0`.