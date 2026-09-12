# Changelog

## 0.4.22 - 2026-09-12

Unified live-development diagnostics and polling update.

- added public `LiveDevelopmentHub` and immutable `LiveDevelopmentResult` APIs
- coordinate plugin source reloads plus one shared `AssetManager` polling transaction instead of letting renderer/audio tooling poll the same watcher independently
- aggregate plugin reloads, generic asset reloads, renderer GPU texture invalidations and audio restart/stop diagnostics into one editor-facing result
- added `changed`, `healthy`, `errors` and `event_count` summaries for console/editor status surfaces
- automatically synchronize renderer scene-texture watches and active audio watches before every development poll
- added lifecycle-safe `start()`, `stop()` and context-manager behavior that only tears down renderer/audio subscriptions activated by the hub itself
- validate renderer/audio integrations use the same `AssetManager`, preventing split invalidation graphs and hard-to-debug duplicate polling
- added optional transaction history plus coordinated subsystem-history clearing
- added regression coverage for shared polling, GPU/audio fan-out, ownership-safe lifecycle, error aggregation and idle-history behavior
- added a runnable `demo_live_development.py` example and advanced the 0.5 roadmap toward hierarchy/inspector and visual-editor tooling
- bumped package version to 0.4.22

## 0.4.21 - 2026-09-12

Skybox and environment-lighting foundation update.

- added public `Skybox3D`, `Environment3D` and `EnvironmentInstallation` APIs
- added inward-facing cube mesh generation with equirectangular panorama UV coordinates
- render skyboxes through the existing `Mesh3D` path so they reuse the current mesh/texture cache and live-asset invalidation architecture
- added camera-follow behavior so panorama skies remain centered around a moving `Camera3D`
- added an unlit skybox material configuration using ambient-only contribution for compatibility with the current forward renderer
- added a creator-facing sky/ground fill-light rig using two directional slots, leaving two directional-light slots available for authored sun/moon lights
- added explicit install/remove/follow lifecycle helpers for scene integration
- shaped the public environment API so a future cubemap/IBL backend can replace the current fill-light implementation without breaking game code
- added environment regression coverage and a runnable `demo_environment3d.py` example
- advanced the 0.4 roadmap toward true image-based lighting, shadows and post-processing
- bumped package version to 0.4.21

## 0.4.20 - 2026-09-12

Live audio asset-reload integration update.

- added public `AudioReloadEvent` diagnostics with restart, stop, skip and backend-error reporting
- added opt-in `AudioEngine.enable_live_reload(...)` and lifecycle controls using the shared `AssetManager` invalidation stream
- automatically watch active audio resources and newly started handles while live reload is enabled
- restart looping sounds and music in place after file edits while preserving `AudioHandle` identity, volume, loop state and music/sound category
- keep one-shot sound effects unchanged by default, with explicit `restart_one_shots=True` support for development workflows that want replay-on-edit
- stop and retire active handles safely when their watched source files are deleted
- deactivate failed restarts instead of leaving stale handles marked active and record backend failures in reload history
- added `watch_active()`, `poll_live_reload()` and reload-history helpers without introducing background threads
- expanded audio regression coverage to 185 total tests and added a runnable `demo_live_audio.py` example
- advanced the 0.5 roadmap toward unified live-development diagnostics and visual-editor hardening
- bumped package version to 0.4.20

## 0.4.19 - 2026-09-12

Renderer GPU texture live-reload integration update.

- added public `RendererAssetBridge` and `GPUTextureInvalidation` APIs
- connected `AssetManager` invalidation callbacks to renderer texture-cache eviction without coupling the generic asset layer to OpenGL
- release stale GPU texture objects immediately when watched source images change or are deleted
- added deterministic discovery/watching of `Sprite2D` textures plus `Material3D` albedo and metallic/roughness textures
- reuse the existing dependency-free polling pipeline and structured `AssetReloadResult` diagnostics
- added explicit bind/unbind lifecycle, context-manager support and invalidation history for editor diagnostics
- added regression coverage for GPU release, scene texture discovery, file-change invalidation and lifecycle behavior
- added a runnable `demo_renderer_asset_bridge.py` integration example
- advanced the 0.5 roadmap toward equivalent audio-resource invalidation and editor hardening
- bumped package version to 0.4.19

