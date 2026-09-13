# SwirEngine 1.1 Roadmap

<!-- SWIR-ROADMAP-STANDARD:v1 -->
<!-- ROADMAP-PROGRESS:START -->
<p align="center">
  <a href="https://github.com/Swir/SwirEngine/actions/workflows/ci.yml"><img alt="CI" src="https://github.com/Swir/SwirEngine/actions/workflows/ci.yml/badge.svg"></a>
  <img alt="Roadmap progress" src="https://img.shields.io/badge/ROADMAP-0.0%25-6e7681?style=for-the-badge">
  <img alt="Completed" src="https://img.shields.io/badge/DONE-0%2F10-1f6feb?style=for-the-badge">
  <img alt="Status" src="https://img.shields.io/badge/STATUS-ACTIVE-f59e0b?style=for-the-badge">
</p>

## 📊 Overall progress

```text
░░░░░░░░░░░░░░░░░░░░ 0.0%
```

| ✅ Completed | ⏳ Remaining | 📦 Total | 🎯 Progress |
|---:|---:|---:|---:|
| **0** | **10** | **10** | **0.0%** |

> Progress is derived only from the equal-weight verified deliverables below. A checkbox becomes
> complete only after implementation, regression coverage and the relevant CI/runtime validation.

- [ ] Standardized gamepad/controller API with hot-plug, button edges, analog deadzones and triggers
- [ ] Creator-facing input actions, rebinding and persistent control profiles
- [ ] GPU instancing / larger-batch rendering path with measurable draw-call and frame-time wins
- [ ] Async/preload asset pipeline with deterministic loading diagnostics and stall reduction
- [ ] Responsive UI layout: anchors, containers, focus, keyboard/gamepad navigation and scaling
- [ ] Expanded audio mixer with buses/groups, fades, spatial controls and runtime diagnostics
- [ ] Animation/tween/state-machine layer usable by both 2D and 3D gameplay
- [ ] Physics/collision performance pass with broad-phase scaling and richer creator queries
- [ ] Editor workflow expansion for scene creation, prefabs, input setup and playtest iteration
- [ ] 1.1 creator hardening: benchmarks, complete sample game, export/runtime smoke tests and documentation

<!-- ROADMAP-PROGRESS:END -->

## Direction

SwirEngine 1.1 is about making complete games easier to build, control and ship while preserving
the stable 1.x public API. The priorities are creator ergonomics, predictable performance and
verified end-user packaging rather than accumulating isolated features.

The historical 1.0 roadmap remains locked at 31/31 (100%) in [`ROADMAP.md`](ROADMAP.md).
