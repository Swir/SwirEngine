# SwirEngine 1.2.0

<p align="center">
  <a href="https://github.com/Swir/SwirEngine/actions/workflows/ci.yml"><img alt="CI" src="https://github.com/Swir/SwirEngine/actions/workflows/ci.yml/badge.svg"></a>
  <a href="https://pypi.org/project/swirengine/"><img alt="PyPI" src="https://img.shields.io/pypi/v/swirengine?style=flat-square"></a>
  <img alt="Python" src="https://img.shields.io/badge/Python-3.10--3.13%20cross--platform%20%7C%203.14%20Windows-3776AB?style=flat-square&logo=python&logoColor=white">
  <img alt="Status" src="https://img.shields.io/badge/status-stable-2ea043?style=flat-square">
  <img alt="License" src="https://img.shields.io/badge/license-MIT-blue?style=flat-square">
</p>

**SwirEngine** is a Python-first 2D/3D game engine built around an approachable API. It combines Python gameplay code with a real OpenGL renderer, scenes, prefabs/ECS, physics, animation, audio, responsive UI, input rebinding, gameplay networking, asset streaming, native desktop export and complete 3D validation demos.

SwirEngine **1.2.0 is the current stable release** published on PyPI and GitHub. The historical 1.0 roadmap is locked at **31/31 = 100%**, 1.1 is locked at **10/10 = 100%**, and the published 1.2 roadmap is locked at **10/10 = 100%**. Development after the stable release is tracked separately in [`ROADMAP_1_3.md`](ROADMAP_1_3.md); unfinished 1.3 work is **not** published as an intermediate package.

## Install stable 1.2.0

Verified support covers **Python 3.10-3.13** on Windows, Linux and macOS, plus **Python 3.14 on Windows x86-64**.

```bash
python -m pip install -U swirengine
```

Optional audio support:

```bash
python -m pip install -U "swirengine[audio]"
```

### Python 3.14 on Windows

Stable upstream `moderngl 5.12.0` and `glcontext 3.0.0` do not currently provide the Windows x86-64 CPython 3.14 wheel combination required by the normal dependency path. SwirEngine therefore builds and validates a dedicated `cp314-cp314-win_amd64` wheel path in GitHub Actions, proves normal pip candidate selection and performs native import validation. Linux/macOS remain on Python 3.10-3.13 until an equivalent dependency path is reproducibly verified.

## Quick 2D game

```python
from swirengine import Color, Game, Rectangle2D


game = Game("My 2D Game", 1280, 720, mode="2d")
player = game.add(Rectangle2D(0, 0, 120, 70, Color(0.1, 0.75, 1.0, 1.0)))

@game.update
def update(dt):
    speed = 380
    if game.key("A"):
        player.x -= speed * dt
    if game.key("D"):
        player.x += speed * dt
    if game.key("W"):
        player.y += speed * dt
    if game.key("S"):
        player.y -= speed * dt

game.run()
```

## Quick 3D game

```python
from swirengine import Color, Cube3D, Game, Vec3


game = Game("My 3D Game", 1280, 720, mode="3d")
cube = game.add(Cube3D(position=Vec3(0, 0, -4), color=Color(0.2, 0.7, 1.0, 1.0)))

@game.update
def update(dt):
    cube.rotation.y += 50 * dt
    cube.rotation.x += 25 * dt

game.run()
```

## Active 1.3 development — Gameplay & Creator Power

The package version intentionally remains **1.2.0** while the 1.3 roadmap is developed. No 1.3 PyPI package, tag or GitHub Release is created until the whole roadmap reaches 10/10 and passes the final release gate.

### GPU instancing + frustum culling — milestone 1/10

The first verified 1.3 milestone adds a native dynamic-instancing path alongside the existing CPU-baked static batching system:

