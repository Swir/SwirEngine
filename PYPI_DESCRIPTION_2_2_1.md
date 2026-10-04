# SwirEngine 2.2.1

**A Python-first engine for building complete 2D, 3D and multiplayer games.**

SwirEngine combines a compact high-level API with modular rendering, scene, physics, UI, asset,
networking, editor and export systems. You can begin with a small Python script, then move to
project-based authoring in SwirEditor without replacing the runtime APIs used by the game.

Version 2.2.1 is a maintenance release for the completed **2.2 Production Tools & Visual Creation**
line. It preserves the 2.2 runtime and editor feature set while providing a clearer package
overview, installation guide and starting points for new users.

- Python-first 2D and 3D runtime
- OpenGL-backed rendering through ModernGL and GLFW
- Scenes, prefabs, ECS, serialization and project assets
- 2D and 3D physics and collision
- Input, retained UI, audio, saves and diagnostics
- Multiplayer replication, prediction and session foundations
- SwirEditor visual authoring and runtime-backed previews
- Project validation, staging and host-native desktop packaging
- MIT licensed

## Installation

SwirEngine requires Python 3.10 through Python 3.14. The maintained release matrix qualifies the base package on
64-bit CPython across explicit Windows, Linux and macOS hosted-runner cells.

Install the base engine:

```bash
python -m pip install -U "swirengine==2.2.1"
```

Install optional audio support:

```bash
python -m pip install -U "swirengine[audio]==2.2.1"
```

Confirm the installation:

```bash
swirengine info
```

## Quick start: 2D

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


game.run()
```

## Quick start: 3D

```python
from swirengine import Color, Cube3D, Game, Vec3

game = Game("My 3D Game", 1280, 720, mode="3d")
cube = game.add(
    Cube3D(
        position=Vec3(0, 0, -4),
        color=Color(0.2, 0.7, 1.0, 1.0),
    )
)


@game.update
def update(dt):
    cube.rotation.y += 50 * dt
    cube.rotation.x += 25 * dt


