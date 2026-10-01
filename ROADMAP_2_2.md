<!-- SWIR-PROGRESS-SVG-PRO:v1 -->

# SwirEngine 2.2 — Production Tools & Visual Creation Roadmap

<img width="100%" src="assets/readme/progress-mini.svg" alt="SwirEngine 2.2 Production Tools and Visual Creation roadmap progress" />

SwirEngine 2.2 starts after the public SwirEngine 2.1.0 creator-workflow release. The target is a finite production-tools release: creators should be able to author more of a complete 2D/3D/multiplayer game visually while the generated data remains backed by shipping runtime systems.

Current verified progress: 8/10 milestones = 80.0%.

## Product rules

- The public SwirEngine 2.1.0 release and tag remain immutable.
- 2.2 progress advances only after exact-head acceptance evidence for a complete milestone.
- Visual tools must serialize portable project data and round-trip through runtime APIs; editor-only mock state does not count.
- Representative 2D, 3D and multiplayer fixtures remain the end-to-end quality gate.
- Performance claims require reproducible evidence; no invented FPS or cross-engine superiority claims.
- The README keeps exactly one deterministic PyPI-safe ASCII progress block sourced from this roadmap.

## Milestones

- [x] **1. Material/Shader authoring foundation.** Add deterministic project material assets, runtime-backed PBR material round-trip, safe shader variant authoring, asset validation, project-session dirty/save/reopen integration and focused regression coverage.
- [x] **2. Material/Shader Editor and live preview.** Add creator-facing material/shader panels, texture/uniform/hook editing, presets, validation diagnostics and a live preview path using the shipping renderer.
- [x] **3. Visual Scripting / Node Graph foundation.** Add a deterministic node-graph asset model, typed pins, validated graph compilation/execution and editor authoring for gameplay logic without weakening the Python scripting path.
- [x] **4. World/Terrain authoring.** Integrate terrain sculpt/paint data, foliage placement, LOD controls and world-streaming authoring with large-world runtime validation.
- [x] **5. Animation State Machine + Blend Tree Editor.** Add visual state/transition authoring, blend trees, parameter inspection and runtime-backed preview/debugging over the shipping animation systems.
- [x] **6. Particle/VFX Editor.** Add visual emitter/effect authoring for CPU/GPU particle systems, deterministic presets, preview controls and bounded runtime diagnostics.
- [x] **7. Lighting, Environment and Post-FX authoring.** Add creator controls for lights, sky/environment, shadows, tone mapping and post-processing with scene persistence and live renderer validation.
- [x] **8. UI Designer 2.2.** Add responsive anchors/containers, reusable styles, interaction states and UI animation authoring while preserving keyboard/gamepad focus/navigation behavior.
- [ ] **9. Multiplayer Debugger + Editor Extension SDK.** Add replication/session inspection, latency/debug views and a bounded plugin API for extending SwirEditor without bypassing project/runtime safety contracts.
- [ ] **10. Production acceptance and 2.2 release readiness.** Drive representative 2D, 3D and multiplayer projects through authoring, profiling, build/export and staged runtime; requalify supported CPython/platform packaging, clean installs, performance/safety evidence, checksums/provenance and the guarded release gate.

## Milestone 1 acceptance gate

Milestone 1 may be checked only when the exact implementation head proves all of the following:

1. Material assets save/load deterministically under the project root.
2. PBR fields round-trip into the shipping `Material3D` runtime representation.
3. Optional custom shader variants use the engine-owned safe shader template and reject unsafe hooks/defines/uniforms.
4. Texture references cannot escape the project `assets/` directory and missing assets are surfaced explicitly.
5. SwirEditor integrated project sessions mark material edits dirty, save them with the project and reopen them without data loss.
6. Focused tests, the progress generator/check and the normal exact-head repository matrix are green.

Milestone 1 accepted on 2026-09-23 after PR #219 exact head `15c17b642cc38a196bd9d21dc9919e146159644f` completed the full pull-request workflow matrix green and post-merge `main` commit `980ad5e3e092c37b099b671b1475d5140d9bfdfc` completed its triggered workflow set without failures.

## Milestone 2 acceptance gate

Milestone 2 may be checked only when the exact implementation head proves all of the following:

1. Material/shader authoring is available through the unified SwirEditor creator shell rather than a disconnected editor-only prototype.
2. Presets and creator-facing editing cover runtime-backed surface fields, texture slots, safe shader defines, hooks and uniforms with actionable validation.
3. The live preview path renders through the shipping 3D runtime (`Mesh3D` / `ShaderMesh3D`) and fails closed when renderer prerequisites or material assets are unavailable.
4. Material edits reuse the deterministic Milestone 1 project asset model and preserve dirty/save/reopen behavior.
5. Focused controller/runtime integration regressions, CLI compatibility coverage, the progress contract and the normal exact-head repository matrix are green.
6. Post-merge `main` completes its triggered workflow set without failures before the roadmap counter advances.

Milestone 2 accepted on 2026-09-23 after PR #221 exact head `8f5848608419dd69903bf4d1cc2277275ca262d7` completed all 20 triggered pull-request workflows successfully. The accepted implementation merged to `main` as `117d9749000730a398b033b3579e20c7c39e88d8`, and all 12 triggered post-merge workflow runs completed successfully before this acceptance record advanced the roadmap to 2/10.

## Milestone 3 acceptance gate

Milestone 3 may be checked only when the exact implementation head proves all of the following:

1. `.swirgraph` assets have a deterministic canonical project representation and safe project-scoped round-trip under `assets/graphs`.
2. Node graphs provide typed pins plus structural/type validation before bounded compilation and execution.
3. Visual graph authoring is integrated into the unified SwirEditor creator shell with creator-facing canvas, compile and preview workflows rather than a disconnected prototype.
4. Integrated project sessions include graph edits in dirty/save/reopen behavior without weakening the Python scripting path or handler bridge.
5. Focused runtime/editor/persistence/security regressions, the progress contract and the normal exact-head repository matrix are green.
6. Post-merge `main` completes its triggered workflow set without failures before the roadmap counter advances.

Milestone 3 accepted on 2026-09-23 after PR #223 exact head `545913c5a6fba16336366d9ac62c8f23c328488e` completed all 23 triggered pull-request workflows successfully. The accepted implementation merged to `main` as `566d3ca2207580f94d175529b5d6774c5da27a66`, and all 12 triggered post-merge workflow runs completed successfully before this acceptance record advanced the roadmap to 3/10.

## Milestone 4 acceptance gate

Milestone 4 may be checked only when the exact implementation head proves all of the following:

1. Terrain sculpting and normalized material painting serialize through a deterministic, versioned `.swirterrain` project asset.
2. Foliage placement remains project-relative and authored LOD/world-streaming controls round-trip into shipping `HeightmapTerrain`/`LargeWorld` runtime APIs.
3. Sparse sculpt undo/redo and dirty-chunk tracking keep editor rebuild work bounded to changed terrain regions.
4. Project-scoped save/load is contained beneath `assets/terrain`, rejects traversal/invalid extensions and reopens without canonical data loss.
5. A creator-facing terrain editor session provides dirty/save/reload and runtime-preview behavior over the same shipping terrain runtime rather than disconnected editor-only state.
6. Focused authoring/persistence/security/runtime regressions, representative fixtures, the progress contract and the normal exact-head repository matrix are green; post-merge `main` must also finish green before the roadmap counter advances.

### M4 implementation and acceptance evidence

- [x] Height/sculpt authoring and dirty-chunk tracking.
- [x] Material paint layers and normalized splat weights.
- [x] Project-relative foliage plus runtime LOD/streaming bridge.
- [x] Sparse sculpt undo/redo and deterministic terrain payloads.
- [x] Project-scoped `.swirterrain` save/load with traversal rejection.
- [x] Editor document dirty/save/reload and shipping-runtime preview integration.
- [x] Full exact-head PR matrix and post-merge `main` acceptance evidence.

Milestone 4 accepted on 2026-09-24 after PR #225 exact head `551994894c1fcdbbecdea5dae3f2ea35b2be5d57` completed all 24 triggered pull-request workflows successfully. The accepted implementation merged to `main` as `71201fb5facb2774ec2e9bcf166f0166a3a71919`, and all 12 triggered post-merge workflow runs completed successfully before this acceptance record advanced the roadmap to 4/10.

## Milestone 5 acceptance gate

Milestone 5 may be checked only when the exact implementation head proves all of the following:

1. `.swiranimgraph` assets provide deterministic, project-scoped state/transition/parameter/blend-tree authoring with persistent creator node positions and safe reopen behavior.
2. State-machine execution, conditions, triggers, exit time, cross-fades and synchronized 1D blend trees run through the shipping `Skeleton3D` / `SkeletalAnimationClip3D` animation systems rather than an editor-only simulator.
3. The unified SwirEditor exposes creator-facing state graph, transition editing, parameter inspection and preview/debug controls over that same runtime-backed asset model.
4. Rig and clip source references persist beside the graph, resolve through the production project-relative `.gltf` / `.glb` resolver, remain confined to the open project, reject ambiguous/invalid resources and invalidate stale cached runtime objects when the source fingerprint changes.
5. A representative source-only Walk/Run/Jump fixture saves and reopens creator resources, exercises locomotion blending plus a trigger transition, and observes the sampled shipping skeletal pose through the editor preview path.
6. Focused animation/editor/persistence/security/runtime regressions, the deterministic progress contract and the normal exact-head repository matrix are green; post-merge `main` must also complete its triggered workflow set without failures before the roadmap counter advances.

### M5 implementation and acceptance evidence

- [x] Runtime skeletal state machine, conditions/triggers, cross-fades and synchronized 1D blend trees.
- [x] Deterministic `.swiranimgraph` creator asset plus project-scoped persistence.
- [x] Visual SwirEditor state/transition/parameter authoring and runtime preview/debugging.
- [x] Persistent rig/clip resource references with stale-binding protection and legacy graph compatibility.
- [x] Production project-relative glTF/GLB resolver with confinement and source-fingerprint cache invalidation.
- [x] Source-only Walk/Run/Jump save/reopen/runtime acceptance fixture.
- [x] Full exact-head PR matrix and post-merge `main` acceptance evidence.

Milestone 5 accepted on 2026-09-24 after PRs #227–#231 delivered the integrated runtime and creator workflow. Final PR #231 exact head `ac30cb0149099fce7c4eebc9a7cb9f7ba6ebb495` completed all 23 triggered pull-request workflows successfully. The accepted implementation merged to `main` as `8fb851bd6679671d66198721f2a5a535df94c942`, and all 12 triggered post-merge workflow runs completed successfully before this acceptance record advanced the roadmap to 5/10.


## Milestone 6 acceptance gate

Milestone 6 may be checked only when the exact implementation head proves all of the following:

1. Deterministic project VFX authoring round-trips creator effects without data loss and maps CPU 2D / GPU 3D settings onto the shipping particle runtimes.
2. The unified SwirEditor exposes creator-facing presets, emitter controls and runtime-backed preview controls for start, pause, bounded stepping, burst and clear.
3. Project texture references remain confined beneath the open project `assets/` directory; missing, invalid and escaping resources fail closed with actionable diagnostics.
4. Runtime diagnostics expose bounded particle capacity/work information without per-frame unbounded editor catch-up or fabricated performance claims.
5. Representative 2D and 3D source-only fixtures save/reopen authored effects and exercise the same runtime-backed preview path used by the editor.
6. Focused VFX/editor/persistence/security regressions, the deterministic progress contract and the normal exact-head repository matrix are green; post-merge `main` must also complete its triggered workflow set without failures before the roadmap counter advances.

### M6 implementation and acceptance evidence

- [x] Deterministic `config/vfx.json` authoring and shipping CPU2D/GPU3D runtime mapping.
- [x] Unified creator presets, emitter controls and start/pause/bounded-step/burst/clear preview.
- [x] Project-confined texture validation including missing, absolute, drive-relative, nested-symlink and live-disappearance cases.
- [x] Bounded runtime diagnostics and strict capacity/seed/trail/burst validation.
- [x] Representative 2D/3D save/reopen, pause/restart, clear/reuse and rejected-reload recovery fixtures.
- [x] Full exact-head PR matrix and post-merge `main` acceptance evidence.

Milestone 6 accepted on 2026-10-01 after PR #233 exact head `110ac0f948ffa125c943e6192b1ce9456689cf80` completed all 26 triggered pull-request workflows successfully. The implementation merged normally to `main` as `2437d641fed0aa636a9bc46b07036893daa67afd`; both commits share tree `33c8f1792aa4b94cbe5bb53cb8d429425ea26576`. All 12 associated post-merge workflow runs completed successfully before this acceptance record advanced the roadmap to 6/10.

