# SwirEngine 1.5.0

<p align="center">
  <a href="https://github.com/Swir/SwirEngine/actions/workflows/ci.yml"><img alt="CI" src="https://github.com/Swir/SwirEngine/actions/workflows/ci.yml/badge.svg"></a>
  <a href="https://pypi.org/project/swirengine/"><img alt="PyPI" src="https://img.shields.io/pypi/v/swirengine?style=flat-square"></a>
  <img alt="Python" src="https://img.shields.io/badge/Python-3.10--3.13%20cross--platform%20%7C%203.14%20Windows-3776AB?style=flat-square&logo=python&logoColor=white">
  <img alt="1.5 roadmap" src="https://img.shields.io/badge/1.5%20ROADMAP-100%25-2ea043?style=flat-square">
  <img alt="Status" src="https://img.shields.io/badge/status-1.5.0%20stable-2ea043?style=flat-square">
  <img alt="License" src="https://img.shields.io/badge/license-MIT-blue?style=flat-square">
</p>

**SwirEngine 1.5.0** is the Production Runtime & Creator Scale stable release of a Python-first 2D/3D game engine with a stable 1.x compatibility contract. Version 1.5 extends the released 1.4 engine with deterministic simulation/replay, resilient save/profile storage, richer audio and animation systems, navigation, world streaming, a retained UI toolkit, creator/editor productivity tooling, and opt-in runtime diagnostics/profiling.

The SwirEngine 1.5 roadmap is complete at **10/10 = 100.0%**. Version **1.5.0 is released and locked**: the final compatibility/runtime/packaging gate passed, the `v1.5.0` GitHub Release is published, and clean public PyPI installation was verified after publication. The source-only 2D and 3D game demos remain integration examples and do not receive separate releases.

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

To pin the stable 1.5 release:

