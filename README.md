# SwirEngine 1.1.0

<p align="center">
  <a href="https://github.com/Swir/SwirEngine/actions/workflows/ci.yml"><img alt="CI" src="https://github.com/Swir/SwirEngine/actions/workflows/ci.yml/badge.svg"></a>
  <a href="https://pypi.org/project/swirengine/"><img alt="PyPI" src="https://img.shields.io/pypi/v/swirengine?style=flat-square"></a>
  <img alt="Python" src="https://img.shields.io/badge/Python-3.10--3.13%20cross--platform%20%7C%203.14%20Windows-3776AB?style=flat-square&logo=python&logoColor=white">
  <img alt="Status" src="https://img.shields.io/badge/status-stable-2ea043?style=flat-square">
  <img alt="License" src="https://img.shields.io/badge/license-MIT-blue?style=flat-square">
</p>

**SwirEngine** is a Python-first 2D/3D game engine built around one approachable API. It combines creator-friendly Python gameplay code with a real OpenGL renderer, scenes, prefabs/ECS, physics, animation, audio, UI, editor tooling, networking, export workflows and complete game demos.

The historical 1.0 roadmap is complete at **31/31 = 100%**, and SwirEngine 1.1 is released at **10/10 = 100%**. Active development follows the consciously planned 1.2 roadmap while preserving the stable public 1.x API.

> **Development policy:** PyPI/GitHub Release publication for 1.2 is frozen until [`ROADMAP_1_2.md`](ROADMAP_1_2.md) reaches a verified **10/10 = 100%** with full CI/runtime/demo/packaging validation.

## Install

SwirEngine currently verifies **Python 3.10-3.13** on Windows, Linux and macOS, plus **Python 3.14 on Windows x86-64**.

```bash
python -m pip install -U swirengine
```

Optional audio support:

```bash
python -m pip install -U "swirengine[audio]"
```

### Python 3.14 Windows renderer support

Stable upstream `moderngl 5.12.0` and `glcontext 3.0.0` do not currently provide the Windows x86-64 CPython 3.14 wheel combination required by the normal dependency path. SwirEngine therefore builds a dedicated `cp314-cp314-win_amd64` wheel from upstream sources in GitHub Actions, checks its metadata, proves pip selects it in a clean Python 3.14 environment and performs native import validation before release publication is allowed.

Linux and macOS remain on the verified Python 3.10-3.13 support window until equally reliable Python 3.14 binary dependency support is available there.

## SwirEngine 1.1 foundation

The released 1.1 line established the production foundation used by 1.2:

- standardized gamepad/controller input and hot-plug snapshots
- semantic input actions, rebinding and persistent versioned control profiles
- static 3D larger-batch rendering with measured draw-work reduction
- bounded asynchronous/preload asset pipeline and load diagnostics
- responsive UI anchors/containers/reference scaling plus keyboard/gamepad focus navigation
- audio buses, fades, spatial attenuation/pan and mixer diagnostics
- deterministic tweens, sequences, timelines, event markers and gameplay state machines
- spatial-hash 2D collision broad phase with overlap, point and nearest-first ray queries
- project-oriented editor scene/prefab/input workflow with reversible Play/Edit state
- creator hardening, official 3D demo validation and verified release gate

See the completed [`ROADMAP_1_1.md`](ROADMAP_1_1.md) and the focused documentation under [`docs/`](docs/).

## SwirEngine 1.2 development

### Sparse pooled particle/VFX runtime

`ParticleEmitter2D` keeps the existing 1.x constructor contract while adding point/box/circle/ring emission regions, color and size interpolation over lifetime, drag, initial rotation, angular velocity and deterministic diagnostics.

The runtime tracks active particle indexes instead of scanning the full pool each frame, and its renderer-facing `children` tuple is cached instead of rebuilt on every access. In the regression case, a capacity of **10,000** with **8 live particles** requires exactly **8 update visits per frame**, rather than 10,000 pool visits. This is a measured Python-side workload reduction for sparse pools, not an end-to-end FPS claim.

```python
from swirengine import Color
from swirengine.particles import ParticleEmissionShape2D, ParticleEmitter2D

sparks = ParticleEmitter2D(
    640,
    360,
    max_particles=2048,
    rate=220,
    end_color=Color(1.0, 0.1, 0.0, 0.0),
    end_size_scale=0.1,
    drag=1.2,
    emission_shape=ParticleEmissionShape2D.RING,
    emission_size=(34, 34),
)
```

See [`docs/PARTICLES_VFX_1_2.md`](docs/PARTICLES_VFX_1_2.md) and `examples/demo_particles_vfx.py`.

### Font assets, fallback families and cached text layout

