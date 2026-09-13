# SwirEngine 1.1.0

<p align="center">
  <a href="https://github.com/Swir/SwirEngine/actions/workflows/ci.yml"><img alt="CI" src="https://github.com/Swir/SwirEngine/actions/workflows/ci.yml/badge.svg"></a>
  <a href="https://pypi.org/project/swirengine/"><img alt="PyPI" src="https://img.shields.io/pypi/v/swirengine?style=flat-square"></a>
  <img alt="Python" src="https://img.shields.io/badge/Python-3.10--3.13%20cross--platform%20%7C%203.14%20Windows-3776AB?style=flat-square&logo=python&logoColor=white">
  <img alt="Status" src="https://img.shields.io/badge/status-stable-2ea043?style=flat-square">
  <img alt="License" src="https://img.shields.io/badge/license-MIT-blue?style=flat-square">
</p>

**SwirEngine** is a Python-first 2D/3D game engine built around one approachable API. It combines
creator-friendly Python gameplay code with a real OpenGL renderer, scenes, prefabs/ECS, physics,
audio, editor tooling, networking, export and complete game demos.

The original 1.0 roadmap is complete at **31/31 deliverables**. SwirEngine 1.1 starts the next
stage: making complete games easier to control, profile, package and ship without turning the
engine into a thin wrapper around another framework.

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

The stable upstream `moderngl 5.12.0` and `glcontext 3.0.0` releases do not currently publish
CPython 3.14 Windows x86-64 wheels. SwirEngine publishes a dedicated
`cp314-cp314-win_amd64` wheel containing verified private copies of those native renderer
components under `swirengine/_vendor_native`. A normal `pip install swirengine` on Windows x64 +
Python 3.14 therefore does **not** require Microsoft Visual C++ Build Tools.

The platform wheel is rebuilt from upstream source in GitHub Actions, checked with `twine`,
installed into a clean Python 3.14 environment and imported before Trusted Publishing is allowed
to upload it. Python 3.10-3.13 continue using normal upstream dependencies. Linux and macOS remain
on the verified 3.10-3.13 support window until equally reliable Python 3.14 binary dependencies
exist there.

## What is new in 1.1.0

### Standardized gamepad/controller input

SwirEngine now has a creator-facing controller layer on top of GLFW's standard gamepad mapping.
Mapped Xbox, PlayStation and compatible controllers expose the same names instead of forcing game
code to depend on platform-specific joystick indexes.

The input layer now provides:

- deterministic discovery of connected standardized gamepads
- controller name and GUID snapshots
- held, pressed and released button queries
- aliases such as `LB`, `RB`, `L1`, `R1`, `L2`, `R2`, `L3`, `R3`, `START` and D-pad directions
- left/right analog stick helpers
- configurable stick/axis deadzone with range rescaling
- trigger helpers normalized to `0.0 .. 1.0`
- hot-plug connection/disconnection edge queries
- automatic per-frame refresh while a normal `Game.run()` window is active
- keyboard fallback remains fully compatible

Example:

```python
from swirengine import Color, Game, Rectangle2D


game = Game("Controller demo", 960, 540, mode="2d")
player = game.add(Rectangle2D(-40, -40, 80, 80, Color(0.1, 0.75, 1.0, 1.0)))


@game.update
def update(dt):
    x, y = game.input.gamepad_stick("left")

    if not game.input.gamepad_connected():
        x = float(game.key("D")) - float(game.key("A"))
        y = float(game.key("S")) - float(game.key("W"))

    speed = 520 if game.input.gamepad_button("A") else 300
    player.x += x * speed * dt
    player.y += y * speed * dt

    if game.input.gamepad_button_pressed("START"):
        player.x = player.y = -40


game.run()
```

For lower-level access, `GamepadSnapshot`, `GAMEPAD_BUTTONS`, `GAMEPAD_AXES`,
`apply_deadzone(...)`, `normalize_gamepad_button(...)` and `normalize_gamepad_axis(...)` are public
1.x APIs.

### Semantic input actions, rebinding and control profiles

SwirEngine 1.1 development also includes a creator-facing semantic action layer. Games can bind
keyboard, mouse, standardized gamepad buttons and directional analog axes to names such as
`jump`, `fire` or `move_left`, then change those bindings from an in-game controls menu without
rewriting gameplay code.

```python
from swirengine.input import InputActions

controls = InputActions(game.input)
controls.key("jump", "SPACE")
controls.gamepad_button("jump", "A")
controls.mouse_button("fire", 0)
controls.gamepad_axis("move_left", "left_x", direction=-1, threshold=0.25)

if controls.pressed("jump"):
    player.jump()

move_left = controls.value("move_left")
controls.save("settings/controls.json")
```

Bindings support held/pressed/released queries, analog values, duplicate-safe multi-binding,
runtime replacement/removal and versioned JSON profiles. Persisted axis thresholds are enforced at
runtime so controller profiles behave consistently after reload. See
[`docs/INPUT_ACTIONS.md`](docs/INPUT_ACTIONS.md) for the full API and rebinding workflow.

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
- labels, panels, buttons and progress bars
- particles
- AABB collision queries
- deterministic fixed-step arcade rigid-body physics
- JSON save data through `SaveStore`
- keyboard, mouse, standardized gamepad input, semantic actions and persistent rebinding profiles
- adjacent compatible sprite batching
- single-pass render-run construction with cached canonical texture keys

