<!-- SWIR-PROGRESS-SVG-PRO:v1 -->

# SwirEngine 2.0 Post-Release Audit & Hardening

<img width="100%" src="assets/readme/progress-mini.svg" alt="SwirEngine 2.0 post-release audit progress: 1 of 10 checkpoints, 10.0%, in progress" />

**Current verified progress: 1/10 checkpoints = 10.0%.**

SwirEngine **2.0.0 is publicly released**. This document is now the authoritative active quality scope. The completed pre-release roadmap remains historical evidence in [`ROADMAP_2_0.md`](ROADMAP_2_0.md) and at the immutable [`v2.0.0` tag](https://github.com/Swir/SwirEngine/tree/v2.0.0).

Audit progress is deliberately independent from the completed 2.0 release roadmap. A checkpoint is marked complete only after its named post-release scope has fresh evidence. Documentation-only or cosmetic work never raises this percentage.

## Release snapshot

| Item | Verified state |
|---|---|
| Public version | `2.0.0` |
| Immutable release source | `4c219f3bed4c107c612a58fa2fb1f1362b4dfc46` |
| GitHub Release | `v2.0.0`, published 2026-09-19 |
| PyPI | `swirengine==2.0.0` public |
| Public clean-install verification | Ubuntu / Python 3.13, macOS / Python 3.13, Windows / Python 3.14 |
| Open repository issues at audit start | `0` |

## Completion standard

The engine may be described as **audit-clean / practically complete** only when all ten checkpoints below are freshly verified, no known critical/high-severity or release-blocking issue remains, public docs match reality, supported runtime/package matrices stay green, representative games remain buildable through documented workflows, and a final fresh review finds no clearly justified high-impact improvement that can safely be implemented.

## Audit checkpoints

- [x] **1. Public Release & Clean-Install Reality Check**
  - verify the immutable `v2.0.0` source identity and public GitHub Release;
  - verify PyPI exposes `swirengine==2.0.0` and required metadata;
  - install only from the public PyPI Simple index in clean environments on the release verification matrix;
  - verify runtime version identity outside the development checkout;
  - record publication-path incidents that should become regression hardening.

- [ ] **2. Architecture, Public API, Migration & Backwards Compatibility**
  - re-audit module boundaries, ownership and high-level versus low-level API consistency;
  - re-run the published 1.5 compatibility floor against installed 2.0 artifacts;
  - exercise documented migrations on representative 1.x projects;
  - remove accidental inconsistencies or document deliberate 2.0-only behavior precisely.

- [ ] **3. Runtime Stability, Lifecycle, Memory & Resource Handling**
  - stress scene/runtime startup-shutdown cycles, streaming, caches and resource pools;
  - probe long-running allocation/release behavior and bounded background work;
  - verify deterministic cleanup after failures and repeated game/session reloads;
  - fix reproducible leaks, lifetime races, unbounded growth or unsafe teardown.

- [ ] **4. Rendering, Physics, Audio, Input & Core Gameplay Systems**
  - exercise real 2D/3D rendering paths and representative workload limits;
  - re-audit physics/collision/navigation behavior at production-facing boundaries;
  - verify audio optionality/failure handling and supported runtime paths;
  - exercise keyboard, mouse and gamepad/rebinding flows through real gameplay fixtures.

- [ ] **5. Networking, Multiplayer & Dedicated Server Hardening**
  - stress session lifecycle, reconnect/resync, replication bounds and compatibility fingerprints;
  - verify player-local versus authoritative state isolation under failure/recovery paths;
  - exercise fixed-tick headless dedicated-server behavior and malformed/mismatched peers;
  - keep public-network/hosting claims limited to what the repository actually verifies.

- [ ] **6. Creator Workflow, Editor Tooling & Representative Games**
  - build, run, prepare, export and recover maintained 2D, 3D and multiplayer projects end to end;
  - identify awkward creator APIs, missing diagnostics and avoidable manual file editing;
  - harden UI/editor/CLI workflows where evidence shows a real production gap;
  - keep examples as integration fixtures rather than separate release products.

- [ ] **7. Packaging, Export, Python & Platform Matrix**
  - re-run wheel/sdist integrity and clean-install checks from public artifacts where applicable;
  - re-run host-native packaged-game probes on claimed Windows/Linux/macOS targets;
  - verify CPython 3.10–3.14 support statements against actual current CI evidence;
  - keep unsupported architectures/runtimes explicit instead of implied.

- [ ] **8. Diagnostics, Crash Handling, Privacy, Security & Safety Boundaries**
  - re-audit logs, crash/support bundles, path handling, archive extraction and generated manifests;
  - validate bounded/redacted diagnostics and opt-in support behavior;
  - probe malformed/untrusted project data at shipping/import/export boundaries;
  - fix any high-impact safety or integrity weakness before audit completion.

- [ ] **9. Documentation, Examples, Upgrade Guidance & Competitive Evidence**
  - reconcile README, changelog, support matrix, migration docs and CLI examples with public 2.0 reality;
  - run documented commands from clean installs and fresh projects;
  - keep benchmark/comparison claims reproducible and technically comparable;
  - remove stale release-prep/freeze wording and unsupported marketing claims.

- [ ] **10. Final Fresh Regression Sweep & Practical-Completion Review**
  - run the supported CI/runtime/packaging matrix from a fresh exact head;
  - verify no open critical/high-severity or release-blocking issues remain;
  - re-run representative 2D/3D/multiplayer shipping workflows;
  - review active code/docs/tooling for one last clearly justified high-impact safe improvement;
  - mark audit-clean only if the result is genuinely clean rather than merely numerically complete.

## Checkpoint 1 verified evidence

The public `v2.0.0` release is anchored to source commit `4c219f3bed4c107c612a58fa2fb1f1362b4dfc46`. The guarded Trusted Publishing workflow rebuilt and revalidated the immutable tag, reran the final compatibility/runtime/real-game/performance/release-safety gates, published wheel/sdist artifacts plus the Windows CPython 3.14 native wheel, then created the GitHub Release and installed `swirengine==2.0.0` from the public PyPI Simple index on Ubuntu/Python 3.13, macOS/Python 3.13 and Windows/Python 3.14.

The first Ubuntu public-install attempt exposed a real PyPI propagation race: the JSON metadata endpoint reported 2.0.0 before the Simple index served it to that runner. Re-running the unchanged public-install job succeeded. This is recorded as a post-release hardening target; the release itself is publicly verified rather than inferred from metadata alone.

## Audit rules

- Keep `v1.4.0`, `v1.5.0` and `v2.0.0` release history immutable.
- Do not retroactively publish source-only 1.6–1.9 checkpoints.
- Prefer fixes with reproducible tests and real creator/runtime evidence.
- Do not raise audit progress for cosmetic changes.
- Do not claim literal perfection; use **audit-clean / practically complete** only when the completion standard above is met.
- Keep repository-facing content in English and keep the SWIR SVG progress source deterministic.