- additive `Instance3D`, `InstancedMesh3D`, `InstancedCube3D` and `Frustum3D` APIs
- real ModernGL per-instance attributes with one `vao.render(..., instances=N)` submission for a visible batch
- reusable grow-on-demand GPU instance buffers and a reusable float32 CPU staging array
- direct transform packing without allocating a separate 4x4 NumPy transform matrix for every instance
- conservative CPU frustum rejection using scale-aware mesh bounding spheres
- per-instance RGBA variation plus existing `Material3D` forward Phong/PBR channels
- directional, point and spot lights under the existing deterministic light budgets
- renderer diagnostics for instance candidates, culled instances, submitted instances and instance batches

The deterministic regression contract requires **1,000 visible compatible instances to map from a 1,000-draw baseline to one instanced draw**, and a separate 1,000-instance culling case requires exactly **100 visible / 900 culled**. `tools/benchmark_gpu_instancing.py` measures host-dependent CPU cull+pack work for 10,000 instances without converting that timing into an FPS claim.

A real Xvfb/software-OpenGL CI gate compiles and executes the production instanced draw path. `examples/demo_gpu_instancing.py` builds a **6,400-instance** PBR-lit field for creator testing.

Current boundary: the 1.3 milestone integrates instanced objects into the direct forward pass. Existing shadow-map overlay and additive cubemap-IBL auxiliary passes still operate on regular `Mesh3D` objects; SwirEngine does not silently fall back to one draw per instance for those passes.

See [`docs/GPU_INSTANCING_1_3.md`](docs/GPU_INSTANCING_1_3.md) and [`ROADMAP_1_3.md`](ROADMAP_1_3.md).

### 3D skeletal animation — milestone 2/10

The second verified 1.3 milestone adds an additive skinned-character pipeline while preserving the established static glTF loaders and stable 1.x behavior:

- creator-facing `swirengine.skeletal` namespace with skeletons, skins, poses, clips and controllers
- glTF/GLB `skins`, `JOINTS_0`, `WEIGHTS_0` and inverse-bind-matrix import
- four weighted joint influences per vertex with normalized float/unsigned-byte/unsigned-short weights
- STEP, LINEAR and CUBICSPLINE animation channels plus shortest-path quaternion SLERP
- named clip playback, looping/non-looping terminal poses and smooth crossfades
- hierarchical pose evaluation and a deterministic **64-joint** GPU palette budget
- OpenGL 3.3 transform-feedback skin deformation for animated positions and normals
- the deformed stream reuses the existing forward Phong/PBR material and lighting path rather than duplicating renderer behavior
- renderer diagnostics for skinned meshes, animated vertices and submitted skin joints

A dedicated Xvfb/software-OpenGL gate executes the real production GPU-skinning path. Generated glTF regression coverage proves skin/weight/animation import and verifies that the legacy static glTF loader remains separate and compatible. `examples/demo_skeletal_animation.py` provides a runnable creator example.

Current boundary: the new skinned path participates in the direct forward renderer. Existing auxiliary shadow-map and additive cubemap-IBL passes are not silently converted to CPU deformation or per-joint fallback behavior.

See [`docs/SKELETAL_ANIMATION_1_3.md`](docs/SKELETAL_ANIMATION_1_3.md) and [`ROADMAP_1_3.md`](ROADMAP_1_3.md).

### 3D collision / physics foundation — milestone 3/10

The third verified 1.3 milestone brings gameplay collision queries and deterministic fixed-step movement into the 3D API without adding a heavyweight native physics dependency:

- additive `AABB3D`, `SphereBounds3D`, `BoxCollider3D`, `SphereCollider3D` and `CollisionWorld3D`
- live transform tracking for creator objects, with explicit collider dimensions available for arbitrary meshes
- deterministic 3D spatial-hash broad phase plus box/box, sphere/sphere and sphere/box narrow phase
- layer/mask/tag filtering, box/sphere/point overlaps, deterministic collision pairs and distance-sorted raycasts
- finite raycasts restrict exact shape tests to intersected spatial cells instead of scanning the full registry
- additive `RigidBody3D` / `PhysicsWorld3D` with dynamic, kinematic and static bodies, forces, impulses, gravity, damping and restitution
- fixed substeps, catch-up caps, `dropped_time` diagnostics and interpolation alpha for stable gameplay simulation

