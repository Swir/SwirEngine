# SwirEngine 1.1.0

<p align="center">
  <a href="https://github.com/Swir/SwirEngine/actions/workflows/ci.yml"><img alt="CI" src="https://github.com/Swir/SwirEngine/actions/workflows/ci.yml/badge.svg"></a>
  <a href="https://pypi.org/project/swirengine/"><img alt="PyPI" src="https://img.shields.io/pypi/v/swirengine?style=flat-square"></a>
  <img alt="Python" src="https://img.shields.io/badge/Python-3.10--3.13%20cross--platform%20%7C%203.14%20Windows-3776AB?style=flat-square&logo=python&logoColor=white">
  <img alt="Status" src="https://img.shields.io/badge/status-stable-2ea043?style=flat-square">
  <img alt="License" src="https://img.shields.io/badge/license-MIT-blue?style=flat-square">
</p>

**SwirEngine** is a Python-first 2D/3D game engine built around an approachable API. It combines Python gameplay code with a real OpenGL renderer, scenes, prefabs/ECS, physics, animation, audio, responsive UI, input rebinding, editor tooling, networking foundations, export workflows and complete 3D validation demos.

SwirEngine **1.1.0** is the current stable release. The historical 1.0 roadmap is locked at **31/31 = 100%**, the released 1.1 roadmap is locked at **10/10 = 100%**, and active 1.2 development is tracked in [`ROADMAP_1_2.md`](ROADMAP_1_2.md).

> **1.2 release freeze:** no SwirEngine 1.2 package, tag or GitHub Release is published until the active roadmap reaches a verified **10/10 = 100%** and the final CI/runtime/demo/packaging gate succeeds.

## Install

Verified support currently covers **Python 3.10-3.13** on Windows, Linux and macOS, plus **Python 3.14 on Windows x86-64**.

```bash
python -m pip install -U swirengine
```

Optional audio support:

```bash
python -m pip install -U "swirengine[audio]"
```

### Python 3.14 on Windows

Stable upstream `moderngl 5.12.0` and `glcontext 3.0.0` do not currently provide the Windows x86-64 CPython 3.14 wheel combination required by the normal dependency path. SwirEngine therefore verifies a dedicated `cp314-cp314-win_amd64` dependency build in GitHub Actions, checks metadata, proves pip selects it from normal candidates and performs native import validation. Linux/macOS remain on Python 3.10-3.13 until equivalent binary dependency support is reproducibly verified.

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

## SwirEngine 1.2 development

The active 1.2 line is additive and preserves compatibility-sensitive 1.x behavior.

### Particle/VFX runtime

`ParticleEmitter2D` supports point/box/circle/ring emission regions, color and size interpolation over lifetime, drag, rotation/angular velocity and deterministic diagnostics. Sparse active-index updates avoid scanning the full particle pool every frame. The regression case uses capacity **10,000** with **8 live particles** and requires exactly **8 update visits per measured frame** rather than 10,000 pool visits. This is a measured Python-side workload reduction, not an unmeasured FPS claim.

See [`docs/PARTICLES_VFX_1_2.md`](docs/PARTICLES_VFX_1_2.md) and `examples/demo_particles_vfx.py`.

### Font assets and cached text layout

`FontAsset`, `FontFamily` and `FontRegistry` define project fonts and ordered fallback coverage. `TextStyle` and `TextLayoutEngine` add newline preservation, bounded-width wrapping, safe splitting of long words, left/center/right alignment and line spacing while materializing ordinary renderer-native `Text2D` runs.

A bounded LRU layout cache exposes diagnostics for requests, hits, misses, evictions and measurement work. After the first layout, the regression suite requires **1,000 identical requests** to be cache hits with **zero additional measurement calls**.

See [`docs/TEXT_FONT_PIPELINE_1_2.md`](docs/TEXT_FONT_PIPELINE_1_2.md) and `examples/demo_text_layout.py`.

### Shared 2D/3D camera systems

