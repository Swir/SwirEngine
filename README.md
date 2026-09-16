# SwirEngine 1.4.0

<p align="center">
  <a href="https://github.com/Swir/SwirEngine/actions/workflows/ci.yml"><img alt="CI" src="https://github.com/Swir/SwirEngine/actions/workflows/ci.yml/badge.svg"></a>
  <a href="https://github.com/Swir/SwirEngine/actions/workflows/release-readiness-1-4.yml"><img alt="1.4 Release Readiness" src="https://github.com/Swir/SwirEngine/actions/workflows/release-readiness-1-4.yml/badge.svg"></a>
  <a href="https://pypi.org/project/swirengine/"><img alt="PyPI" src="https://img.shields.io/pypi/v/swirengine?style=flat-square"></a>
  <img alt="Python" src="https://img.shields.io/badge/Python-3.10--3.13%20cross--platform%20%7C%203.14%20Windows-3776AB?style=flat-square&logo=python&logoColor=white">
  <img alt="1.4 roadmap" src="https://img.shields.io/badge/1.4%20ROADMAP-100%25-2ea043?style=flat-square">
  <img alt="Status" src="https://img.shields.io/badge/status-1.4%20technical%20release%20candidate-2ea043?style=flat-square">
  <img alt="License" src="https://img.shields.io/badge/license-MIT-blue?style=flat-square">
</p>

**SwirEngine 1.4.0** is the completed **Production World & Engine Power** line of a Python-first 2D/3D game engine with a stable 1.x compatibility baseline. The technical 1.4 roadmap is **10/10 = 100.0%** and the final non-publishing validation matrix is green. Publication to PyPI/GitHub Release remains a separate explicit guarded action and is not implied by this repository state.

```text
████████████████████ 100.0% — 10/10
```

SwirEngine combines an approachable Python gameplay API with real OpenGL rendering, 2D/3D scene systems, terrain/world streaming, Physics 2.0, character controllers, GPU VFX, asset processing, scene acceleration, editor authoring, Multiplayer 2.0, native desktop export and deterministic regression/performance gates.

## Install

Verified support covers **Python 3.10-3.13** on Windows, Linux and macOS, plus **Python 3.14 on Windows x86-64** through the dedicated native-wheel path.

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

## What shipped in 1.4

### 1. Terrain + World LOD

- immutable heightmaps and chunk mesh generation
- distance-based LOD and bounded local chunk selection
- reusable terrain mesh cache and terrain material/splat metadata
- heightfield collision queries
- direct integration with `LargeWorldStreamer`
- deterministic cache/LOD contracts and real OpenGL terrain validation

### 2. Physics 2.0

- additive `PhysicsScene3D` / `PhysicsBody3D` APIs
- deterministic box/sphere contacts
- friction, restitution, shape sweeps and optional continuous collision handling
- distance joints, sleeping/wake behavior and diagnostics
- backend-ready public protocol while preserving the established 1.x physics path

### 3. Character Controllers

- first-person, third-person and platformer controller presets
- grounded state, jumping, coyote time and jump buffering
- step-up, slope handling and ground snapping
- camera synchronization/collision
- semantic input actions and navigation-provider steering
- deterministic shape-sweep performance budget

### 4. Renderer 2.0

- opt-in `Renderer2`, `Renderer2Settings` and `Decal3D`
- one-to-four-cascade directional shadows with stabilization and PCF
- sampleable depth/view-normal prepass
- SSAO, HDR bloom, decals, ACES tone mapping and deterministic pass diagnostics
- real Mesa/OpenGL 3.3 execution coverage

### 5. GPU VFX + Particle Power

- `GPUParticleEmitter3D` and `Game.gpu_particles(...)`
- OpenGL 3.3 transform-feedback ping-pong simulation
- point/box/sphere emission with gravity, drag, lifetime and color/size evolution
- sprite, textured, additive/alpha, geometry-trail and instanced-mesh paths
- bounded scheduler diagnostics without per-particle Python update work

### 6. Asset Pipeline 2.0

- bounded background import with caller-thread finalization
- SHA-256 source/dependency fingerprints
- transitive hot-reload and cache invalidation
- persistent content-addressed derived asset cache
- dependency-aware glTF/GLB processing and stronger PBR preservation
- conservative mesh/texture optimization and creator diagnostics

### 7. Scene Acceleration + Occlusion

- conservative world AABBs and deterministic static BVH
- dynamic-refit layer and cached scene-membership synchronization
- broad frustum pruning and additive Renderer2 candidate views
- CPU Hi-Z reference queries
- real GPU maximum-depth Hi-Z pyramid with no CPU readback
- 16,384-object deterministic workload with only 32 leaf tests in the validation layout

### 8. Editor Authoring Power

- ordered multi-select with range/add/toggle modes
- grouped property, gizmo and asset edits
- transaction-safe undo/redo
- persistent authoring sidecars and safe drag-and-drop asset paths
- material, physics and navigation inspector adapters
- explicit Play/Edit authoring isolation
- opt-in `swirengine.editor14` public facade

### 9. Multiplayer 2.0

- replicated-component schemas
- canonical snapshots and sparse deltas
- bounded out-of-order interpolation
- deterministic client prediction and authoritative reconciliation
- bounded server rewind foundations
- per-channel bandwidth diagnostics
- stable `NetworkPacket` bridge and `swirengine.multiplayer14` facade

### 10. Integrated showcase + hardening + guarded release gate