The performance contract keeps claims measurable: a sparse **1,000-collider** pair workload must stay at least **100x below brute-force candidate enumeration**, and a short finite ray through a 1,000-collider registry must visit fewer than ten candidates. The dedicated 10,000-collider benchmark reports host timing only as diagnostic data and does not claim an FPS uplift.

Current boundary: box colliders are axis-aligned, rigid-body response is box-vs-box, and sphere colliders currently participate in queries rather than rigid-body response. This milestone does not claim OBB/mesh collision, CCD, joints or a full constraint solver.

See [`docs/COLLISION_PHYSICS_1_3.md`](docs/COLLISION_PHYSICS_1_3.md) and [`ROADMAP_1_3.md`](ROADMAP_1_3.md).

### Navigation & pathfinding — milestone 4/10

The fourth verified 1.3 milestone adds deterministic navigation for 2D games and grounded 3D worlds while keeping future navmesh implementations behind a stable provider seam:

- dedicated `swirengine.navigation` creator namespace
- weighted deterministic A* on `NavigationGrid2D` and an XZ-plane `NavigationGrid3D`
- blocked cells, traversal costs, cardinal/diagonal movement and safe no-corner-cutting behavior by default
- bounded revision-aware route caching so unchanged repeated routes do not repeat A* expansion
- obstacle/cost revisions invalidate stale routes and trigger automatic agent repathing
- `max_expansions` supports budgeted searches without poisoning the stable route cache
- `NavigationAgent2D` / `NavigationAgent3D` consume a distance budget across waypoints and preserve 3D target height
- runtime-checkable `NavigationProvider2D` / `NavigationProvider3D` protocols provide the compatibility route toward later authored/generated navmesh backends

The regression contract performs one cold 64x64 route query and then **999 identical requests**: it requires exactly one cache miss, 999 cache hits and zero A* node expansion on the final cached query. `tools/benchmark_navigation.py` separately runs one cold 128x128 obstacle route plus 1,000 cached requests and reports host timing only; no FPS uplift is claimed.

Current boundary: this milestone provides grid navigation and flat XZ-plane 3D navigation. It does not claim polygon navmesh generation, off-mesh links, crowd steering/RVO, slope traversal or arbitrary 3D navigation volumes.

See [`docs/NAVIGATION_PATHFINDING_1_3.md`](docs/NAVIGATION_PATHFINDING_1_3.md) and [`ROADMAP_1_3.md`](ROADMAP_1_3.md).

### Large world / chunk streaming — milestone 5/10

The fifth verified 1.3 milestone adds deterministic large-world residency without turning every frame into a scan of the full authored or procedural world:

- dedicated `swirengine.large_world` creator namespace with `ChunkKey`, `ChunkDefinition`, `ChunkRegistry`, `ChunkContent`, `LargeWorldSettings` and `LargeWorldStreamer`
- shared 2D/3D addressing with floor-correct negative coordinates, plus local preload, active and retention windows
- nearest-first bounded activation and bounded deactivation/asset-finalization work for teleport and fast-travel scenarios
- `SceneMount` integration so chunk-owned scene objects and ECS entities follow established lifecycle cleanup
- optional `AssetStreamingManager` staging with shared-asset reference-counted pinning and the existing deterministic LRU residency policy
- optional visibility gating plus creator-visible activation/asset/deactivation-hook failures and single-chunk retry
- sparse provider-miss caching, bounded by retention; `ChunkRegistry.revision` invalidates authored-world misses automatically and mutable procedural providers can invalidate explicitly
- diagnostics for local candidates, provider queries, ready/active/waiting/failed chunks and cached missing keys

