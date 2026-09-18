<!-- SWIR-README-STANDARD:v2 -->

<div align="center">

<img width="100%" src="assets/readme/hero.svg" alt="SwirEngine — Python-first engine for complete 2D, 3D and multiplayer games" />

<br>

![CI](https://img.shields.io/github/actions/workflow/status/Swir/SwirEngine/ci.yml?branch=main&style=for-the-badge&label=CI&color=02050A&logo=githubactions&logoColor=62E5FF)
[![PyPI](https://img.shields.io/pypi/v/swirengine?style=for-the-badge&color=02050A&logo=pypi&logoColor=62E5FF)](https://pypi.org/project/swirengine/)
![Python](https://img.shields.io/badge/Python-3.10--3.14%2064--bit%20CPython%20source%20matrix-02050A?style=for-the-badge&logo=python&logoColor=62E5FF)
![Status](https://img.shields.io/badge/STATUS-1.5.0%20STABLE-02050A?style=for-the-badge&logoColor=62E5FF)
![Source](https://img.shields.io/badge/SOURCE%20ROADMAP-2.0-02050A?style=for-the-badge&logoColor=62E5FF)
![License](https://img.shields.io/badge/LICENSE-MIT-02050A?style=for-the-badge&logo=opensourceinitiative&logoColor=62E5FF)

[![Author](https://img.shields.io/badge/Author-Swir-0088FF?style=flat-square&logo=github)](https://github.com/Swir)
[![Stars](https://img.shields.io/github/stars/Swir/SwirEngine?style=flat-square&color=0088FF)](https://github.com/Swir/SwirEngine/stargazers)

<br>

[**Install**](#-install) · [**Quick Start**](#-quick-start) · [**2.0 Roadmap**](ROADMAP_2_0.md) · [**Examples**](#-real-game-integration-fixtures) · [**Releases**](https://github.com/Swir/SwirEngine/releases)

</div>

<img width="100%" src="https://raw.githubusercontent.com/Swir/Swir/main/assets/power-divider-v4.svg" alt="SWIR electric divider" />

## 📊 Project status

<img width="100%" src="assets/readme/progress-card.svg" alt="SwirEngine 2.0 verified roadmap progress: 9 of 10 milestones, 90.0%, in progress" />

**Active source scope:** SwirEngine 2.0 — Release-Quality Python-First Game Production  
**Verified source progress:** **9/10 milestones = 90.0% — IN PROGRESS**  
**Latest public stable release:** **SwirEngine 1.5.0**  
**Release readiness:** **not beta-ready and not release-ready**; roadmap progress and release readiness are separate gates.

`Release/PyPI: frozen until SwirEngine 2.0`

SwirEngine is a Python-first 2D/3D game engine focused on complete creator workflows: runtime systems,
real rendering validation, deterministic tooling, multiplayer foundations, production project manifests,
diagnostics, export staging and host-native desktop shipping. The repository completed source-only
checkpoints 1.6–1.9 without publishing them; 2.0 is now the active measured development scope.

The first nine verified 2.0 milestones lock the published **1.5.0** compatibility floor, integrate project
creation/validation/run/shipping preparation, add a production-facing multiplayer contract, harden runtime
scalability/resource lifecycle behavior, establish the verified base-engine Python/platform matrix, prove
representative 2D/3D/multiplayer production workflows, verify exact-source wheel/sdist clean installs plus
host-native packaged-game execution on Windows/Linux/macOS, establish reproducible performance evidence,
and add deterministic staged-export/build identity plus privacy-safe support-bundle verification. The final
2.0 release gate and public-install verification remain outstanding.

## ✨ Highlights

| Area | Current source capability |
|---|---|
| Unified 2D + 3D | Sprite/tilemap workflows and OpenGL-backed 3D scenes under one Python-first runtime. |
| Scenes + content | Scenes, prefabs, serialization, production scene packages, content build graphs and streaming foundations. |
| Rendering | Materials, lighting, shadows, post-processing, instancing, culling, terrain/LOD, bounded transient-resource reuse and production-sized 2D/3D scalability checks. |
| Animation | Tween/timeline/state machines, animation graphs, skeletal animation and GPU skinning paths. |
| Physics + navigation | 2D/3D collision and rigid-body systems, character controllers, navigation and local-avoidance foundations. |
| Audio | Runtime audio engine, buses/groups, spatial behavior and source-development mixer/runtime work. |
| UI + input | Retained UI, focus/navigation, keyboard/mouse/gamepad input and production rebinding/settings foundations. |
| Saves + profiles | Save/profile APIs plus source-development autosave, recovery and production user-data integration. |
| Networking | TCP/gameplay APIs plus source-only production session/replication contracts, compatibility fingerprints, reconnect resynchronization and a headless dedicated-server adapter used by the multiplayer fixture. |
| Creator workflow | `swirengine workflow` composes project/run/scene/content/settings/save-policy checks, safe preparation, export-profile validation and actionable diagnostics. |
| Packaging | Exact-source wheel/sdist inspection, isolated clean installs, installed-artifact 2D/3D/multiplayer fixture execution and host-native desktop package runtime verification. |
| Performance evidence | Locked deterministic runtime/creator/network/render/world workloads with contextual CI evidence; shared-runner timings are regression signals, not unsupported FPS claims. |
| Diagnostics | Profiling, bounded crash/support reporting, streaming pressure/lifecycle diagnostics, deterministic build-integrity seals and privacy/integrity audits for generated support bundles. |
| Compatibility | Published 1.5.0 root API is the explicit 2.0 migration floor; current source base-engine matrix is verified on 64-bit CPython 3.10–3.14 across hosted Windows, Linux and macOS runners. |

## 📦 Install

The latest **public stable package is 1.5.0**.

Published 1.5.0 validation covers **Python 3.10-3.13** on Windows, Linux and macOS, plus
**Python 3.14 on Windows x86-64** through the documented native-wheel path. Separately, the current
source-development 2.0 base-engine matrix is verified on 64-bit CPython **3.10–3.14** across the hosted
Windows, Linux and macOS runner families. That source evidence is not a published 2.0 package claim.
See [`docs/SUPPORT_MATRIX_2_0.md`](docs/SUPPORT_MATRIX_2_0.md) for architecture boundaries and non-claims.

```bash
python -m pip install -U swirengine==1.5.0
```

Optional audio support:

```bash
python -m pip install -U "swirengine[audio]==1.5.0"
```

Current source development:

```bash
git clone https://github.com/Swir/SwirEngine.git
cd SwirEngine
git fetch --tags
python -m pip install -e ".[dev]"
```

> `pyproject.toml` intentionally remains at 1.5.0 until the verified final SwirEngine 2.0 release gate.
> No 1.6, 1.7, 1.8 or 1.9 package/tag/release is created.

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

## 🧭 Current 2.0 development workflow

The active roadmap is [`ROADMAP_2_0.md`](ROADMAP_2_0.md). Its ten release-quality milestones cover:

1. public API and migration compatibility;
2. creator workflow and integrated tooling;
3. multiplayer and dedicated-server production behavior;
4. renderer/runtime scalability and resource lifecycle;
5. the final Python/platform support matrix;
6. representative 2D/3D/multiplayer shipping workflows;
7. packaging, clean installs and native desktop shipping;
8. reproducible performance/competitive evidence;
9. export/build integrity, diagnostics and release safety;
10. the final 2.0 release gate and public PyPI verification.

Milestone 1 locks compatibility to the actual published `v1.5.0` root API rather than a hand-written
subset. Milestone 2 adds one integrated creator inspection/preparation path over the existing project,
run-session, scene/prefab, content-build, input/settings and save/profile policies. New projects receive
editable controls/settings defaults automatically, while existing projects can be prepared without
overwriting user files. Milestone 3 adds deterministic client/server compatibility checks, a production
session facade, reconnect token rotation with forced full resynchronization, explicit authoritative versus
player-local state boundaries and a validated fixed-tick headless dedicated-server path. Milestone 4
hardens streaming/cache lifecycle semantics, explicit resource teardown and pressure diagnostics while
locking representative 16,384-tile, 4,096-sprite and 4,096-object scene workloads to bounded/reuse/pruning
invariants instead of unsupported shared-runner FPS claims. Milestone 5 verifies all 15 Windows/Linux/macOS
× CPython 3.10–3.14 base-engine cells through platform probes, wheel construction, isolated clean installs
and maintained headless 2D/3D runtime fixtures. Milestone 6 drives maintained 2D, 3D and multiplayer
projects through the same production creator/shipping contracts, including real focus/navigation/activation,
player-local data isolation, privacy-safe diagnostic evidence, deterministic export staging, source/staged
runtime entrypoints and deliberate missing-scene/asset/entrypoint failure probes. Milestone 7 builds the
exact candidate source as wheel and sdist, performs bounded archive safety/inventory validation, installs
each artifact into isolated environments, runs the maintained fixtures from those installs and then builds,
validates and executes host-native desktop packages on Windows, Linux and macOS from the clean wheel.
Milestone 8 locks six existing deterministic performance/scalability workloads to their source thresholds,
captures exact commit/Python/platform runner context in ephemeral CI evidence and performs an official-doc
workflow audit for Arcade, Panda3D and Ursina without publishing technically invalid cross-engine FPS,
latency, memory or superiority rankings. Milestone 9 verifies staged export bytes against the canonical
inventory/checksums, seals a deterministic build identity including generated native build inputs and audits
opt-in support bundles for bounded content, integrity, redaction, safe paths and expected build identity.

```bash
git fetch --tags
python tools/verify_2_0_public_api.py
python tools/verify_platform_matrix_2_0.py
python tools/verify_real_game_shipping_2_0.py
python tools/verify_performance_evidence_2_0.py --validate-only
python tools/verify_release_safety_2_0.py
swirengine new MyGame --mode 3d
swirengine workflow MyGame --profile windows
swirengine workflow MyGame --json
swirengine run MyGame --dry-run
```

For an older source project missing creator directories or editable defaults:

```bash
swirengine workflow . --prepare
```

See:
- [`docs/MIGRATING_TO_2_0.md`](docs/MIGRATING_TO_2_0.md)
- [`docs/public_api_2_0.json`](docs/public_api_2_0.json)
- [`docs/API_STABILITY.md`](docs/API_STABILITY.md)
- [`docs/CREATOR_WORKFLOW_2_0.md`](docs/CREATOR_WORKFLOW_2_0.md)
- [`docs/MULTIPLAYER_PRODUCTION_2_0.md`](docs/MULTIPLAYER_PRODUCTION_2_0.md)
- [`docs/RUNTIME_SCALABILITY_2_0.md`](docs/RUNTIME_SCALABILITY_2_0.md)
- [`docs/SUPPORT_MATRIX_2_0.md`](docs/SUPPORT_MATRIX_2_0.md)
- [`docs/REAL_GAME_SHIPPING_2_0.md`](docs/REAL_GAME_SHIPPING_2_0.md)
- [`docs/PACKAGING_SHIPPING_2_0.md`](docs/PACKAGING_SHIPPING_2_0.md)
- [`docs/PERFORMANCE_EVIDENCE_2_0.md`](docs/PERFORMANCE_EVIDENCE_2_0.md)
- [`docs/RELEASE_SAFETY_2_0.md`](docs/RELEASE_SAFETY_2_0.md)
- [`docs/SWIRENGINE_2_0_READINESS_AUDIT.md`](docs/SWIRENGINE_2_0_READINESS_AUDIT.md)
- [`ROADMAP_2_0.md`](ROADMAP_2_0.md)

## 🎮 Real-game integration fixtures

Representative projects are source-only engine integration fixtures and do **not** receive separate releases:

- **SwirEngine 2D Game Demo** — [`examples/2d_game_demo/`](examples/2d_game_demo/)
- **SwirEngine 3D Game Demo** — [`examples/3d_game_demo/`](examples/3d_game_demo/)
- **SwirEngine Multiplayer Game Demo** — [`examples/multiplayer_game_demo/`](examples/multiplayer_game_demo/)
- **Neon Frontier 1.3** — locked historical compatibility fixture
- **Neon Frontier 1.4** — locked compatibility/showcase fixture
- **Neon Cube Hunt 3D** — OpenGL + packaged-runtime regression arena
- **Neon Snake 3D** — complete 3D regression project

The verified 2.0 real-game shipping gate drives the maintained 2D, 3D and multiplayer fixtures through
creator preparation, source runtime, deterministic staged export, staged runtime, settings/save boundaries,
scene/content integrity, real UI focus/navigation/activation and privacy-safe runtime diagnostics. Fixture
failures are treated as engine integration failures rather than demo-only issues.

## 🧪 Development and verification

```bash
python -m pip install -e ".[dev]"
pytest
ruff check src tests examples demo_projects tools
python -m compileall -q src tests examples demo_projects tools
python tools/verify_creator_workflow_2_0.py
pytest -q tests/test_multiplayer_2_0.py
python examples/multiplayer_game_demo/run_game.py
python tools/verify_runtime_scalability_2_0.py
python tools/verify_platform_matrix_2_0.py
python -m pytest -q tests/test_platform_matrix_2_0.py
python tools/verify_real_game_shipping_2_0.py
python -m pytest -q tests/test_real_game_shipping_2_0.py
python -m pytest -q tests/test_packaging_shipping_2_0.py
python tools/verify_performance_evidence_2_0.py --output build/performance-evidence.json
python -m pytest -q tests/test_performance_evidence_2_0.py
python tools/verify_release_safety_2_0.py
python -m pytest -q tests/test_release_safety_2_0.py
```

Progress assets are generated from the authoritative **2.0** roadmap:

```bash
python tools/generate_progress_svg.py
python tools/generate_progress_svg.py --check
```

The generator owns one README card, one active-roadmap mini graphic and one reusable SVG marked
**TEMPLATE / NOT PROJECT DATA**. Only the card and mini are embedded as live progress.

The SVG layer visualizes verified roadmap math; it never replaces CI, release, compatibility or
runtime gates.

## 🧱 Architecture and technology

SwirEngine keeps a high-level Python creator surface over modular runtime systems. The repository
contains rendering, scene/ECS, assets, serialization, physics, audio, input/UI, networking, editor,
diagnostics and export/shipping modules with focused regression workflows. Advanced systems remain
available as explicit APIs instead of being hidden behind a single monolithic game object.

The 2.0 architecture work is evaluated against real-game integration, resource lifetime, deterministic
tooling, failure handling and package/export behavior—not feature count alone.

## 🔒 API and release policy

- `v1.4.0` and `v1.5.0` are immutable published historical releases except for genuine maintenance fixes.
- **1.5.0 remains the latest public stable package.**
- 1.6, 1.7, 1.8 and 1.9 are completed source-only checkpoints and are not published.
- The 2D, 3D and multiplayer game demos remain source-only integration fixtures.
- The published 1.5.0 `swirengine.__all__` surface is the starting compatibility floor for 2.0.
- Deliberate 2.0 breaking changes require a documented migration, tests and explicit engineering justification.
- The next GitHub Release, release tag and PyPI publication must be **SwirEngine 2.0**.
- Publication is forbidden until the exact final candidate passes the dedicated Milestone 10 release gate.

Historical locked compatibility evidence remains explicit: **SwirEngine 1.4 is released and locked**.
The published 1.5.0 gate verified **Python 3.10-3.13** cross-platform and **Python 3.14 on Windows x86-64**.
Its locked 1.5 capability evidence includes **Deterministic Simulation & Replay**, **Save & Profile 2.0**,
**World Streaming 2.0**, **UI Toolkit 2.0** and **Runtime Diagnostics & Profiling 2.0**. These statements
describe published historical release evidence and remain separate from the verified source-development
SwirEngine 2.0 base-engine support matrix.

See [`docs/API_STABILITY.md`](docs/API_STABILITY.md),
[`docs/MIGRATING_TO_2_0.md`](docs/MIGRATING_TO_2_0.md) and
[`docs/SUPPORT_MATRIX_2_0.md`](docs/SUPPORT_MATRIX_2_0.md).

## 🗺 Roadmaps

| Line | Scope | Verified state |
|---|---|---:|
| 1.0 | [`ROADMAP.md`](ROADMAP.md) | 31/31 = 100%, historical |
| 1.1 | [`ROADMAP_1_1.md`](ROADMAP_1_1.md) | 10/10 = 100%, historical |
| 1.2 | [`ROADMAP_1_2.md`](ROADMAP_1_2.md) | 10/10 = 100%, historical |
| 1.3 | [`ROADMAP_1_3.md`](ROADMAP_1_3.md) | 10/10 = 100%, locked compatibility |
| 1.4 | [`ROADMAP_1_4.md`](ROADMAP_1_4.md) | 10/10 = 100.0%, released/locked |
| 1.5 | [`ROADMAP_1_5.md`](ROADMAP_1_5.md) | 10/10 = 100.0%, released/locked |
| 1.6 | [`ROADMAP_1_6.md`](ROADMAP_1_6.md) | 10/10 = 100.0%, source-only checkpoint |
| 1.7 | [`ROADMAP_1_7.md`](ROADMAP_1_7.md) | 10/10 = 100.0%, source-only checkpoint |
| 1.8 | [`ROADMAP_1_8.md`](ROADMAP_1_8.md) | 10/10 = 100.0%, source-only checkpoint |
| 1.9 | [`ROADMAP_1_9.md`](ROADMAP_1_9.md) | 10/10 = 100.0%, source-only checkpoint |
| **2.0** | **[`ROADMAP_2_0.md`](ROADMAP_2_0.md)** | **9/10 = 90.0%, active development** |

## ⚠️ Current limitations

- The PyPI package is still 1.5.0; source-only 1.6–2.0 development is not published.
- SwirEngine 2.0 currently has no beta-ready or release-ready claim.
- The verified 2.0 base-engine matrix covers only the 64-bit hosted runner architectures exercised by CI; 32-bit Python, PyPy, free-threaded CPython and unverified architectures are not claimed.
- Optional extras such as audio are not automatically covered by the base-engine support claim without their own evidence.
- Desktop build plans are host-native; unsupported cross-compilation is intentionally rejected.
- The dedicated-server contract is headless and deterministic but does not claim public matchmaking, hosting infrastructure or universal transport support.
- Cross-engine FPS, latency and memory rankings remain intentionally unclaimed without an identical maintained comparison harness.
- Visual editor ergonomics remain an area for later creator-tooling hardening even though the integrated Milestone 2 workflow is verified.

## 🔎 Search Keywords

`Python game engine` · `Python 2D engine` · `Python 3D engine` · `Python multiplayer engine` ·
`pip game engine` · `game development Python` · `OpenGL Python game engine` · `scene prefab engine` ·
`Python ECS` · `Python physics engine` · `Python game editor` · `desktop game packaging` ·
`PyInstaller game build` · `game engine networking` · `SwirEngine`

---

<div align="center">

**SWIR ENGINEERING · PYTHON-FIRST GAME PRODUCTION**

[GitHub](https://github.com/Swir/SwirEngine) · [Releases](https://github.com/Swir/SwirEngine/releases) · [PyPI](https://pypi.org/project/swirengine/)

</div>