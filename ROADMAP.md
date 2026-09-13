# SwirEngine Roadmap

<!-- SWIR-ROADMAP-STANDARD:v1 -->
<!-- ROADMAP-PROGRESS:START -->
<p align="center">
  <a href="https://github.com/Swir/SwirEngine/actions/workflows/ci.yml"><img alt="CI" src="https://github.com/Swir/SwirEngine/actions/workflows/ci.yml/badge.svg"></a>
  <img alt="Roadmap progress" src="https://img.shields.io/badge/ROADMAP-100.0%25-2ea043?style=for-the-badge">
  <img alt="Completed" src="https://img.shields.io/badge/DONE-31%2F31-1f6feb?style=for-the-badge">
  <img alt="Status" src="https://img.shields.io/badge/STATUS-COMPLETE-2ea043?style=for-the-badge">
</p>

## 📊 Overall progress

```text
████████████████████ 100.0%
```

| ✅ Completed | ⏳ Remaining | 📦 Total | 🎯 Progress |
|---:|---:|---:|---:|
| **31** | **0** | **31** | **100.0%** |

> **Progress rule:** the equal-weight deliverables below are the source of truth. Update `[x]/[ ]` first, then update badges, numbers, percentage and the 20-segment bar. Never estimate progress from version numbers, commit count or activity.

- [x] 0.2 real 2D workflow complete
- [x] 0.3 core 2D gameplay feature set complete
- [x] 0.3 hardening foundation: bounded text cache, stats, profiler, debug overlay, batching and deterministic asset diagnostics
- [x] 0.3 larger sample games and creator-facing API polish
- [x] 0.4 Camera3D, perspective/view matrices and local navigation
- [x] 0.4 MeshData/Mesh3D GPU caching and mesh statistics
- [x] 0.4 OBJ import with triangulation, normals and UV support
- [x] 0.4 glTF/GLB scene, hierarchy and base-color material loading
- [x] 0.4 multi-light Phong rendering
- [x] 0.4 Cook-Torrance metallic/roughness PBR
- [x] 0.4 Skybox3D and Environment3D baseline
- [x] 0.4 true cubemap / image-based environment lighting
- [x] 0.4 shadows
- [x] 0.4 post-processing
- [x] 0.4 color-space/PBR hardening plus normal, occlusion and emissive material maps
- [x] 0.5 prefab/instance and versioned scene/prefab serialization foundation
- [x] 0.5 ECS runtime, persistence and migrations
- [x] 0.5 plugin runtime, hot reload and state preservation/rollback foundation
- [x] 0.5 AssetManager plus renderer/audio live reload bridges
- [x] 0.5 LiveDevelopmentHub
- [x] 0.5 SceneInspector hierarchy, editing and unified undo/redo
- [x] 0.5 EditorProjectState / EditorWorkspace shell foundation
- [x] 0.5 stronger multi-domain rollback guarantees
- [x] 0.5 connect editor models to an actual interactive visual front-end
- [x] 0.6 editor asset browser
- [x] 0.6 editor console and profiler models
- [x] 0.6 transform gizmo foundation
- [x] 0.6 viewport picking and direct manipulation
- [x] 0.6 tighter editor/runtime integration
- [x] 0.7 networking, packaging profiles and desktop/mobile/web export targets
- [x] 1.0 stable documented API, tests and release tooling suitable for a first stable release
<!-- ROADMAP-PROGRESS:END -->

## 0.2 - Real 2D workflow — complete

Completed: textured sprites, alpha blending, texture cache, camera 2D, names/tags,
creator-friendly scene/input shortcuts, render layers, cached text rendering,
adjacent-texture GPU sprite batching and frame/render profiling.

## 0.3 - 2D gameplay systems — complete and hardened

Completed: sprite sheets, named animation clips, asset manager, AABB box collisions,
collision layers/masks, one-shot keyboard and mouse input, tilemaps, JSON save data,
pooled particles, fixed-step arcade rigid-body physics, pluggable sound/music playback,
screen-space UI, labels, panels, buttons and progress bars.

Hardening completed: bounded dynamic-text cache, renderer statistics, frame profiler,
built-in debug overlay, sprite draw-call batching that preserves transparent render order,
deterministic asset scanning and creator-facing asset/alias diagnostics. Two larger asset-free
sample games now exercise complete gameplay loops across input, UI, tags, collision logic,
progression, procedural spawning and scene cleanup. Additive `Scene.require(...)`,
`Scene.remove_many(...)` and `Scene.remove_tagged(...)` helpers round out common creator workflows
without changing existing lookup/removal semantics.

## 0.4 - Serious 3D — complete