game.run()
```

## Create and open a project

Create a project from the command line:

```bash
swirengine new MyGame --mode 2d
swirengine editor MyGame
```

For a 3D project:

```bash
swirengine new My3DGame --mode 3d
swirengine editor My3DGame
```

The separate editor entry point is also available:

```bash
swireditor MyGame
```

Project commands include:

```bash
swirengine doctor MyGame
swirengine workflow MyGame
swirengine run MyGame
swirengine export MyGame
```

## Runtime capabilities

### 2D

SwirEngine's 2D runtime includes:

- rectangles, sprites, text, tilemaps and animated sprites;
- cameras, layers and scene organization;
- collision queries, rigid bodies and contact handling;
- particles and reusable visual effects;
- keyboard, mouse and gamepad input;
- retained UI, layout, focus and navigation;
- deterministic scene and prefab serialization.

### 3D

The 3D runtime includes:

- mesh primitives plus OBJ and glTF asset paths;
- materials, shader variants and PBR-oriented rendering;
- directional, point and spot lights;
- shadows, skyboxes, image-based environments and post-processing;
- instancing, visibility queries, scene acceleration and LOD foundations;
- terrain and large-world streaming foundations;
- skeletal animation and GPU skinning paths;
- 3D collision, rigid bodies and character controllers.

A working graphics context and compatible system graphics stack are required for rendered
applications. Headless and software-rendered CI qualification does not guarantee identical
performance on every GPU or driver.

### Multiplayer foundations

SwirEngine provides explicit building blocks for game networking:

- TCP transport and packet framing;
- gameplay messages and RPC routing;
- opt-in replicated component schemas;
- canonical snapshots and sparse entity deltas;
- snapshot interpolation;
- client prediction and authoritative reconciliation;
- bounded rewind history for lag-compensation foundations;
- transport/QoS, session lifecycle and reconnect foundations;
- a fixed-tick headless dedicated-server adapter;
- bounded network profiling and privacy-conscious multiplayer diagnostics.

These are engine-side foundations. SwirEngine does not include a hosted backend, public matchmaking
service, account platform or game-server hosting.

## SwirEditor

SwirEditor uses the same project data and runtime systems as shipped games. Its creator workflow
includes:

- Project Hub and project-backed sessions;
- multi-scene authoring and recovery;
- hierarchy and typed Inspector workflows;
- multi-selection and component/prefab authoring;
- 2D and 3D viewport rendering;
- object picking, transform gizmos, snapping and grid controls;
- asset import, reimport and content validation;
- isolated Play, Pause, Stop and Step sessions;
- console source navigation and profiler views;
- input, settings, animation, physics, navigation, audio, UI and save/profile tooling;
- deterministic staging and Build/Export workflows.

Editor previews are designed to exercise shipping runtime paths. They do not silently replace game
entry points or turn editor-only mock data into a second runtime format.

## Production tools introduced in 2.2

The completed 2.2 roadmap adds runtime-backed visual creation tools for:

- deterministic material and shader assets with live renderer preview;
- typed visual scripting and node-graph authoring;
- terrain sculpting, material painting, foliage and streaming/LOD configuration;
- animation state machines, transitions, parameters and synchronized 1D blend trees;
- CPU 2D and GPU 3D particle/VFX authoring;
- lighting, environment, shadows and post-processing profiles;
- responsive UI layouts, reusable styles, interaction states and bounded animation;
- multiplayer replication/session inspection and measured RTT diagnostics;
- capability-gated SwirEditor extension panels and actions.

Visual tools are additive. Python remains the primary scripting and runtime integration path.

## Project data, export and reliability

SwirEngine favors deterministic, inspectable project data:

- canonical scene and creator-tool serialization;
- project-confined asset references and traversal rejection;
- explicit validation before runtime or export;
- save/reopen and relocated-export verification;
- staged runtime checks outside the authoring checkout;
- clean-wheel and exact-source release validation;
- checksums and provenance for guarded public releases.

Desktop application builds are **host-native**. Cross-compilation and universal support for every
operating-system or CPU combination are not implied.

## Examples

The source repository contains focused subsystem examples and larger integration fixtures:

- 2D scrolling platformer;
- 3D bunker FPS;
- deterministic multiplayer simulation;
- asset-free Breakout and Dodge Arena samples;
- editor, rendering, physics, animation, UI and networking demonstrations.

The examples are source-repository fixtures rather than separately published games. Clone the
repository to run them:

```bash
git clone https://github.com/Swir/SwirEngine.git
cd SwirEngine
python -m pip install -e ".[dev]"
python examples/sample_breakout.py
python examples/sample_dodge_arena.py
```

[Browse all examples](https://github.com/Swir/SwirEngine/tree/main/examples).

## Compatibility and important boundaries

- Package metadata supports CPython `>=3.10,<3.15`.
- The maintained release matrix is limited to verified 64-bit hosted-runner environments.
- 32-bit Python, PyPy, free-threaded CPython and unverified CPU architectures are not claimed.
- Optional audio has its own dependency and runtime requirements.
- Native desktop packaging is performed for the current host platform.
- Visual authoring does not remove the need for application-specific Python integration.
- Multiplayer tooling is not a hosted online service or a performance guarantee.
- The Editor Extension SDK is for trusted, explicitly installed Python extensions. It is a bounded
  editor API, not an operating-system security sandbox.
- Performance evidence is contextual; SwirEngine makes no unsupported cross-engine FPS, latency or
  memory-superiority claims.

## Documentation

- [Repository and full README](https://github.com/Swir/SwirEngine)
- [2.2 roadmap](https://github.com/Swir/SwirEngine/blob/main/ROADMAP_2_2.md)
- [Migrating from 2.1 to 2.2](https://github.com/Swir/SwirEngine/blob/main/docs/MIGRATING_TO_2_2.md)
- [Examples](https://github.com/Swir/SwirEngine/tree/main/examples)
- [Changelog](https://github.com/Swir/SwirEngine/blob/main/CHANGELOG.md)
- [Releases](https://github.com/Swir/SwirEngine/releases)
- [Issue tracker](https://github.com/Swir/SwirEngine/issues)

## License

SwirEngine is distributed under the
[MIT License](https://github.com/Swir/SwirEngine/blob/main/LICENSE).
