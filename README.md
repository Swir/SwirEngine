# SwirEngine 1.2.0

<p align="center">
  <a href="https://github.com/Swir/SwirEngine/actions/workflows/ci.yml"><img alt="CI" src="https://github.com/Swir/SwirEngine/actions/workflows/ci.yml/badge.svg"></a>
  <a href="https://pypi.org/project/swirengine/"><img alt="PyPI" src="https://img.shields.io/pypi/v/swirengine?style=flat-square"></a>
  <img alt="Python" src="https://img.shields.io/badge/Python-3.10--3.13%20cross--platform%20%7C%203.14%20Windows-3776AB?style=flat-square&logo=python&logoColor=white">
  <img alt="Status" src="https://img.shields.io/badge/status-stable-2ea043?style=flat-square">
  <img alt="License" src="https://img.shields.io/badge/license-MIT-blue?style=flat-square">
</p>

**SwirEngine** is a Python-first 2D/3D game engine built around an approachable API. It combines Python gameplay code with a real OpenGL renderer, scenes, prefabs/ECS, physics, animation, audio, responsive UI, input rebinding, gameplay networking, asset streaming, native desktop export and complete 3D validation demos.

SwirEngine **1.2.0** is the current stable release candidate for the final publication gate. The historical 1.0 roadmap is locked at **31/31 = 100%**, the released 1.1 roadmap is locked at **10/10 = 100%**, and the 1.2 roadmap is now verified at **10/10 = 100%** in [`ROADMAP_1_2.md`](ROADMAP_1_2.md). Publication remains gated by the final exact-head CI/runtime/demo/packaging checks and public-artifact post-release verification.

## Install

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

## What 1.2 adds

SwirEngine 1.2 is additive and preserves compatibility-sensitive 1.x behavior while filling major engine-level gaps beyond a low-level game library.

### Particle/VFX runtime

`ParticleEmitter2D` adds point/box/circle/ring emission, lifetime color/size curves, drag, rotation/angular velocity and deterministic diagnostics. Sparse active-index updates avoid scanning a full particle pool every frame. The regression case uses capacity **10,000** with **8 live particles** and requires exactly **8 update visits** per measured frame.

See [`docs/PARTICLES_VFX_1_2.md`](docs/PARTICLES_VFX_1_2.md) and `examples/demo_particles_vfx.py`.

### Font assets and cached text layout

`FontAsset`, `FontFamily`, `FontRegistry`, `TextStyle` and `TextLayoutEngine` provide fallback families, wrapping, long-word splitting, alignment, line spacing and bounded LRU diagnostics. After the first layout, **1,000 identical requests** must be cache hits with zero extra measurement calls.

See [`docs/TEXT_FONT_PIPELINE_1_2.md`](docs/TEXT_FONT_PIPELINE_1_2.md) and `examples/demo_text_layout.py`.

### Shared 2D/3D camera systems

`CameraRig2D` and `CameraRig3D` provide world bounds, time-step-aware smoothing, deterministic decaying shake and multi-segment rails. The 2D rig adds dead-zone follow; the 3D rig preserves active view direction while moving the camera.

See [`docs/CAMERA_SYSTEMS_1_2.md`](docs/CAMERA_SYSTEMS_1_2.md) and `examples/demo_camera_systems.py`.

### Typed settings, migrations and profile saves

The stable `SaveStore` API remains compatible. The opt-in 1.2 storage layer adds `SettingSpec`, `SettingsSchema`, versioned `SettingsStore`, deterministic `MigrationRegistry`, traversal-safe `ProfileStore` / `ProfilePaths`, independent save slots and stronger atomic writes using same-directory temporary files, `fsync` and `os.replace`.

See [`docs/SAVE_CONFIG_1_2.md`](docs/SAVE_CONFIG_1_2.md) and `examples/demo_save_config.py`.

### Gameplay networking

The existing framed `NetworkPacket`/`TCPPeer` transport remains compatible. `GameplaySession` adds named gameplay messages, ordered routing, explicit RPC registration, bounded RPC results, connection lifecycle state and deterministic diagnostics. RPC never resolves arbitrary Python attributes or globals from remote input.