## 0.4.18 - 2026-09-12

Live asset reload and runtime-cache invalidation update.

- added suffix-based `AssetManager` loader registration with normalized deterministic loader lookup
- added canonical-path runtime caching so aliases and direct paths share one loaded asset instance
- added cache inspection, explicit invalidation, deterministic cached-path listing and bulk cache clearing
- added renderer/audio/editor invalidation callbacks so stale external runtime resources can be released when source assets change
- integrated the existing dependency-free `PollingFileWatcher` into `AssetManager` for watched asset creation/modification/deletion tracking
- added `AssetReloadResult` with change kind, aliases, cache state, reload success and loader error diagnostics
- reload previously cached assets automatically after supported file edits while leaving failed reloads uncached instead of serving stale data
- invalidate deleted assets without attempting to reload missing files
- added `watch_cached()` for editor/dev workflows that want to watch every currently loaded resource
- added live-asset regression coverage and a runnable `demo_live_assets.py`
- advanced the 0.5 roadmap toward direct renderer/audio cache bridges and visual-editor architecture hardening
- bumped package version to 0.4.18

## 0.4.17 - 2026-09-12

Editor-owned hot-reload state-domain architecture update.

- added public `HotReloadStateDomain` scoped state facade while preserving existing provider names and snapshot formats
- added deterministic domain metadata, `domains`, `domain_of(...)`, `names_for_domain(...)` and `remove_domain(...)` APIs
- added domain-aware registration for arbitrary callbacks and scene/ECS state providers
- added selective `HotReloadStateRegistry.capture(domains=...)` with validation for unknown domains and conflicting name/domain filters
- added `PluginManager.reload(..., state_domains=...)` so manual plugin reload can preserve only editor/game-owned state groups when required
- added `PluginAutoReloader(..., state_domains=...)` so watcher-triggered reload follows the same preservation policy
- reject state-domain filters when state preservation is explicitly disabled instead of silently ignoring contradictory configuration
- added regression coverage for domain ownership, ordered selective snapshots, clearing, cross-domain safety, plugin reload filtering and auto-reloader propagation
- expanded the hot-reload example with scene/editor domains and advanced the 0.5 roadmap toward live asset invalidation and stronger multi-domain rollback
- bumped package version to 0.4.17

## 0.4.16 - 2026-09-12

Automatic plugin file-watching and development hot-reload workflow update.

- added public `PollingFileWatcher`, `FileChangeEvent`, `PluginAutoReloader` and `ReloadResult` APIs
- added dependency-free deterministic polling for file creation, modification and deletion across Windows, Linux and macOS
- added source-file-to-plugin mappings that automatically call `PluginManager.reload(...)` after edits
- preserve registered runtime state by default during watcher-triggered reloads, building on the 0.4.15 scene/ECS snapshot pipeline
- report reload success/failure as structured results and optional callbacks instead of crashing the editor/game polling loop
- keep deleted files watched so recreating a source file can trigger a later reload
- added regression coverage for watcher lifecycle and automatic plugin reload behavior
- added a runnable automatic-reload example and advanced the 0.5 roadmap toward editor-owned state domains and live asset reload
- bumped package version to 0.4.16

## 0.4.15 - 2026-09-12

State-preserving plugin hot-reload architecture update.

- added public `HotReloadStateRegistry`, `HotReloadSnapshot` and `HotReloadStateError` APIs
- added deterministic named runtime-state providers with ordered capture/restore snapshots
- added partial snapshots, explicit provider removal/replacement and strict missing-provider diagnostics
- added `register_scene(...)` bridging versioned `SceneSerializer` snapshots into the hot-reload pipeline while preserving the same live `Scene` object
- made module-backed `PluginManager.reload(...)` automatically preserve registered runtime state by default
- added `preserve_state=False` for advanced reloads that intentionally discard runtime state
- strengthened reload rollback so failed replacement lifecycle/state restoration cleans up the replacement, restores the previous plugin and reapplies the captured state
- centralized replacement dependency validation so hot reload rejects malformed/self/empty dependencies consistently with initial registration
- clear hot-reload state providers during manager shutdown to avoid stale editor/runtime callbacks
- added regression coverage for ordered/partial snapshots, capture errors, scene restoration, successful stateful reload, rollback and opt-out behavior
- added a runnable hot-reload-state example and advanced the 0.5 architecture roadmap toward watcher-driven reload/editor state domains
- bumped package version to 0.4.15

