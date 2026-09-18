<!-- SWIR-README-STANDARD:v2 -->

<div align="center">

<img width="100%" src="assets/readme/hero.svg" alt="SwirEngine — Python-first engine for complete 2D and 3D games" />

<br>

![CI](https://img.shields.io/github/actions/workflow/status/Swir/SwirEngine/ci.yml?branch=main&style=for-the-badge&label=CI&color=02050A&logo=githubactions&logoColor=62E5FF)
[![PyPI](https://img.shields.io/pypi/v/swirengine?style=for-the-badge&color=02050A&logo=pypi&logoColor=62E5FF)](https://pypi.org/project/swirengine/)
![Python](https://img.shields.io/badge/Python-3.10--3.13%20cross--platform%20%7C%203.14%20Windows-02050A?style=for-the-badge&logo=python&logoColor=62E5FF)
![Status](https://img.shields.io/badge/STATUS-1.5.0%20STABLE-02050A?style=for-the-badge&logoColor=62E5FF)
![Source](https://img.shields.io/badge/SOURCE%20ROADMAP-2.0-02050A?style=for-the-badge&logoColor=62E5FF)
![License](https://img.shields.io/badge/LICENSE-MIT-02050A?style=for-the-badge&logo=opensourceinitiative&logoColor=62E5FF)

[![Author](https://img.shields.io/badge/Author-Swir-0088FF?style=flat-square&logo=github)](https://github.com/Swir)
[![Stars](https://img.shields.io/github/stars/Swir/SwirEngine?style=flat-square&color=0088FF)](https://github.com/Swir/SwirEngine/stargazers)

<br>

[**Install**](#-install) · [**Quick Start**](#-quick-start) · [**2.0 Source Work**](#-current-20-source-work) · [**Roadmaps**](#-roadmaps) · [**Releases**](https://github.com/Swir/SwirEngine/releases)

</div>

<img width="100%" src="https://raw.githubusercontent.com/Swir/Swir/main/assets/power-divider-v4.svg" alt="SWIR electric divider" />

## 📊 Project status

<img width="100%" src="assets/readme/progress-card.svg" alt="SwirEngine 2.0 verified roadmap progress: 0 of 10 milestones, 0.0%, in progress" />

**Active source scope:** SwirEngine 2.0 — Complete Game Production & Public Release  
**Verified 2.0 progress:** **0/10 milestones = 0.0% — IN PROGRESS**  
**Latest public stable release:** **SwirEngine 1.5.0**  
**Completed source checkpoint:** **SwirEngine 1.9 = 10/10 = 100.0%**  
**Release readiness:** **NOT READY** — the new 2.0 roadmap has an explicit denominator and starts from zero; completed 1.9 work is evidence/input, not inherited 2.0 completion.

`Release/PyPI: frozen until SwirEngine 2.0`

SwirEngine is a Python-first 2D/3D game engine focused on a unified creator API, production runtime
systems, real rendering validation, deterministic tooling and a practical path from a project manifest
to a shipped desktop game. The public package remains the verified 1.5.0 stable baseline while source
development now moves through the dedicated 2.0 release roadmap.

Source checkpoints 1.6, 1.7, 1.8 and 1.9 are complete and remain source-only history. They established
large-world/runtime work, frame/resource hardening, rendering delivery, project manifests, production
settings/save/scenes/content, crash/support diagnostics, desktop shipping and representative 2D/3D/
multiplayer production gates. SwirEngine 2.0 must now convert that accumulated capability into a stable,
coherent public product with an explicit migration contract and final release evidence.

## ✨ Highlights

| Area | What creators get |
|---|---|
| Unified 2D + 3D | One Python-first runtime for sprite/tilemap projects and OpenGL 3D scenes. |
| Production runtime | Scenes, prefabs, ECS, plugins, settings, saves/profiles, deterministic simulation and replay. |
| Rendering | PBR materials, lighting, shadows, post-processing, instancing, culling, terrain/LOD and the completed 1.8 render-graph/GPU delivery checkpoint. |
| Animation | Tween/timeline/state machines, animation graphs, skeletal animation and GPU skinning. |
| Physics + navigation | 2D/3D collision, Physics 2.0, character controllers, deterministic navigation and local avoidance. |
| Audio | Audio buses/groups, spatial attenuation and the additive Audio 2.0 mixer/runtime. |
| UI + input | Retained UI, keyboard/mouse/gamepad focus, controller input, rebinding foundations and production settings integration. |
| Large worlds | Asset Pipeline 2.0, derived caching, world streaming and bounded resource/runtime diagnostics. |
| Networking | Stable networking APIs plus source-only replication/session/QoS foundations exercised by the 1.9 multiplayer fixture. |
| Creator workflow | Project manifests, editor tooling, development sessions, export staging, deterministic build plans and host-native desktop validation. |
| Diagnostics | Stable profiler plus additive runtime/resource/timing capture and privacy-bounded support bundles. |
| Compatibility | Released 1.5.0 public API is now machine-locked as the explicit 2.0 migration baseline. |

## 📦 Install

The latest **public stable package is 1.5.0**.

Verified published support covers **Python 3.10-3.13** on Windows, Linux and macOS, plus
**Python 3.14 on Windows x86-64** through the validated native-wheel path documented for the stable line.

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

> The repository contains source-only work newer than the published 1.5.0 package. The package version
> intentionally stays frozen during ordinary 2.0 development so intermediate source state cannot masquerade
> as a public release.

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

## 🧭 Current 2.0 source work

The authoritative roadmap is [`ROADMAP_2_0.md`](ROADMAP_2_0.md). It starts at **0/10**, deliberately
separate from the completed 1.9 source checkpoint.

The first milestone establishes the public API/migration contract before larger 2.0 product changes are
allowed to reshape the creator surface. The released `v1.5.0` root exports are stored in a machine-readable
baseline, and all 2.0 root additions/removals must be represented in a separate migration ledger.

Development verification:

```bash
python tools/verify_api_contract_2_0.py
python tools/verify_api_contract_2_0.py --json
python tools/generate_progress_svg.py --check
```

The API verifier is static: it reads `swirengine.__all__` and `__version__` from the syntax tree without
importing renderer, audio, networking or editor backends. During ordinary development it requires both the
package surface and `pyproject.toml` to remain at `1.5.0`. Explicit release-candidate mode requires both to
be exactly `2.0.0` and is reserved for the final verified release path.

See:
- [`ROADMAP_2_0.md`](ROADMAP_2_0.md)
- [`docs/API_MIGRATION_2_0.md`](docs/API_MIGRATION_2_0.md)
- [`docs/api-contracts/swirengine-1.5-public-api.json`](docs/api-contracts/swirengine-1.5-public-api.json)
- [`docs/api-contracts/swirengine-2.0-migration.json`](docs/api-contracts/swirengine-2.0-migration.json)
- [`docs/SWIRENGINE_2_0_READINESS_AUDIT.md`](docs/SWIRENGINE_2_0_READINESS_AUDIT.md)
- [`ROADMAP_1_9.md`](ROADMAP_1_9.md) — completed source checkpoint

## 🧱 Completed 1.9 production foundation

SwirEngine 1.9 closed the source-only production path that 2.0 now builds on:

- validated `swirproject.toml`, production profiles, `doctor`, deterministic run plans and project fingerprints;
- shipping input/action maps, keyboard/gamepad UI focus, rebinding and display/accessibility settings;
- save/profile/config lifecycle with bounded manual saves, autosaves and recovery diagnostics;
- explicit boot scenes, scene/prefab dependencies and export-safe content validation;
- deterministic content build graph with warmup/preload/stream planning;
- privacy-bounded crash reports and deterministic support bundles;
- Windows/Linux/macOS host-native shipping plans with clean-wheel package/runtime probes;
- representative 2D, 3D and multiplayer source-to-staged runtime validation;
- final 1.9 Python 3.10/3.13/3.14 source checkpoint and evidence-based 2.0 readiness audit.

No 1.9 tag, GitHub Release or PyPI package was created.

## 🎮 Validation games and examples

Representative projects are integration fixtures rather than separate releases:

- **SwirEngine 2D Game Demo** — [`examples/2d_game_demo/`](examples/2d_game_demo/)
- **SwirEngine 3D Game Demo** — [`examples/3d_game_demo/`](examples/3d_game_demo/)
- **SwirEngine Multiplayer Game Demo** — [`examples/multiplayer_game_demo/`](examples/multiplayer_game_demo/)
- **Neon Frontier 1.4** — locked 1.4 compatibility/showcase project
- **Neon Frontier 1.3** — locked 1.3 regression game
- **Neon Cube Hunt 3D** — OpenGL + packaged-runtime regression arena
- **Neon Snake 3D** — complete 3D regression project

The 2.0 roadmap keeps the 2D, 3D and multiplayer games as integration gates. They are used to find
awkward APIs, missing creator workflows, packaging failures and runtime regressions rather than to create
separate demo releases.

## 🧪 Development and verification

```bash
python -m pip install -e ".[dev]"
pytest
ruff check src tests examples demo_projects tools
python -m compileall -q src tests examples demo_projects tools
```

The completed 1.9 gate remains locked and must continue passing while 2.0 evolves:

```bash
python tools/verify_1_9_source_checkpoint.py --require-complete
```

Progress assets are generated from the authoritative 2.0 roadmap and must stay synchronized:

```bash
python tools/generate_progress_svg.py
python tools/generate_progress_svg.py --check
```

The SVG layer reports roadmap evidence only; it does not replace CI, migration, packaging or release gates.

## 🔒 API and release policy

- `v1.4.0` and `v1.5.0` are published stable historical releases.
- The public stable package remains **1.5.0** while 2.0 is developed and verified.
- Source checkpoints 1.6–1.9 remain source-only and receive no retroactive public releases.
- The released 1.5.0 `swirengine.__all__` surface is the locked 2.0 migration baseline.
- Source-only subsystems do not become public 2.0 root API automatically; promotion/removal must be explicit and tested.
- The 2D, 3D and multiplayer demo projects remain source-only integration fixtures.
- The next public GitHub Release and PyPI publication must be **SwirEngine 2.0**, only after the 2.0 roadmap is verified 10/10 and its final gate is green.
- After publication, a clean public-index PyPI install and dedicated post-release audit are still required.

See [`docs/API_STABILITY.md`](docs/API_STABILITY.md) and [`docs/API_MIGRATION_2_0.md`](docs/API_MIGRATION_2_0.md).

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
- SwirEngine 1.9 — [`ROADMAP_1_9.md`](ROADMAP_1_9.md) — **10/10 = 100.0%**, completed source-only checkpoint
- **SwirEngine 2.0 — [`ROADMAP_2_0.md`](ROADMAP_2_0.md) — 0/10 = 0.0%, active public-release roadmap**

## ⚠️ Current limitations

- The published PyPI package intentionally does not contain source-only work developed after 1.5.0.
- SwirEngine 2.0 currently has **0 verified roadmap milestones**; the existence of completed 1.9 systems does not imply 2.0 release readiness.
- Android and Web export targets remain experimental staging paths and are not stable platform claims.
- Desktop cross-compilation is not claimed; native builds belong on the matching host platform.
- The final 2.0 Python/platform support matrix is not locked until its dedicated milestone passes.
- Source-only systems are not treated as public stable API until the 2.0 migration/release process says so.
- Performance timings in CI are workload regression contracts, not unsupported FPS claims.

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

<div align="center">

### `BUILD • TEST • RELEASE • EVOLVE`

⭐ **If this project is useful, consider leaving a star.**

[**← SWIR profile**](https://github.com/Swir) · [**All projects →**](https://github.com/Swir?tab=repositories)

</div>
