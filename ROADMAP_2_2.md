<!-- SWIR-PROGRESS-SVG-PRO:v1 -->

# SwirEngine 2.2 — Production Tools & Visual Creation Roadmap

<img width="100%" src="assets/readme/progress-mini.svg" alt="SwirEngine 2.2 Production Tools and Visual Creation roadmap progress" />

SwirEngine 2.2 starts after the public SwirEngine 2.1.0 creator-workflow release. The target is a finite production-tools release: creators should be able to author more of a complete 2D/3D/multiplayer game visually while the generated data remains backed by shipping runtime systems.

Current verified progress: 0/10 milestones = 0.0%.

## Product rules

- The public SwirEngine 2.1.0 release and tag remain immutable.
- 2.2 progress advances only after exact-head acceptance evidence for a complete milestone.
- Visual tools must serialize portable project data and round-trip through runtime APIs; editor-only mock state does not count.
- Representative 2D, 3D and multiplayer fixtures remain the end-to-end quality gate.
- Performance claims require reproducible evidence; no invented FPS or cross-engine superiority claims.
- The README keeps exactly one deterministic PyPI-safe ASCII progress block sourced from this roadmap.

## Milestones

- [ ] **1. Material/Shader authoring foundation.** Add deterministic project material assets, runtime-backed PBR material round-trip, safe shader variant authoring, asset validation, project-session dirty/save/reopen integration and focused regression coverage.
- [ ] **2. Material/Shader Editor and live preview.** Add creator-facing material/shader panels, texture/uniform/hook editing, presets, validation diagnostics and a live preview path using the shipping renderer.
- [ ] **3. Visual Scripting / Node Graph foundation.** Add a deterministic node-graph asset model, typed pins, validated graph compilation/execution and editor authoring for gameplay logic without weakening the Python scripting path.
- [ ] **4. World/Terrain authoring.** Integrate terrain sculpt/paint data, foliage placement, LOD controls and world-streaming authoring with large-world runtime validation.
- [ ] **5. Animation State Machine + Blend Tree Editor.** Add visual state/transition authoring, blend trees, parameter inspection and runtime-backed preview/debugging over the shipping animation systems.
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

Until that evidence is green, active 2.2 progress remains **0/10 = 0.0%**.