## 0.4.14 - 2026-09-12

ECS reference-graph persistence update.

- upgraded scene/prefab documents to format version 3 with automatic v1/v2 migration
- added stable `$entity` references from registered ECS components to persisted entities
- added deterministic `$component` references between persisted ECS components
- restore cyclic component graphs by allocating every entity/component shell before field hydration
- preserved existing component-to-scene-object `$ref` behavior and legacy document compatibility
- added strict validation for malformed or unknown entity/component references
- expanded ECS persistence regression coverage for cyclic graphs, invalid references and v1/v2 migration
- expanded the persistence example to demonstrate entity and component references
- advanced the 0.5 architecture roadmap toward deeper scene/editor hot reload
- bumped package version to 0.4.14

## 0.4.13 - 2026-09-12

Plugin runtime and hot-reload architecture update.

- added public `PluginManager`, `PluginInfo` and `PluginError` APIs
- added deterministic plugin registration plus `on_load`, `on_enable`, `on_disable` and `on_unload` lifecycle hooks
- added dependency-aware activation with recursive dependency enablement, missing-dependency diagnostics and cycle detection
- prevented disabling required plugins unless cascade shutdown is explicitly requested
- added named shared-service publishing so plugins can collaborate without direct import coupling
- added module plugin entrypoints through `create_plugin()` or `plugin`
- added controlled module hot reload that preserves enabled state and attempts rollback when replacement lifecycle setup fails
- reject hot reload while enabled dependants exist so live dependency graphs are not silently invalidated
- added reverse dependency-safe shutdown and service cleanup
- added plugin lifecycle/dependency/service regression coverage plus a runnable plugin example
- advanced the 0.5 roadmap toward component/entity reference persistence and deeper scene/editor hot-reload integration
- bumped package version to 0.4.13

## 0.4.12 - 2026-09-12

ECS persistence and serializer-migration update.

- upgraded the scene/prefab document format to version 2 with automatic version-1 migration
- added ECS entity persistence to scene documents, including stable IDs, names, enabled state and tags
- added registered dataclass component persistence through the existing safe allow-list codec registry
- preserved references from persisted ECS components to serialized scene objects
- added explicit stable-ID restoration to `ECSWorld.create_entity(...)` while keeping automatic IDs backward compatible
- advanced the entity allocator past restored IDs so newly created entities cannot collide after load
- added strict validation for invalid/duplicate persisted IDs, malformed ECS metadata and target-scene ID conflicts
- kept callable/object ECS systems runtime-only instead of serializing executable behavior
- added ECS persistence/migration regression coverage and a runnable persistence example
- advanced the 0.5 architecture roadmap toward richer reference persistence, hot reload and plugin APIs
- bumped package version to 0.4.12

## 0.4.11 - 2026-09-12

Entity/component/system architecture foundation update.

- added public `Entity` and `ECSWorld` APIs with no mandatory component base class
- added one-component-per-concrete-type storage with base-class lookup, replacement, removal and required-component helpers
- added stable monotonic entity IDs, names, tags, enabled state, lookup, destruction and world detachment semantics
- added filtered component queries by type, enabled state and required tags
- added snapshot `rows(...)` queries returning `(entity, component...)` tuples in requested component order
- added callable and object-based systems with deterministic priority + registration ordering, enabled filtering and removal
- integrated one ECS world into every `Scene` with `create_entity(...)`, `entities`, `query_entities(...)` and scene-update execution
- made `Scene.clear()` clear ECS entities by default while allowing `clear_entities=False` for advanced workflows
- added seven ECS regression tests plus a runnable `demo_ecs.py`
- advanced the 0.5 architecture roadmap while leaving unfinished 0.4 rendering goals active
- bumped package version to 0.4.11

## 0.4.10 - 2026-09-12

Native metallic/roughness PBR renderer update.

