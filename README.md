<!-- SWIR-README-STANDARD:v2 -->

<div align="center">

<img width="100%" src="assets/readme/hero.svg" alt="SwirEngine — Python-first engine for complete 2D and 3D games" />

<br>

![CI](https://img.shields.io/github/actions/workflow/status/Swir/SwirEngine/ci.yml?branch=main&style=for-the-badge&label=CI&color=02050A&logo=githubactions&logoColor=62E5FF)
[![PyPI](https://img.shields.io/pypi/v/swirengine?style=for-the-badge&color=02050A&logo=pypi&logoColor=62E5FF)](https://pypi.org/project/swirengine/)
![Python](https://img.shields.io/badge/Python-3.10--3.13%20cross--platform%20%7C%203.14%20Windows-02050A?style=for-the-badge&logo=python&logoColor=62E5FF)
![Status](https://img.shields.io/badge/STATUS-1.5.0%20STABLE-02050A?style=for-the-badge&logoColor=62E5FF)
![Source](https://img.shields.io/badge/SOURCE%20ROADMAP-1.9-02050A?style=for-the-badge&logoColor=62E5FF)
![License](https://img.shields.io/badge/LICENSE-MIT-02050A?style=for-the-badge&logo=opensourceinitiative&logoColor=62E5FF)

[![Author](https://img.shields.io/badge/Author-Swir-0088FF?style=flat-square&logo=github)](https://github.com/Swir)
[![Stars](https://img.shields.io/github/stars/Swir/SwirEngine?style=flat-square&color=0088FF)](https://github.com/Swir/SwirEngine/stargazers)

<br>

[**Install**](#-install) · [**Quick Start**](#-quick-start) · [**Source Workflow**](#-current-source-workflow) · [**Roadmaps**](#-roadmaps) · [**Releases**](https://github.com/Swir/SwirEngine/releases)

</div>

<img width="100%" src="https://raw.githubusercontent.com/Swir/Swir/main/assets/power-divider-v4.svg" alt="SWIR electric divider" />

## 📊 Project status

<img width="100%" src="assets/readme/progress-card.svg" alt="SwirEngine 1.9 verified roadmap progress: 9 of 10 milestones, 90.0%, in progress" />

**Active source scope:** SwirEngine 1.9 — Production Workflow & Game Shipping  
**Verified source progress:** **9/10 milestones = 90.0% — IN PROGRESS**  
**Latest public stable release:** **SwirEngine 1.5.0**  
**Release readiness:** intermediate 1.6–1.9 development is source-only.

`Release/PyPI: frozen until SwirEngine 2.0`

SwirEngine is a Python-first 2D/3D game engine focused on a unified creator API, production runtime
systems, real rendering validation, deterministic tooling and a practical path from a project manifest
to a shipped desktop game. The public package remains the verified 1.5.0 stable baseline while the
repository continues additive source development toward 2.0.

SwirEngine 1.6, 1.7 and 1.8 are completed source-only checkpoints. The active 1.9 roadmap has now
verified the end-to-end 2D, 3D and multiplayer real-game production gate; the remaining milestone is
the final 1.9 source checkpoint and measured 2.0 readiness audit.

**SwirEngine 1.5.0** remains the released and locked public compatibility baseline. Its locked contract
includes **Deterministic Simulation & Replay**, **Save & Profile 2.0**, **World Streaming 2.0**,
**UI Toolkit 2.0** and **Runtime Diagnostics & Profiling 2.0**. `ROADMAP_1_5.md` remains
**10/10 = 100.0%**; that historical completion is separate from the active 1.9 source progress above.

## ✨ Highlights

| Area | What creators get |
|---|---|
| Unified 2D + 3D | One Python-first runtime for sprite/tilemap projects and OpenGL 3D scenes. |
| Production runtime | Scenes, prefabs, ECS, plugins, settings, saves/profiles, deterministic simulation and replay. |
| Rendering | PBR materials, lighting, shadows, post-processing, instancing, culling, terrain/LOD and the completed 1.8 render-graph/GPU delivery checkpoint. |
| Animation | Tween/timeline/state machines, animation graphs, skeletal animation and GPU skinning. |
| Physics + navigation | 2D/3D collision, Physics 2.0, character controllers, deterministic navigation and local avoidance. |
| Audio | Audio buses/groups, spatial attenuation and the additive Audio 2.0 mixer/runtime. |
| UI + input | Retained UI, keyboard/mouse/gamepad focus, controller input, rebinding foundations and the source-only 1.9 production input/UI/settings contract. |
| Large worlds | Asset Pipeline 2.0, derived caching, world streaming and bounded resource/runtime diagnostics. |
| Networking | Stable networking APIs plus source-only replication/server foundations developed after 1.5. |
| Creator workflow | Editor productivity tooling, manifest/profile validation, unified development sessions, export staging and verified host-native desktop build plans. |
| Diagnostics | Stable profiler plus additive runtime/resource/timing capture systems. |
| Compatibility | Stable 1.x public baseline with later source systems kept additive or opt-in where behavior could change. |

## 📦 Install

The latest **public stable package is 1.5.0**.

Verified published support covers **Python 3.10-3.13** on Windows, Linux and macOS, plus
**Python 3.14 on Windows x86-64** through the dedicated validated native-wheel path.

```bash
python -m pip install -U swirengine==1.5.0
```

Optional audio support:

```bash
python -m pip install -U "swirengine[audio]==1.5.0"
```

For current source development:

```bash
git clone https://github.com/Swir/SwirEngine.git
cd SwirEngine
python -m pip install -e ".[dev]"
```

> The current repository contains source-only 1.6–1.9 work that is intentionally newer than the
> published 1.5.0 package version. No intermediate release or PyPI publication is created.

## 🚀 Quick Start

### 2D

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

### 3D

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

## 🛠 Current source workflow

SwirEngine 1.9 turns the accumulated runtime systems into a coherent project/shipping path.

Create and validate a source-development project:

```bash
swirengine new MyGame --mode 3d
swirengine doctor MyGame
```

Milestone 1 provides validated `swirproject.toml` manifests, deterministic project fingerprints, named
production profiles and profile-driven export:

```bash
swirengine export MyGame --profile windows
```

Milestone 2 adds one verified run path for both 2D and 3D projects:

```bash
swirengine run MyGame --dry-run
swirengine run MyGame -- --level arena
```

Milestone 3 adds the production input/UI/settings layer: version-controlled semantic action maps,
keyboard/gamepad menu focus, bounded player rebinding, display/accessibility settings and atomic
player settings persistence. The source example exercises a title → settings → gameplay flow without
requiring a rendering window.

Milestone 4 integrates save/profile/config systems into the production lifecycle with bounded manual
slots, rotating autosaves, background snapshot validation, recovery/migration diagnostics and a
portable Windows/macOS/Linux user-data policy. Shipping settings share the same per-profile user-data
tree, so a real game can persist controls, display/accessibility preferences and game state coherently.

Milestone 5 adds the production scene/prefab/level package path: projects can declare an explicit boot
scene, deterministic scene dependencies and reusable prefabs; the exporter validates that declared
scene content stays inside the project and cannot be silently omitted from a shipping package. Legacy
projects without `[scenes]` keep the established 1.x export behavior.

Milestone 6 adds an opt-in production content build graph for assets, scenes, shaders and generated
shipping data. It derives deterministic dependency-first warmup/preload/stream plans, bridges preload
and streaming groups to the existing runtime systems, validates generated and filesystem content before
shipping, and makes `ProjectExporter` refuse profiles that would silently omit required graph content.

Milestone 7 adds an opt-in production crash/support path: bounded structured logs, privacy-safe crash
reports, project/build identity, diagnostic/performance snapshots and deterministic support ZIPs that
contain generated report metadata only. The workflow never sweeps arbitrary user files, argv or the
process environment into a support bundle automatically.

Milestone 8 adds deterministic host-native desktop shipping plans and artifact manifests. Clean-wheel
validation now proves actual packaged smoke-game build, inventory, verification and runtime execution on
Windows, Linux and macOS while unsupported desktop cross-compilation remains an explicit error.

Milestone 9 closes the representative real-game production path. The maintained 2D and 3D games plus a
deterministic multiplayer fixture are copied into isolated project manifests, exercise shipping input,
settings and save/profile state, validate scene/content graphs, stage deterministic export inventories and
run both source and staged entrypoints. Player-specific data stays outside redistributable project content.

See:
- [`docs/PROJECT_PRODUCTION_1_9.md`](docs/PROJECT_PRODUCTION_1_9.md)
- [`docs/RUN_SESSIONS_1_9.md`](docs/RUN_SESSIONS_1_9.md)
- [`docs/INPUT_UI_SETTINGS_1_9.md`](docs/INPUT_UI_SETTINGS_1_9.md)
- [`docs/GAME_STATE_PRODUCTION_1_9.md`](docs/GAME_STATE_PRODUCTION_1_9.md)
- [`docs/SCENE_PACKAGES_1_9.md`](docs/SCENE_PACKAGES_1_9.md)
- [`docs/CONTENT_BUILD_1_9.md`](docs/CONTENT_BUILD_1_9.md)
- [`docs/RUNTIME_DIAGNOSTICS_1_9.md`](docs/RUNTIME_DIAGNOSTICS_1_9.md)
- [`docs/desktop-shipping-1.9.md`](docs/desktop-shipping-1.9.md)
- [`docs/REAL_GAME_PRODUCTION_1_9.md`](docs/REAL_GAME_PRODUCTION_1_9.md)
- [`ROADMAP_1_9.md`](ROADMAP_1_9.md)

## 🎮 Validation games and examples

Representative projects are integration fixtures rather than separate releases:

- **SwirEngine 2D Game Demo** — [`examples/2d_game_demo/`](examples/2d_game_demo/)
- **SwirEngine 3D Game Demo** — [`examples/3d_game_demo/`](examples/3d_game_demo/)
- **SwirEngine Multiplayer Game Demo** — [`examples/multiplayer_game_demo/`](examples/multiplayer_game_demo/)
- **Neon Frontier 1.4** — locked 1.4 compatibility/showcase project
- **Neon Frontier 1.3** — locked 1.3 regression game
- **Neon Cube Hunt 3D** — OpenGL + packaged-runtime regression arena
- **Neon Snake 3D** — complete 3D regression project

The 1.9 Real-Game Production Gate drives the 2D, 3D and multiplayer fixtures through the same
project/run/settings/save/assets/scenes/export workflow used by creators, including staged runtime checks.

## 🧪 Development and verification

```bash
python -m pip install -e ".[dev]"
pytest
ruff check src tests examples demo_projects tools
python -m compileall -q src tests examples demo_projects tools
```

Dedicated workflows additionally cover source-checkpoint contracts, OpenGL/runtime probes,
deterministic workloads, clean-wheel installation, desktop export and packaged-game regressions.

Progress assets are generated from the authoritative 1.9 roadmap and must stay synchronized:

```bash
python tools/generate_progress_svg.py
python tools/generate_progress_svg.py --check
```

The SVG layer does not replace roadmap math or release gates.

## 🔒 API and release policy

- `v1.4.0` and `v1.5.0` are published stable historical releases.
- The public stable package stays at **1.5.0** while 1.6–1.9 are developed as source-only checkpoints.
- Stable 1.x behavior is preserved; later source systems are additive or opt-in where required.
- The 2D, 3D and multiplayer demo projects remain source-only integration fixtures.
- No 1.6, 1.7, 1.8 or 1.9 GitHub Release, release tag or PyPI publication is permitted.
- The next public GitHub Release and PyPI publication must be **SwirEngine 2.0**, after its dedicated
  roadmap and full release gate are verified.

See [`docs/API_STABILITY.md`](docs/API_STABILITY.md).

## 🗺 Roadmaps

- SwirEngine 1.0 — [`ROADMAP.md`](ROADMAP.md) — **31/31 = 100%**, historical
- SwirEngine 1.1 — [`ROADMAP_1_1.md`](ROADMAP_1_1.md) — **10/10 = 100%**, historical
- SwirEngine 1.2 — [`ROADMAP_1_2.md`](ROADMAP_1_2.md) — **10/10 = 100%**, historical
- SwirEngine 1.3 — [`ROADMAP_1_3.md`](ROADMAP_1_3.md) — **10/10 = 100%**, locked compatibility line
- SwirEngine 1.4 — [`ROADMAP_1_4.md`](ROADMAP_1_4.md) — **10/10 = 100.0%**, released and locked
- SwirEngine 1.5 — [`ROADMAP_1_5.md`](ROADMAP_1_5.md) — **10/10 = 100.0%**, released and locked
- SwirEngine 1.6 — [`ROADMAP_1_6.md`](ROADMAP_1_6.md) — **10/10 = 100.0%**, source-only checkpoint
- SwirEngine 1.7 — [`ROADMAP_1_7.md`](ROADMAP_1_7.md) — **10/10 = 100.0%**, source-only checkpoint
- SwirEngine 1.8 — [`ROADMAP_1_8.md`](ROADMAP_1_8.md) — **10/10 = 100.0%**, source-only checkpoint
- **SwirEngine 1.9 — [`ROADMAP_1_9.md`](ROADMAP_1_9.md) — 9/10 = 90.0%, active source roadmap**

## ⚠️ Current limitations

- The published PyPI package intentionally does not contain source-only 1.6–1.9 development work.
- Android and Web export targets remain experimental staging paths; they are not upgraded to stable
  platform support by a manifest profile.
- Desktop cross-compilation is not claimed; native builds belong on the matching host platform.
- Later source systems are not treated as public stable API until the 2.0 release process says so.
- Performance timings in CI are workload regression contracts, not unmeasured FPS claims.

## 🔗 Links

- PyPI: https://pypi.org/project/swirengine/
- Repository: https://github.com/Swir/SwirEngine
- Releases: https://github.com/Swir/SwirEngine/releases
- Changelog: https://github.com/Swir/SwirEngine/blob/main/CHANGELOG.md

## 🔎 Search Keywords

`python game engine` • `python 2d game engine` • `python 3d game engine` • `python game development` •
`python game framework` • `python OpenGL engine` • `2d 3d game engine` • `pip install game engine` •
`python game runtime` • `python creator tools` • `python game packaging` • `python game exporter` •
`python multiplayer game engine` • `python PBR renderer` • `python game editor` • `cross platform game engine`

## License

MIT

<img width="100%" src="https://raw.githubusercontent.com/Swir/Swir/main/assets/power-divider-v4.svg" alt="SWIR electric divider" />