SwirEngine 1.2 adds a layout layer above the existing renderer-native `Text2D` primitive instead of replacing the stable 1.x text API. `FontAsset`, `FontFamily` and `FontRegistry` describe project fonts and ordered Unicode fallback coverage. `TextStyle` and `TextLayoutEngine` add explicit newline preservation, bounded-width word wrapping, safe splitting of overlong words, left/center/right alignment and configurable line spacing.

```python
from swirengine.text import (
    FontAsset,
    FontFamily,
    FontRegistry,
    TextAlign,
    TextLayoutEngine,
    TextStyle,
)

fonts = FontRegistry()
fonts.register(
    FontFamily(
        "hud",
        (
            FontAsset("assets/fonts/Inter-Regular.ttf", "latin", ((0x20, 0x024F),)),
            FontAsset(
                "assets/fonts/NotoSansCyrillic-Regular.ttf",
                "cyrillic",
                ((0x0400, 0x052F),),
            ),
        ),
    )
)

text = TextLayoutEngine(fonts)
layout = text.layout(
    "Mission update: Привет! Collect all energy cells.",
    TextStyle(
        family="hud",
        font_size=24,
        max_width=420,
        align=TextAlign.LEFT,
    ),
)
scene.add_many(*text.text_objects(layout, -200, 180, screen_space=True, layer=1500))
```

Layout results are immutable and cached through a bounded LRU. `TextLayoutDiagnostics` exposes requests, hits, misses, evictions, cache entries, measurement calls and fallback switches. The regression suite performs one layout and then **1,000 identical requests**; all 1,000 repeats must hit the cache with **zero additional measurement calls**. This is a measured reduction in repeated Python-side layout/measurement work, not an FPS claim.

`text_objects(...)` materializes ordinary `Text2D` runs, so scene ownership and the existing renderer stay compatible with 1.x. See [`docs/TEXT_FONT_PIPELINE_1_2.md`](docs/TEXT_FONT_PIPELINE_1_2.md) and `examples/demo_text_layout.py`.

## Quick 2D game

```python
from swirengine import Color, Game, Rectangle2D


game = Game("My 2D Game", 1280, 720, mode="2d")
player = game.add(
    Rectangle2D(0, 0, 120, 70, Color(0.1, 0.75, 1.0, 1.0), name="player")
)

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
cube = game.add(
    Cube3D(position=Vec3(0, 0, -4), color=Color(0.2, 0.7, 1.0, 1.0))
)

@game.update
def update(dt):
    cube.rotation.y += 50 * dt
    cube.rotation.x += 25 * dt

game.run()
```

## Engine capabilities

### 2D runtime

- textured `Sprite2D` rendering with alpha blending, render layers and camera workflows
- sprite sheets, named `AnimatedSprite2D` clips and pooled tilemaps
- renderer text-texture caching plus 1.2 font-family fallback and cached wrapping/layout
- responsive labels, panels, buttons and progress bars with anchors/containers/reference scaling
- keyboard/mouse/gamepad focus navigation and activation
- sparse pooled particle/VFX runtime with lifecycle interpolation and diagnostics
- spatial-hash AABB collision broad phase with overlap, point and ray queries
- deterministic fixed-step arcade rigid-body physics
- JSON save data through `SaveStore`
- keyboard, mouse, standardized gamepad input, semantic actions and persistent rebinding profiles
- adjacent compatible sprite batching and single-pass render-run construction
- shared tween/timeline/state-machine animation runtime

### 3D runtime

- perspective `Camera3D`
- `MeshData`, `Mesh3D`, lazy GPU mesh caching and OBJ import
- static glTF/GLB scene and material import
- Phong and Cook-Torrance GGX metallic/roughness PBR
- base-color, metallic/roughness, normal, occlusion and emissive material channels
- directional, point and spot lights with deterministic GPU budgets and diagnostics
- skybox/environment support and cubemap image-based lighting
- directional GPU shadows, post-processing, ACES/Reinhard tone mapping and FXAA
- sRGB/linear color-space handling for PBR material channels
- bounded transform-matrix caching and static cube larger-batch path
- shared tween/timeline/state-machine animation runtime

### Architecture and production systems

- scene names/tags and creator-friendly lookup/removal helpers
- reusable prefabs and per-instance overrides
- versioned scene/prefab JSON serialization and codec registry
- lightweight ECS with entities, components, queries and prioritized systems
- plugin runtime, file watcher and transactional hot-reload state restoration
- renderer/audio live-asset reload bridges
- bounded asynchronous asset preload with diagnostics and in-flight deduplication
- audio mixer buses/groups, fades and spatial audio controls
- font asset/fallback registry plus deterministic cached text layout diagnostics
- project-oriented scene/prefab/input editor workflow with reversible playtest state
- deterministic networking packet foundation and TCP client/server peers
- packaging profiles and export manifests
- `LiveDevelopmentHub`, debug overlay and programmatic profiler