The measurable performance contract is based on locality rather than a synthetic FPS number: update candidate work is bounded by `(2 * preload_radius + 1)^dimensions`. The dedicated 3D benchmark requires exactly **125 local candidates** for radius 2 while moving through hundreds of far-separated positions, and sparse-world regressions prove provider misses are not re-queried every frame or retained without bound.

Current boundary: this milestone is chunk lifetime/residency and activation infrastructure. It does not claim terrain LOD/clipmaps, renderer occlusion culling, a persistent world database, editor terrain authoring or network interest management.

See [`docs/LARGE_WORLD_STREAMING_1_3.md`](docs/LARGE_WORLD_STREAMING_1_3.md) and [`ROADMAP_1_3.md`](ROADMAP_1_3.md).

### Advanced material & shader pipeline — milestone 6/10

The sixth verified 1.3 milestone adds controlled creator shader customization without replacing the engine-owned render contract:

- additive `ShaderTemplate`, `ShaderHookPoint`, deterministic `ShaderVariantSpec` and `ShaderMaterial3D` APIs
- context-free `prepare_shader_variant()` plus the creator-friendly `shader_material_3d()` helper
- production `ShaderMesh3D` rendering through the renderer selected by `Game`
- bounded LRU backend program cache with hit/miss/failure/eviction/invalidation diagnostics
- explicit hook seams for vertex/fragment globals, surface modification and post-lighting work
- conservative validation that rejects unknown hooks, unsafe preprocessor/layout/state escape paths and invalid defines/uniforms
- shared mesh VBOs across variants plus cached VAO bindings per mesh/variant key
- existing `Mesh3D`, `Material3D`, Phong and PBR paths remain unchanged

The deterministic performance contract requires **1,000 resolves of one prepared variant to produce exactly one backend compile, one miss and 999 cache hits**. A production-pipeline regression also requires two compatible shader meshes to share one uploaded VBO and one VAO binding. `tools/benchmark_shader_pipeline.py` repeats 10,000 cache resolves as host timing only; it does not claim an FPS uplift.

A dedicated Xvfb/software-OpenGL gate compiles and renders a real custom `ShaderMesh3D` through `Game`, including a runtime custom uniform and fragment hook. Current boundary: custom shader meshes participate in the direct-forward pass and do not silently claim auxiliary shadow-map/IBL support or arbitrary custom sampler binding.

See [`docs/ADVANCED_SHADER_MATERIAL_1_3.md`](docs/ADVANCED_SHADER_MATERIAL_1_3.md) and [`ROADMAP_1_3.md`](ROADMAP_1_3.md).

## Stable 1.2 feature set

SwirEngine 1.2 is additive and preserves compatibility-sensitive 1.x behavior while filling major engine-level gaps beyond a low-level game library.

### 2D

- sprites, textures, render layers, sprite sheets and animation clips
- tilemaps and adjacent compatible sprite batching
- responsive labels/panels/buttons/progress bars with anchors and containers
- keyboard/mouse/gamepad focus navigation and semantic input actions
- persistent input rebinding profiles
- sparse pooled particles/VFX and diagnostics
- bounded/smoothed camera rigs, dead-zone follow, rails and deterministic shake
- spatial-hash AABB broad phase, overlap/point/ray queries and fixed-step arcade physics
- typed/versioned settings, migrations, profiles and save slots
- deterministic tween/timeline/state-machine animation runtime
- font fallback registry, wrapping/alignment and bounded cached text layout

### 3D

