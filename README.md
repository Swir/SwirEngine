# SwirEngine 1.0.3

<p align="center">
  <a href="https://github.com/Swir/SwirEngine/actions/workflows/ci.yml"><img alt="CI" src="https://github.com/Swir/SwirEngine/actions/workflows/ci.yml/badge.svg"></a>
  <a href="https://pypi.org/project/swirengine/"><img alt="PyPI" src="https://img.shields.io/pypi/v/swirengine?style=flat-square"></a>
  <img alt="Python" src="https://img.shields.io/badge/Python-3.10--3.14-3776AB?style=flat-square&logo=python&logoColor=white">
  <img alt="Status" src="https://img.shields.io/badge/status-stable-2ea043?style=flat-square">
  <img alt="License" src="https://img.shields.io/badge/license-MIT-blue?style=flat-square">
</p>

**SwirEngine** is a modern Python-first 2D/3D game engine built around one approachable API.
It is designed to let Python developers create real games without having to learn raw OpenGL
before putting gameplay on screen.

SwirEngine 1.0 is a stable line with a tested cross-platform runtime, GPU rendering, input,
physics, audio, assets, scenes, prefabs/ECS, editor tooling, networking and project export.
The 1.0 roadmap is complete at **31/31 deliverables**.

## Install

SwirEngine currently supports **Python 3.10-3.14**.

```bash
python -m pip install -U swirengine
```

On 64-bit Windows, Python 3.14 is supported directly by SwirEngine 1.0.3:

```powershell
py -3.14 -m pip install -U swirengine
```

Optional audio support:

```bash
python -m pip install -U "swirengine[audio]"
```

### Python 3.14 native renderer support

The upstream stable `moderngl 5.12.0` and `glcontext 3.0.0` releases do not currently publish
CPython 3.14 Windows x86-64 wheels. SwirEngine 1.0.3 closes that installation gap by publishing a
separate `cp314-cp314-win_amd64` SwirEngine wheel. That platform wheel contains verified private
copies of the native renderer backend under `swirengine/_vendor_native`, so a normal
`pip install swirengine` on 64-bit Windows + Python 3.14 does **not** require Microsoft Visual C++
Build Tools.

The native backend is built from the same upstream source versions in GitHub Actions, installed
into a clean Python 3.14 environment, imported there, checked by `twine`, and only then allowed
into the release pipeline. Python 3.10-3.13 continue using the normal upstream dependencies.

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

## What is included

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
- keyboard and mouse held/pressed/released queries
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

### Smoother frame workloads in 1.0.3

SwirEngine 1.0.3 reduces avoidable per-frame CPU work without changing the public game API.
Sprite batching no longer resolves the same texture filesystem path over and over each frame, and
it no longer creates a second visible-object tuple before forming render runs. Static 3D
transforms reuse bounded cached matrix calculations while callers still receive independent
mutable matrix results. These changes target steadier CPU frame times in sprite-heavy 2D scenes
and 3D scenes containing repeated static geometry.

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

Projects created by SwirEngine 1.0.3 declare compatibility with the stable engine line:

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
build tools. Linux and macOS use the same profile system. Android and Web are intentionally
reported as experimental staging/research targets.

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
textures. Cubemap IBL, shadows and post-processing are complete runtime features rather than
future roadmap placeholders.

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
- larger asset-free 2D sample games under `examples/`

The Windows demo build pipeline does more than create an `.exe`: it probes the packaged GLFW
runtime so missing native libraries are caught before a release is published.

## Development

```bash
python -m pip install -e ".[dev]"
pytest
ruff check src tests examples demo_projects tools
python -m compileall -q src examples demo_projects tools
```

CI validates SwirEngine on:

- Windows, Linux and macOS
- Python 3.10, 3.11, 3.12, 3.13 and 3.14
- wheel/sdist packaging and metadata
- clean-wheel installation
- a dedicated CPython 3.14 Windows platform-wheel build and native import test
- selected real OpenGL demo paths

## Versioning and API stability

SwirEngine follows semantic versioning for the stable 1.x public API. The exported
`swirengine.__all__` surface is treated as the stable compatibility contract. Patch releases fix
bugs, compatibility and performance problems without intentionally breaking that API.

`README.md` is also the long description published to PyPI. Release-contract tests therefore
verify that the README release number and supported Python window stay synchronized with package
metadata. User-visible fixes should update code, tests, changelog and README together.

See [`docs/API_STABILITY.md`](docs/API_STABILITY.md) for the compatibility policy.

## Roadmap

The original SwirEngine 1.0 roadmap is complete:

```text
████████████████████ 100.0%
31 / 31 deliverables complete
```

See [`ROADMAP.md`](ROADMAP.md) for the verified 1.0 milestone history and future planning.

## Links

- PyPI: https://pypi.org/project/swirengine/
- Repository: https://github.com/Swir/SwirEngine
- Releases: https://github.com/Swir/SwirEngine/releases
- Roadmap: https://github.com/Swir/SwirEngine/blob/main/ROADMAP.md
- Changelog: https://github.com/Swir/SwirEngine/blob/main/CHANGELOG.md

## License

MIT
