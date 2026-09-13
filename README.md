# SwirEngine 1.0.2

<p align="center">
  <a href="https://github.com/Swir/SwirEngine/actions/workflows/ci.yml"><img alt="CI" src="https://github.com/Swir/SwirEngine/actions/workflows/ci.yml/badge.svg"></a>
  <a href="https://pypi.org/project/swirengine/"><img alt="PyPI" src="https://img.shields.io/pypi/v/swirengine?style=flat-square"></a>
  <img alt="Python" src="https://img.shields.io/badge/Python-3.10--3.13-3776AB?style=flat-square&logo=python&logoColor=white">
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

SwirEngine currently supports **Python 3.10-3.13**.

```bash
python -m pip install -U swirengine
```

On Windows, Python 3.13 is the recommended interpreter for the current release:

```powershell
py -3.13 -m pip install -U swirengine
```

Optional audio support:

```bash
python -m pip install -U "swirengine[audio]"
```

### Python 3.14

Python 3.14 is not declared as supported yet. SwirEngine depends on native OpenGL packages
(`moderngl` and `glcontext`) whose current stable releases do not provide prebuilt CPython 3.14
Windows wheels. Without that wheel, `pip` attempts a local C/C++ build and may ask for Microsoft
Visual C++ Build Tools. SwirEngine 1.0.2 declares `Python >=3.10,<3.14` so installers fail early
with a clear compatibility message instead of entering that native build path.

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

Projects created by SwirEngine 1.0.2 declare compatibility with the stable engine line:

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
ruff check src tests examples demo_projects
python -m compileall -q src examples demo_projects
```

CI validates SwirEngine on:

- Windows, Linux and macOS
- Python 3.10, 3.11, 3.12 and 3.13
- wheel/sdist packaging and metadata
- clean-wheel installation
- selected real OpenGL demo paths

## Versioning and API stability

SwirEngine follows semantic versioning for the stable 1.x public API. The exported
`swirengine.__all__` surface is treated as the stable compatibility contract. Patch releases fix
bugs and packaging/documentation problems without intentionally breaking that API.

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
