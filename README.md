<!-- SWIR-README-STANDARD:v2 -->

<div align="center">

<img width="100%" src="assets/readme/hero.svg" alt="SwirEngine — Python-first engine for complete 2D, 3D and multiplayer games" />

<br>

![CI](https://img.shields.io/github/actions/workflow/status/Swir/SwirEngine/ci.yml?branch=main&style=for-the-badge&label=CI&color=02050A&logo=githubactions&logoColor=62E5FF)
[![PyPI](https://img.shields.io/pypi/v/swirengine?style=for-the-badge&color=02050A&logo=pypi&logoColor=62E5FF)](https://pypi.org/project/swirengine/)
![Python](https://img.shields.io/badge/Python-3.10--3.14%2064--bit%20CPython%20source%20matrix-02050A?style=for-the-badge&logo=python&logoColor=62E5FF)
![Status](https://img.shields.io/badge/STATUS-2.0.0%20PUBLIC-02050A?style=for-the-badge&logoColor=62E5FF)
![Audit](https://img.shields.io/badge/POST--RELEASE%20AUDIT-ACTIVE-02050A?style=for-the-badge&logoColor=62E5FF)
![License](https://img.shields.io/badge/LICENSE-MIT-02050A?style=for-the-badge&logo=opensourceinitiative&logoColor=62E5FF)

[![Author](https://img.shields.io/badge/Author-Swir-0088FF?style=flat-square&logo=github)](https://github.com/Swir)
[![Stars](https://img.shields.io/github/stars/Swir/SwirEngine?style=flat-square&color=0088FF)](https://github.com/Swir/SwirEngine/stargazers)

<br>

[**Install**](#-install) · [**Quick Start**](#-quick-start) · [**Post-Release Audit**](POST_RELEASE_AUDIT_2_0.md) · [**2.0 Roadmap**](ROADMAP_2_0.md) · [**Examples**](#-real-game-integration-fixtures) · [**Releases**](https://github.com/Swir/SwirEngine/releases)

</div>

<img width="100%" src="https://raw.githubusercontent.com/Swir/Swir/main/assets/power-divider-v4.svg" alt="SWIR electric divider" />

## 📊 Project status

<img width="100%" src="assets/readme/progress-card.svg" alt="SwirEngine 2.0 post-release audit progress: 1 of 10 checkpoints, 10.0%, in progress" />

**Active verified scope:** SwirEngine 2.0 — Post-Release Audit & Hardening  
**Audit progress:** **1/10 checkpoints = 10.0% — IN PROGRESS**  
**Latest public stable release:** **SwirEngine 2.0.0**  
**Completed release roadmap:** **10/10 milestones = 100.0%**  
**Public release source:** immutable `v2.0.0` at `4c219f3bed4c107c612a58fa2fb1f1362b4dfc46`

SwirEngine is a Python-first 2D/3D game engine focused on complete creator workflows rather than isolated feature demos. The public 2.0.0 release combines scene/content systems, rendering, animation, physics, navigation, audio, UI/input, saves/profiles, networking, dedicated-server foundations, diagnostics, deterministic export/build integrity, packaging and maintained representative 2D/3D/multiplayer integration fixtures.

The 2.0 release roadmap is complete and historical. Active work now follows [`POST_RELEASE_AUDIT_2_0.md`](POST_RELEASE_AUDIT_2_0.md): fresh architecture/API, runtime/resource, rendering/gameplay, multiplayer, creator workflow, packaging/platform, diagnostics/security, documentation and final regression audits. Cosmetic documentation work does not raise audit progress.

## ✨ Highlights

| Area | Public 2.0 capability |
|---|---|
| Unified 2D + 3D | Sprite/tilemap workflows and OpenGL-backed 3D scenes under one Python-first runtime. |
| Scenes + content | Scenes, prefabs, serialization, production scene packages, content build graphs and streaming foundations. |
| Rendering | Materials, lighting, shadows, post-processing, instancing, culling, terrain/LOD and bounded transient-resource reuse. |
| Animation | Tween/timeline/state machines, animation graphs, skeletal animation and GPU skinning paths. |
| Physics + navigation | 2D/3D collision and rigid-body systems, character controllers, navigation and local-avoidance foundations. |
| Audio | Runtime audio engine, buses/groups and spatial behavior through the optional audio path. |
| UI + input | Retained UI, focus/navigation, keyboard/mouse/gamepad input and rebinding/settings foundations. |
| Saves + profiles | Save/profile APIs, autosave/recovery foundations and production user-data integration. |
| Networking | Session/replication contracts, compatibility fingerprints, reconnect resynchronization and a headless dedicated-server adapter. |
| Creator workflow | `swirengine workflow` composes project/run/scene/content/settings/save-policy checks, safe preparation, export-profile validation and diagnostics. |
| Packaging | Exact-source wheel/sdist checks, isolated installs, installed-artifact fixtures and host-native packaged-game verification. |
| Diagnostics | Profiling, bounded crash/support reporting, streaming pressure/lifecycle diagnostics, deterministic build-integrity seals and privacy/integrity checks. |
| Compatibility | Published 1.5.0 root API remains the explicit migration floor; 2.0 source validation covers 64-bit CPython 3.10–3.14 on hosted Windows/Linux/macOS runners. |

## 📦 Install

The latest public package is **SwirEngine 2.0.0**:

```bash
python -m pip install -U swirengine==2.0.0
```

Optional audio support:

```bash
python -m pip install -U "swirengine[audio]==2.0.0"
```

Development checkout:

```bash
git clone https://github.com/Swir/SwirEngine.git
cd SwirEngine
python -m pip install -e ".[dev]"
```

The release pipeline rebuilt the immutable `v2.0.0` source, re-ran final compatibility/runtime/real-game/performance/release-safety gates, published through PyPI Trusted Publishing, created the GitHub Release, and verified fresh public-PyPI installs on Ubuntu/Python 3.13, macOS/Python 3.13 and Windows/Python 3.14. See [`docs/SUPPORT_MATRIX_2_0.md`](docs/SUPPORT_MATRIX_2_0.md) for exact architecture/runtime boundaries and explicit non-claims.

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

## 🧭 Active post-release workflow

The active quality source is [`POST_RELEASE_AUDIT_2_0.md`](POST_RELEASE_AUDIT_2_0.md). The completed release roadmap remains in [`ROADMAP_2_0.md`](ROADMAP_2_0.md), with its full pre-publication evidence permanently available at the immutable [`v2.0.0` snapshot](https://github.com/Swir/SwirEngine/blob/v2.0.0/ROADMAP_2_0.md).

Current audit domains:

1. public release and clean-install reality;
2. architecture/API/migration/backwards compatibility;
3. runtime lifecycle, memory and resource handling;
4. rendering, physics, audio, input and core gameplay systems;
5. networking, multiplayer and dedicated server;
6. creator/editor workflows and representative games;
7. packaging/export/Python/platform matrix;
8. diagnostics, crash handling, privacy/security/safety;
9. documentation/examples/upgrade/competitive evidence;
10. final fresh regression sweep and practical-completion review.

Core verification commands:

```bash
python tools/verify_2_0_release_candidate.py --require-final
python tools/verify_2_0_public_api.py
python tools/verify_platform_matrix_2_0.py
python tools/verify_real_game_shipping_2_0.py
python tools/verify_performance_evidence_2_0.py --validate-only
python tools/verify_release_safety_2_0.py
python tools/generate_progress_svg.py --check
swirengine new MyGame --mode 3d
swirengine workflow MyGame --profile windows
swirengine workflow MyGame --json
swirengine run MyGame --dry-run
```

For an older source project missing creator directories or editable defaults:

```bash
swirengine workflow . --prepare
```

Reference documentation:

- [`POST_RELEASE_AUDIT_2_0.md`](POST_RELEASE_AUDIT_2_0.md)
- [`ROADMAP_2_0.md`](ROADMAP_2_0.md)
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
- [`docs/RELEASE_GATE_2_0.md`](docs/RELEASE_GATE_2_0.md)
- [`docs/SWIRENGINE_2_0_READINESS_AUDIT.md`](docs/SWIRENGINE_2_0_READINESS_AUDIT.md) — historical pre-release audit

## 🎮 Real-game integration fixtures

Representative projects remain source-only engine integration fixtures and do **not** receive separate releases:

- **SwirEngine 2D Game Demo** — [`examples/2d_game_demo/`](examples/2d_game_demo/)
- **SwirEngine 3D Game Demo** — [`examples/3d_game_demo/`](examples/3d_game_demo/)
- **SwirEngine Multiplayer Game Demo** — [`examples/multiplayer_game_demo/`](examples/multiplayer_game_demo/)
- **Neon Frontier 1.3** — locked historical compatibility fixture
- **Neon Frontier 1.4** — locked compatibility/showcase fixture
- **Neon Cube Hunt 3D** — OpenGL + packaged-runtime regression arena
- **Neon Snake 3D** — complete 3D regression project

The 2.0 real-game gate drives maintained 2D, 3D and multiplayer fixtures through creator preparation, source runtime, deterministic staged export, staged runtime, settings/save boundaries, scene/content integrity, real UI focus/navigation/activation and privacy-safe diagnostics. Fixture failures are engine integration failures rather than demo-only issues.

## 🧪 Development and verification

```bash
python -m pip install -e ".[dev]"
pytest
ruff check src tests examples demo_projects tools
python -m compileall -q src tests examples demo_projects tools
python tools/verify_2_0_release_candidate.py --require-final
python tools/verify_creator_workflow_2_0.py
pytest -q tests/test_multiplayer_2_0.py
python examples/multiplayer_game_demo/run_game.py
python tools/verify_runtime_scalability_2_0.py
python tools/verify_platform_matrix_2_0.py
python tools/verify_real_game_shipping_2_0.py
python tools/verify_performance_evidence_2_0.py --output build/performance-evidence.json
python tools/verify_release_safety_2_0.py
```

Progress assets are generated from the authoritative active post-release audit:

```bash
python tools/generate_progress_svg.py
python tools/generate_progress_svg.py --check
```

The generator owns one README card, one authoritative-status mini graphic and one reusable SVG marked **TEMPLATE / NOT PROJECT DATA**. Only the card and mini are embedded as live progress. The SVG layer visualizes verified audit math; it never replaces CI, runtime, safety, compatibility or packaging gates.

## 🧱 Architecture and technology

SwirEngine keeps a high-level Python creator surface over modular rendering, scene/ECS, assets, serialization, physics, audio, input/UI, networking, editor, diagnostics and export/shipping systems. Advanced systems remain available as explicit APIs instead of being hidden behind one monolithic game object.

Post-release hardening is evaluated against real-game integration, API consistency, resource lifetime, deterministic tooling, failure handling, package/export behavior and creator productivity—not raw feature count.

## 🔒 API and release policy

- `v1.4.0`, `v1.5.0` and `v2.0.0` are immutable published historical releases.
- **2.0.0 is the latest public stable package.**
- 1.6, 1.7, 1.8 and 1.9 remain completed source-only checkpoints and are not retroactively published.
- The 2D, 3D and multiplayer game demos remain source-only integration fixtures.
- The published 1.5.0 `swirengine.__all__` surface is the explicit starting compatibility floor for 2.0.
- Deliberate breaking changes require documented migration evidence, tests and engineering justification.
- Post-release fixes must preserve release history; existing tags/artifacts are never moved or overwritten.
- Future publication/version policy must be decided from fresh release evidence rather than inferred from the completed 2.0 roadmap.

Historical locked compatibility evidence remains explicit: SwirEngine 1.4 and 1.5 are released/locked; source-only 1.6–1.9 remain engineering checkpoints. The 2.0 public release adds the completed 2.0 release-quality scope while keeping unsupported platform/runtime claims explicit.

## 🗺 Roadmaps and audits

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
| **2.0 release** | **[`ROADMAP_2_0.md`](ROADMAP_2_0.md)** | **10/10 = 100.0%, published** |
| **2.0 post-release** | **[`POST_RELEASE_AUDIT_2_0.md`](POST_RELEASE_AUDIT_2_0.md)** | **1/10 = 10.0%, active audit** |

## ⚠️ Current limitations

- The verified base-engine source matrix is limited to the 64-bit hosted runner architectures exercised by CI; 32-bit Python, PyPy, free-threaded CPython and unverified architectures are not claimed.
- Optional extras such as audio require their own dependency/runtime evidence and are not silently promoted to the base-engine support claim.
- Desktop build plans are host-native; unsupported cross-compilation is intentionally rejected.
- The dedicated-server contract is headless and deterministic but does not claim public matchmaking, hosting infrastructure or universal transport support.
- Cross-engine FPS, latency and memory rankings remain intentionally unclaimed without an identical maintained comparison harness.
- Visual editor ergonomics remain an explicit post-release audit area even though the integrated creator workflow is verified.
- Public package propagation can briefly differ between PyPI metadata and the Simple index immediately after publication; the post-release audit tracks hardening of that verification path.

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