Completed: real `Camera3D`, perspective/view matrices, local camera navigation, `MeshData`,
`Mesh3D`, lazy GPU mesh caching, mesh render statistics, Wavefront OBJ import with polygon
triangulation plus generated normals, optional UV channels, OBJ `vt` import, `Material3D`,
textured forward rendering with per-instance tinting, static glTF 2.0 mesh import, GLB 2.0
containers, binary chunks, default/custom scene selection, hierarchical node traversal, 4x4
node matrices, TRS/quaternion transforms, world-space normal transformation, mirrored-winding
preservation, glTF/GLB base-color material loading with per-primitive material boundaries,
`baseColorFactor`, external images, data-URI images and embedded GLB `bufferView` textures,
`DirectionalLight3D`, `PointLight3D`, `SpotLight3D`, distance/cone attenuation, legacy Phong
specular/shininess material controls and simultaneous multi-light forward rendering with
explicit per-type GPU budgets plus overflow diagnostics. Native Cook-Torrance
metallic/roughness shading is available for PBR materials, including glTF 2.0
`metallicFactor`, `roughnessFactor` and packed `metallicRoughnessTexture` support while the
legacy Phong path remains available for existing materials. `Skybox3D` adds camera-centered
panorama skies through the normal `Mesh3D` render/cache path, while `Environment3D` provides a
creator-facing sky/ground fill-light rig with install/remove lifecycle helpers and an API shaped
for a later transition to image-based lighting without breaking game code. PBR material fidelity
now also covers glTF `normalTexture`, `occlusionTexture`, `emissiveTexture`, emissive factors,
normal scale and occlusion strength. The forward PBR shader derives a tangent frame from position/
UV derivatives for tangent-space normal maps, applies AO to the ambient contribution, evaluates
emissive independently from scene lights, and performs sRGB decode/linear lighting/sRGB output for
base-color and emissive channels while keeping data textures in linear space. Renderer live reload
tracks every supported PBR texture channel. `PostProcessRenderer` now adds an optional off-screen
GPU resolve with ACES/Reinhard tone mapping, exposure/gamma control, contrast/saturation grading,
vignette and FXAA. `Game.configure_postprocess(...)` keeps that pass disabled by default so existing
projects retain their rendering behavior until creators opt in. `ImageBasedEnvironment3D` now reaches
the runtime PBR renderer through real GPU cubemap sampling: diffuse environment light uses the
low-frequency mip, specular reflections select mip LOD from material roughness, AO participates in the
environment contribution, cubemap resources are cached/released deterministically, and all six faces
participate in asset live reload. The cubemap/IBL types and helpers are also exposed through the public
package API. Directional shadows now complete the 0.4 renderer path with an opt-in reusable GPU depth
map, raw depth sampling, camera-focused orthographic light framing, configurable depth/normal bias and a
3x3 PCF resolve applied before additive IBL. `Game.configure_shadows(...)` keeps legacy rendering
unchanged until creators explicitly enable the pass.

## 0.5 - Architecture — complete for 1.0