- replaced the metallic/roughness-to-Phong rendering bridge with a native Cook-Torrance GGX path for PBR-enabled `Material3D` instances
- retained the legacy Phong shader path for materials that do not opt into metallic/roughness, preserving existing 0.4 rendering behavior
- added glTF-compatible packed `metallicRoughnessTexture` sampling with roughness from the green channel and metallic from the blue channel
- multiply packed texture channels by `roughnessFactor` and `metallicFactor` as required by the glTF material model
- added `Material3D.metallic_roughness_texture` and kept the historical CPU-side Phong bridge fields for compatibility with code that inspects them
- upgraded glTF/GLB material loading to resolve external, data-URI and embedded GLB metallic/roughness textures through the existing content-addressed image cache
- retained strict TEXCOORD_0/texture-transform validation for both base-color and metallic/roughness maps
- added PBR material, glTF metallic/roughness texture and invalid-UV regression coverage
- added a standalone `demo_pbr3d.py` example comparing smooth/rough dielectric and metallic surfaces
- fixed package-version drift where `swirengine.__version__` was 0.4.9 while `pyproject.toml` still declared 0.4.8
- added a regression test that requires runtime and installed package metadata versions to match
- advanced the 0.4 roadmap to skybox/environment lighting, shadows, post-processing and broader glTF material maps
- bumped package version to 0.4.10

## 0.4.9 - 2026-09-12

Scene/prefab persistence architecture update.

- added public `SceneSerializer`, `SceneCodecRegistry` and `SceneSerializationError`
- added versioned, deterministic JSON documents for scenes and reusable prefabs
- added UTF-8 file helpers with automatic parent-directory creation
- added an explicit allow-list codec registry so scene loading never dynamically imports arbitrary JSON-specified classes
- registered core 2D primitives, `Cube3D` and all 3D light types by default
- added custom dataclass registration for game/plugin scene-object types
- preserved paths, tuples, sets, vectors, colors and transforms without flattening their runtime types
- preserved cross-object references during round trips, including cyclic references between registered scene objects
- added strict validation for document kind/version, unknown types, missing/unknown fields and invalid references
- added scene replacement/append loading behavior and prefab name/independent-spawn round-trip coverage
- added a runnable scene-serialization example
- advanced the 0.5 architecture roadmap toward editor files, hot reload and serializer migrations
- bumped package version to 0.4.9

## 0.4.8 - 2026-09-12

Prefab architecture foundation update.

- added public `Prefab` reusable deep-copy blueprints for groups and object graphs
- added immutable `PrefabInstance` handles with root, lookup, tag and scene-removal helpers
- preserve internal references by deep-copying complete prefab object graphs as one unit
- isolate source objects, stored templates, separate spawned instances and mutable override values
- added per-instance attribute overrides targeting object indexes or unique object names
- added explicit validation for unknown indexes, missing/ambiguous names and invalid override attributes
- added `Prefab.from_scene(...)` with optional filtered scene capture
- added creator-facing `Scene.prefab(...)` and `Scene.instantiate(...)` integration
- added prefab regression coverage and a runnable prefab spawning example
- advanced the 0.5 architecture roadmap early without declaring the unfinished 0.4 renderer milestone complete
- bumped package version to 0.4.8

## 0.4.7 - 2026-09-12

PBR-factor bridge and asset-diagnostics update.

- added optional `Material3D.metallic` and `Material3D.roughness` controls with strict 0..1 validation
- added a compatibility-preserving metallic/roughness-to-Phong bridge so existing OpenGL 3.3 forward rendering reacts to glTF PBR factors immediately
- preserved legacy Phong behavior when metallic/roughness are not supplied
- mapped glTF/GLB `metallicFactor` and `roughnessFactor` directly into renderer-ready `Material3D` instances instead of leaving them as metadata only
- kept `GltfPrimitiveAsset.metallic_factor` and `roughness_factor` for backward compatibility
- added explicit validation for unsupported `metallicRoughnessTexture` rather than silently rendering it incorrectly
- added public `AssetInfo` and `AssetDiagnostics` snapshots
- added deterministic recursive/non-recursive asset scanning with size and normalized suffix metadata
- added missing-alias detection, total-byte accounting and suffix filtering without loading assets into RAM/GPU memory
- added regression coverage for PBR mapping, legacy-material compatibility, bounds validation, asset scans and alias health
- advanced 0.3 hardening by completing creator-facing asset diagnostics
- advanced 0.4 toward a native Cook-Torrance metallic/roughness shader and texture-driven PBR
- bumped package version to 0.4.7

