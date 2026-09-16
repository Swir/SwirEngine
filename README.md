# SwirEngine 1.3.0

<p align="center">
  <a href="https://github.com/Swir/SwirEngine/actions/workflows/ci.yml"><img alt="CI" src="https://github.com/Swir/SwirEngine/actions/workflows/ci.yml/badge.svg"></a>
  <a href="https://pypi.org/project/swirengine/"><img alt="PyPI" src="https://img.shields.io/pypi/v/swirengine?style=flat-square"></a>
  <img alt="Python" src="https://img.shields.io/badge/Python-3.10--3.13%20cross--platform%20%7C%203.14%20Windows-3776AB?style=flat-square&logo=python&logoColor=white">
  <img alt="Stable roadmap" src="https://img.shields.io/badge/1.3%20ROADMAP-100%25-2ea043?style=flat-square">
  <img alt="Development roadmap" src="https://img.shields.io/badge/1.4%20ROADMAP-30%25-0969da?style=flat-square">
  <img alt="Status" src="https://img.shields.io/badge/status-1.3%20stable%20%7C%201.4%20development-0969da?style=flat-square">
  <img alt="License" src="https://img.shields.io/badge/license-MIT-blue?style=flat-square">
</p>

**SwirEngine 1.3.0 is the current stable release** of a Python-first 2D/3D game engine built around an approachable, stable 1.x API. It combines Python gameplay code with a real OpenGL renderer, GPU instancing, skeletal animation, 2D/3D physics and collision, navigation, large-world streaming, shader/material variants, editor integration, gameplay utilities, responsive UI, audio, networking and native desktop export.

The 1.3 **Gameplay & Creator Power** roadmap is complete at **10/10 = 100.0%**. Historical 1.0, 1.1 and 1.2 roadmaps remain locked at 100%.

```text
████████████████████ 100.0%
```

## Active development — SwirEngine 1.4

SwirEngine 1.4 is the **Production World & Engine Power** development line. Stable users remain on 1.3.0 while 1.4 is built milestone-by-milestone behind the stable 1.x API compatibility contract.

```text
██████░░░░░░░░░░░░░░ 30.0% — 3/10
```

Milestone #1, **Terrain + World LOD**, is complete on the 1.4 development line. It adds immutable heightmaps, chunk mesh generation, distance LOD, bounded local chunk selection, LRU mesh reuse, terrain material/splat metadata, heightfield ground queries and direct integration with the existing `LargeWorldStreamer`. The milestone is covered by deterministic cache/LOD performance gates and a real Xvfb/software-OpenGL terrain render smoke.

Milestone #2, **Physics 2.0**, is also complete. It adds additive `PhysicsScene3D` / `PhysicsBody3D` APIs, deterministic box/sphere contacts, friction and restitution response, shape sweeps, optional continuous collision handling, distance joints, sleeping/wake behavior, diagnostics and a backend-ready protocol while keeping the existing 1.x physics path intact. The dedicated gate validates regression compatibility, sparse broad-phase/CCD behavior, an integration demo, strict Ruff and compileall.

Milestone #3, **Character Controllers**, is verified as well. It adds a deterministic kinematic `CharacterController3D` backed by Physics 2.0 shape sweeps, first-person, third-person and platformer presets, grounded state, jumping, coyote time, jump buffering, step-up and slope handling, ground snapping, camera synchronization/collision, semantic `InputActions` integration and revision-aware `NavigationProvider3D` steering. The controller API is available both from `swirengine.character` and directly from the top-level `swirengine` package. Its dedicated validation covers movement/camera/navigation regressions, a deterministic sweep-budget gate, integration demo, strict Ruff and compileall, while the full cross-platform CI, desktop export and demo validators remain green.

The remaining 1.4 plan focuses on Renderer 2.0, GPU VFX, Asset Pipeline 2.0, scene acceleration/occlusion, stronger editor authoring, Multiplayer 2.0 and one integrated production-scale release showcase.