Post-merge evidence includes CI `36835339285`, Desktop Export `36835339254`, real OpenGL/packaged Neon Snake `36835339398`, and Showcase + Hardening `36835339320`. The latter initially failed during Python 3.10 build-dependency resolution (`hatchling>=1.25` unavailable from the index at that attempt); one failed-job rerun passed without any code, dependency or gate change, including clean wheel installation, real OpenGL 2D/3D execution and Windows one-file runtime probes. The failed attempt remains in Actions history; only the completed successful final attempt is acceptance evidence.

The VFX GPU fixture validates the shipping CPU-side particle scheduling bridge; no new physical-GPU performance claim or public 2.2 release is implied.

## Milestone 7 acceptance gate

Milestone 7 may be checked only when the exact implementation head proves all of the following:

1. Scene-keyed lighting data round-trips deterministically through project save/reopen and maps directional, point and spot lights onto shipping renderer systems.
2. The unified SwirEditor exposes lights, sky/environment, shadows, SSAO/bloom, tone mapping and color-grading controls with scene-safe selection and validation.
3. Live preview uses an isolated owned production renderer/context, remains bounded, preserves authoring state and fails closed when project resources change or disappear.
4. Lighting libraries, bound scenes and skybox assets remain project-confined, validate before export replacement and survive default export relocation with manifest hashes.
5. Representative 2D and 3D projects render reopened profiles and live editor changes through required real EGL paths, including an isolated installed-wheel relocated-runtime gate.
6. Focused lighting/editor/persistence/security/export regressions, native Tk lifecycle coverage, the deterministic progress contract and the normal exact-head repository matrix are green; post-merge `main` must also complete its triggered workflow set without failures before the roadmap counter advances.

### M7 implementation and acceptance evidence

- [x] Deterministic scene-keyed `config/lighting.json` authoring and shipping light/environment/post-FX runtime mapping.
- [x] Unified creator tabs for lights, environment, shadows, effects and color grading.
- [x] Isolated bounded live preview with pause/step/stop, scene-switch cleanup and live asset revalidation.
- [x] Project-confined scene/skybox validation plus fail-closed default export and relocation.
- [x] Representative 2D/3D save/reopen, real EGL, native Tk and isolated installed-wheel shipping qualification.
- [x] Full exact-head PR matrix and post-merge `main` acceptance evidence.

Milestone 7 accepted on 2026-10-01 after PR #235 exact head `89c4a890f098b3780b0ef3a86b4629ded8be6898` completed all 33 exact-SHA Actions workflows successfully with 153 successful PR check runs. The implementation merged normally to `main` as `f694768a176d693f1638d18240346e701f8fc3ab`; both commits share tree `a2a54049e4ed39d4057496ab410c485d3cc50a76`. All 18 associated post-merge workflow runs and all 103 check runs completed successfully before this acceptance record advanced the roadmap to 7/10.

Post-merge evidence includes focused Editor Lighting run `36877834624`, CI, Desktop Export, packaging, real-game, source-checkpoint and final release-gate workflows on the exact merge SHA. Required real EGL saved-profile/live-preview tests, native Tk lifecycle coverage and isolated installed-wheel relocated 2D/3D rendering all completed successfully. This is source-development acceptance only; no new physical-GPU performance claim or public 2.2 release is implied. Milestone 8 is the next open production-tools target.

## Milestone 8 acceptance gate

Milestone 8 may be checked only when the exact implementation head proves all of the following:

1. A deterministic, versioned `config/ui-designer.json` document round-trips responsive widget hierarchies, reusable themes/styles and bounded UI animation tracks without changing the legacy `config/ui-hud.json` contract.
2. Responsive flow containers plus top-level viewport and nested parent anchors build the shipping `UIToolkit` tree while preserving keyboard, pointer and gamepad focus/navigation behavior.
3. The unified SwirEditor exposes creator-facing widget, container, style, interaction-state and animation controls with dirty/save/reopen behavior and an isolated runtime-backed preview.
4. Action labels remain portable data, require explicit runtime handlers and stay inert in editor/export validation; invalid bindings, malformed documents, traversal and symlink escapes fail closed without replacing live authoring state or previous export output.
5. Default Build/Export Wizard staging preserves the canonical UI document and manifest hash through relocation; an isolated installed wheel reopens it and exercises responsive layout, focus/navigation, animation sampling and a real software-EGL frame.
6. Focused UI Designer, legacy UI/HUD, editor session, export, native Tk, persistence and safety regressions, the deterministic progress contract and the normal exact-head repository matrix are green; post-merge `main` must also complete its triggered workflow set without failures before the roadmap counter advances.

