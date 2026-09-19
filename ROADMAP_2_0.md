<!-- SWIR-PROGRESS-SVG-PRO:v1 -->

# SwirEngine 2.0 Roadmap — Release-Quality Python-First Game Production

<img width="100%" src="assets/readme/progress-mini.svg" alt="SwirEngine 2.0 verified roadmap progress: 10 of 10 milestones, 100.0%, release prep" />

**Current verified progress: 10/10 milestones = 100.0%.**

`Release/PyPI: frozen until SwirEngine 2.0`

This roadmap is the authoritative active development scope after the completed source-only 1.9 checkpoint.
The ten source-development milestones are now candidate-complete, but **100% roadmap progress is not a
public-release claim**. The exact 2.0.0 finalization head must still pass the complete release matrix before
merge, immutable tagging, GitHub Release/PyPI publication and public-install verification are allowed.

The latest public package remains **SwirEngine 1.5.0** until the guarded 2.0 publication workflow succeeds.
Source-only 1.6–1.9 checkpoints remain historical engineering evidence and are not retroactively published.

## Release gate principles

- Preserve the stable 1.x compatibility floor unless a deliberate 2.0 migration is documented, tested and justified.
- Prefer creator-facing end-to-end workflows over disconnected subsystem demos.
- Keep representative 2D, 3D and multiplayer games as integration fixtures, not separate releases.
- Require reproducible evidence for performance or competitive comparisons; do not make unsupported superiority claims.
- Validate shipping on each claimed host platform. Unsupported cross-compilation remains explicit rather than implied.
- Keep release readiness separate from roadmap progress. A 100% source roadmap still requires the exact final candidate gate and public verification.
- No GitHub Release, release tag or PyPI publication is permitted until the 10/10 finalization candidate passes the complete exact-head release matrix.

## Milestones

- [x] **1. Public API & Migration Contract**
  - freeze a machine-verifiable compatibility floor from the actual published `v1.5.0` root API;
  - document the 1.5.0 → 2.0 migration policy and migration ledger;
  - prove every published 1.5.0 root export remains present while allowing additive 2.0 exports;
  - keep package/module version metadata frozen at 1.5.0 until the final 2.0 release gate;
  - require future breaking changes to update migration evidence, tests and release notes together.

- [x] **2. Creator Workflow & Integrated Tooling**
  - make project creation, validation, run sessions, scene/prefab editing, settings, save data and export coherent;
  - remove avoidable manual file surgery from representative projects;
  - add actionable diagnostics for malformed projects, missing assets and invalid shipping configuration;
  - prove the workflow through maintained 2D and 3D fixtures.

- [x] **3. Multiplayer & Dedicated Server Production Contract**
  - harden replication/session lifecycle, reconnect/failure handling and deterministic compatibility checks;
  - provide a documented headless/dedicated-server path where technically supported;
  - separate authoritative server state from player-local settings/save data;
  - exercise the contract with the multiplayer fixture and failure-path tests.

- [x] **4. Renderer, Runtime Scalability & Resource Lifecycle**
  - audit scene/render workload scaling, streaming, asset lifetime, memory/resource release and diagnostics;
  - fix high-impact stalls, leaks or unbounded caches found by reproducible workloads;
  - validate 2D and 3D runtime paths under representative production-sized workloads;
  - preserve lower-level control without making the high-level creator API harder to use.

- [x] **5. Final Python & Platform Support Matrix**
  - define the exact Python/OS matrix that 2.0 will publicly claim;
  - run supported combinations through unit, runtime, packaging and platform-specific probes;
  - document unsupported combinations and architecture constraints precisely;
  - remove stale support claims from docs and metadata.

- [x] **6. Representative Real-Game Shipping Gate**
  - drive polished 2D, 3D and multiplayer fixtures through input/UI, settings, save/profile, scenes, assets, diagnostics and export;
  - run source and staged/shipped entrypoints, including failure-path checks;
  - verify game-local and player-local data boundaries;
  - treat fixture failures as engine integration failures rather than demo-only issues.

- [x] **7. Packaging, Clean Install & Native Desktop Shipping**
  - build wheel and sdist from the exact candidate source;
  - verify clean installation and import/runtime smoke tests from built artifacts;
  - build and validate host-native Windows, Linux and macOS game packages for claimed targets;
  - verify artifact inventories, manifests and launch behavior without relying on the development checkout.