See [`ROADMAP_1_4.md`](ROADMAP_1_4.md), [`docs/TERRAIN_WORLD_LOD_1_4.md`](docs/TERRAIN_WORLD_LOD_1_4.md), [`docs/PHYSICS_2_1_4.md`](docs/PHYSICS_2_1_4.md) and [`docs/CHARACTER_CONTROLLERS_1_4.md`](docs/CHARACTER_CONTROLLERS_1_4.md).

## Install

Verified support covers **Python 3.10-3.13** on Windows, Linux and macOS, plus **Python 3.14 on Windows x86-64** through the dedicated validated native-wheel path.

```bash
python -m pip install -U swirengine
```

Optional audio support:

```bash
python -m pip install -U "swirengine[audio]"
```

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

## What shipped in 1.3

### 1. GPU instancing + frustum culling

- `Instance3D`, `InstancedMesh3D`, `InstancedCube3D`, `Frustum3D`
- real per-instance GPU attributes and one instanced submission per compatible visible batch
- reusable CPU/GPU staging buffers
- conservative frustum rejection and renderer diagnostics
- deterministic 1,000-instance draw/cull regression gates

### 2. 3D skeletal animation

- glTF/GLB skins, joints, weights and inverse-bind matrices
- STEP, LINEAR and CUBICSPLINE animation channels
- named clips, looping, crossfades and hierarchical poses
- GPU skinning with a deterministic 64-joint palette budget
- production OpenGL smoke validation

### 3. 3D collision / physics foundation

- `AABB3D`, sphere/box colliders and `CollisionWorld3D`
- spatial-hash broad phase and deterministic shape queries
- overlap, point, sphere, box and ray queries with filtering
- fixed-step `RigidBody3D` / `PhysicsWorld3D`
- measurable candidate-reduction performance gates

### 4. Navigation & pathfinding

- weighted deterministic A* for 2D and grounded 3D XZ navigation
- traversal costs, blocked cells and safe diagonal movement
- bounded revision-aware route caching
- navigation agents with automatic repathing
- stable provider protocols for future navigation backends

### 5. Large world / chunk streaming

- chunk registry, chunk content and bounded `LargeWorldStreamer`
- local preload/active/retention windows
- bounded activation, deactivation and asset-finalization budgets
- scene/ECS ownership and streaming hooks
- sparse provider-miss caching and deterministic diagnostics

### 6. Advanced material & shader pipeline

- `ShaderTemplate`, `ShaderHookPoint`, `ShaderVariantSpec`, `ShaderMaterial3D`
- production `ShaderMesh3D`
- safe creator hook points and custom uniforms
- bounded LRU shader program cache
- shared mesh uploads and cached VAO bindings

### 7. 2D renderer power pass

- tilemap viewport-local submission
- cached render roots and dirty transform synchronization
- O(1) tile counts
- conservative world-space culling
- reusable NumPy sprite staging buffers
- renderer diagnostics for culling and tilemap locality

### 8. Advanced gameplay framework

- `Scheduler`, `TimerHandle`, `Signal`, `ObjectPool`, `Cooldown`, `Spawner`, `GameplayRuntime`
- deterministic min-heap timers
- mutation-safe signals
- prewarmed bounded pools
- allocation-reuse and dormant-timer regression gates

### 9. Creator / editor integration

- `swirengine.creator` integration over the existing editor architecture
- lazy subsystem diagnostics and deterministic metadata filtering
- no background polling of hidden systems
- integration with existing hierarchy, inspector, viewport, assets, console, profiler and playtest workflow

### 10. Full game + hardening + release gate

**Neon Frontier 1.3** is the integrated validation game for the release. One application exercises production OpenGL, GPU instancing, `ShaderMesh3D`, 3D collision queries, 3D navigation, bounded large-world streaming, gameplay scheduling, camera and lighting.

The final gate validates:

- full pytest matrix and strict Ruff/compileall
- Windows, Linux and macOS Python coverage
- Windows x64 / Python 3.14 native wheel selection and import path
- wheel/sdist metadata and clean-wheel installation
- one-file and one-directory native desktop export
- real Xvfb/software-OpenGL runtime execution
- Windows one-file `NeonFrontier13.exe` packaged runtime probe
- deterministic performance contracts without synthetic FPS claims
- strict `tools/verify_1_3_release_candidate.py --require-complete`
- public PyPI metadata and clean-install verification after publication

## Stable feature set

### 2D

- sprites, textures, layers, sprite sheets and animation
- tilemaps, batching and viewport culling
- responsive labels, panels, buttons and progress bars
- keyboard, mouse and gamepad input with rebinding
- particles/VFX, camera rigs and collision queries
- settings, migrations, profiles and save slots
- tween/timeline/state-machine animation runtime
- font fallback, wrapping, alignment and cached text layout

### 3D

- perspective cameras and camera rigs
- mesh primitives, OBJ and static glTF/GLB import
- Phong and Cook-Torrance GGX metallic/roughness PBR
- directional, point and spot lights
- skybox/environment cubemaps and IBL
- directional shadows, post-processing, tone mapping and FXAA
- GPU instancing and frustum culling
- skeletal animation and GPU skinning
- collision queries and fixed-step gameplay physics
- deterministic navigation and large-world chunk residency
- controlled shader/material variants

### Production systems

- scenes, lifecycle hooks, grouped mounts and cached update snapshots
- prefabs, overrides, batch spawning and versioned serialization
- lightweight indexed ECS
- plugin runtime and transactional hot reload
- staged asset streaming with deterministic LRU residency
- audio buses/groups and spatial attenuation
- deterministic networking, gameplay messages and RPC
- project/editor workflow with reversible playtest state
- native export manifests and PyInstaller desktop builds
- debug overlay and profiler

## Performance regression gates

SwirEngine keeps performance claims reproducible and workload-specific. Examples include:

- 1,000 compatible instanced objects -> one instanced draw
- 1,000-instance culling workload -> exactly 900 rejected in the test frustum
- 1,000 shader-variant resolves -> one compile + 999 cache hits
- 192×192 tilemap -> viewport-local cell work instead of whole-map scanning
- 10,000 dormant gameplay timers -> zero heap pops across idle updates
- 10,000 registered editor systems -> only the selected group is polled
- sparse 2D/3D collision workloads -> large broad-phase candidate reduction
- 1,024 terrain chunks -> a radius-2 focus scans only 25 local chunks; stationary frames reuse cached meshes
- terrain LOD0 512 triangles vs coarse LOD 8 triangles in the deterministic benchmark workload
- Physics 2.0 sparse-scene broad-phase and thin-wall CCD workloads -> dedicated deterministic regression gate
- Character Controllers 1.4 movement workload -> deterministic per-frame shape-sweep budget gate with FPS claims explicitly excluded

Host timings are diagnostics only. SwirEngine does **not** turn those numbers into unmeasured FPS claims.

## Validation demos and examples

- **Neon Frontier 1.3** — integrated 1.3 full-game/release validation
- **Neon Cube Hunt 3D** — OpenGL + packaged-runtime validation arena
- **Neon Snake 3D** — complete 3D Snake validation project
- **Terrain + World LOD 1.4** — real OpenGL heightmap/chunk/LOD/cache validation project
- `examples/demo_gpu_instancing.py`
- `examples/demo_skeletal_animation.py`
- `examples/demo_collision3d_physics.py`
- `examples/demo_navigation_pathfinding.py`
- `examples/demo_large_world_streaming.py`
- `examples/demo_terrain_world_lod.py`
- `examples/demo_physics2_contacts.py`
- `examples/demo_character_controllers.py`
- `examples/demo_shader_variants.py`
- `examples/demo_renderer2d_power.py`
- `examples/demo_gameplay_framework.py`
- `examples/demo_creator_editor_integration.py`