## 0.4.6 - 2026-09-12

Multi-light forward-rendering and diagnostics update.

- upgraded the 3D forward shader from one light per type to multiple simultaneous lights
- added explicit OpenGL 3.3 budgets of four directional, four point and four spot lights per pass
- added deterministic scene-order light selection that respects `enabled` and `visible`
- preserved the legacy fallback directional light only when no explicit active light exists
- added public `LightSelection3D`, `select_lights(...)` and per-type light-budget constants
- added renderer statistics for directional/point/spot light counts and dropped-over-budget lights
- propagated light statistics into `FrameProfile`, profiler averaging and the built-in debug overlay
- hardened point/spot shader math against zero-distance light vectors
- expanded the 3D lighting example to exercise multiple lights of every type
- added regression tests for ordering, filtering, fallback behavior, GPU-budget overflow and diagnostics
- advanced the 0.4 roadmap from single-light Phong rendering toward PBR, shadows and post-processing
- bumped package version to 0.4.6

## 0.4.5 - 2026-09-11

3D lighting and material-specular update.

- added public `DirectionalLight3D`, `PointLight3D` and `SpotLight3D` scene objects
- added normalized light directions, intensity/range validation and smooth spotlight cone validation
- added creator-facing `Game.directional_light(...)`, `Game.point_light(...)` and `Game.spot_light(...)`
- upgraded the forward 3D shader with world-space positions, camera-aware Phong specular highlights and per-material shininess
- added distance attenuation for point/spot lights and smooth inner/outer spotlight cutoffs
- preserved the previous default directional lighting when a 3D scene contains no explicit lights
- kept unmaterialed legacy cubes free from new specular highlights for closer visual compatibility
- added `Material3D.specular` and `Material3D.shininess` controls
- added 3D lighting regression tests and a runnable multi-light example
- advanced the 0.4 roadmap toward richer PBR, multiple simultaneous lights, shadows and post-processing
- bumped package version to 0.4.5

## 0.4.4 - 2026-09-11

glTF/GLB material-preservation update.

- added public `GltfPrimitiveAsset`, `load_gltf_material(...)` and `load_gltf_primitives(...)`
- preserved glTF primitive boundaries instead of forcing multi-material meshes into one material-less mesh
- mapped glTF `baseColorFactor` to renderer-ready `Material3D.tint`
- mapped glTF `baseColorTexture` to renderer-ready `Material3D.texture`
- added external image URI support for glTF materials
- added content-addressed temporary image caching for base64 data-URI textures
- added embedded GLB `bufferView` image extraction for PNG/JPEG/WebP material textures
- exposed metallic/roughness factors as primitive metadata for future PBR renderer work
- added strict validation for unsupported alpha modes, emissive materials, non-zero texture-coordinate sets and texture-transform extensions
- kept existing `load_gltf(...)` and `load_gltf_scene(...)` behavior backward compatible
- added material/texture regression tests and a runnable glTF material example
- advanced the 0.4 roadmap from asset containers into material-aware 3D loading
- bumped package version to 0.4.4

## 0.4.3 - 2026-09-11

GLB container and glTF scene-graph update.

- extended `load_gltf(...)` to support binary GLB 2.0 containers in addition to JSON `.gltf`
- added strict GLB header/chunk validation plus JSON and BIN chunk decoding
- added public `GltfSceneMesh` metadata and `load_gltf_scene(...)`
- added default/custom scene selection and fallback root-node discovery for assets without scenes
- added hierarchical node traversal with cycle and invalid-node validation
- added glTF 4x4 node matrix support and TRS composition with normalized quaternion rotation
- added world-space position baking and inverse-transpose normal transformation
- preserved triangle winding for mirrored/negative-scale node transforms
- kept `load_gltf(..., mesh_index=...)` behavior backward compatible for direct mesh loading
- expanded glTF regression coverage for GLB, hierarchy, scale/translation, quaternion rotation and malformed containers
- advanced the 0.4 roadmap toward glTF materials and full lighting
- bumped package version to 0.4.3

## 0.4.2 - 2026-09-11

Static glTF 2.0 import update.

