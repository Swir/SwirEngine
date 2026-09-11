# Changelog

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
- added hover/pressed/click state handling with topmost-button hit testing
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
- added asset alias/path validation for audio through the existing `AssetManager`
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
