<!-- SWIR-README-STANDARD:v2 -->

<div align="center">

<img width="100%" src="assets/readme/hero.svg" alt="SwirEngine — Python-first engine for complete 2D, 3D and multiplayer games" />

<br>

![CI](https://img.shields.io/github/actions/workflow/status/Swir/SwirEngine/ci.yml?branch=main&style=for-the-badge&label=CI&color=02050A&logo=githubactions&logoColor=62E5FF)
[![PyPI](https://img.shields.io/pypi/v/swirengine?style=for-the-badge&color=02050A&logo=pypi&logoColor=62E5FF)](https://pypi.org/project/swirengine/)
![Python](https://img.shields.io/badge/Python-3.10--3.14%2064--bit%20CPython%20verified%20matrix-02050A?style=for-the-badge&logo=python&logoColor=62E5FF)
![Status](https://img.shields.io/badge/STATUS-2.0.0%20PUBLISHED-02050A?style=for-the-badge&logoColor=62E5FF)
![Development](https://img.shields.io/badge/2.1%20ROADMAP-10%2F10-02050A?style=for-the-badge&logoColor=62E5FF)
![License](https://img.shields.io/badge/LICENSE-MIT-02050A?style=for-the-badge&logo=opensourceinitiative&logoColor=62E5FF)

[![Author](https://img.shields.io/badge/Author-Swir-0088FF?style=flat-square&logo=github)](https://github.com/Swir)
[![Stars](https://img.shields.io/github/stars/Swir/SwirEngine?style=flat-square&color=0088FF)](https://github.com/Swir/SwirEngine/stargazers)

<br>

[**Install**](#-install) · [**Quick Start**](#-quick-start) · [**2.1 Roadmap**](ROADMAP_2_1.md) · [**Examples**](#-real-game-integration-fixtures) · [**Releases**](https://github.com/Swir/SwirEngine/releases)

</div>

<img width="100%" src="https://raw.githubusercontent.com/Swir/Swir/main/assets/power-divider-v4.svg" alt="SWIR electric divider" />

## 📊 Project status

<!-- SWIR-PYPI-PROGRESS:START -->
```text
Scope: SwirEngine 2.1 - SwirEditor & Creator Workflow
Progress: [##############################] 100.0%
Counter: 10 / 10 milestones
Status: COMPLETE
```
<!-- SWIR-PYPI-PROGRESS:END -->

**Active verified development scope:** SwirEngine 2.1 — SwirEditor & Creator Workflow  
**2.1 roadmap:** **10/10 milestones = 100.0% — COMPLETE**  
**2.1 beta-ready gate:** **YES — roadmap acceptance complete; publication pending**  
**Latest public stable release:** **SwirEngine 2.0.0**  
**Release date:** **2026-09-19**  
**Release source:** immutable tag **`v2.0.0`** from commit **`3fe0ff11e09ca0b4a9abcb2b757c12514100bc59`**

SwirEngine 2.0.0 is publicly released on GitHub and PyPI and remains the latest public stable package. The finite [`ROADMAP_2_1.md`](ROADMAP_2_1.md) source-development scope is complete: milestones 1–9 established the project-backed SwirEditor, authoring, runtime-backed gameplay tooling and creator-facing Build/Export workflow, while Milestone 10 drove representative 2D, 3D and multiplayer fixtures through the editor and requalified exact-source packaging, compatibility, performance, release-safety and the supported Windows/Linux/macOS CPython 3.10–3.14 matrix. Phase A acceptance evidence is anchored to exact preflight head `7b7cecb02b0d573d72cc55ec34ecfd307492f3ff`. No SwirEngine 2.1 tag, package version or public release is implied by roadmap completion.

Stable 2.0 maintenance is no longer tracked as a separate active progress scope. Historical audit evidence remains preserved, and concrete regressions, compatibility failures, security/safety issues or release-blocking defects still reopen focused maintenance when discovered.

## ✨ Highlights

| Area | Verified capability |
|---|---|
| Unified 2D + 3D | Sprite/tilemap workflows and OpenGL-backed 3D scenes under one Python-first runtime. |
| Scenes + content | Scenes, prefabs, serialization, production scene packages, content build graphs and streaming foundations. |
| SwirEditor 2.1 | Project-backed sessions, Project Hub, multi-scene authoring/recovery, typed Inspector multi-selection, component/prefab authoring, a production 2D/3D viewport with picking, camera navigation, transform gizmos, snapping, overlays, grid controls and live rendering, verified asset import/reimport and content validation, integrated Play/Pause/Stop/Step with isolated runtime state, Console source navigation, Profiler views and failure-safe diagnostics, runtime-backed gameplay authoring for input/rebinding, display/accessibility settings, animation, physics/collision, navigation/AI, audio, UI/HUD and save/profile workflows, plus the verified Build/Export Wizard. |
| Rendering | Materials, lighting, shadows, post-processing, instancing, culling, terrain/LOD and bounded transient-resource reuse. |
| Animation | Tween/timeline/state machines, animation graphs, skeletal animation and GPU skinning paths, with SwirEditor 2.1 clip authoring backed by the shipping runtime sampling model. |
| Physics + navigation | 2D/3D collision and rigid-body systems, character controllers, navigation and local-avoidance foundations, with SwirEditor 2.1 creator tooling backed by the shipping runtime APIs. |
| Audio | Runtime audio engine, buses/groups, spatial behavior and optional audio support, with SwirEditor 2.1 bus/cue authoring and runtime preview. |
| UI + input | Retained UI, focus/navigation, keyboard/mouse/gamepad input, rebinding and settings foundations, with integrated SwirEditor 2.1 HUD/input authoring. |
| Saves + profiles | Save/profile APIs, autosave/recovery foundations and production user-data integration, with SwirEditor 2.1 profile/policy/default authoring and runtime round-trip validation. |
| Networking | Gameplay networking, compatibility fingerprints, reconnect resynchronization and a fixed-tick headless dedicated-server adapter exercised by the multiplayer fixture. |
| Creator workflow | `swirengine workflow` composes project/run/scene/content/settings/save-policy checks, safe preparation, export-profile validation and diagnostics. |
| Packaging | Exact-source wheel/sdist checks, isolated installs, installed-artifact fixture execution, host-native desktop packaging validation and SwirEditor 2.1 Build/Export staging with deterministic artifact inspection. |
| Performance evidence | Deterministic runtime/creator/network/render/world workloads with contextual CI evidence; no unsupported cross-engine FPS claims. |
| Diagnostics | Profiling, bounded crash/support reporting, streaming pressure/lifecycle diagnostics, deterministic build-integrity seals and privacy/integrity audits for support bundles. |
| Compatibility | Published 1.5.0 root API remains the documented migration floor; 2.0 base-engine CI covers the maintained 64-bit CPython 3.10–3.14 hosted runner matrix within documented architecture limits. |

## 📦 Install

Install the latest public stable release from PyPI:

```bash
python -m pip install -U "swirengine==2.0.0"
```

Optional audio support:

```bash
python -m pip install -U "swirengine[audio]==2.0.0"
```

Source development:

```bash
git clone https://github.com/Swir/SwirEngine.git
cd SwirEngine
python -m pip install -e ".[dev]"
```

The verified base-engine matrix covers maintained **64-bit CPython 3.10–3.14** jobs across hosted Windows, Linux and macOS runners. This is not a blanket claim for 32-bit Python, PyPy, free-threaded CPython, all CPU architectures or every optional dependency. See [`docs/SUPPORT_MATRIX_2_0.md`](docs/SUPPORT_MATRIX_2_0.md).
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

## 🧭 Active development and stable maintenance

SwirEngine has one completed source-development scope awaiting a separate publication decision:

- [`ROADMAP_2_1.md`](ROADMAP_2_1.md) — **2.1 SwirEditor & Creator Workflow**, **10/10 = 100.0%**, source roadmap complete; publication pending.

Historical release-development detail remains preserved in [`ROADMAP_2_0.md`](ROADMAP_2_0.md), which is **10/10 = 100.0%** only for its named source-development scope. The former 2.0 post-release audit is retained as a historical verification snapshot rather than a parallel active roadmap.

### Key documentation

- [`ROADMAP_2_1.md`](ROADMAP_2_1.md) — completed 2.1 editor/creator source roadmap
- [`docs/MIGRATING_TO_2_1.md`](docs/MIGRATING_TO_2_1.md) — 2.0 → 2.1 migration guidance for source development
- [`docs/RELEASE_GATE_2_1.md`](docs/RELEASE_GATE_2_1.md) — 2.1 milestone acceptance and publication boundary
- [`ROADMAP_2_0.md`](ROADMAP_2_0.md) — historical 2.0 source-development roadmap
- [`docs/SWIRENGINE_2_0_POST_RELEASE_AUDIT.md`](docs/SWIRENGINE_2_0_POST_RELEASE_AUDIT.md) — archived post-release verification snapshot
- [`docs/SWIRENGINE_2_0_RUNTIME_LIFECYCLE_AUDIT.md`](docs/SWIRENGINE_2_0_RUNTIME_LIFECYCLE_AUDIT.md) — verified 2.0 lifecycle evidence
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
- [`docs/SWIRENGINE_2_0_READINESS_AUDIT.md`](docs/SWIRENGINE_2_0_READINESS_AUDIT.md) — pre-release readiness evidence

## 🎮 Real-game integration fixtures

Representative projects are source-only engine integration fixtures and do **not** receive separate releases:

- **SwirEngine 2D Game Demo** — [`examples/2d_game_demo/`](examples/2d_game_demo/)
- **SwirEngine 3D Game Demo** — [`examples/3d_game_demo/`](examples/3d_game_demo/)
- **SwirEngine Multiplayer Game Demo** — [`examples/multiplayer_game_demo/`](examples/multiplayer_game_demo/)
- **Neon Frontier 1.3** — locked historical compatibility fixture
- **Neon Frontier 1.4** — locked compatibility/showcase fixture
- **Neon Cube Hunt 3D** — OpenGL + packaged-runtime regression arena
- **Neon Snake 3D** — complete 3D regression project

The maintained shipping and compatibility gates drive representative fixtures through creator preparation, source runtime, deterministic staged export, staged runtime, settings/save boundaries, scene/content integrity, UI focus/navigation/activation and privacy-safe diagnostics. Fixture failures are engine integration failures, not demo-only issues.

## 🧪 Development and verification

```bash
python -m pip install -e ".[dev]"
pytest
ruff check src tests examples demo_projects tools
python -m compileall -q src tests examples demo_projects tools
python tools/generate_progress_svg.py --check
python tools/verify_2_1_release_readiness.py
python tools/verify_2_0_release_candidate.py --require-final
python tools/verify_creator_workflow_2_0.py
python tools/verify_runtime_scalability_2_0.py
python tools/verify_platform_matrix_2_0.py
python tools/verify_real_game_shipping_2_0.py
python tools/verify_performance_evidence_2_0.py --output build/performance-evidence.json
python tools/verify_release_safety_2_0.py
```

`tools/generate_progress_svg.py` deterministically derives the PyPI-safe README ASCII progress block and the internal/roadmap SVG assets from the same verified 2.1 checklist. Presentation tests verify source math, the exact ASCII percentage/counter, the absence of README progress SVGs, bounded SVG fill geometry, the single roadmap mini, the template contract and legacy-meter cleanup outside the explicit PyPI exception.

## 🧱 Architecture and technology

SwirEngine keeps a high-level Python creator surface over modular runtime systems. The repository contains rendering, scene/ECS, assets, serialization, physics, audio, input/UI, networking, editor, diagnostics and export/shipping modules with focused regression workflows. Advanced systems remain available through explicit APIs instead of being hidden behind one monolithic game object.

Engineering quality is evaluated against complete games, public installation, resource lifetime, deterministic tooling, creator workflow, failure handling and shipping behavior—not feature count alone.

## 🔒 API and release policy

- `v1.4.0`, `v1.5.0` and `v2.0.0` are immutable published releases; release history is not rewritten.
- **2.0.0 is the latest public stable package.**
- 1.6, 1.7, 1.8 and 1.9 remain completed source-only checkpoints and were never published as releases.
- The 2D, 3D and multiplayer game demos remain source-only integration fixtures.
- The published 1.5.0 `swirengine.__all__` surface remains the documented starting compatibility floor for 2.0 migration validation.
- Breaking post-2.0 changes require explicit engineering justification, migration documentation and tests.
- SwirEngine 2.1 roadmap acceptance is complete, but publication remains a separate guarded decision; no 2.1 release is implied by 100% roadmap progress.
- A completed historical roadmap does not imply literal perfection; concrete stable-line regressions still reopen focused maintenance.

## 🗺 Roadmaps and active development

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
| 2.0 | [`ROADMAP_2_0.md`](ROADMAP_2_0.md) | 10/10 = 100.0%, released 2026-09-19 |
| 2.0 post-release | [`docs/SWIRENGINE_2_0_POST_RELEASE_AUDIT.md`](docs/SWIRENGINE_2_0_POST_RELEASE_AUDIT.md) | 5/10 = 50.0%, archived snapshot |
| **2.1** | **[`ROADMAP_2_1.md`](ROADMAP_2_1.md)** | **10/10 = 100.0%, source roadmap complete; publication pending** |

## ⚠️ Current limitations

- The SwirEngine 2.1 source roadmap is complete, but no 2.1 public release has been published; publication remains a separate Phase C decision with its own exact-source release gate.
- The verified base-engine matrix covers only the maintained 64-bit hosted runner architectures exercised by CI; 32-bit Python, PyPy, free-threaded CPython and unverified architectures are not claimed.
- Optional extras such as audio require their own dependency/runtime evidence beyond the base-engine support matrix.
- Desktop build plans are host-native; unsupported cross-compilation is intentionally rejected.
- The dedicated-server contract is headless and deterministic but does not claim public matchmaking, hosting infrastructure or universal transport support.
- Cross-engine FPS, latency and memory superiority rankings remain intentionally unclaimed without an identical maintained comparison harness.

## 🔎 Search Keywords

`Python game engine` · `Python 2D engine` · `Python 3D engine` · `Python multiplayer engine` ·
`pip game engine` · `game development Python` · `OpenGL Python game engine` · `scene prefab engine` ·
`Python ECS` · `Python physics engine` · `Python game editor` · `SwirEditor` · `desktop game packaging` ·
`PyInstaller game build` · `game engine networking` · `SwirEngine`

---

<div align="center">

**SWIR ENGINEERING · PYTHON-FIRST GAME PRODUCTION**

[GitHub](https://github.com/Swir/SwirEngine) · [Releases](https://github.com/Swir/SwirEngine/releases) · [PyPI](https://pypi.org/project/swirengine/)

</div>