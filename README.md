# SwirEngine 1.1.0

<p align="center">
  <a href="https://github.com/Swir/SwirEngine/actions/workflows/ci.yml"><img alt="CI" src="https://github.com/Swir/SwirEngine/actions/workflows/ci.yml/badge.svg"></a>
  <a href="https://pypi.org/project/swirengine/"><img alt="PyPI" src="https://img.shields.io/pypi/v/swirengine?style=flat-square"></a>
  <img alt="Python" src="https://img.shields.io/badge/Python-3.10--3.13%20cross--platform%20%7C%203.14%20Windows-3776AB?style=flat-square&logo=python&logoColor=white">
  <img alt="Status" src="https://img.shields.io/badge/status-stable-2ea043?style=flat-square">
  <img alt="License" src="https://img.shields.io/badge/license-MIT-blue?style=flat-square">
</p>

**SwirEngine** is a Python-first 2D/3D game engine built around one approachable API. It combines creator-friendly Python gameplay code with a real OpenGL renderer, scenes, prefabs/ECS, physics, animation, audio, editor tooling, networking, export and complete game demos.

The original 1.0 roadmap is complete at **31/31 deliverables**. SwirEngine 1.1 is the next stage: making complete games easier to control, animate, profile, optimize, package and ship without turning the engine into a thin wrapper around another framework.

> **Development policy:** the active 1.1 line is developed on `main`, but PyPI/GitHub Release publication is frozen until [`ROADMAP_1_1.md`](ROADMAP_1_1.md) reaches a verified 10/10 = 100%.

## Install

SwirEngine supports **Python 3.10-3.13** on Windows, Linux and macOS, plus **Python 3.14 on Windows x86-64**.

```bash
python -m pip install -U swirengine
```

On 64-bit Windows with Python 3.14:

```powershell
py -3.14 -m pip install -U swirengine
```

Optional audio support:

```bash
python -m pip install -U "swirengine[audio]"
```

### Python 3.14 native renderer support

The stable upstream `moderngl 5.12.0` and `glcontext 3.0.0` releases do not currently publish CPython 3.14 Windows x86-64 wheels. SwirEngine publishes a dedicated `cp314-cp314-win_amd64` wheel containing verified private copies of those native renderer components under `swirengine/_vendor_native`. A normal `pip install swirengine` on Windows x64 + Python 3.14 therefore does **not** require Microsoft Visual C++ Build Tools.

The platform wheel is rebuilt from upstream source in GitHub Actions, checked with `twine`, installed into a clean Python 3.14 environment and imported before Trusted Publishing is allowed to upload it. Python 3.10-3.13 continue using normal upstream dependencies. Linux and macOS remain on the verified 3.10-3.13 support window until equally reliable Python 3.14 binary dependencies exist there.

## SwirEngine 1.1 development

### Standardized gamepad/controller input

SwirEngine has a creator-facing controller layer on top of GLFW's standard gamepad mapping. Mapped Xbox, PlayStation and compatible controllers expose consistent names instead of forcing game code to depend on platform-specific joystick indexes.

The input layer provides deterministic discovery, controller name/GUID snapshots, held/pressed/released button queries, common aliases, left/right stick helpers, configurable deadzones, normalized triggers, hot-plug edges and automatic refresh in `Game.run()`.

### Semantic input actions, rebinding and control profiles

Games can bind keyboard, mouse, standardized gamepad buttons and directional analog axes to names such as `jump`, `fire` or `move_left`, then change those bindings from an in-game controls menu without rewriting gameplay code.

```python
from swirengine.input import InputActions

controls = InputActions(game.input)
controls.key("jump", "SPACE")
controls.gamepad_button("jump", "A")
controls.mouse_button("fire", 0)
controls.gamepad_axis("move_left", "left_x", direction=-1, threshold=0.25)

if controls.pressed("jump"):
    player.jump()

controls.save("settings/controls.json")
```

Bindings support held/pressed/released queries, analog values, duplicate-safe multi-binding, runtime replacement/removal and versioned JSON profiles. See [`docs/INPUT_ACTIONS.md`](docs/INPUT_ACTIONS.md).

### Static 3D larger-batch rendering

Static cube-heavy scenery can be baked into combined `Mesh3D` batches with `build_static_cube_batches(...)`. Compatible cubes are grouped by color, transforms are baked once into combined geometry, and the existing renderer submits one mesh draw per batch.

```python
from swirengine import Cube3D, Vec3
from swirengine.graphics.static_batch import build_static_cube_batches

walls = [Cube3D(position=Vec3(x * 2.0, 0.0, -12.0)) for x in range(100)]
batch = build_static_cube_batches(walls)
for mesh in batch.meshes:
    game.add(mesh)
```

