# SwirEngine 1.3 Roadmap

<!-- SWIR-ROADMAP-STANDARD:v1 -->
<!-- ROADMAP-PROGRESS:START -->
<p align="center">
  <a href="https://github.com/Swir/SwirEngine/actions/workflows/ci.yml"><img alt="CI" src="https://github.com/Swir/SwirEngine/actions/workflows/ci.yml/badge.svg"></a>
  <img alt="Roadmap progress" src="https://img.shields.io/badge/ROADMAP-50.0%25-0969da?style=for-the-badge">
  <img alt="Completed" src="https://img.shields.io/badge/DONE-5%2F10-0969da?style=for-the-badge">
  <img alt="Status" src="https://img.shields.io/badge/STATUS-ACTIVE-0969da?style=for-the-badge">
</p>

## 📊 Overall progress

```text
██████████░░░░░░░░░░ 50.0%
```

| ✅ Completed | ⏳ Remaining | 📦 Total | 🎯 Progress |
|---:|---:|---:|---:|
| **5** | **5** | **10** | **50.0%** |

> Progress is derived only from the equal-weight verified deliverables below. A checkbox becomes
> complete only after implementation, regression coverage, README/CHANGELOG synchronization and
> the relevant CI/runtime validation.

- [x] GPU Instancing + Frustum Culling: native per-instance GPU attributes/submissions, reusable buffers,
      CPU view-frustum rejection, diagnostics and performance gates
- [x] 3D Skeletal Animation: glTF skins/skeletons, GPU skinning, clips, blending and creator-friendly
      animation control
- [x] 3D Collision / Physics Foundation: 3D bounds, broad phase, ray/sphere/box queries and deterministic
      gameplay foundations
- [x] Navigation & Pathfinding: A* grid navigation, path queries, agents and a route toward authored or
      generated navigation meshes
- [x] Large World / Chunk Streaming: chunked residency, distance/visibility activation and streaming
      hooks for large 2D/3D scenes
- [ ] Advanced Material & Shader Pipeline: reusable shader/material variants, compilation caching,
      custom shader hooks and diagnostics without bypassing engine safety
- [ ] 2D Renderer Power Pass: stronger batching/culling, tilemap chunk visibility and lower
      Python/per-frame overhead for very large 2D scenes
- [ ] Advanced Gameplay Framework: timers, signals, object pools, cooldown/spawn helpers and
      composition-friendly gameplay utilities
- [ ] Creator / Editor Integration: expose 1.3 systems through the existing workspace, inspector,
      viewport and diagnostics without starting a separate 2.0 editor project
- [ ] 1.3 Full Game + Hardening + Release Gate: complete validation game, API/docs audit,
      platform/packaging verification, performance contracts and one final 1.3 release

<!-- ROADMAP-PROGRESS:END -->

## Direction

SwirEngine 1.3 is the **Gameplay & Creator Power** line. It is additive to the stable public 1.x API
and focuses on larger dynamic worlds, stronger 3D production systems, lower renderer overhead and
more complete creator workflows.

The historical 1.0 roadmap remains locked at 31/31 (100%) in [`ROADMAP.md`](ROADMAP.md), the
completed 1.1 roadmap remains locked at 10/10 (100%) in [`ROADMAP_1_1.md`](ROADMAP_1_1.md), and
the published 1.2 roadmap remains locked at 10/10 (100%) in [`ROADMAP_1_2.md`](ROADMAP_1_2.md).

## Release policy

No PyPI package, GitHub Release or 1.3 release tag is allowed until this roadmap reaches exactly
10/10 = 100.0%, all checkboxes are `[x]`, and the exact release head passes the full
CI/runtime/demo/packaging gate plus public-artifact post-release verification.