See [`docs/NETWORK_GAMEPLAY_1_2.md`](docs/NETWORK_GAMEPLAY_1_2.md) and `examples/demo_network_gameplay.py`.

### Scene, prefab and ECS ergonomics

Scenes gain lifecycle hooks, cached update snapshots and grouped mounts. `Scene.compose_entity()` creates component bundles in one call; indexed `ECSWorld.query()` narrows iteration while retaining deterministic insertion order and subclass-aware lookup; system order is cached until registration changes; `Prefab.instantiate_many()` adds deterministic batch spawning.

The regression case creates **1,000 `Position`-only entities plus one `Position + Velocity` entity** and requires the mixed query to visit exactly **one indexed candidate**.

See [`docs/SCENE_ECS_ERGONOMICS_1_2.md`](docs/SCENE_ECS_ERGONOMICS_1_2.md) and `examples/demo_scene_ecs_ergonomics.py`.

### Budgeted asset streaming

`AssetStreamingManager` and `AssetStreamingBudget` add staged background file/decode work, game-thread finalization through nonblocking `pump()`, deterministic LRU residency, count/byte budgets, pin/unpin/touch/evict controls and hitch/residency diagnostics. Resident-byte totals are maintained incrementally, so diagnostics and budget checks are **O(1)** with respect to resident asset count.

GPU/context-owned uploads remain on the owning render thread.

See [`docs/ASSET_STREAMING_1_2.md`](docs/ASSET_STREAMING_1_2.md) and `examples/demo_asset_streaming.py`.

### Renderer and VFX frame-work reduction

The renderer performance pass reduces repeated Python work without changing draw order or claiming an unmeasured FPS uplift. Repeatable 2D scene lists stream render runs instead of allocating a second frame-sized outer tuple, stable sprite batch keys use a bounded cache, valid immutable colors reuse identity, and particle range sampling avoids temporary sorted lists.

Regression coverage checks a **512-sprite** streamed run and **1,000 repeated stable state/color operations** for cache/identity reuse. Host-dependent timings remain diagnostic rather than fixed FPS claims.

See [`docs/RENDERER_VFX_PERFORMANCE_1_2.md`](docs/RENDERER_VFX_PERFORMANCE_1_2.md) and `tools/benchmark_renderer_vfx_framework.py`.

### Native desktop build/export hardening

Desktop staging produces deterministic manifest v2 integrity hashes and a generated `swirengine-build.spec`. `ProjectExporter.build_native()` explicitly runs PyInstaller only when host and requested Windows/Linux/macOS target match. Entrypoints/includes/icons reject absolute or parent-traversal paths, while assets, scenes and dynamically loaded scripts remain bundled.

The shipping workflow builds and launches **one-file and one-directory executables on Windows, Linux and macOS** and validates packaged resource access.

```bash
swirengine export . --target windows --name MyGame --onefile --windowed
swirengine export . --target windows --name MyGame --onefile --windowed --build-native
```

See [`docs/BUILD_EXPORT_1_2.md`](docs/BUILD_EXPORT_1_2.md), `examples/demo_export_pipeline.py` and `tools/verify_desktop_export.py`.

### Creator hardening and release contract

The final 1.2 gate cross-checks roadmap math, package metadata, Python support, public API anchors, documentation, complete demo projects, performance gates and publication safety. Normal CI runs the active 1.2 contract; the release workflow additionally requires exactly **10/10 = 100%** and version **1.2.0** before any package can be published.

PyPI uses GitHub OIDC Trusted Publishing. After publication, a separate matrix waits for the public PyPI metadata, installs `swirengine==1.2.0` from `https://pypi.org/simple` rather than the checkout, validates version/core API, then runs representative runtime smoke on Linux and Windows CPython 3.14.

See [`docs/CREATOR_HARDENING_1_2.md`](docs/CREATOR_HARDENING_1_2.md).

## Engine capabilities

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

### Production systems