- [x] **8. Performance Evidence & Competitive Quality Audit**
  - establish deterministic performance workloads with regression thresholds;
  - publish only technically comparable benchmark evidence with commands, hardware/runtime context and limitations;
  - compare creator productivity and shipping workflows where objective reproduction is possible;
  - fix material regressions before release rather than hiding them behind documentation.

- [x] **9. Export/Build Integrity, Diagnostics & Release Safety**
  - harden content completeness, build identity, crash/support diagnostics and failure reporting;
  - verify required scene/asset/generated content cannot be silently omitted from a successful build;
  - audit privacy/safety boundaries for logs and support bundles;
  - re-run locked historical compatibility/source-checkpoint contracts needed to protect the candidate.

- [x] **10. SwirEngine 2.0 Final Release Gate & Public Verification**
  - complete compatibility/migration validation, supported CI/runtime matrix and documentation accuracy audit;
  - pass clean wheel/sdist install, representative real-game workflows, performance regressions and export/build validation;
  - arm package/module metadata at 2.0.0 only after the 9/10 preflight head is fully green;
  - require the complete exact-head 2.0.0 finalization matrix to pass before merge, tag or publication;
  - publish only through the immutable tag/Trusted Publishing workflow, then confirm a fresh public PyPI install and begin the post-release audit.

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

## Milestone 2 verification contract

Milestone 2 is complete only when the exact implementation head proves all of the following:

1. New 2D and 3D projects expose one coherent creator layout and editable shipping defaults without manual setup.
2. `swirengine workflow` validates the manifest, deterministic run plan, scene packages, content graph, shipping defaults, creator directories and save/profile policy through one creator-facing command.
3. `--prepare` is additive and idempotent: it creates only missing creator directories/defaults and never overwrites existing project configuration.
4. Human diagnostics include actionable next steps for malformed projects, missing entrypoints/assets and invalid scene/content declarations.
5. `--json` returns deterministic machine-readable workflow evidence suitable for CI and higher-level tooling.
6. Equivalent checkouts produce the same workflow fingerprint; absolute checkout and player-data paths are not encoded into portable evidence.
7. Inspection does not execute the game, export a package or create player save/profile data.
8. Maintained 2D and 3D real-game fixtures pass the integrated workflow with scene packages, content graphs and editable defaults present.
9. The dedicated workflow passes on Python 3.10, 3.13 and 3.14 with focused tests, Ruff and bytecode compilation.
10. Full repository CI, historical compatibility/source checkpoints, desktop export and representative demo/runtime gates remain green.

## Milestone 2 verified evidence

Implementation head `79a1a8302a96cb82f49b2b5f368618397b2f5724` passed every triggered workflow before this closeout
was marked. The dedicated Creator Workflow 2.0 gate passed on Python 3.10, 3.13 and 3.14, including focused
creator tests, maintained 2D/3D fixture verification, strict Ruff and bytecode compilation. The exact head
also passed full repository CI, where Python 3.13 completed **1532 tests with 4 skipped**, plus locked
1.4/1.5 hardening, source checkpoints 1.6–1.9, project-production regression checks, game demos, Neon Snake
3D, desktop export and the clean-wheel/native runtime checks exercised by the locked 1.5/1.9 gates.

The integrated workflow is additive over existing project/run/editor/scene/content/settings/save/export
contracts and the public package/module version remains 1.5.0. Milestone 2 is therefore verified at
**2/10 = 20.0%**. Release readiness remains separate; this closeout head must re-pass its triggered matrix
before merge.

## Milestone 3 verification contract

Milestone 3 is complete only when the exact implementation head proves all of the following:

1. Client and server compatibility fingerprints cover project, protocol, build, replication schema and content identity.
2. Compatibility mismatches are rejected before join/resume mutates authoritative session state.
3. Disconnect/resume rotates the single-use resume token and forces a full replication resynchronization when authoritative history exists.
4. Authoritative gameplay state explicitly rejects settings, display, accessibility, controls/input bindings, profile and save data.
5. Authoritative player-state payloads are bounded, portable and returned as defensive snapshots so caller mutation cannot rewrite stored authoritative state.
6. The dedicated-server adapter runs through the existing fixed-tick headless runtime and validates startup before execution.
7. Dedicated-server snapshots preserve the authoritative server tick and fail deterministically on mismatch.
8. The maintained multiplayer real-game fixture exercises join, authoritative/local state separation, match start, disconnect/resume and full resynchronization without public sockets.
9. The dedicated workflow passes on Python 3.10, 3.13 and 3.14 with focused multiplayer/session/replication/server tests, snapshot-isolation regressions, Ruff and bytecode compilation.
10. Full repository CI, locked 1.4/1.5 hardening, source checkpoints 1.6–1.9, desktop export and representative game/runtime gates remain green.