- added `load_gltf(...)` for JSON `.gltf` 2.0 assets
- added external binary buffer and embedded base64 data-URI support
- added accessor decoding for common glTF component and vector types, including byte strides
- added indexed and non-indexed TRIANGLES primitive import
- added POSITION, NORMAL and TEXCOORD_0 attribute import with validation
- added automatic flat-normal generation when glTF normals are absent
- added multi-primitive mesh combination with zero-filled UV fallback for mixed UV data
- added clear errors for unsupported sparse accessors, GLB containers and non-triangle primitives
- added creator-facing `Game.gltf(...)` and top-level `load_gltf` API
- added glTF regression tests and a runnable 3D viewer example
- advanced the 0.4 roadmap toward GLB, node transforms, materials and lighting
- bumped package version to 0.4.2

## 0.4.1 - 2026-09-11

Textured 3D materials update.

- added optional per-vertex UV coordinates to `MeshData` while preserving the existing six-float `interleaved()` default
- added UV-aware GPU mesh uploads using an eight-float position/normal/UV vertex layout
- added `Material3D` with optional albedo texture, tint, ambient and diffuse strengths
- added texture sampling to the forward 3D shader without breaking existing solid-color `Cube3D` and `Mesh3D` workflows
- made `Mesh3D.color` continue to act as an instance tint multiplied by the material tint
- upgraded `cube_mesh()` and the built-in cube renderer geometry with face-local UV coordinates
- upgraded Wavefront OBJ loading to parse `vt` records, positive/negative texture indices and mixed missing-UV data
- kept OBJ files without texture coordinates UV-less instead of inventing a material requirement
- added UV/material/OBJ regression tests and a textured OBJ example
- advanced the 0.4 roadmap from mesh/import foundation into textured material rendering
- bumped package version to 0.4.1

## 0.4.0 - 2026-09-11

Serious 3D foundation milestone.

- added `Camera3D` with perspective settings, look-at view matrices and local-space movement
- made `Game(mode="3d")` expose a real `Camera3D` while preserving `Camera2D` for 2D games
- added validated CPU-side `MeshData` and transformable `Mesh3D` scene objects
- added lazy GPU mesh upload/cache in the renderer with mesh/triangle/upload statistics
- upgraded 3D normal transformation for non-uniform model scaling
- added Wavefront OBJ loading with polygon fan triangulation, positive/negative indices and normals
- added automatic flat-normal generation when OBJ normals are missing
- added creator-facing `Game.mesh(...)` and `Game.obj(...)` factories
- kept the existing `Cube3D` API working through the upgraded camera-aware 3D renderer
- added a runnable OBJ viewer/navigation example and 3D camera/mesh/import tests
- bumped package version to 0.4.0 because the public 3D API now starts the roadmap's 0.4 milestone

## 0.3.5 - 2026-09-11

Renderer performance and diagnostics update.

- added adjacent-compatible `Sprite2D` batching that preserves render order and transparency
- added a reusable dynamic GPU vertex buffer that grows geometrically for large sprite runs
- added `RendererStats` with draw-call, sprite, batch, primitive, triangle and cache counters
- added `Profiler` and immutable `FrameProfile` history/averaging APIs
- instrumented update, physics and rendering sections in the main game loop
- added `DebugOverlay` plus `Game.show_debug(...)` for live FPS/timing/render statistics
- bounded the dynamic text texture cache with LRU eviction to prevent debug/HUD text growth
- exposed profiler/debug/statistics types from the top-level package
- added batching, profiler and debug-overlay tests plus a profiler example
- hardened batching to ignore non-renderable scene service objects
- marked the remaining 0.2 rendering/profiling goals complete
- bumped package version to 0.3.5

## 0.3.4 - 2026-09-11

UI and text-rendering update.

- added cached `Text2D` rendering through Pillow + the existing textured quad shader
- added camera-independent `screen_space` rendering for rectangles, sprites and text
- added `UIManager`, `UILabel`, `UIPanel`, `UIButton` and `UIProgressBar`
- added hover, press and click handling with topmost-button hit testing
- added one-frame mouse pressed/released queries to `InputManager`
- added `Game.ui`, `Game.text(...)`, `Game.label(...)`, `Game.panel(...)`, `Game.button(...)` and `Game.progress_bar(...)`
- added automatic UI child registration and cleanup through `Game.remove(...)`
- fixed framebuffer resize bookkeeping so UI hit testing follows the real window size
- added headless UI/input tests and a runnable UI example
- marked the 0.3 gameplay feature set complete and moved the milestone into API hardening
- bumped package version to 0.3.4