## Development and verification

```bash
python -m pip install -e ".[dev]"
pytest
ruff check src tests examples demo_projects tools
python -m compileall -q src examples demo_projects tools
python tools/verify_1_3_release_candidate.py --require-complete
```

Additional dedicated benchmarks and OpenGL validators live under `tools/` and are executed by GitHub Actions.

## Python 3.14 on Windows

Stable upstream native renderer dependencies do not expose the same wheel path for every Python/platform combination. SwirEngine therefore validates a dedicated `cp314-cp314-win_amd64` release candidate on Windows x86-64, checks metadata, proves normal pip candidate selection and performs native import validation. Linux/macOS remain on the explicitly verified Python 3.10-3.13 cross-platform matrix.

## Versioning and API stability

SwirEngine follows semantic versioning for the stable 1.x public API. Version 1.3.0 is additive to established 1.x behavior; existing projects are not required to adopt the new systems. The 1.4 development line remains unreleased until its guarded roadmap reaches 10/10.

See [`docs/API_STABILITY.md`](docs/API_STABILITY.md).

## 1.3 documentation

- [`docs/GPU_INSTANCING_1_3.md`](docs/GPU_INSTANCING_1_3.md)
- [`docs/SKELETAL_ANIMATION_1_3.md`](docs/SKELETAL_ANIMATION_1_3.md)
- [`docs/COLLISION_PHYSICS_1_3.md`](docs/COLLISION_PHYSICS_1_3.md)
- [`docs/NAVIGATION_PATHFINDING_1_3.md`](docs/NAVIGATION_PATHFINDING_1_3.md)
- [`docs/LARGE_WORLD_STREAMING_1_3.md`](docs/LARGE_WORLD_STREAMING_1_3.md)
- [`docs/ADVANCED_SHADER_MATERIAL_1_3.md`](docs/ADVANCED_SHADER_MATERIAL_1_3.md)
- [`docs/RENDERER_2D_POWER_1_3.md`](docs/RENDERER_2D_POWER_1_3.md)
- [`docs/ADVANCED_GAMEPLAY_FRAMEWORK_1_3.md`](docs/ADVANCED_GAMEPLAY_FRAMEWORK_1_3.md)
- [`docs/CREATOR_EDITOR_INTEGRATION_1_3.md`](docs/CREATOR_EDITOR_INTEGRATION_1_3.md)

## 1.4 development documentation

- [`docs/TERRAIN_WORLD_LOD_1_4.md`](docs/TERRAIN_WORLD_LOD_1_4.md) — milestone #1, verified
- [`docs/PHYSICS_2_1_4.md`](docs/PHYSICS_2_1_4.md) — milestone #2, verified
- [`docs/CHARACTER_CONTROLLERS_1_4.md`](docs/CHARACTER_CONTROLLERS_1_4.md) — milestone #3, verified

## Roadmaps

- SwirEngine 1.0 — [`ROADMAP.md`](ROADMAP.md) — **31/31 = 100%**, historical and locked
- SwirEngine 1.1 — [`ROADMAP_1_1.md`](ROADMAP_1_1.md) — **10/10 = 100%**, released and locked
- SwirEngine 1.2 — [`ROADMAP_1_2.md`](ROADMAP_1_2.md) — **10/10 = 100%**, released and locked
- SwirEngine 1.3 — [`ROADMAP_1_3.md`](ROADMAP_1_3.md) — **10/10 = 100.0%**, released and locked
- SwirEngine 1.4 — [`ROADMAP_1_4.md`](ROADMAP_1_4.md) — **3/10 = 30.0%**, active development

## Links

- PyPI: https://pypi.org/project/swirengine/
- Repository: https://github.com/Swir/SwirEngine
- Releases: https://github.com/Swir/SwirEngine/releases
- Changelog: https://github.com/Swir/SwirEngine/blob/main/CHANGELOG.md

## License

MIT