## Milestone 3 verified evidence

Hardened implementation head `419368d6aa910b211a1f71ebdc458ed4b3882d2d` passed every triggered workflow before this closeout
was marked. The dedicated Multiplayer Production 2.0 gate passed on Python 3.10, 3.13 and 3.14, including
focused multiplayer production tests, the existing replication/prediction/session/dedicated-server regression
suites, the representative multiplayer fixture, defensive snapshot-isolation regressions, strict Ruff and
bytecode compilation. The same exact head also passed full repository CI, locked 1.4/1.5 hardening, source
checkpoints 1.6–1.9, Game Demos, Demo Game 3D, Neon Snake 3D, Desktop Export and Real-Game Production 1.9.

The new production layer is additive over the established session, replication, networking and headless-server
APIs; the public package/module version remains 1.5.0 and the fixture opens no public sockets. Milestone 3 is
therefore verified at **3/10 = 30.0%**. Release readiness remains separate; this closeout head must re-pass
its triggered matrix before merge.

## Milestone 4 verification contract

Milestone 4 is complete only when the exact implementation head proves all of the following:

1. Asset streaming residency remains explicitly bounded by byte and asset-count budgets when unpinned eviction is possible.
2. Pinned over-budget pressure is surfaced in diagnostics instead of silently evicting protected resources.
3. Streaming teardown drains or detaches owned pending work deterministically and can release all session-owned residency without worker repopulation races.
4. Externally supplied preloaders remain externally owned and usable after a streaming session shuts down.
5. External cache invalidation reconciles stale residency and re-enters background loading without synchronous decode/file work on the caller thread.
6. Null-like cached values and creator size-estimator failures participate in deterministic invalidation/accounting instead of leaving hidden residency divergence.
7. Transient render resources reuse exact descriptors under explicit bounds and return owned residency to zero on close.
8. Representative 2D workloads retain viewport-local tile visibility and stable 4,096-sprite CPU staging without reallocations.
9. A 4,096-object sparse 3D scene workload retains BVH pruning with fewer than 128 object tests and more than 96% object-test reduction.
10. The dedicated Python 3.10/3.13/3.14 workflow plus full repository compatibility, checkpoint, demo and export gates pass on the exact implementation head.

## Milestone 4 verified evidence

Hardened implementation head `7c690970d614d26af07458eecaf9c425ad65e1ab` passed every triggered workflow before this closeout
was marked. The dedicated Runtime Scalability 2.0 workflow passed on Python 3.10, 3.13 and 3.14, including
focused asset-streaming, resource-pool, renderer, visibility and acceleration regressions, deterministic
production-sized workload verification, strict Ruff and bytecode compilation. The same exact head also
passed full repository CI, Asset Pipeline 2.0/1.4, Large World 1.3, locked 1.4/1.5 hardening, source
checkpoints 1.6–1.9, Game Demos, Demo Game 3D, Neon Snake 3D, Content Build 1.9 and Desktop Export.

The runtime hardening remains additive over stable 1.x behavior: ordinary shutdown preserves cache residency
unless explicit release is requested, shared preloaders stay externally owned, and no benchmark is converted
into an unsupported FPS claim. Milestone 4 is therefore verified at **4/10 = 40.0%**. Release readiness
remains separate; this closeout head must re-pass its triggered matrix before merge.

## Milestone 5 verification contract

Milestone 5 is complete only when the exact implementation head proves all of the following:

1. The candidate base-engine support matrix is explicit and limited to 64-bit CPython 3.10–3.14 on verified hosted Windows, Linux and macOS runners.
2. All 15 OS/Python cells run focused compatibility tests and a platform probe that validates CPython, OS family, Python minor, pointer width and base runtime dependencies.
3. Every matrix cell builds a wheel from the exact candidate source and installs it into a clean virtual environment.
4. Clean-wheel verification removes source-path environment overrides, runs from a temporary working directory and proves `swirengine` imports outside the development checkout.
5. Every clean-wheel cell runs maintained headless 2D and 3D fixtures from the installed artifact rather than the editable source tree.
6. Windows x86-64 CPython 3.14 uses the dedicated native-bundled ModernGL/glcontext wheel path and verifies that the vendored renderer modules are imported from the installed package.
7. Linux/macOS CPython 3.14 pass through normal dependency resolution; unsupported combinations are removed rather than bypassed.
8. Documentation explicitly excludes unverified 32-bit, PyPy, free-threaded Python and unverified architecture claims, and keeps optional extras separate from the base-engine matrix.
9. Published 1.5.0 package metadata stays frozen, including its historical project URLs, until the final verified 2.0 release step.
10. Platform Matrix 2.0 plus full repository CI, locked 1.4/1.5 hardening, source checkpoints 1.6–1.9 and Desktop Export pass on the exact implementation head.

## Milestone 5 verified evidence

Implementation head `d312225a9540e4ced797c0aca7d95aeea370a404` passed every triggered workflow before this closeout
was marked. The dedicated Platform Matrix 2.0 run completed all **15/15** Windows/Linux/macOS × CPython
3.10–3.14 cells successfully. Each cell passed focused compatibility/matrix tests, source-platform probing,
wheel construction, isolated clean-wheel installation, headless 2D/3D runtime verification, strict Ruff and
bytecode compilation. The Windows CPython 3.14 cell additionally built and validated the dedicated
`cp314-cp314-win_amd64` SwirEngine wheel with bundled renderer-native modules.

The same exact implementation head also passed full repository CI, locked 1.4/1.5 hardening, source
checkpoints 1.6–1.9 and Desktop Export. The verified claim remains intentionally narrow: the base engine is
covered only on the 64-bit hosted runner architectures used by the gate; 32-bit Python, PyPy, free-threaded
CPython and unverified CPU architectures remain outside the claim, and optional extras require separate
evidence. Milestone 5 is therefore verified at **5/10 = 50.0%**. Release readiness remains separate; this
closeout head must re-pass its triggered matrix before merge.

## Milestone 6 verification contract

Milestone 6 is complete only when the exact implementation head proves all of the following:

1. Maintained 2D, 3D and multiplayer fixtures are prepared as isolated production projects through the existing creator workflow rather than a parallel demo-only path.
2. Every fixture validates version-controlled semantic input actions, shipping settings/defaults, save/profile policy, scene packages and content build graphs before staging.
3. Representative UI behavior uses real `UIButton`/`UIFocusManager` focus, navigation and activation together with player input overrides instead of metadata-only assertions.
4. Every fixture runs its source entrypoint and the staged/exported entrypoint successfully from isolated working directories.
5. Player-local settings/save/profile data remain outside the redistributable project tree while version-controlled defaults remain under project `config/`.
6. Runtime diagnostics are captured through the bounded privacy-safe diagnostics contract, redact secret/path-bearing data, survive JSON roundtrip and produce deterministic SHA-256 evidence.
7. Scene/content/input/settings/game-state/diagnostics/export/fixture fingerprints are validated as SHA-256 evidence and remain portable across isolated roots.
8. Failure probes reject a missing declared gameplay scene, a missing required asset and a missing project entrypoint before a successful shipping result can be reported.
9. The dedicated Real-Game Shipping 2.0 workflow passes on Python 3.10, 3.13 and 3.14 with focused fixture/failure/UI/diagnostic tests, Ruff and bytecode compilation.
10. Full repository CI, locked 1.4/1.5 hardening, source checkpoints 1.6–1.9 and Desktop Export pass on the exact implementation head.

## Milestone 6 verified evidence

Implementation head `64e00a542d5d942f1be8afdd397dbbbdaf3f3243` passed every triggered workflow before this closeout
was marked. The dedicated Real-Game Shipping 2.0 workflow passed on Python 3.10, 3.13 and 3.14, exercising
the maintained 2D, 3D and multiplayer fixtures through isolated project preparation, semantic input/UI,
settings and save/profile boundaries, scene/content validation, privacy-safe runtime diagnostics, deterministic
export staging, source/staged runtime entrypoints and deliberate failure probes.

The same exact implementation head also passed full repository CI, locked 1.4/1.5 hardening, source
checkpoints 1.6–1.9 and Desktop Export. The gate reuses production systems rather than adding demo-only
shipping shortcuts, keeps player-local data outside redistributable content and preserves the public package
version at 1.5.0. Milestone 6 is therefore verified at **6/10 = 60.0%**. Release readiness remains separate;
this closeout head must re-pass its triggered matrix before merge.