### 3D runtime

- perspective `Camera3D`
- `MeshData`, `Mesh3D` and lazy GPU mesh caching
- OBJ import with triangulation, normals and UVs
- static glTF/GLB scene and material import
- Phong and Cook-Torrance GGX metallic/roughness PBR
- base-color, metallic/roughness, normal, occlusion and emissive material channels
- directional, point and spot lights
- deterministic per-light GPU budgets and diagnostics
- skybox/environment support
- true cubemap image-based lighting
- directional GPU shadows, post-processing, ACES/Reinhard tone mapping and FXAA
- sRGB/linear color-space handling for PBR material channels
- bounded transform-matrix caching for repeated static object transforms

### Performance foundation

The renderer already avoids repeated texture path resolution in steady-state 2D batching and
builds render runs in one pass instead of allocating a second visible-object tuple. Repeated static
3D transforms use a bounded matrix cache while callers still receive independent mutable matrix
results. The 1.1 roadmap continues with larger GPU-side batching/instancing and frame-time work.

### Architecture and game systems

- scene names, tags and creator-friendly lookup/removal helpers
- reusable prefabs and per-instance overrides
- versioned scene/prefab JSON serialization
- safe codec registry and cyclic reference preservation
- lightweight ECS with entities, components, queries and prioritized systems
- plugin runtime
- polling file watcher and plugin hot reload
- transactional multi-domain state restore/rollback
- asset hot reload bridges for renderer and audio
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

Create a project directly from the installed package:

```bash
swirengine new MyGame --mode 2d
swirengine new My3DGame --mode 3d
```

Generated projects declare compatibility with the stable engine line:

```toml
engine = ">=1.0,<2.0"
```

Check the installed engine:

```bash
swirengine info
```

## Export

Create a deterministic export/staging directory:

```bash
swirengine export . --target windows --name MyGame --onefile --windowed
```

Desktop targets expose the native PyInstaller command instead of silently invoking third-party
build tools. Android and Web remain experimental staging/research targets.

## PBR example

```python
from swirengine import Color, Game, Material3D, Vec3, cube_mesh


game = Game("PBR", mode="3d")
material = Material3D(
    tint=Color(0.82, 0.35, 0.12, 1.0),
    ambient=0.04,
    metallic=0.9,
    roughness=0.18,
)
model = game.mesh(cube_mesh(), material=material)
model.position = Vec3(0.0, 0.0, -4.0)

game.directional_light(direction=Vec3(-0.4, -1.0, -0.3), intensity=0.9)
game.camera.look_at(model.position)
game.run()
```

The PBR path supports glTF-style packed metallic/roughness maps, normal maps, AO and emissive
textures. Cubemap IBL, shadows, post-processing and tone mapping are complete runtime features.

## Diagnostics

Enable the built-in debug overlay before `game.run()`:

```python
game.show_debug()
```

It exposes FPS, frame/CPU timings, update/physics/render timings, draw calls, batches, sprites,
triangles, light usage and dropped-light counts. Programmatic profiling is available through
`game.profiler`.

## Official demo projects

The repository contains complete games built with the public SwirEngine API:

- **Neon Cube Hunt 3D** — 3D collection arena used for real OpenGL and packaged-runtime testing
- **Neon Snake 3D** — complete 3D Snake with growth, food, collision, score, PBR and post-processing
- `examples/demo_gamepad.py` — controller + keyboard-fallback input example
- larger asset-free 2D samples under `examples/`

The Windows demo build pipeline also probes the final packaged GLFW runtime so missing native
libraries are caught before demo publication.

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
- real OpenGL paths through the official 3D demo workflows

## Versioning and API stability

SwirEngine follows semantic versioning for the stable 1.x public API. The exported
`swirengine.__all__` surface is treated as a compatibility contract. Patch releases fix bugs,
compatibility and performance issues; minor releases add backwards-compatible creator features.

`README.md` is also the long description published to PyPI. Release-contract tests verify that
README version/support claims stay synchronized with package metadata. User-visible changes are
expected to update code, tests, README and changelog together before publication.

See [`docs/API_STABILITY.md`](docs/API_STABILITY.md) for the compatibility policy.

## Roadmap

The original SwirEngine 1.0 roadmap remains complete and historical:

```text
████████████████████ 100.0%
31 / 31 deliverables complete
```

The active expansion plan lives in [`ROADMAP_1_1.md`](ROADMAP_1_1.md). The historical 1.0 dashboard
is kept in [`ROADMAP.md`](ROADMAP.md) and is not artificially increased beyond 100%.

## Links

- PyPI: https://pypi.org/project/swirengine/
- Repository: https://github.com/Swir/SwirEngine
- Releases: https://github.com/Swir/SwirEngine/releases
- 1.0 roadmap: https://github.com/Swir/SwirEngine/blob/main/ROADMAP.md
- 1.1 roadmap: https://github.com/Swir/SwirEngine/blob/main/ROADMAP_1_1.md
- Changelog: https://github.com/Swir/SwirEngine/blob/main/CHANGELOG.md

## License

MIT