- perspective cameras, bounded/smoothed camera rigs, rails and deterministic shake
- `MeshData`, `Mesh3D`, lazy GPU mesh caching and OBJ import
- static glTF/GLB scene/material import
- Phong and Cook-Torrance GGX metallic/roughness PBR
- base-color, metallic/roughness, normal, occlusion and emissive channels
- directional, point and spot lights with deterministic GPU budgets
- skybox/environment support and cubemap image-based lighting
- directional GPU shadows, post-processing, tone mapping and FXAA
- sRGB/linear color-space handling
- bounded transform caching and static larger-batch rendering
- on active 1.3 development branches: native GPU instancing/frustum culling, GPU-skinned glTF skeletal animation, 3D collision/fixed-step gameplay physics, deterministic 2D/3D navigation, bounded large-world chunk residency and controlled shader/material variants

### Production systems

- scenes with names/tags, lifecycle hooks, cached update snapshots and grouped mounts
- reusable prefabs, overrides, deterministic batch spawning and versioned serialization
- indexed lightweight ECS with composition helpers, deterministic queries and cached prioritized systems
- plugin runtime, file watcher and transactional hot-reload restoration
- budgeted staged asset streaming with in-flight deduplication, deterministic LRU residency and diagnostics
- audio buses/groups, fades and spatial attenuation/pan
- typed settings, deterministic migrations and profile-oriented save layout
- project-oriented editor workflow with reversible playtest state
- deterministic TCP transport plus gameplay messages, explicit RPC and session diagnostics
- deterministic export manifests, generated desktop specs and explicit native builds
- debug overlay and programmatic profiler

## 1.2 creator documentation

- [`docs/PARTICLES_VFX_1_2.md`](docs/PARTICLES_VFX_1_2.md) — sparse pooled particles and VFX
- [`docs/TEXT_FONT_PIPELINE_1_2.md`](docs/TEXT_FONT_PIPELINE_1_2.md) — font fallback and cached text layout
- [`docs/CAMERA_SYSTEMS_1_2.md`](docs/CAMERA_SYSTEMS_1_2.md) — shared 2D/3D camera rigs
- [`docs/SAVE_CONFIG_1_2.md`](docs/SAVE_CONFIG_1_2.md) — typed settings, migrations, profiles and saves
- [`docs/NETWORK_GAMEPLAY_1_2.md`](docs/NETWORK_GAMEPLAY_1_2.md) — gameplay messages, RPC and diagnostics
- [`docs/SCENE_ECS_ERGONOMICS_1_2.md`](docs/SCENE_ECS_ERGONOMICS_1_2.md) — scene/prefab/ECS composition and lifecycle
- [`docs/ASSET_STREAMING_1_2.md`](docs/ASSET_STREAMING_1_2.md) — staged streaming and residency budgets
- [`docs/RENDERER_VFX_PERFORMANCE_1_2.md`](docs/RENDERER_VFX_PERFORMANCE_1_2.md) — renderer/VFX frame-work reduction
- [`docs/BUILD_EXPORT_1_2.md`](docs/BUILD_EXPORT_1_2.md) — native desktop build/export hardening
- [`docs/CREATOR_HARDENING_1_2.md`](docs/CREATOR_HARDENING_1_2.md) — final creator/release contract

## Performance regression gates

SwirEngine keeps performance claims narrow and reproducible:

- **GPU instancing 1.3:** 1,000 visible compatible instances model 1,000 source submissions -> one instanced draw; a separate 1,000-instance case must cull exactly 900 outside the test frustum
- **skeletal animation 1.3:** bind-pose palettes, normalized skin weights, clip sampling/crossfade and glTF skin import are deterministic regressions, while a real software-OpenGL smoke executes the production transform-feedback GPU skinning path
- **3D collision 1.3:** a sparse 1,000-collider pair workload must reduce broad-phase candidates by at least 100x versus brute force; a short finite ray through 1,000 sparse colliders must visit fewer than ten candidates
- **navigation 1.3:** one cold 64x64 path plus 999 identical requests must produce one cache miss, 999 hits and zero node expansion on the final cached query
- **large-world streaming 1.3:** radius-2 3D streaming must enumerate exactly 125 local candidate keys independent of world extent; sparse provider misses must be cached locally and pruned with retention rather than queried every frame or accumulated forever
- **shader/material pipeline 1.3:** 1,000 resolves of one prepared variant must produce exactly one backend compile and 999 cache hits; two compatible `ShaderMesh3D` objects must share one mesh upload and one VAO binding
- **static 3D batching:** 100 compatible static cubes map from 100 renderer-facing object draws to one combined mesh draw
- **async preload:** a reproducible synthetic I/O-like benchmark must demonstrate real overlap/wait reduction
- **asset streaming residency:** exact incremental byte accounting is verified through eviction
- **2D collision:** a sparse 1,000-collider case must reduce broad-phase candidates by at least 100x versus brute-force all-pairs enumeration
- **particle/VFX:** 10,000 capacity with eight live particles must perform exactly eight update visits
- **text layout:** after first layout, 1,000 identical requests must hit cache with zero additional measurement calls
- **indexed ECS:** a 1,001-entity mixed query must reduce candidates to exactly one
- **renderer/VFX frame work:** a 512-sprite repeatable run streams without an outer cache and stable state/color operations reuse cached objects

These are workload/regression measurements, not synthetic FPS promises.

## Project generator and native desktop export

```bash
swirengine new MyGame --mode 2d
swirengine new My3DGame --mode 3d
swirengine info
swirengine export . --target windows --name MyGame --onefile --windowed
swirengine export . --target windows --name MyGame --onefile --windowed --build-native
```

Generated projects remain compatible with the stable engine line:

```toml
engine = ">=1.0,<2.0"
```

The shipping workflow builds and launches one-file and one-directory executables on Windows, Linux and macOS. Android and Web remain experimental staging/research targets until their shipping paths are fully verified.

## Official validation demos and examples

- **Neon Cube Hunt 3D** — 3D collection arena used for real OpenGL and packaged-runtime validation
- **Neon Snake 3D** — complete 3D Snake with growth, food, collision, score, PBR and post-processing
- `examples/demo_gpu_instancing.py` — active 1.3 dynamic instancing/frustum-culling demo with 6,400 cubes
- `examples/demo_skeletal_animation.py` — active 1.3 skinned-character animation and GPU-skinning demo
- `examples/demo_collision3d_physics.py` — active 1.3 collision queries and fixed-step 3D gameplay physics
- `examples/demo_navigation_pathfinding.py` — active 1.3 weighted A*, dynamic obstacles and automatic 3D agent repathing
- `examples/demo_large_world_streaming.py` — active 1.3 local-window residency, bounded chunk activation and reversible scene ownership
- `examples/demo_shader_variants.py` — active 1.3 deterministic shader variants, safe hooks, uniforms and bounded program-cache diagnostics
- `examples/demo_gamepad.py` — controller + keyboard fallback
- `examples/demo_static_3d_batching.py` — static larger-batch rendering
- `examples/demo_asset_streaming.py` — staged loading, residency budgets and eviction
- `examples/demo_responsive_ui.py` — resize-aware UI and focus navigation
- `examples/demo_animation_runtime.py` — tween/sequence/timeline/state machine
- `examples/demo_collision_queries.py` — spatial collision queries and diagnostics
- `examples/demo_editor_workflow.py` — scene/prefab/input/playtest workflow
- `examples/demo_particles_vfx.py` — sparse pooled particle lifecycle
- `examples/demo_text_layout.py` — fallback, wrapping, alignment and cache diagnostics
- `examples/demo_camera_systems.py` — camera rails/smoothing/shake
- `examples/demo_save_config.py` — typed settings, profiles and save slots
- `examples/demo_network_gameplay.py` — deterministic messages, RPC and diagnostics
- `examples/demo_scene_ecs_ergonomics.py` — lifecycle, mounts, indexed queries and prefab waves
- `examples/demo_export_pipeline.py` — manifest v2, integrity hashes and native spec