- scenes with names/tags, lifecycle hooks, cached update snapshots and grouped mounts
- reusable prefabs, overrides, deterministic batch spawning and versioned serialization
- indexed lightweight ECS with composition helpers, deterministic queries and cached prioritized systems
- plugin runtime, file watcher and transactional hot-reload restoration
- budgeted staged asset streaming with in-flight deduplication, deterministic LRU residency and diagnostics
- audio buses/groups, fades and spatial attenuation/pan
- font fallback registry and cached text-layout diagnostics
- typed settings, deterministic migrations and profile-oriented save layout
- project-oriented editor workflow with reversible playtest state
- deterministic TCP transport plus gameplay messages, explicit RPC and session diagnostics
- deterministic export manifests, generated desktop specs and explicit native builds
- debug overlay and programmatic profiler

## Performance regression gates

SwirEngine keeps performance claims narrow and reproducible:

- **static 3D batching:** 100 compatible static cubes map from 100 renderer-facing object draws to one combined mesh draw
- **async preload:** a reproducible synthetic I/O-like benchmark must demonstrate real overlap/wait reduction
- **asset streaming residency:** exact incremental byte accounting is verified through eviction
- **2D collision:** a sparse 1,000-collider case must reduce broad-phase candidates by at least 100x versus brute-force all-pairs enumeration
- **particle/VFX:** 10,000 capacity with eight live particles must perform exactly eight update visits
- **text layout:** after first layout, 1,000 identical requests must hit cache with zero additional measurement calls
- **indexed ECS:** a 1,001-entity mixed query must reduce candidates to exactly one
- **renderer/VFX frame work:** a 512-sprite repeatable run streams without an outer cache and stable state/color operations reuse cached objects

These are workload/regression measurements, not synthetic FPS promises.

## Project generator and export

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

Android and Web remain experimental staging/research targets until their shipping paths are fully verified.

## Official validation demos and examples

- **Neon Cube Hunt 3D** — 3D collection arena used for real OpenGL and packaged-runtime validation
- **Neon Snake 3D** — complete 3D Snake with growth, food, collision, score, PBR and post-processing
- `examples/demo_gamepad.py` — controller + keyboard fallback
- `examples/demo_static_3d_batching.py` — static larger-batch rendering
- `examples/demo_async_assets.py` — background/preload diagnostics
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
```

CI validates:

- Windows, Linux and macOS with Python 3.10, 3.11, 3.12 and 3.13
- Windows x86-64 with Python 3.14
- wheel/sdist metadata and clean-wheel installation
- dedicated Windows CPython 3.14 native dependency/wheel selection and import checks
- one-file and one-directory desktop executables on Windows/Linux/macOS Python 3.13
- reproducible performance/regression gates
- real OpenGL paths through both official 3D demo workflows

## Versioning and API stability

SwirEngine follows semantic versioning for the stable 1.x public API. Existing 1.x behavior remains compatibility-sensitive and the 1.2 production systems are additive. User-visible work keeps code, tests, README, CHANGELOG and focused examples/documentation aligned.

The 1.2 roadmap is complete; publication is controlled by the exact-head final gate and Trusted Publishing workflow rather than by another version bump. See [`docs/API_STABILITY.md`](docs/API_STABILITY.md) and [`docs/CREATOR_HARDENING_1_2.md`](docs/CREATOR_HARDENING_1_2.md).

## Roadmap

- SwirEngine 1.0: [`ROADMAP.md`](ROADMAP.md) — **31/31 = 100%**, historical and locked
- SwirEngine 1.1: [`ROADMAP_1_1.md`](ROADMAP_1_1.md) — **10/10 = 100%**, released
- SwirEngine 1.2: [`ROADMAP_1_2.md`](ROADMAP_1_2.md) — **10/10 = 100.0%**, complete and in final release verification

## Links

- PyPI: https://pypi.org/project/swirengine/
- Repository: https://github.com/Swir/SwirEngine
- Releases: https://github.com/Swir/SwirEngine/releases
- Changelog: https://github.com/Swir/SwirEngine/blob/main/CHANGELOG.md

## License

MIT
