# SwirEngine 1.4.0

<p align="center">
  <a href="https://github.com/Swir/SwirEngine/actions/workflows/ci.yml"><img alt="CI" src="https://github.com/Swir/SwirEngine/actions/workflows/ci.yml/badge.svg"></a>
  <a href="https://pypi.org/project/swirengine/"><img alt="PyPI" src="https://img.shields.io/pypi/v/swirengine?style=flat-square"></a>
  <img alt="Python" src="https://img.shields.io/badge/Python-3.10--3.13%20cross--platform%20%7C%203.14%20Windows-3776AB?style=flat-square&logo=python&logoColor=white">
  <img alt="1.4 roadmap" src="https://img.shields.io/badge/1.4%20ROADMAP-100%25-2ea043?style=flat-square">
  <img alt="Status" src="https://img.shields.io/badge/status-1.4%20stable-2ea043?style=flat-square">
  <img alt="License" src="https://img.shields.io/badge/license-MIT-blue?style=flat-square">
</p>

**SwirEngine 1.4.0** is the Production World & Engine Power release line of a Python-first 2D/3D game engine with a stable 1.x compatibility contract. It combines an approachable gameplay API with a real OpenGL renderer, production-oriented world systems, physics, character controllers, GPU VFX, scalable visibility, asset processing, editor authoring, multiplayer foundations and native desktop export.

The 1.4 roadmap is complete at **10/10 = 100.0%** and **v1.4.0 is published**. The release workflow gates the GitHub Release behind the PyPI publishing stage and follows publication with clean public-index installation checks, while preserving the strict CI/runtime/packaging and tag/version contracts used to close the roadmap.

```text
████████████████████ 100.0% — 10/10
```

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

## What is new in 1.4

### 1. Terrain + World LOD

- immutable heightmaps and chunk mesh generation
- distance-based LOD with bounded local chunk selection
- terrain material/splat metadata and heightfield ground queries
- direct `LargeWorldStreamer` integration
- deterministic cache/LOD performance contracts and real OpenGL validation

### 2. Physics 2.0

- additive `PhysicsScene3D` / `PhysicsBody3D` APIs
- deterministic box/sphere contact generation and response
- friction, restitution, sleeping/wake behavior and distance joints
- shape sweeps and continuous-collision foundations
- backend-ready public protocol while preserving established 1.x physics APIs

### 3. Character Controllers

- production `CharacterController3D`
- first-person, third-person and platformer presets
- grounded state, jumping, coyote time and jump buffering
- step-up, slope handling and ground snapping
- camera collision/synchronization and navigation steering

### 4. Renderer 2.0

- opt-in `Renderer2`, `Renderer2Settings` and `Decal3D`
- one-to-four cascade directional shadows with texel stabilization and 3×3 PCF
- depth/view-normal prepass and SSAO with depth-aware blur
- HDR bloom and bounded screen-space decals
- deterministic frame-pass diagnostics
- real EGL/OpenGL 3.3 execution validation

### 5. GPU VFX + Particle Power

- `GPUParticleEmitter3D` and `Game.gpu_particles(...)`
- OpenGL 3.3 transform-feedback ping-pong simulation
- point, box and sphere emitters
- GPU gravity, drag, lifetime, size and color evolution
- HDR textured sprite particles, alpha/additive blending and trails
- built-in instanced mesh-particle rendering

### 6. Asset Pipeline 2.0

- bounded background import with caller-thread finalization
- SHA-256 source/dependency fingerprints
- transitive hot-reload and cache invalidation
- persistent content-addressed derived artifacts
- dependency-aware glTF/GLB processing
- stronger PBR preservation, conservative mesh cleanup and opt-in texture optimization

### 7. Scene Acceleration + Occlusion

- deterministic static BVH and separate dynamic-refit layer
- conservative world AABBs and broad frustum pruning
- `SceneAcceleratedRenderer2` candidate-view integration
- CPU Hi-Z reference queries
- real OpenGL 3.3 GPU maximum-depth pyramid without CPU readback
- deterministic 16,384-object validation workload

### 8. Editor Authoring Power

- ordered multi-selection with replace/add/toggle/range behavior
- grouped property, gizmo and asset authoring
- transaction-safe undo/redo and persistent authoring sidecars
- safe asset drag/drop paths
- material, physics and navigation inspector adapters
- explicit Play/Edit authoring isolation
- opt-in `swirengine.editor14` creator-facing facade

### 9. Multiplayer 2.0

- replicated-component schemas
- canonical snapshots and sparse deltas
- bounded out-of-order interpolation
- deterministic client prediction and reconciliation
- bounded server rewind foundations
- per-channel bandwidth diagnostics
- stable `NetworkPacket` bridge

### 10. Showcase + hardening + release gate

**Neon Frontier 1.4** is the integrated release-validation project. It intentionally uses generated geometry/data so source checkouts, CI and packaged probes do not depend on external game assets. A single application exercises terrain/LOD, Physics 2.0, Character Controllers, Renderer 2.0, GPU VFX, large-world streaming, Editor Authoring and Multiplayer 2.0.

The final hardening path validates:

- deterministic headless full-system integration
- the integrated performance budget
- real Linux OpenGL 3.3 execution under Xvfb/Mesa
- clean wheel installation outside the source tree
- Windows one-file `NeonFrontier14.exe` packaging and runtime probing
- Python 3.10-3.13 cross-platform compatibility plus the Windows CPython 3.14 native-wheel path
- strict 10/10 version/roadmap/release-workflow consistency
- Trusted Publishing to PyPI without duplicate-artifact masking
- post-publication installation from public PyPI before the release is considered complete

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
- mesh primitives, OBJ and glTF/GLB import
- Phong and Cook-Torrance GGX metallic/roughness PBR
- directional, point and spot lights
- skybox/environment cubemaps and IBL
- cascaded directional shadows, SSAO, bloom, decals, tone mapping and FXAA
- GPU instancing, frustum culling and scene acceleration
- skeletal animation and GPU skinning
- 3D collision, Physics 2.0 and character controllers
- deterministic navigation and large-world chunk residency
- terrain/LOD and GPU particle/VFX systems
- controlled shader/material variants