## Milestone 7 verification contract

Milestone 7 is complete only when the exact implementation head proves all of the following:

1. Exact candidate source builds one wheel and one sdist and both pass metadata/inventory validation before installation.
2. Archive validation rejects traversal, absolute or drive-qualified paths, case-folded duplicates, repository/build-state leakage and unsupported link/device entries.
3. Archive inventory is bounded to 50,000 members, 64 MiB per member and 256 MiB total uncompressed data.
4. Wheel and sdist install independently into fresh virtual environments with `PYTHONPATH`/`PYTHONHOME` stripped, user site disabled and import provenance outside the checkout.
5. Maintained 2D, 3D and multiplayer fixtures execute from both clean artifact installs outside the development checkout.
6. Host-native packaged-game verification builds from the clean wheel, validates its plan/manifest and executes its runtime marker on Windows, Linux and macOS.
7. Packaging remains host-native only and does not imply unsupported cross-compilation.
8. Package/module version remains 1.5.0 and no tag, GitHub Release or PyPI publication occurs.
9. Packaging Shipping 2.0 stays active for roadmap/README/progress closeout changes and verifies deterministic SVG generation plus presentation regressions.
10. Full repository CI, locked 1.4/1.5 hardening, source checkpoints 1.6–1.9 and Desktop Export pass on the exact implementation head.

## Milestone 7 verified evidence

Hardened implementation head `03aaef751260fc9de0c1a031f1f93b29fdd2c10c` passed every triggered
workflow before this closeout was marked. Packaging Shipping 2.0 passed on Windows, Linux and macOS with
CPython 3.13, including focused archive-safety/progress tests, deterministic SVG checks, exact-source wheel
and sdist builds, Twine metadata validation, isolated clean installs, maintained 2D/3D/multiplayer fixture
execution and host-native packaged-game build/manifest/runtime verification.

The same exact head passed full repository CI, locked 1.4/1.5 hardening, source checkpoints 1.6–1.9 and
Desktop Export. The archive gate now rejects drive-qualified paths and wheel symlinks in addition to
traversal, duplicate and sdist special entries, and it bounds archive inventory before clean installation.
Milestone 7 is therefore verified at **7/10 = 70.0%**. Release readiness remains separate; this closeout
head must re-pass its triggered matrix before merge.

## Milestone 8 verification contract

Milestone 8 is complete only when the exact implementation head proves all of the following:

1. The evidence contract names a bounded deterministic workload set spanning runtime scheduling, creator authoring, multiplayer replication, renderer-resource lifecycle, world streaming and production 2D/3D scalability.
2. Existing benchmark time budgets are parsed from their source scripts and must exactly match the locked contract; the evidence gate may not silently loosen those thresholds.
3. Runtime evidence records the exact commit, Python implementation/version, OS, architecture and hosted-runner context together with each command and bounded output.
4. The reference harness executes every selected workload with deterministic hash seeding, explicit timeout and an expected success marker while preserving each workload's own correctness invariants.
5. Shared-CI wall-clock observations are explicitly regression evidence rather than FPS, latency, memory or superiority marketing claims.
6. Cross-engine runtime ranking remains disabled until an identical maintained workload, rendering/content setup, dependency set and platform/runtime context exists for every compared engine.
7. The competitive workflow audit uses dated official documentation sources for Arcade, Panda3D and Ursina, records only positive reproducible facts and never infers that an unlisted capability is absent.
8. SwirEngine creator/shipping evidence points to the already verified project, workflow, real-game and packaging gates instead of inventing a synthetic productivity score.
9. The dedicated Performance Evidence 2.0 workflow passes metadata/tests/Ruff/compile on Python 3.10, 3.13 and 3.14 and uploads one contextual Ubuntu 24.04 / Python 3.13 evidence artifact.
10. Full repository CI, locked 1.4/1.5 hardening, source checkpoints 1.6–1.9 and Desktop Export pass on the exact implementation head with package/module metadata still frozen at 1.5.0.

## Milestone 8 verified evidence

Hardened implementation head `c810888b28fcc773429778e0bac7ac5d49ee4275` passed every triggered
workflow before this closeout was marked. Performance Evidence 2.0 passed its Python 3.10, 3.13 and 3.14
contract jobs plus the Ubuntu 24.04 / Python 3.13 reference-evidence harness and artifact upload. The gate
locks existing benchmark budgets to their source constants, records contextual observations without
committing a runner-dependent score and explicitly blocks unsupported cross-engine runtime ranking.

