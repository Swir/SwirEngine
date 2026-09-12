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
`DirectionalLight3D`, `PointLight3D`, `SpotLight3D`, distance/cone attenuation, Phong
specular/shininess material controls and simultaneous multi-light forward rendering with
explicit per-type GPU budgets plus overflow diagnostics. glTF `metallicFactor` and
`roughnessFactor` now reach runtime `Material3D` and use a compatibility-preserving
metallic/roughness-to-Phong bridge so those PBR factors affect rendering instead of being
metadata-only.

Next: native Cook-Torrance metallic/roughness shading and `metallicRoughnessTexture`, then
skybox, shadows and post-processing.

## 0.5 - Architecture

Early foundation landed during 0.4.8-0.4.9: reusable deep-copy `Prefab` blueprints,
independent `PrefabInstance` graphs, per-instance overrides, filtered scene capture and direct
scene instantiation/removal helpers, plus versioned JSON scene/prefab serialization with a
safe allow-list codec registry, custom dataclass registration, cross-object reference
preservation and file helpers suitable for future editor/hot-reload workflows.

Next: components/ECS, serializer migrations, hot reload and plugin API.

## 0.6 - Tools

Visual editor, hierarchy/inspector, asset browser, console/profiler and scene gizmos.

## 0.7+ - Runtime and export

Networking, packaging profiles, Windows/Linux/macOS exporters, Android/Web research targets.

## 1.0

Stable documented API with editor, 2D/3D rendering, physics, audio, assets, scene/prefab
workflow, tests and release tooling.