Additive `CameraRig2D` and `CameraRig3D` controllers provide world bounds, time-step-aware exponential smoothing, deterministic decaying shake and multi-segment rails. The 2D rig adds dead-zone follow; the 3D rig preserves active view direction while the rig moves the camera.

```python
from swirengine.graphics.camera import Camera2D
from swirengine.graphics.camera_runtime import CameraBounds2D, CameraRail2D, CameraRig2D
from swirengine.math.types import Vec2

camera = Camera2D()
rig = CameraRig2D(
    camera,
    smoothing=8.0,
    dead_zone=Vec2(6.0, 4.0),
    bounds=CameraBounds2D(-20.0, -12.0, 20.0, 12.0),
)
rail = CameraRail2D((Vec2(-12.0, 0.0), Vec2(0.0, 6.0), Vec2(12.0, 0.0)))
rig.move_on_rail(rail, 0.5, 1.0 / 60.0)
rig.shake(1.5, 0.35, frequency=14.0, seed=42.0)
```

See [`docs/CAMERA_SYSTEMS_1_2.md`](docs/CAMERA_SYSTEMS_1_2.md) and `examples/demo_camera_systems.py`.

### Typed settings, migrations and profile saves

The stable `SaveStore` API and its plain-object JSON format remain compatible. SwirEngine 1.2 adds an opt-in production storage layer:

- `SettingSpec` and `SettingsSchema` for typed defaults, allowed choices and numeric bounds
- `SettingsStore` with explicit format/version envelopes, reset/update helpers and diagnostics
- `MigrationRegistry` with required one-version-at-a-time transforms before current-schema validation
- `ProfileStore` / `ProfilePaths` for traversal-safe profiles and independent save slots
- a cloud-sync-friendly layout separating `settings.json` from `saves/<slot>.json`
- stronger atomic writes using a unique same-directory temporary file, flush + `fsync`, then `os.replace`

```python
from swirengine.storage import ProfileStore, SettingSpec, SettingsSchema

schema = SettingsSchema(
    {
        "volume": SettingSpec(0.8, (int, float), minimum=0.0, maximum=1.0),
        "difficulty": SettingSpec("normal", str, choices=("easy", "normal", "hard")),
        "fullscreen": SettingSpec(False, bool),
    }
)

profile = ProfileStore("user-data", "player-01")
settings = profile.settings(schema, version=1, autoload=False)
settings.update({"volume": 0.65, "difficulty": "hard"}).save()
profile.save_slot("slot-1", autoload=False).update({"level": 8}).save()
```

Future-version settings files are rejected instead of silently losing data; missing migration steps fail explicitly. Profile/slot tokens reject path traversal. See [`docs/SAVE_CONFIG_1_2.md`](docs/SAVE_CONFIG_1_2.md) and `examples/demo_save_config.py`.

### Gameplay networking

The existing framed `NetworkPacket`/`TCPPeer` transport remains compatible. SwirEngine 1.2 adds `GameplaySession` for deterministic game-loop networking, named `GameplayMessage` events, ordered `MessageRouter` dispatch, an explicit `RPCRegistry`, bounded RPC result buffering, connection lifecycle state and deterministic `NetworkDiagnostics` counters.

```python
from swirengine import GameplaySession

session = GameplaySession(peer)
session.router.on("player.spawn", lambda message: print(message.payload))
session.rpc.register("score.add", lambda payload: payload["current"] + payload["points"])

session.send("player.spawn", {"player_id": 7})
request_id = session.call_rpc("score.add", {"current": 100, "points": 25})
session.update()
```

RPC methods must be registered explicitly: remote data is never used for arbitrary Python attribute/global lookup. Networking remains polling-based and thread-free, so handler execution stays ordered relative to the simulation loop. See [`docs/NETWORK_GAMEPLAY_1_2.md`](docs/NETWORK_GAMEPLAY_1_2.md) and `examples/demo_network_gameplay.py`.

### Scene, prefab and ECS ergonomics