The 100-cube regression case reduces renderer-facing object draws from **100 to 1 (99%)** without claiming an unmeasured FPS number. Translation, rotation, scale, UVs and transformed normals are baked correctly. See [`docs/STATIC_3D_BATCHING.md`](docs/STATIC_3D_BATCHING.md).

### Async/preload asset pipeline

Large scene transitions can preload filesystem/CPU asset work through a bounded worker pool rather than decoding every resource serially on the gameplay thread. `AssetPreloader` supports individual `load_async(...)` calls, whole-batch `preload(...)` / `preload_async(...)`, in-flight deduplication and deterministic timing/cache/error diagnostics.

```python
from swirengine.asset_pipeline import AssetPreloader
from swirengine.assets import AssetManager

assets = AssetManager("assets")
assets.register_loader("txt", lambda path: path.read_text(encoding="utf-8"))

with AssetPreloader(assets, max_workers=4) as preloader:
    report = preloader.preload([
        "levels/city.txt",
        "missions/chapter1.txt",
        "config/vehicles.txt",
    ])
```

GPU/context-owned uploads still belong on the render thread; background loading targets file I/O, parsing, decompression and thread-safe CPU-side decoding. See [`docs/ASYNC_ASSET_PIPELINE.md`](docs/ASYNC_ASSET_PIPELINE.md).

### Responsive UI layout and focus navigation

Menus and HUDs can opt into viewport anchors, reference-resolution scaling and vertical or horizontal containers instead of maintaining separate hard-coded coordinates for every resolution. `UIManager` integrates the layout pass with deterministic keyboard/gamepad focus and preserves existing pointer behavior.

```python
from swirengine import Game, UIAnchor, UILayout


game = Game("Responsive menu", 1280, 720)
play = game.button("Play", 0, 0, 260, 58)
options = game.button("Options", 0, 0, 260, 58)
game.ui.container(
    play,
    options,
    spacing=18,
    layout=UILayout(anchor=UIAnchor.CENTER, scale_with_viewport=True,
                    reference_width=1280, reference_height=720),
)
game.run()
```

Keyboard `Tab`/arrows and gamepad D-pad move focus; `Enter`/`Space` or standardized gamepad `A` activate the focused button. See [`docs/RESPONSIVE_UI.md`](docs/RESPONSIVE_UI.md).

### Expanded audio mixer

Audio can be organized into creator-defined buses such as weapons, dialogue, ambience or vehicles, with independent gain/mute controls composed with the existing master/sound/music volumes. Handles support deterministic fade-in/fade-out/fade-to transitions driven by `AudioEngine.update(dt)` and optional stop-on-fade behavior.

Spatial handles use listener-relative distance attenuation and optional stereo panning on capable backends, while scalar-only custom backends remain compatible. `audio.diagnostics()` reports active, music, spatial and fading handle counts together with bus/mute state. See [`docs/AUDIO_MIXER.md`](docs/AUDIO_MIXER.md).

### Animation, tweens, timelines and gameplay state machines

SwirEngine 1.1 includes one deterministic animation runtime shared by 2D, 3D, UI and gameplay code instead of forcing each subsystem to invent its own interpolation/update loop.

`Tween` interpolates numeric values and common engine value types through property paths, with delay, easing, repeat and yoyo behavior. `TweenSequence` chains motion or UI beats, while `AnimationTimeline` runs tracks in parallel, exposes deterministic event markers for gameplay/VFX/audio synchronization and supports seeking. `StateMachine` adds prioritized transitions, wildcard transitions, enter/update/exit callbacks and `time_in_state` for explicit gameplay state flow. `AnimationSystem` owns and updates these pieces through one creator-facing surface.

```python
from swirengine.animation import AnimationSystem, Tween, TweenSequence, ease_in_out_quad

animations = AnimationSystem()
animations.add(
    TweenSequence(
        Tween(player, "position.x", 8.0, 0.6, easing=ease_in_out_quad),
        Tween(player, "rotation.y", 180.0, 0.35),
    )
)

# In the gameplay update loop:
animations.update(dt)
```

This layer is designed for camera moves, UI transitions, scripted sequences, enemy/player states and ordinary 2D/3D object animation while keeping the stable 1.x API additive. See [`docs/ANIMATION_RUNTIME.md`](docs/ANIMATION_RUNTIME.md) and `examples/demo_animation_runtime.py`.

### Spatial collision broad phase and richer queries