### M8 implementation and acceptance evidence

- [x] Deterministic project-confined `config/ui-designer.json` authoring with reusable themes, styles, responsive widget hierarchies and bounded animation tracks.
- [x] Shipping `UIToolkit` runtime mapping for flow containers, viewport/parent anchors, interaction states, actions, input focus and animation playback.
- [x] Unified SwirEditor creator controls with dirty/save/reopen behavior and isolated runtime-backed preview lifecycle.
- [x] Explicit portable action bindings, transactional reload/save and fail-closed malformed, traversal, directory and symlink handling.
- [x] Default Wizard export, manifest hashing, relocation, isolated installed-wheel runtime, real software EGL and native Tk qualification.
- [x] Full exact-head PR matrix and post-merge `main` acceptance evidence.

Milestone 8 accepted on 2026-10-01 after PR #237 exact head `81136e3ec1599cbc8553cdc3afe7b82f4e9efb34` completed all 41 exact-SHA Actions workflows successfully with 173 successful PR check runs. The implementation merged normally to `main` as `e4a916f66ef7329e88acb675995c9751870c3b5d`; both commits share tree `539c1d5e894929a69cf2b0554b2f235fec2af552`. All 19 associated post-merge workflow runs and all 107 final check runs completed successfully before this acceptance record advanced the roadmap to 8/10.

The post-merge Lighting, UI Designer and Real-Game jobs each encountered an infrastructure-only package-install stall or timeout on their first attempt. The affected jobs were rerun on the unchanged exact merge SHA and completed successfully without any code, dependency or gate change. Required Python 3.10/3.13/3.14 UI contracts, default-export relocation, installed-wheel execution, real software EGL output and native Tk lifecycle validation all passed. This is source-development acceptance only; no public 2.2 release or physical-GPU performance claim is implied. Milestone 9 is the next open production-tools target.

## Milestone 9 acceptance gate

Milestone 9 may be checked only when the exact implementation head proves all of the following:

1. A bounded ping/pong protocol measures real monotonic round-trip time, rejects invalid, replayed, mismatched and late packets, and never labels configured transport impairment or QoS delay as measured latency.
2. The debugger reads production multiplayer session, replication, profiler and transport state through privacy-safe aliases and allowlisted aggregates, with hard client, channel, counter, sample, event and 2 MiB capture limits and no raw identifiers, tokens, payloads, addresses, paths or provider errors.
3. The SwirEditor debugger controller remains transient and clean, supports explicit attach/detach/sample/RTT/capture operations, releases references on close and confines atomic capture export below the project `.swir` directory without joining normal save/reopen state.
4. The Editor Extension SDK is an explicit capability-gated boundary for trusted installed Python extensions, not an operating-system sandbox, and exposes only bounded immutable declarative panels/actions without discovery, autoload, `PluginManager` bridging or raw app/session/root/scene/renderer objects.
5. The unified dynamic Tk host renders deterministic extension snapshots, sanitizes lifecycle and callback failures, cleans up on close and exposes the multiplayer debugger through a built-in restricted adapter rather than passing the production session to extension code.
6. Project and desktop export exclude `.swir` editor state for broad, direct and case-insensitive include shapes; traversal, entrypoint/icon aliases, symlinks and unsafe source changes fail before previous output cleanup, while a relocated installed runtime still exercises privacy-safe debugger and RTT behavior.
7. Focused M9, legacy multiplayer, M8 UI, native Tk, real localhost RTT, installed-runtime relocation, safety, progress, Ruff and compile gates plus the normal repository matrix are green for the exact PR head; after normal merge, every required workflow and check for the exact merged `main` SHA must also be green before the roadmap counter advances from 8/10.