## Development and verification

```bash
python -m pip install -e ".[dev]"
pytest
ruff check src tests examples demo_projects tools
python -m compileall -q src examples demo_projects tools
python tools/verify_1_2_release_candidate.py --require-complete
python tools/benchmark_gpu_instancing.py
pytest tests/test_skeletal_animation.py
pytest tests/test_collision3d.py tests/test_rigidbody3d.py
python tools/benchmark_collision3d.py
pytest tests/test_navigation.py
python tools/benchmark_navigation.py
python examples/demo_navigation_pathfinding.py
pytest tests/test_large_world.py tests/test_large_world_provider_cache.py
python tools/benchmark_large_world.py
python examples/demo_large_world_streaming.py
pytest tests/test_shader_pipeline.py tests/test_shader_mesh.py
python tools/benchmark_shader_pipeline.py
python examples/demo_shader_variants.py
```

CI validates:

- Windows, Linux and macOS with Python 3.10, 3.11, 3.12 and 3.13
- Windows x86-64 with Python 3.14
- wheel/sdist metadata and clean-wheel installation
- dedicated Windows CPython 3.14 native dependency/wheel selection and import checks
- one-file and one-directory desktop executables on Windows/Linux/macOS Python 3.13
- reproducible performance/regression gates, including 1.3 3D collision, navigation, large-world locality and shader-cache workloads
- real OpenGL paths through Neon Cube Hunt 3D, Neon Snake 3D, GPU instancing, skeletal GPU skinning and `ShaderMesh3D`

## Versioning and API stability

SwirEngine follows semantic versioning for the stable 1.x public API. Existing 1.x behavior remains compatibility-sensitive. New 1.3 development is additive unless a future explicitly planned version documents a migration.

The installed/public package remains **1.2.0** during 1.3 development. The 1.3 release is frozen until its roadmap reaches exactly 10/10 = 100.0% and the final exact head passes CI/runtime/demo/packaging plus public-artifact post-release verification.

See [`docs/API_STABILITY.md`](docs/API_STABILITY.md), [`docs/CREATOR_HARDENING_1_2.md`](docs/CREATOR_HARDENING_1_2.md), [`docs/GPU_INSTANCING_1_3.md`](docs/GPU_INSTANCING_1_3.md), [`docs/SKELETAL_ANIMATION_1_3.md`](docs/SKELETAL_ANIMATION_1_3.md), [`docs/COLLISION_PHYSICS_1_3.md`](docs/COLLISION_PHYSICS_1_3.md), [`docs/NAVIGATION_PATHFINDING_1_3.md`](docs/NAVIGATION_PATHFINDING_1_3.md), [`docs/LARGE_WORLD_STREAMING_1_3.md`](docs/LARGE_WORLD_STREAMING_1_3.md) and [`docs/ADVANCED_SHADER_MATERIAL_1_3.md`](docs/ADVANCED_SHADER_MATERIAL_1_3.md).

## Roadmaps

- SwirEngine 1.0: [`ROADMAP.md`](ROADMAP.md) — **31/31 = 100%**, historical and locked
- SwirEngine 1.1: [`ROADMAP_1_1.md`](ROADMAP_1_1.md) — **10/10 = 100%**, released and locked
- SwirEngine 1.2: [`ROADMAP_1_2.md`](ROADMAP_1_2.md) — **10/10 = 100.0%**, published and locked
- SwirEngine 1.3: [`ROADMAP_1_3.md`](ROADMAP_1_3.md) — **6/10 = 60.0%**, active development

## Links

- PyPI: https://pypi.org/project/swirengine/
- Repository: https://github.com/Swir/SwirEngine
- Releases: https://github.com/Swir/SwirEngine/releases
- Changelog: https://github.com/Swir/SwirEngine/blob/main/CHANGELOG.md

## License

MIT