### Production systems

- scenes, lifecycle hooks, grouped mounts and cached update snapshots
- prefabs, overrides, batch spawning and versioned serialization
- lightweight indexed ECS
- plugin runtime and transactional hot reload
- Asset Pipeline 2.0 with derived caching and dependency invalidation
- audio buses/groups and spatial attenuation
- stable networking plus opt-in Multiplayer 2.0 replication foundations
- creator/editor workflow with advanced authoring and reversible playtest state
- native export manifests and PyInstaller desktop builds
- debug overlay and profiler

## Performance regression policy

SwirEngine keeps performance claims reproducible and workload-specific. The repository contains deterministic contracts for terrain locality/LOD, Physics 2.0 broad-phase/CCD behavior, controller sweep budgets, Renderer 2.0 planning, GPU-particle CPU scheduling, Asset Pipeline 2.0 cold/warm/invalidation behavior, scene-visibility pruning, editor multi-selection authoring, Multiplayer 2.0 snapshot/delta workloads and the final integrated showcase.

Host timings are diagnostics only. SwirEngine does **not** turn host-side timing numbers into unmeasured FPS claims. GPU correctness is validated separately with real OpenGL smoke tests.

## Validation demos and examples

- **Neon Frontier 1.4** — integrated 1.4 release validation
- **Neon Frontier 1.3** — locked 1.3 regression game
- **Neon Cube Hunt 3D** — OpenGL + packaged-runtime regression arena
- **Neon Snake 3D** — complete 3D regression project
- [`examples/2d_game_demo/`](examples/2d_game_demo/) — source-only classic platformer showcase
- [`examples/3d_game_demo/`](examples/3d_game_demo/) — source-only classic corridor-FPS showcase
- `examples/demo_terrain_world_lod.py`
- `examples/demo_physics2_contacts.py`
- `examples/demo_character_controllers.py`
- `examples/demo_renderer2_1_4.py`
- `examples/demo_gpu_particles_1_4.py`
- `examples/demo_asset_pipeline2.py`
- `examples/demo_scene_acceleration_1_4.py`
- `examples/demo_editor_authoring_1_4.py`
- `examples/demo_multiplayer_2_1_4.py`

## Development and verification

```bash
python -m pip install -e ".[dev]"
pytest
ruff check src tests examples demo_projects tools
python -m compileall -q src examples demo_projects tools
python tools/verify_1_4_release_candidate.py --require-complete
```

Dedicated milestone benchmarks, OpenGL validators, clean-wheel checks and native packaging probes live under `tools/` and `.github/workflows/`.

## API stability

SwirEngine follows semantic versioning for the stable 1.x public API. Version 1.4.0 is additive to established 1.x behavior: existing projects are not required to adopt Renderer 2.0, Physics 2.0, the 1.4 editor facade or Multiplayer 2.0. Historical 1.0-1.3 roadmaps remain locked.

See [`docs/API_STABILITY.md`](docs/API_STABILITY.md).

## 1.4 documentation

- [`docs/TERRAIN_WORLD_LOD_1_4.md`](docs/TERRAIN_WORLD_LOD_1_4.md)
- [`docs/PHYSICS_2_1_4.md`](docs/PHYSICS_2_1_4.md)
- [`docs/CHARACTER_CONTROLLERS_1_4.md`](docs/CHARACTER_CONTROLLERS_1_4.md)
- [`docs/RENDERER2_1_4.md`](docs/RENDERER2_1_4.md)
- [`docs/GPU_VFX_PARTICLES_1_4.md`](docs/GPU_VFX_PARTICLES_1_4.md)
- [`docs/ASSET_PIPELINE_2_1_4.md`](docs/ASSET_PIPELINE_2_1_4.md)
- [`docs/SCENE_ACCELERATION_OCCLUSION_1_4.md`](docs/SCENE_ACCELERATION_OCCLUSION_1_4.md)
- [`docs/EDITOR_AUTHORING_1_4.md`](docs/EDITOR_AUTHORING_1_4.md)
- [`docs/MULTIPLAYER_2_1_4.md`](docs/MULTIPLAYER_2_1_4.md)
- [`docs/RELEASE_HARDENING_1_4.md`](docs/RELEASE_HARDENING_1_4.md)

## Roadmaps

- SwirEngine 1.0 — [`ROADMAP.md`](ROADMAP.md) — **31/31 = 100%**, historical and locked
- SwirEngine 1.1 — [`ROADMAP_1_1.md`](ROADMAP_1_1.md) — **10/10 = 100%**, released and locked
- SwirEngine 1.2 — [`ROADMAP_1_2.md`](ROADMAP_1_2.md) — **10/10 = 100%**, released and locked
- SwirEngine 1.3 — [`ROADMAP_1_3.md`](ROADMAP_1_3.md) — **10/10 = 100%**, released and locked
- SwirEngine 1.4 — [`ROADMAP_1_4.md`](ROADMAP_1_4.md) — **10/10 = 100.0%**, released and locked

## Links

- PyPI: https://pypi.org/project/swirengine/
- Repository: https://github.com/Swir/SwirEngine
- Releases: https://github.com/Swir/SwirEngine/releases
- Changelog: https://github.com/Swir/SwirEngine/blob/main/CHANGELOG.md

## License

MIT
