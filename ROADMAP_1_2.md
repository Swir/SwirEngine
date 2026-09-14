# SwirEngine 1.2 Roadmap

<!-- SWIR-ROADMAP-STANDARD:v1 -->
<!-- ROADMAP-PROGRESS:START -->
<p align="center">
  <a href="https://github.com/Swir/SwirEngine/actions/workflows/ci.yml"><img alt="CI" src="https://github.com/Swir/SwirEngine/actions/workflows/ci.yml/badge.svg"></a>
  <img alt="Roadmap progress" src="https://img.shields.io/badge/ROADMAP-100.0%25-1f6feb?style=for-the-badge">
  <img alt="Completed" src="https://img.shields.io/badge/DONE-10%2F10-1f6feb?style=for-the-badge">
  <img alt="Status" src="https://img.shields.io/badge/STATUS-COMPLETE-1f6feb?style=for-the-badge">
</p>

## 📊 Overall progress

```text
████████████████████ 100.0%
```

| ✅ Completed | ⏳ Remaining | 📦 Total | 🎯 Progress |
|---:|---:|---:|---:|
| **10** | **0** | **10** | **100.0%** |

> Progress is derived only from the equal-weight verified deliverables below. A checkbox becomes
> complete only after implementation, regression coverage, README/CHANGELOG synchronization and
> the relevant CI/runtime validation.

- [x] Particle/VFX runtime: sparse pooled updates, spawn shapes, lifecycle curves and diagnostics
- [x] Text/font pipeline: font assets, fallback families, layout/wrapping/alignment and cache diagnostics
- [x] Camera systems: bounds, shake, smoothing, rails/blends and shared 2D/3D creator ergonomics
- [x] Save/config expansion: typed settings, migrations, profiles, atomic writes and cloud-friendly layout
- [x] Networking gameplay layer: messages/RPC helpers, connection state and deterministic diagnostics
- [x] Scene/prefab/ECS ergonomics: composition helpers, lifecycle hooks and faster large-world iteration
- [x] Asset streaming: budgets, residency/eviction, staged background loading and hitch diagnostics
- [x] Renderer/VFX performance pass: batching/state reduction and measurable frame-work regression gates
- [x] Build/export hardening: portable project templates and verified Windows/Linux/macOS shipping workflows
- [x] 1.2 creator hardening: complete demo, documentation/API audit, compatibility and final release gate

<!-- ROADMAP-PROGRESS:END -->

## Direction

SwirEngine 1.2 builds on the completed 1.1 foundation without breaking the stable public 1.x API.
The focus is richer game-production systems, less per-frame Python work, better creator feedback and
shipping complete projects with predictable behavior.

The historical 1.0 roadmap remains locked at 31/31 (100%) in [`ROADMAP.md`](ROADMAP.md), and the
completed 1.1 roadmap remains locked at 10/10 (100%) in [`ROADMAP_1_1.md`](ROADMAP_1_1.md).

## Release policy

The SwirEngine 1.2 roadmap is complete at a verified 10/10 = 100.0%. Publication is still permitted
only after the final 1.2 release head passes the complete release contract, CI/runtime/demo/packaging
and native export gates. After publication, the public PyPI artifact must pass post-release verification
before 1.2 is considered finished.