`demo_projects/showcase_1_4/run_game.py` exercises terrain, world streaming, Physics 2.0 character movement, Renderer 2.0 configuration, GPU VFX, editor authoring and Multiplayer 2.0 in one deterministic scenario. The final matrix validates the headless path, a real Mesa/OpenGL 3.3 Renderer2/VFX path, all nine 1.4 deterministic performance contracts, package build/Twine metadata, clean-wheel installation, cross-platform CI, native desktop export, legacy 1.x compatibility and the Windows CPython 3.14 native wheel.

The production release workflow is guarded by:

```bash
python tools/verify_1_4_release_candidate.py --require-complete
```

No publication is performed by the normal CI or 1.4 readiness workflow.

## Integrated 1.4 showcase

Headless deterministic validation:

```bash
python demo_projects/showcase_1_4/run_game.py
```

Real Renderer2/VFX validation on a machine with an OpenGL 3.3 display, or under Mesa/Xvfb:

```bash
SWIR_1_4_SHOWCASE_RENDER=1 SWIR_1_4_SHOWCASE_FRAMES=12 \
  xvfb-run -a python demo_projects/showcase_1_4/run_game.py
```

See [`docs/SHOWCASE_1_4.md`](docs/SHOWCASE_1_4.md) for the complete integration contract.

## Validation philosophy

SwirEngine keeps performance claims workload-specific and reproducible. Host timings are diagnostics unless a benchmark defines a deterministic threshold; the project does not turn host-side benchmark numbers into unsupported FPS claims.

Current 1.4 gates cover:

- full pytest + Ruff + compileall across the supported OS/Python matrix
- all nine deterministic 1.4 performance workloads
- real Mesa/OpenGL 3.3 Renderer2, GPU VFX and Hi-Z execution
- integrated headless and rendered 1.4 showcase paths
- wheel/sdist build, Twine checks and clean-wheel imports
- Windows, Linux and macOS native one-file/one-directory export smoke coverage
- Windows x86-64 CPython 3.14 native renderer dependency wheel selection
- historical 1.3 compatibility through **Neon Frontier 1.3** and its packaged/runtime gates

## Stable 1.x feature set

### 2D

- sprites, textures, layers, sprite sheets and animation
- tilemaps, batching and viewport culling
- responsive labels, panels, buttons and progress bars
- keyboard, mouse and gamepad input with rebinding
- particles/VFX, camera rigs and collision queries
- settings, profiles, save slots and serialization
- tween/timeline/state-machine animation runtime

### 3D

- perspective cameras and camera rigs
- mesh primitives, OBJ and glTF/GLB import
- Phong and Cook-Torrance GGX metallic/roughness PBR
- directional, point and spot lights
- skybox/environment cubemaps and IBL
- directional shadows, post-processing and FXAA
- GPU instancing, skeletal animation and GPU skinning
- legacy 1.x collision/physics plus additive Physics 2.0
- navigation, terrain, large-world streaming and scene acceleration
- Renderer 2.0, GPU VFX and controlled shader/material variants

### Production systems

- scenes, lifecycle hooks, prefabs and versioned serialization
- indexed ECS
- plugin runtime and transactional hot reload
- staged asset streaming plus Asset Pipeline 2.0
- audio buses/groups and spatial attenuation
- deterministic networking plus Multiplayer 2.0
- editor/project workflow with reversible playtest state
- native export manifests and PyInstaller desktop builds
- debug overlay and profiler

## What shipped in 1.3

**SwirEngine 1.3.0** established the locked Gameplay & Creator Power compatibility baseline. Its roadmap remains **10/10 = 100.0%** and is intentionally preserved while 1.4 extends the engine additively.

The 1.3 line delivered GPU instancing and frustum culling, skeletal animation, 3D collision/physics foundations, navigation/pathfinding, large-world chunk streaming, controlled shader/material variants, stronger 2D rendering, advanced gameplay utilities, creator/editor integration and the integrated **Neon Frontier 1.3** validation game. The historical release contract remains active in CI so 1.4 cannot silently regress the completed 1.3 API/runtime surface.

## Documentation

- [`ROADMAP_1_4.md`](ROADMAP_1_4.md) — completed 1.4 roadmap
- [`docs/RELEASE_READINESS_1_4.md`](docs/RELEASE_READINESS_1_4.md) — final technical release contract
- [`docs/SHOWCASE_1_4.md`](docs/SHOWCASE_1_4.md) — integrated production showcase
- [`docs/TERRAIN_WORLD_LOD_1_4.md`](docs/TERRAIN_WORLD_LOD_1_4.md)
- [`docs/PHYSICS_2_1_4.md`](docs/PHYSICS_2_1_4.md)
- [`docs/CHARACTER_CONTROLLERS_1_4.md`](docs/CHARACTER_CONTROLLERS_1_4.md)
- [`docs/RENDERER2_1_4.md`](docs/RENDERER2_1_4.md)
- [`docs/GPU_VFX_PARTICLES_1_4.md`](docs/GPU_VFX_PARTICLES_1_4.md)
- [`docs/ASSET_PIPELINE_2_1_4.md`](docs/ASSET_PIPELINE_2_1_4.md)
- [`docs/SCENE_ACCELERATION_OCCLUSION_1_4.md`](docs/SCENE_ACCELERATION_OCCLUSION_1_4.md)
- [`docs/EDITOR_AUTHORING_1_4.md`](docs/EDITOR_AUTHORING_1_4.md)
- [`docs/MULTIPLAYER_2_1_4.md`](docs/MULTIPLAYER_2_1_4.md)

## Release safety

The repository can be technically ready at 1.4.0 without automatically publishing anything. PyPI Trusted Publishing and GitHub Release creation remain behind the production workflow and its strict 10/10 release verifier. A release tag or explicit publication trigger is still required; normal pull-request validation cannot publish.

## License

MIT.