Foundation landed during 0.4.8-0.4.22: reusable deep-copy `Prefab` blueprints,
independent `PrefabInstance` graphs, per-instance overrides, filtered scene capture and direct
scene instantiation/removal helpers, versioned JSON scene/prefab serialization with a safe
allow-list codec registry and cross-object reference preservation, a lightweight public
`Entity`/`ECSWorld` runtime with arbitrary Python components, filtered queries, snapshot rows,
deterministic prioritized systems and direct `Scene` integration, version-3 scene persistence
for ECS entity metadata/components with stable-ID restoration, automatic v1/v2 migrations and
cyclic entity/component reference graphs, plus a public plugin runtime with deterministic
dependency activation, lifecycle hooks and shared services. Module hot reload has an ordered
runtime-state registry, scene/ECS snapshot bridging, automatic state preservation and rollback
restoration so editor/game state can survive plugin code reloads. A dependency-free polling
file watcher and `PluginAutoReloader` connect source-file edits to state-preserving reload
transactions without background threads. Named state domains let editor/game subsystems own,
inspect, clear and selectively preserve independent state groups during manual or watcher-driven
reloads without changing existing provider names or snapshot formats. Atomic multi-provider restore
now pre-captures rollback baselines before any mutation and reverses every touched provider when a
restore callback fails, including partially-mutated failing providers; plugin reloads use that path
for multi-provider/domain preservation while legacy single-provider callback behavior remains stable.
`AssetManager` adds a suffix-based loader registry, canonical-path runtime cache, watched asset
invalidation, structured reload results and invalidation callbacks. `RendererAssetBridge` connects
those callbacks directly to renderer GPU textures, releases stale ModernGL resources, automatically
discovers 2D sprite and all supported 3D material textures in a scene and reuses the same deterministic
polling pipeline. `AudioEngine` can subscribe to that same asset invalidation stream, automatically watch
active audio files, restart looping sounds/music in place while preserving handle identity and volume,
optionally restart one-shots, stop deleted resources safely and expose structured reload diagnostics.
`LiveDevelopmentHub` now coordinates plugin reloads plus one shared asset poll and aggregates
plugin, asset, GPU-texture and audio events into one editor-facing `LiveDevelopmentResult` with
health/error summaries and lifecycle-safe subscription management. `SceneInspector` now adds a
GUI-agnostic hierarchy/inspector model spanning classic scene objects and ECS entities, runtime-stable
selection keys, searchable/tag-filterable hierarchy rows, immutable field snapshots and bounded
reversible property editing with undo/redo history. ECS component inspection/editing extends that
same contract to component public fields, with stable entity-anchored history and safe stale-component
detection during undo/redo. The editor hierarchy now also supports mixed object/entity parenting,
deterministic sibling ordering, indexed reparenting, depth/parent/order row metadata, cycle prevention
and automatic promotion of children when a parent disappears from the runtime scene. Property edits,
component edits, reparenting and sibling moves now share one chronological bounded undo/redo history,
with stale-target and stale-parent protection so failed structural rollback attempts leave history intact.
Portable `EditorHierarchyState` snapshots now persist parenting, sibling order and selection across scene
serialization/reload using scene-object indices and stable ECS IDs rather than process-local object keys;
restore pre-validates all references and can leave project loading out of the user's undo history.
`EditorProjectState` and `EditorWorkspace` now lift that foundation to project scope: per-scene hierarchy,
selection and viewport state, validated panel layout, JSON/file persistence, scene switching, hierarchy
filters and immutable `EditorShellFrame` snapshots are coordinated behind one GUI-agnostic visual-editor
shell contract. `EditorAssetBrowser` now provides the Assets-panel data model on top of `AssetManager`,
including deterministic type classification, folder discovery, search/filtering, stable selection,
alias/cache/loader metadata and missing-alias health without forcing asset contents into RAM/GPU memory.
`EditorConsole` and `EditorProfiler` now provide bounded, thread-safe log capture plus immutable runtime
profiling snapshots with filtering, logging integration, averages, peaks and frame-budget health for the
visual editor Console and Profiler panels. `EditorTransformGizmo` adds GUI-agnostic Move/Rotate/Scale
editing for the engine's existing 2D/3D transform conventions, integrates viewport snap preferences and
routes mutations through `SceneInspector` so transform edits participate in the same undo/redo history.
`EditorViewportController` now adds perspective screen-to-world rays, nearest visible `Mesh3D` picking,
selection synchronization and camera-plane pointer dragging that reuses the transform gizmo/history path.
`EditorFrontendController` now joins those models into one toolkit-neutral interactive frame contract, and
`TkEditorApp` provides the first dependency-free desktop visual editor with hierarchy search/selection,
inspector edits, shared Undo/Redo, gizmo/snap controls, Assets, Console and Profiler panels. The
`EditorRuntimeSession` establishes isolated Play/Edit synchronization by cloning the authored scene through
its configured serializer, running updates only against the preview copy, supporting pause/resume and
single-frame stepping, then discarding runtime mutations on Stop. `EditorPreviewSession` and
`RendererViewportBridge` now connect that isolated runtime to the active renderer framebuffer, and the Tk
front-end exposes Play/Pause/Stop/Step controls plus a live embedded RGB viewport while preserving Edit-mode
scene switching and authoring-state isolation.

## 0.6 - Tools — complete for 1.0

Visual editor foundation includes a shared project/workspace shell, hierarchy/inspector contract,
persistent panel layout and viewport preferences, a GUI-agnostic asset browser, reusable Console/
Profiler panel models, toolkit-independent scene Move/Rotate/Scale gizmos with snapping and undo/redo,
camera-aware 3D viewport picking/direct manipulation, and a real interactive Tk desktop front-end that
connects those models without adding a mandatory GUI dependency. Isolated `EditorRuntimeSession` Play/Edit
scene execution is integrated with `RendererViewportBridge` and `EditorPreviewSession`; the editor has
direct Play/Pause/Stop/Step controls and can embed live frames read from the renderer framebuffer.

## 0.7+ - Runtime and export — foundation complete

Completed: deterministic length-prefixed JSON networking primitives, incremental packet decoding,
non-blocking poll-driven TCP client/server peers, serializable packaging profiles and deterministic
project staging. Windows, Linux and macOS profiles expose ready-to-run PyInstaller build commands without
silently invoking third-party tooling; Android and Web are explicit experimental staging/research targets
with machine-readable export manifests. The `swirengine export` CLI exposes all targets through the same
profile/export pipeline.

## 1.0 - stable release complete

SwirEngine 1.0.0 defines the `swirengine.__all__` surface as the stable 1.x public API and documents its
semantic-versioning and deprecation policy in `docs/API_STABILITY.md`. Runtime and package metadata are
locked together by regression tests. CI verifies the engine across Windows, Linux and macOS on Python
3.10-3.13, while a dedicated packaging job builds wheel/sdist artifacts, validates metadata with Twine and
installs the built wheel in a clean environment before importing it. A tag-driven release workflow verifies
that `vX.Y.Z` matches package metadata before creating distribution artifacts and the GitHub Release.