The same exact head passed full repository CI, locked 1.4/1.5 hardening, source checkpoints 1.6–1.9 and
Desktop Export. The competitive quality audit cites dated official documentation for Arcade, Panda3D and
Ursina while limiting claims to reproducible workflow facts; it makes no cross-engine FPS/latency/memory or
superiority claim. Milestone 8 is therefore verified at **8/10 = 80.0%**. Release readiness remains separate;
this closeout head must re-pass its triggered matrix before merge.

## Milestone 9 verification contract

Milestone 9 is complete only when the exact implementation head proves all of the following:

1. Strict staged-export verification checks the canonical `swir-export.json` inventory and SHA-256 map without executing the game or build tool.
2. Missing, tampered, unexpected, symlinked, unsafe, duplicate or case-colliding staged paths fail deterministically instead of being accepted as successful output.
3. Generated native build inputs participate in a deterministic build identity together with target, entrypoint, application identity, packaging metadata and declared staged content.
4. `swir-build-integrity.json` records a reproducible integrity seal and re-verification rejects stale or tampered staged bytes.
5. Post-build verification permits only explicitly recognized native build outputs while keeping the declared staged-content boundary strict.
6. Support-bundle audit accepts only generated `bundle.json` and `report.json`, enforces bounded payloads, safe ZIP paths and exact report hash/fingerprint integrity.
7. Privacy declarations keep automatic environment, argv, arbitrary user-file and traceback-source capture disabled; secret-like data and absolute trace paths remain redacted/sanitized.
8. Support evidence can be bound to an expected verified build identity without automatically collecting private process state or user files.
9. The dedicated Release Safety 2.0 workflow passes on Python 3.10, 3.13 and 3.14 with focused regressions, deterministic failure injection, Ruff and bytecode compilation.
10. Full repository CI, locked 1.4/1.5 hardening, source checkpoints 1.6–1.9, representative game validations and Desktop Export pass on the exact implementation head.

## Milestone 9 verified evidence

Hardened implementation head `70788364ba14ca69a6658d11596bdc7ea0797eb5` passed every triggered
workflow before this closeout was marked. Release Safety 2.0 passed its Python 3.10, 3.13 and 3.14 jobs,
including staged-export integrity, deterministic build identity/seal verification, privacy-safe support-bundle
auditing, deliberate tamper/injection rejection, strict Ruff and bytecode compilation.

The same exact head passed full repository CI, locked 1.4/1.5 hardening, source checkpoints 1.6–1.9,
Game Demos, Demo Game 3D, Neon Snake 3D and Desktop Export. The integrity seal is evidence rather than a
publisher code-signature claim, and support-bundle validation preserves the existing opt-in privacy model.
Milestone 9 is therefore verified at **9/10 = 90.0%**. Release readiness remains separate; this closeout
head must re-pass its triggered matrix before merge.

## Milestone 10 release-prep evidence

Preflight implementation head `a7bfc9715d04f1e0f105e3fa5eba898e0ccbfd4b` passed every triggered
pre-publication workflow before 2.0.0 metadata was armed: Final Release Gate 2.0, full CI, Public API 2.0,
Platform Matrix 2.0, Packaging Shipping 2.0, Desktop Export, source checkpoints 1.6–1.9 and locked 1.4/1.5
hardening all completed successfully. That green preflight authorizes this separate 10/10 release-prep
candidate with package/module metadata set to **2.0.0**.

This checkbox records completion of the named **source roadmap scope**, not a claim that SwirEngine 2.0 is
already public. The exact 2.0.0 finalization head must now re-pass the complete matrix before merge. Only
after that may the immutable `v2.0.0` tag, guarded GitHub Release/Trusted Publishing workflow and fresh
public PyPI installation verification run. The post-release architecture/API/runtime/packaging audit begins
immediately after successful public verification.

## Historical handoff

SwirEngine 1.9 completed its source-only production/shipping checkpoint at 10/10. Its archived evidence
remains in [`ROADMAP_1_9.md`](ROADMAP_1_9.md) and
[`docs/SWIRENGINE_2_0_READINESS_AUDIT.md`](docs/SWIRENGINE_2_0_READINESS_AUDIT.md). This 2.0 roadmap
supersedes 1.9 only as the **active development measurement**, not as a rewrite of historical evidence.