`CollisionWorld2D` now uses a tunable spatial-hash broad phase before AABB narrow-phase checks, so sparse worlds no longer need to test every possible collider pair. The index is rebuilt from live bounds before public queries, which preserves existing 1.x behavior for moving targets without requiring manual synchronization.

```python
from swirengine import AABB, BoxCollider2D, CollisionWorld2D, Rectangle2D

world = CollisionWorld2D(cell_size=64)
player = world.add(BoxCollider2D(Rectangle2D(0, 0, 32, 32), tag="player"))
world.add(BoxCollider2D(Rectangle2D(24, 0, 32, 32), tag="enemy"))

nearby = world.overlap_aabb(AABB(0, 0, 256, 256), tag="enemy")
hits = world.raycast(0, 0, 1, 0, max_distance=1000)
```

The collision API also exposes point queries, region overlap queries, nearest-first ray hits and operation diagnostics with broad-phase candidate and actual narrow-phase-test counts. The deterministic 1,000-collider regression case requires at least a **100x candidate reduction** versus all-pairs enumeration; this is a workload reduction measurement, not an FPS claim. See [`docs/PHYSICS_BROADPHASE.md`](docs/PHYSICS_BROADPHASE.md) and `examples/demo_collision_queries.py`.

## Quick 2D game