### Visual editor foundation

- project/workspace state
- hierarchy and inspector
- unified undo/redo and component editing
- persistent mixed object/entity hierarchy
- asset browser, console and profiler panels
- move/rotate/scale gizmos with snapping
- viewport picking/direct manipulation and embedded live preview
- interactive Tk editor frontend
- isolated Play/Edit runtime session
- project scene/prefab discovery and semantic input-profile authoring

## Performance foundation

SwirEngine keeps measurable performance work explicit. Current regression gates include:

- **static 3D batching:** 100 compatible static cubes map from 100 renderer-facing object draws to one combined mesh draw
- **async preload:** a reproducible synthetic I/O-like benchmark must demonstrate real overlap/wait reduction
- **2D collision:** a sparse 1,000-collider case must reduce broad-phase candidates by at least 100x versus brute-force all-pairs enumeration
- **particle/VFX:** a pool capacity of 10,000 with eight live particles must perform exactly eight particle update visits per measured frame
- **text layout:** after the first layout, 1,000 identical requests must be cache hits with no additional measurement calls

These are narrow workload/regression measurements. SwirEngine does not convert them into unmeasured FPS claims.

## Project generator and export

```bash
swirengine new MyGame --mode 2d
swirengine new My3DGame --mode 3d
swirengine info
swirengine export . --target windows --name MyGame --onefile --windowed
```

Generated projects declare compatibility with the stable engine line:

```toml
engine = ">=1.0,<2.0"
```

Desktop targets expose deterministic staging/build plans. Android and Web remain experimental staging/research targets unless and until their shipping path is fully verified.

## Diagnostics

Enable the built-in debug overlay before `game.run()`:

```python
game.show_debug()
```

It exposes FPS, frame/CPU timings, update/physics/render timings, draw calls, batches, sprites, triangles, light usage and dropped-light counts. Programmatic profiling is available through `game.profiler`. Individual production systems also expose focused diagnostics such as asset preload, collision, particles and text-layout cache metrics.

## Official demo projects and examples

- **Neon Cube Hunt 3D** — 3D collection arena used for real OpenGL and packaged-runtime validation
- **Neon Snake 3D** — complete 3D Snake with growth, food, collision, score, PBR and post-processing
- `examples/demo_gamepad.py` — controller + keyboard fallback
- `examples/demo_static_3d_batching.py` — static larger-batch rendering
- `examples/demo_async_assets.py` — background/preload loading diagnostics
- `examples/demo_responsive_ui.py` — resize-aware UI with focus navigation
- `examples/demo_animation_runtime.py` — tween/sequence/timeline/state-machine runtime
- `examples/demo_collision_queries.py` — spatial collision queries and diagnostics
- `examples/demo_editor_workflow.py` — scene/prefab/input/playtest project workflow
- `examples/demo_particles_vfx.py` — sparse pooled particle/VFX lifecycle
- `examples/demo_text_layout.py` — font fallback, wrapping, alignment and layout-cache diagnostics
- larger asset-free 2D samples under `examples/`

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
- dedicated CPython 3.14 Windows platform-wheel build, pip-selection and native import tests
- reproducible performance/regression gates
- real OpenGL paths through the official 3D demo workflows

## Versioning and API stability

SwirEngine follows semantic versioning for the stable 1.x public API. Existing 1.x behavior remains compatibility-sensitive; new production systems are additive. User-visible changes are expected to keep code, tests, README, CHANGELOG and examples/documentation aligned.

PyPI/GitHub Release publication for active 1.2 remains frozen until all 10 roadmap deliverables are verified complete. See [`docs/API_STABILITY.md`](docs/API_STABILITY.md).

## Roadmap

- SwirEngine 1.0: [`ROADMAP.md`](ROADMAP.md) — **31/31 = 100%**, historical and locked
- SwirEngine 1.1: [`ROADMAP_1_1.md`](ROADMAP_1_1.md) — **10/10 = 100%**, released
- SwirEngine 1.2: [`ROADMAP_1_2.md`](ROADMAP_1_2.md) — active development roadmap

## Links

- PyPI: https://pypi.org/project/swirengine/
- Repository: https://github.com/Swir/SwirEngine
- Releases: https://github.com/Swir/SwirEngine/releases
- Changelog: https://github.com/Swir/SwirEngine/blob/main/CHANGELOG.md

## License

MIT