## 0.3.3 - 2026-09-11

Audio foundation and lifecycle update.

- added `AudioEngine` with sound-effect and background-music channels
- added pluggable `AudioBackend` protocol and lazy `PygameAudioBackend`
- added independent master, sound and music volume controls with live handle updates
- added looping, per-handle volume, stop controls and automatic music replacement
- added `Game.audio`, `Game.sound(...)` and `Game.music(...)` creator-facing APIs
- added automatic audio shutdown when the game runtime exits
- added optional `audio` installation extra so headless users and CI stay lightweight
- added audio lifecycle/volume tests
- added bytecode compilation to the cross-platform CI matrix
- bumped package version to 0.3.3

## 0.3.2 - 2026-09-11

Physics and effects update.

- added `RigidBody2D` with dynamic, kinematic and static body modes
- added fixed-step gravity, forces, impulses, damping and restitution
- added axis-by-axis AABB collision resolution through `PhysicsWorld2D`
- integrated physics with the existing `CollisionWorld2D` registry
- added `Game.physics` and `Game.rigidbody(...)` convenience APIs
- added pooled `ParticleEmitter2D` using renderer-native rectangles
- added configurable particle rate, burst emission, lifetime, speed, angle, size, gravity and fading
- added `Game.particles(...)` with automatic pooled child registration and cleanup
- added rigid-body and particle tests
- bumped package version to 0.3.2

## 0.3.1 - 2026-09-11

Level-building and persistence update.

- added `TileMap2D` with atlas UV mapping and a fixed reusable sprite pool
- added tile fill/clear/row loading plus world/cell coordinate helpers
- added `Game.tilemap(...)` with asset-root resolution and automatic scene registration
- added tilemap child cleanup through `Game.remove(...)`
- added `SaveStore` with defaults, dict-like helpers and UTF-8 JSON persistence
- added atomic save writes using a same-directory temporary file and `os.replace`
- added optional `Game.storage` autoload through `save_path=...`
- added tilemap and save-data tests
- bumped package version to 0.3.1

## 0.3.0 - 2026-09-11

First gameplay-systems milestone.

- added `SpriteSheet`, `AnimationClip` and `AnimatedSprite2D`
- added normalized sprite UV regions for sprite-sheet rendering
- added stable 2D render layers
- added `AssetManager` with aliases, resolution, existence checks and strict loading
- added `AABB`, `BoxCollider2D` and `CollisionWorld2D`
- added collision layers/masks and tag-filtered collision queries
- added `Game.sprite(...)` and `Game.collider(...)` convenience factories
- added collider cleanup when a scene object is removed through `Game.remove(...)`
- added named key pressed/released helpers
- fixed all lint failures found by GitHub Actions after 0.2.0
- upgraded CI to current Node-24-based official GitHub actions
- disabled matrix fail-fast so one platform cannot hide results from the others
- expanded the suite from 16 to 33 tests
- added animation and collision examples

## 0.2.0 - 2026-09-11

First creator-focused 2D milestone.

- added `Sprite2D` with PNG/JPEG/etc. loading through Pillow
- added GPU texture rendering, alpha blending and lazy texture cache
- added `Camera2D` with movement, zoom, look-at and follow helpers
- added `Game.add`, `spawn`, `add_many`, `remove` and `key` shortcuts
- added scene names, tags, lookup helpers and collection protocol support
- added visibility flags for renderable primitives
- added renderer resource cleanup
- made plain `pytest` work directly from a source checkout
- expanded tests and 2D examples

## 0.1.0 - 2026-09-11

Initial engine foundation.

- unified `Game` API with 2D and 3D modes
- OpenGL 3.3 renderer via ModernGL
- GLFW window/input backend
- 2D colored rectangle rendering
- lit 3D cube rendering
- scene lifecycle
- event bus
- keyboard and mouse state
- variable and fixed update callbacks
- vector/color/transform math
- CLI project generator
- examples and tests
- GitHub Actions CI