```python
from swirengine import Color, Game, Rectangle2D


game = Game("My 2D Game", 1280, 720, mode="2d")
player = game.add(Rectangle2D(0, 0, 120, 70, Color(0.1, 0.75, 1.0, 1.0), name="player"))

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

## Engine capabilities

### 2D runtime

- textured `Sprite2D` rendering with alpha blending
- colored primitives and render layers
- `Camera2D` movement, zoom and follow workflows
- sprite sheets and named `AnimatedSprite2D` clips
- tilemaps backed by pooled sprites
- cached text rendering and bounded LRU text-texture cache
- responsive labels, panels, buttons and progress bars with anchors/containers/reference scaling
- keyboard/mouse/gamepad focus navigation and UI activation
- particles
- spatial-hash AABB collision broad phase with overlap, point and ray queries
- deterministic fixed-step arcade rigid-body physics
- JSON save data through `SaveStore`
- keyboard, mouse, standardized gamepad input, semantic actions and persistent rebinding profiles
- adjacent compatible sprite batching
- single-pass render-run construction with cached canonical texture keys
- shared tween/timeline/state-machine animation runtime

### 3D runtime

- perspective `Camera3D`
- `MeshData`, `Mesh3D` and lazy GPU mesh caching
- OBJ import with triangulation, normals and UVs
- static glTF/GLB scene and material import
- Phong and Cook-Torrance GGX metallic/roughness PBR
- base-color, metallic/roughness, normal, occlusion and emissive material channels
- directional, point and spot lights with deterministic GPU budgets and diagnostics
- skybox/environment support and true cubemap image-based lighting
- directional GPU shadows, post-processing, ACES/Reinhard tone mapping and FXAA
- sRGB/linear color-space handling for PBR material channels
- bounded transform-matrix caching for repeated static object transforms
- static cube larger-batch path with explicit draw-call reduction metrics
- shared tween/timeline/state-machine animation runtime

### Performance foundation

The renderer avoids repeated texture-path resolution in steady-state 2D batching and builds render runs in one pass instead of allocating a second visible-object tuple. Repeated static 3D transforms use a bounded matrix cache while callers still receive independent mutable matrix results.

For repeated level geometry, `build_static_cube_batches(...)` moves transform work out of the frame loop and combines compatible static cubes into renderer-native `Mesh3D` batches. The regression suite verifies that 100 same-color cubes map from 100 object draws to one combined draw.

The async asset pipeline moves thread-safe file/CPU decoding work out of serial scene-transition loading and reports the measured wait component separately. CI includes a reproducible synthetic I/O-like benchmark that must demonstrate a real overlap win without turning that measurement into an end-to-end FPS claim.

The 2D collision world uses a spatial hash to reduce pair and local-overlap candidate sets before narrow-phase intersection tests. A deterministic sparse-world regression with 1,000 colliders guards against accidentally returning to brute-force all-pairs scaling.

### Architecture and game systems

- scene names, tags and creator-friendly lookup/removal helpers
- reusable prefabs and per-instance overrides
- versioned scene/prefab JSON serialization
- safe codec registry and cyclic reference preservation
- lightweight ECS with entities, components, queries and prioritized systems
- plugin runtime and polling file watcher/plugin hot reload
- transactional multi-domain state restore/rollback
- asset hot reload bridges for renderer and audio
- bounded asynchronous asset preload with deterministic diagnostics and in-flight deduplication
- responsive UI containers with keyboard/gamepad focus navigation
- audio buses/groups, deterministic fades, spatial attenuation/pan and runtime diagnostics
- deterministic tweens, sequences, parallel timelines, event markers and gameplay state machines
- spatial-hash collision diagnostics, overlap/point/raycast queries and layer/tag filters
- `LiveDevelopmentHub`
- pluggable sound effects and music backend

### Visual editor foundation

- project/workspace state
- hierarchy and inspector
- unified undo/redo
- component editing
- mixed object/entity parenting and reordering
- persistent hierarchy state
- asset browser
- console and profiler panels
- move/rotate/scale gizmos with snapping
- viewport picking and direct manipulation
- interactive Tk editor frontend
- isolated Play/Edit runtime session
- embedded live renderer preview

### Networking and export

- deterministic length-prefixed JSON packets
- non-blocking TCP client/server peers
- packaging profiles
- Windows, Linux and macOS PyInstaller build plans
- Android and Web experimental staging targets
- machine-readable export manifests

## Project generator

```bash
swirengine new MyGame --mode 2d
swirengine new My3DGame --mode 3d
swirengine info
```

Generated projects declare compatibility with the stable engine line:

```toml
engine = ">=1.0,<2.0"
```

## Export

Create a deterministic export/staging directory:

```bash
swirengine export . --target windows --name MyGame --onefile --windowed
```

Desktop targets expose the native PyInstaller command instead of silently invoking third-party build tools. Android and Web remain experimental staging/research targets.

## Diagnostics

Enable the built-in debug overlay before `game.run()`:

```python
game.show_debug()
```

It exposes FPS, frame/CPU timings, update/physics/render timings, draw calls, batches, sprites, triangles, light usage and dropped-light counts. Programmatic profiling is available through `game.profiler`.

## Official demo projects and examples

- **Neon Cube Hunt 3D** — 3D collection arena used for real OpenGL and packaged-runtime testing
- **Neon Snake 3D** — complete 3D Snake with growth, food, collision, score, PBR and post-processing
- `examples/demo_gamepad.py` — controller + keyboard-fallback input example
- `examples/demo_static_3d_batching.py` — 200-cube static larger-batch rendering example
- `examples/demo_async_assets.py` — background/preload loading workflow with timing diagnostics
- `examples/demo_responsive_ui.py` — resize-aware menu with keyboard/gamepad focus navigation
- `examples/demo_animation_runtime.py` — tween/sequence/timeline/state-machine runtime example
- `examples/demo_collision_queries.py` — spatial collision overlap, point/raycast and diagnostics example
- larger asset-free 2D samples under `examples/`

The Windows demo build pipeline also probes the final packaged GLFW runtime so missing native libraries are caught before demo publication.

## Development and verification

```bash
python -m pip install -e ".[dev]"
pytest
ruff check src tests examples demo_projects tools
python -m compileall -q src examples demo_projects tools
```

CI validates SwirEngine on:

- Windows, Linux and macOS with Python 3.10, 3.11, 3.12 and 3.13
- Windows x86-64 with Python 3.14
- wheel/sdist packaging and metadata
- clean-wheel installation
- a dedicated CPython 3.14 Windows platform-wheel build, pip-selection and native import test
- reproducible performance gates for static 3D frame preparation and async preload wait reduction
- real OpenGL paths through the official 3D demo workflows

## Versioning and API stability

SwirEngine follows semantic versioning for the stable 1.x public API. The exported `swirengine.__all__` surface is treated as a compatibility contract. User-visible changes are expected to update code, tests, README and changelog together. PyPI/GitHub Release publication for the active 1.1 roadmap remains frozen until all 10 deliverables are verified complete.

See [`docs/API_STABILITY.md`](docs/API_STABILITY.md) for the compatibility policy.

## Roadmap

The original SwirEngine 1.0 roadmap remains complete and historical:

```text
████████████████████ 100.0%
31 / 31 deliverables complete
```

The active expansion plan lives in [`ROADMAP_1_1.md`](ROADMAP_1_1.md). The historical 1.0 dashboard is kept in [`ROADMAP.md`](ROADMAP.md) and is not artificially increased beyond 100%.

## Links

- PyPI: https://pypi.org/project/swirengine/
- Repository: https://github.com/Swir/SwirEngine
- Releases: https://github.com/Swir/SwirEngine/releases
- 1.0 roadmap: https://github.com/Swir/SwirEngine/blob/main/ROADMAP.md
- 1.1 roadmap: https://github.com/Swir/SwirEngine/blob/main/ROADMAP_1_1.md
- Changelog: https://github.com/Swir/SwirEngine/blob/main/CHANGELOG.md

## License

MIT