```bash
python -m pip install -U swirengine==1.5.0
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

## What is new in 1.5

### 1. Deterministic Simulation & Replay

- opt-in fixed-step simulation clock
- deterministic replay recording and playback
- canonical portable replay data and state fingerprints
- checkpoints, seeking and bounded recording
- deterministic long-run validation workload

### 2. Save & Profile 2.0

- versioned integrity-checked save envelopes
- atomic primary/backup writes and safe recovery
- ordered project migrations and profile isolation
- legacy 1.x import without rewriting old save files
- bounded autosave rotation and health inspection

### 3. Audio 2.0

- bounded priority-aware SFX voice budgets
- deterministic voice stealing and protected voices
- portable mixer snapshots with timed interpolation
- stable 1.x spatial composition reused underneath the new layer
- deterministic headless diagnostics and state fingerprints

### 4. Animation Graphs 2.0

- reusable clips and typed graph parameters
- prioritized transitions, wildcard sources and exit-time gates
- deterministic timed source/target cross-fades
- generic portable poses and nested property bindings
- headless diagnostics and reproducible fingerprints

### 5. Navigation 2.0

- deterministic waypoint-graph routing
- node/edge filters, area costs and bounded endpoint snapping
- creator-facing agents and multi-waypoint path following
- deterministic local avoidance with spatial-bucket broad phase
- portable query/runtime diagnostics

### 6. World Streaming 2.0

- finite deterministic partition registry
- dependency-safe activation/deactivation and lifecycle rollback
- hard active-cost budgets and bounded local-window updates
- retention hysteresis, failure isolation and explicit retry
- creator-first `WorldStream` facade with Game-aware cleanup

### 7. UI Toolkit 2.0

- retained widget trees
- responsive horizontal/vertical layout
- resolution-independent scaling
- unified mouse, keyboard and gamepad focus navigation
- centralized themes, portable snapshots and deterministic diagnostics

### 8. Editor Productivity 2.0

- non-destructive prefab authoring and variants
- selective apply/revert with graph-safe references
- bounded shared creator command history
- previewable transactional multi-object batch edits
- asset-reference diagnostics without loading asset contents

### 9. Runtime Diagnostics & Profiling 2.0

- bounded structured frame/update/physics/render timing history
- arbitrary timing domains, subsystem counters and resource accounting
- optional Python allocation snapshots
- fault-contained diagnostics providers
- deterministic versioned capture/export with SHA-256 fingerprints
- stable 1.x `Profiler` remains unchanged

### 10. Showcase, Hardening & Release Gate

The final 1.5 hardening line validates the package as a whole instead of creating standalone releases for the example games. The gate covers:

- full pytest, Ruff and compile validation
- Python 3.10/3.13/3.14 focused release-contract testing
- the complete supported cross-platform CI matrix
- all nine 1.5 deterministic/workload benchmark contracts
- both source-only game demos in headless mode and real Linux OpenGL 3.3 under Xvfb/Mesa
- portable wheel/sdist build plus `twine check`
- clean virtual-environment installation outside the editable source tree
- source-demo probes against the clean wheel
- Windows one-file packaging/runtime probes for both demos
- the dedicated Windows CPython 3.14 native-wheel route
- locked 1.3 and 1.4 compatibility gates
- tag-only Trusted Publishing to PyPI
- public-index installation verification before the release is accepted as complete

See [`docs/RELEASE_HARDENING_1_5.md`](docs/RELEASE_HARDENING_1_5.md).

## Stable 1.x feature set

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
- skyboxes, environment cubemaps and IBL
- cascaded shadows, SSAO, bloom, decals, tone mapping and FXAA
- GPU instancing, frustum culling and scene acceleration
- skeletal animation and GPU skinning
- 3D collision, Physics 2.0 and character controllers
- deterministic navigation, large-world streaming and terrain/LOD
- GPU particle/VFX systems
- controlled shader/material variants

### Production systems

- scenes, lifecycle hooks, grouped mounts and cached update snapshots
- prefabs, overrides, batch spawning and versioned serialization
- lightweight indexed ECS
- plugin runtime and transactional hot reload
- Asset Pipeline 2.0 with derived caching and dependency invalidation
- audio buses/groups and spatial attenuation
- stable networking plus opt-in replication foundations
- creator/editor workflow with reversible playtest state
- native export manifests and PyInstaller desktop builds
- debug overlay, stable profiler and additive 1.5 diagnostics

## Performance regression policy

SwirEngine keeps performance claims reproducible and workload-specific. The repository contains deterministic contracts for every completed 1.5 subsystem plus the established 1.x engine workloads.

Host timings are diagnostics only. SwirEngine does **not** turn host-side timing numbers into unmeasured FPS claims. Renderer correctness is validated separately with real OpenGL smoke tests.

## Validation demos and examples

- **SwirEngine 2D Game Demo** — source-only classic platformer showcase under [`examples/2d_game_demo/`](examples/2d_game_demo/)
- **SwirEngine 3D Game Demo** — source-only corridor-FPS showcase under [`examples/3d_game_demo/`](examples/3d_game_demo/)
- **Neon Frontier 1.4** — released and locked 1.4 compatibility/showcase project
- **Neon Frontier 1.3** — locked 1.3 regression game
- **Neon Cube Hunt 3D** — OpenGL + packaged-runtime regression arena
- **Neon Snake 3D** — complete 3D regression project
- `examples/demo_deterministic_replay_1_5.py`
- `examples/demo_save_profile_2_1_5.py`
- `examples/demo_audio_2_1_5.py`
- `examples/demo_animation_graphs_2_1_5.py`
- `examples/demo_navigation_2_1_5.py`
- `examples/demo_world_streaming_2_1_5.py`
- `examples/demo_ui_toolkit_2_1_5.py`
- `examples/demo_editor_productivity_1_5.py`
- `examples/demo_performance_diagnostics_2_1_5.py`

## Development and verification

```bash
python -m pip install -e ".[dev]"
pytest
ruff check src tests examples demo_projects tools
python -m compileall -q src examples demo_projects tools
python tools/verify_1_5_release_candidate.py --require-complete
```

Dedicated milestone benchmarks, OpenGL validators, clean-wheel checks and native packaging probes live under `tools/` and `.github/workflows/`.

## API stability

SwirEngine follows semantic versioning for the stable 1.x public API. Version 1.5.0 is additive to established 1.x behavior: existing projects are not required to adopt deterministic replay, Save & Profile 2.0, Audio 2.0, Animation Graphs 2.0, Navigation 2.0, World Streaming 2.0, UI Toolkit 2.0, Editor Productivity 2.0 or Runtime Diagnostics & Profiling 2.0.

SwirEngine 1.4 and **1.5.0 are released and locked**. Their compatibility/runtime showcases continue to run as regression gates. Historical 1.0-1.5 roadmaps stay locked except for genuine maintenance needed to keep their compatibility validation working on later stable lines.

See [`docs/API_STABILITY.md`](docs/API_STABILITY.md).

## 1.5 documentation

- [`docs/DETERMINISTIC_REPLAY_1_5.md`](docs/DETERMINISTIC_REPLAY_1_5.md)
- [`docs/SAVE_PROFILE_2_1_5.md`](docs/SAVE_PROFILE_2_1_5.md)
- [`docs/AUDIO_2_1_5.md`](docs/AUDIO_2_1_5.md)
- [`docs/ANIMATION_GRAPHS_2_1_5.md`](docs/ANIMATION_GRAPHS_2_1_5.md)
- [`docs/NAVIGATION_2_1_5.md`](docs/NAVIGATION_2_1_5.md)
- [`docs/WORLD_STREAMING_2_1_5.md`](docs/WORLD_STREAMING_2_1_5.md)
- [`docs/UI_TOOLKIT_2_1_5.md`](docs/UI_TOOLKIT_2_1_5.md)
- [`docs/EDITOR_PRODUCTIVITY_2_1_5.md`](docs/EDITOR_PRODUCTIVITY_2_1_5.md)
- [`docs/PERFORMANCE_DIAGNOSTICS_2_1_5.md`](docs/PERFORMANCE_DIAGNOSTICS_2_1_5.md)
- [`docs/RELEASE_HARDENING_1_5.md`](docs/RELEASE_HARDENING_1_5.md)

## Roadmaps

- SwirEngine 1.0 — [`ROADMAP.md`](ROADMAP.md) — **31/31 = 100%**, historical and locked
- SwirEngine 1.1 — [`ROADMAP_1_1.md`](ROADMAP_1_1.md) — **10/10 = 100%**, released and locked
- SwirEngine 1.2 — [`ROADMAP_1_2.md`](ROADMAP_1_2.md) — **10/10 = 100%**, released and locked
- SwirEngine 1.3 — [`ROADMAP_1_3.md`](ROADMAP_1_3.md) — **10/10 = 100%**, released and locked
- SwirEngine 1.4 — [`ROADMAP_1_4.md`](ROADMAP_1_4.md) — **10/10 = 100.0%**, released and locked
- SwirEngine 1.5 — [`ROADMAP_1_5.md`](ROADMAP_1_5.md) — **10/10 = 100.0%**, released and locked

## Links

- PyPI: https://pypi.org/project/swirengine/
- Repository: https://github.com/Swir/SwirEngine
- Releases: https://github.com/Swir/SwirEngine/releases
- Changelog: https://github.com/Swir/SwirEngine/blob/main/CHANGELOG.md

## License

MIT
