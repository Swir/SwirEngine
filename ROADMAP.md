# SwirEngine Roadmap

## 0.2 - Real 2D workflow — complete

Completed: textured sprites, alpha blending, texture cache, camera 2D, names/tags,
creator-friendly scene/input shortcuts, render layers, cached text rendering,
adjacent-texture GPU sprite batching and frame/render profiling.

## 0.3 - 2D gameplay systems — feature complete, hardening in progress

Completed: sprite sheets, named animation clips, asset manager, AABB box collisions,
collision layers/masks, one-shot keyboard and mouse input, tilemaps, JSON save data,
pooled particles, fixed-step arcade rigid-body physics, pluggable sound/music playback,
screen-space UI, labels, panels, buttons and progress bars.

Hardening completed so far: bounded dynamic-text cache, renderer statistics, frame profiler,
built-in debug overlay, sprite draw-call batching that preserves transparent render order,
deterministic asset scanning and creator-facing asset/alias diagnostics.

Remaining hardening: larger sample games and creator-facing API polish while 3D grows in parallel.

## 0.4 - Serious 3D — in progress

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
for a later transition to image-based lighting without breaking game code.

Next: true cubemap/image-based environment lighting, shadows and post-processing. Then harden
color-space/PBR fidelity and broaden glTF material coverage with normal, occlusion and emissive maps.

## 0.5 - Architecture

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
reloads without changing existing provider names or snapshot formats. `AssetManager` adds a
suffix-based loader registry, canonical-path runtime cache, watched asset invalidation, structured
reload results and invalidation callbacks. `RendererAssetBridge` connects those callbacks directly
to renderer GPU textures, releases stale ModernGL resources, automatically discovers 2D sprite
and 3D material textures in a scene and reuses the same deterministic polling pipeline.
`AudioEngine` can subscribe to that same asset invalidation stream, automatically watch active
audio files, restart looping sounds/music in place while preserving handle identity and volume,
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

Next: strengthen rollback guarantees for multi-domain restore, connect the editor workspace shell to
an actual interactive visual front-end and add scene transform gizmos plus console/profiler integration.

## 0.6 - Tools

Visual editor foundation now includes a shared project/workspace shell, hierarchy/inspector contract,
persistent panel layout and viewport preferences plus a GUI-agnostic asset browser data model. Next:
interactive visual front-end, console/profiler integration and scene transform gizmos.

## 0.7+ - Runtime and export

Networking, packaging profiles, Windows/Linux/macOS exporters, Android/Web research targets.

## 1.0

Stable documented API with editor, 2D/3D rendering, physics, audio, assets, scene/prefab
workflow, tests and release tooling.