SwirEngine 1.2 expands scene composition without replacing the stable scene/prefab/ECS APIs. Ordinary scene objects can opt into `on_added_to_scene`, `on_start`, `on_stop` and `on_removed_from_scene` lifecycle hooks. `Scene.update()` reuses a cached stable update snapshot until scene membership changes, with `SceneDiagnostics` exposing snapshot rebuilds and actual object updates.

`Scene.mount()` / `SceneMount` provide idempotent grouped ownership for rooms, encounters and streamed chunks. `Scene.compose_entity()` creates component bundles in one call, while indexed `ECSWorld.query()` narrows iteration to compatible component candidates and still preserves deterministic entity insertion order and subclass-aware component lookup. System ordering is cached until registration changes, and optional world lifecycle hooks make systems easier to compose. `Prefab.instantiate_many()` adds deterministic batch spawning with independent per-instance overrides.

The regression case creates **1,000 `Position`-only entities plus one `Position + Velocity` entity** and requires `query(Position, Velocity)` to visit exactly **one indexed candidate**, rather than checking all 1,001 entities. This is a measured reduction in Python-side query work, not an FPS claim.

See [`docs/SCENE_ECS_ERGONOMICS_1_2.md`](docs/SCENE_ECS_ERGONOMICS_1_2.md) and `examples/demo_scene_ecs_ergonomics.py`.

### Budgeted asset streaming

`AssetStreamingManager` builds staged loading and deterministic residency on top of the existing `AssetManager` / `AssetPreloader` APIs. File/decode work runs through the background preloader while the game loop controls finalization with nonblocking `pump(max_completions=...)` calls.

`AssetStreamingBudget` caps resident asset count and estimated resident bytes. The residency set uses deterministic LRU eviction with explicit `touch()`, `pin()`, `unpin()` and `evict()` controls, while `AssetStreamingDiagnostics` reports pending/completed/failed work, residency, evictions, peak memory and finalize hitches. Resident-byte totals are maintained incrementally, so diagnostics and byte-budget checks are **O(1)** with respect to the number of resident assets rather than rescanning the complete LRU set.

GPU/context-owned uploads remain on the owning game/render thread; background workers are for file/decode work. See [`docs/ASSET_STREAMING_1_2.md`](docs/ASSET_STREAMING_1_2.md) and `examples/demo_asset_streaming.py`.

### Renderer and VFX frame-work reduction

The 1.2 renderer performance pass removes repeated Python-side work without changing draw order or claiming a synthetic FPS uplift. Repeatable 2D scene lists now stream render runs instead of first allocating a second outer frame-sized run tuple. Immutable sprite batch-state keys are reused through a bounded cache across stable frames, already-valid immutable `Color.clamped()` calls return the same object, and particle range sampling no longer creates a temporary `sorted()` list for every sampled lifetime/speed/angle/size/rotation value.

Regression coverage requires a **512-sprite** repeatable render-run view to be consumed without materializing an outer cache, and **1,000 repeated stable sprite-state lookups** to produce one miss plus 1,000 cache hits with object-identity reuse. The valid-color fast path is likewise checked for **1,000 identity-preserving calls**. Host-dependent timings remain diagnostic rather than fixed CI thresholds.

See [`docs/RENDERER_VFX_PERFORMANCE_1_2.md`](docs/RENDERER_VFX_PERFORMANCE_1_2.md) and run `python tools/benchmark_renderer_vfx_framework.py` for local measurements.

### Native desktop build/export hardening

Desktop staging now produces a portable `swirengine-build.spec` plus export-manifest format v2 with deterministic SHA-256 hashes for every staged input. `ProjectExporter.build_native()` is an explicit opt-in that executes PyInstaller only when the requested Windows/Linux/macOS target matches the current host. Staging-only `export()` remains the default, so existing 1.x workflows do not unexpectedly execute build tools.

Project assets, scenes and dynamically loaded scripts are preserved in the generated bundle. Entrypoints, includes and icons reject absolute/parent-traversal paths. The dedicated desktop shipping workflow builds **both one-file and one-directory executables on Windows, Linux and macOS**, launches the artifact, imports SwirEngine from inside the package and verifies bundled asset/script access. This validation targets Python 3.13 across all three desktop OSes; the separate Windows CPython 3.14 engine-wheel gate remains distinct.

