<!-- SWIR-PROGRESS-SVG-PRO:v1 -->

# SwirEngine 1.9 Roadmap — Production Workflow & Game Shipping

SwirEngine 1.9 is a **completed source-only historical checkpoint**. Its live progress graphic has been
retired so the shared SWIR progress assets can represent the active SwirEngine 2.0 roadmap without
rewriting 1.9 history.

**Current verified progress: 10/10 milestones = 100.0%.**  
**Historical status:** COMPLETE for the named 1.9 source scope.  
**Release readiness:** no 1.9 release was authorized; the next public GitHub Release and PyPI publication remains SwirEngine 2.0.

`Release/PyPI: frozen until SwirEngine 2.0`

## Release policy preserved from the checkpoint

- Published `v1.4.0` and `v1.5.0` history remains immutable.
- SwirEngine 1.9 is source-only: no `v1.9.0`, GitHub Release, release tag or PyPI publication was created.
- 1.9 systems were developed as additive/opt-in extensions where stable 1.x behavior could otherwise change.
- The completed 1.9 checkpoint hands active development to [`ROADMAP_2_0.md`](ROADMAP_2_0.md).

## Verified milestones

- [x] **1. Project Manifest & Production Profiles**
- [x] **2. Unified Run & Development Session Workflow**
- [x] **3. Input, UI & Settings Shipping Contract**
- [x] **4. Save, Profile & Game-State Production Integration**
- [x] **5. Scene, Prefab & Level Package Workflow**
- [x] **6. Content Build Graph & Shipping Asset Preparation**
- [x] **7. Runtime Diagnostics, Crash Reports & Support Bundles**
- [x] **8. Desktop Shipping Matrix & Reproducible Build Plans**
- [x] **9. Real-Game Production Gate**
- [x] **10. 1.9 Source Checkpoint & 2.0 Readiness Audit**

## Historical verification evidence

| Milestone | Verified implementation/closeout head | Key retained evidence |
|---|---|---|
| 1 | `d9e4b5fcc98d64847d75ae3e02c9910d56dcf2f6` | Python 3.10/3.13/3.14 gate; 23 focused tests on 3.13; 2,000-cycle workload 1.1970 s under 5.0 s. |
| 2 | `e18aa3777598a47c64bcb400946227e6d14583ff` | Python 3.10/3.13/3.14 gate; 45 focused tests; 5,000-plan workload 0.8142 s under 5.0 s. |
| 3 | `3593f54bc7438b92a1dbb75819624cd4d00bf412` | 35 shipping + 12 input/gamepad regressions; 5,000-cycle workload 1.2300 s; Python 3.10/3.13/3.14. |
| 4 | `0cdf57a11a5d3c6df9fc5f5285ae14ea96a04a02` | 7 production-state + 53 save/profile regressions; 32-write/recovery workload 0.0396 s. |
| 5 | `dc60b13dd1b317149d483a94ec4456ffdb3ac54d` | Scene/export/serialization compatibility gate; legacy projects without `[scenes]` retained. |
| 6 | `71d185b3b32299adfaeee772d27abb7105667614` | 38 focused content/export tests; 256-node × 2,500-plan workload 1.2311 s under 8.0 s. |
| 7 | `8546ccc0bf2d70575ab05628e8bf8d4aab4c6f0a` | 14 focused diagnostics tests; 1,000-report workload 0.2926 s; privacy-bounded support bundles. |
| 8 | `5da85ae39df0f55c3b1679eabf0cfddc3daef08a` | Python 3.10/3.13/3.14 plus clean-wheel native package/runtime probes on Windows, Linux and macOS; 500-plan workload 2.0154 s. |
| 9 | `ab44450e1d2ae9566967b0ec398b712cfe479c85` | 2D/3D/multiplayer source-to-staged runtime gate on Python 3.10/3.13/3.14; deterministic staging on Windows/Linux/macOS. |
| 10 | `07bd248764a7353a82c50d353196e7b2e8bae8ff` | Final 1.9 closeout candidate; merged by PR #151 into `main` as `ece63c81a81d8a30fd084e83200f610e39463f3d` after the source-checkpoint handoff. |

The milestone-specific implementation details remain attributable through the recorded commits, pull-request
history and dedicated documentation. The active 2.0 roadmap does not reinterpret these percentages as 2.0
completion.

## 1.9 production contracts retained

The completed checkpoint established:

- validated `swirproject.toml` project manifests and production profiles;
- deterministic run sessions and creator startup diagnostics;
- semantic input maps, UI focus, rebinding and display/accessibility settings;
- bounded save/profile/autosave integration and portable user-data policy;
- explicit boot scenes, scene/prefab registries and shipping-safe dependency validation;
- deterministic content build/preload/stream planning and export completeness checks;
- privacy-bounded runtime diagnostics, crash reports and creator support bundles;
- host-native desktop shipping plans and artifact manifests;
- representative 2D, 3D and multiplayer real-game integration gates;
- a source-checkpoint/readiness audit that intentionally did not publish 1.9.

## Source references

- [`docs/PROJECT_PRODUCTION_1_9.md`](docs/PROJECT_PRODUCTION_1_9.md)
- [`docs/RUN_SESSIONS_1_9.md`](docs/RUN_SESSIONS_1_9.md)
- [`docs/INPUT_UI_SETTINGS_1_9.md`](docs/INPUT_UI_SETTINGS_1_9.md)
- [`docs/GAME_STATE_PRODUCTION_1_9.md`](docs/GAME_STATE_PRODUCTION_1_9.md)
- [`docs/SCENE_PACKAGES_1_9.md`](docs/SCENE_PACKAGES_1_9.md)
- [`docs/CONTENT_BUILD_1_9.md`](docs/CONTENT_BUILD_1_9.md)
- [`docs/RUNTIME_DIAGNOSTICS_1_9.md`](docs/RUNTIME_DIAGNOSTICS_1_9.md)
- [`docs/desktop-shipping-1.9.md`](docs/desktop-shipping-1.9.md)
- [`docs/REAL_GAME_PRODUCTION_1_9.md`](docs/REAL_GAME_PRODUCTION_1_9.md)
- [`docs/SWIRENGINE_2_0_READINESS_AUDIT.md`](docs/SWIRENGINE_2_0_READINESS_AUDIT.md)

## Handoff

SwirEngine 1.9 closed the source-only production/shipping path. Active progress measurement now belongs to
[`ROADMAP_2_0.md`](ROADMAP_2_0.md), whose completion and release readiness are separate from this historical
10/10 checkpoint.
