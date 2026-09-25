<!-- SWIR-PROGRESS-SVG-PRO:v1 -->

# SwirEngine 2.2 — Production Tools & Visual Creation Roadmap

<img width="100%" src="assets/readme/progress-mini.svg" alt="SwirEngine 2.2 Production Tools and Visual Creation roadmap progress" />

SwirEngine 2.2 starts after the public SwirEngine 2.1.0 creator-workflow release. The target is a finite production-tools release: creators should be able to author more of a complete 2D/3D/multiplayer game visually while the generated data remains backed by shipping runtime systems.

Current verified progress: 5/10 milestones = 50.0%.

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
- [ ] **6. Particle/VFX Editor.** Add visual emitter/effect authoring for CPU/GPU particle systems, deterministic presets, preview controls and bounded runtime diagnostics.
- [ ] **7. Lighting, Environment and Post-FX authoring.** Add creator controls for lights, sky/environment, shadows, tone mapping and post-processing with scene persistence and live renderer validation.
- [ ] **8. UI Designer 2.0.** Add responsive anchors/containers, reusable styles, interaction states and UI animation authoring while preserving keyboard/gamepad focus/navigation behavior.
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