```bash
swirengine export . --target windows --name MyGame --onefile --windowed
swirengine export . --target windows --name MyGame --onefile --windowed --build-native
```

See [`docs/BUILD_EXPORT_1_2.md`](docs/BUILD_EXPORT_1_2.md), `examples/demo_export_pipeline.py` and `tools/verify_desktop_export.py`.

## Engine capabilities

### 2D

- sprites, textures, render layers, sprite sheets and named animation clips
- tilemaps plus adjacent compatible sprite batching with streamed repeatable run preparation
- responsive labels/panels/buttons/progress bars with anchors and containers
- keyboard/mouse/gamepad focus navigation and semantic input actions
- persistent input rebinding profiles
- sparse pooled particles/VFX and diagnostics
- bounded/smoothed camera rigs, dead-zone follow, rails and deterministic shake
- spatial-hash AABB broad phase, overlap/point/ray queries and fixed-step arcade physics
- typed/versioned settings, migrations, profiles and independent save slots
- deterministic tween/timeline/state-machine animation runtime

### 3D

- perspective cameras plus bounded/smoothed camera rigs, rails and deterministic shake
- `MeshData`, `Mesh3D`, lazy GPU mesh caching and OBJ import
- static glTF/GLB scene/material import
- Phong and Cook-Torrance GGX metallic/roughness PBR
- base-color, metallic/roughness, normal, occlusion and emissive material channels
- directional, point and spot lights with deterministic GPU budgets
- skybox/environment support and cubemap image-based lighting
- directional GPU shadows, post-processing, tone mapping and FXAA
- sRGB/linear color-space handling
- bounded transform caching and static cube larger-batch rendering

### Production systems

- scenes with names/tags, lifecycle hooks, cached update snapshots and grouped mounts
- reusable prefabs, per-instance overrides, deterministic batch spawning and versioned serialization
- indexed lightweight ECS with composition helpers, deterministic queries and cached prioritized systems
- plugin runtime, file watcher and transactional hot-reload restoration
- budgeted staged asset streaming with in-flight deduplication, deterministic LRU residency, pinning and diagnostics
- audio buses/groups, fades and spatial attenuation/pan
- font fallback registry and cached text-layout diagnostics
- typed settings, deterministic migrations and profile-oriented save layout
- project-oriented editor workflow with reversible playtest state
- deterministic TCP transport plus gameplay messages, explicit RPC and session diagnostics
- deterministic export manifests, generated desktop build specs, explicit native builds and cross-platform shipping smoke gates
- debug overlay and programmatic profiler

## Performance regression gates

SwirEngine keeps performance claims narrow and reproducible:

- **static 3D batching:** 100 compatible static cubes map from 100 renderer-facing object draws to one combined mesh draw
- **async preload:** a reproducible synthetic I/O-like benchmark must demonstrate real overlap/wait reduction
- **asset streaming residency:** resident-byte accounting is maintained incrementally so diagnostics and byte-budget checks do not sum the full residency set; regression coverage verifies exact accounting through explicit eviction
- **2D collision:** a sparse 1,000-collider case must reduce broad-phase candidates by at least 100x versus brute-force all-pairs enumeration
- **particle/VFX:** a 10,000-capacity pool with eight live particles must perform exactly eight update visits per measured frame
- **text layout:** after the first layout, 1,000 identical requests must hit cache with zero additional measurement calls
- **indexed ECS:** a 1,001-entity mixed-component regression must reduce `Position + Velocity` query candidates to exactly one
- **renderer/VFX frame work:** a 512-sprite repeatable run must stream without an outer cache; after first resolution, 1,000 stable sprite-state lookups and 1,000 already-valid color clamps must reuse cached/identity objects

These are workload/regression measurements, not synthetic FPS promises.

## Project generator and export

```bash
swirengine new MyGame --mode 2d
swirengine new My3DGame --mode 3d
swirengine info
swirengine export . --target windows --name MyGame --onefile --windowed
# Explicit native compilation; run on a host matching the target:
swirengine export . --target windows --name MyGame --onefile --windowed --build-native
```

Generated projects declare compatibility with the stable engine line:

```toml
engine = ">=1.0,<2.0"
```

Desktop targets provide deterministic staging, manifest integrity hashes and generated PyInstaller specs. Native compilation is explicit and host-matched rather than pretending to cross-compile. Android and Web remain experimental staging/research targets until their shipping paths are fully verified.

## Official validation demos and examples

- **Neon Cube Hunt 3D** — 3D collection arena used for real OpenGL and packaged-runtime validation
- **Neon Snake 3D** — complete 3D Snake with growth, food, collision, score, PBR and post-processing
- `examples/demo_gamepad.py` — controller + keyboard fallback
- `examples/demo_static_3d_batching.py` — static larger-batch rendering
- `examples/demo_async_assets.py` — background/preload diagnostics
- `examples/demo_asset_streaming.py` — staged loading, residency budgets, eviction and hitch diagnostics
- `examples/demo_responsive_ui.py` — resize-aware UI and focus navigation
- `examples/demo_animation_runtime.py` — tween/sequence/timeline/state machine
- `examples/demo_collision_queries.py` — spatial collision queries and diagnostics
- `examples/demo_editor_workflow.py` — scene/prefab/input/playtest workflow
- `examples/demo_particles_vfx.py` — sparse pooled particle lifecycle
- `examples/demo_text_layout.py` — fallback, wrapping, alignment and cache diagnostics
- `examples/demo_camera_systems.py` — camera rail/smoothing/shake workflow
- `examples/demo_save_config.py` — typed settings, profile layout and save slots
- `examples/demo_network_gameplay.py` — deterministic messages, RPC and diagnostics
- `examples/demo_scene_ecs_ergonomics.py` — lifecycle, mounts, indexed queries and prefab waves
- `examples/demo_export_pipeline.py` — manifest v2, integrity hashes and generated native spec

## Development and verification

```bash
python -m pip install -e ".[dev]"
pytest
ruff check src tests examples demo_projects tools
python -m compileall -q src examples demo_projects tools
```

CI validates:

- Windows, Linux and macOS with Python 3.10, 3.11, 3.12 and 3.13
- Windows x86-64 with Python 3.14
- wheel/sdist metadata and clean-wheel installation
- dedicated Windows CPython 3.14 dependency/native-wheel selection and import checks
- real one-file and one-directory desktop executable builds on Windows/Linux/macOS Python 3.13, including packaged-resource runtime smoke
- reproducible performance/regression gates
- real OpenGL paths through the official 3D demo workflows

## Versioning and API stability

SwirEngine follows semantic versioning for the stable 1.x public API. Existing 1.x behavior remains compatibility-sensitive and new production systems are additive. User-visible work is expected to keep code, tests, README, CHANGELOG and focused examples/documentation aligned.

PyPI/GitHub Release publication for active 1.2 remains frozen until all 10 roadmap deliverables are verified complete. See [`docs/API_STABILITY.md`](docs/API_STABILITY.md).

## Roadmap

- SwirEngine 1.0: [`ROADMAP.md`](ROADMAP.md) — **31/31 = 100%**, historical and locked
- SwirEngine 1.1: [`ROADMAP_1_1.md`](ROADMAP_1_1.md) — **10/10 = 100%**, released
- SwirEngine 1.2: [`ROADMAP_1_2.md`](ROADMAP_1_2.md) — **9/10 = 90.0%**, active development roadmap

## Links

- PyPI: https://pypi.org/project/swirengine/
- Repository: https://github.com/Swir/SwirEngine
- Releases: https://github.com/Swir/SwirEngine/releases
- Changelog: https://github.com/Swir/SwirEngine/blob/main/CHANGELOG.md

## License

MIT
