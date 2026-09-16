# SwirEngine 1.4 Roadmap

<!-- SWIR-ROADMAP-STANDARD:v1 -->
<!-- ROADMAP-PROGRESS:START -->
<p align="center">
  <a href="https://github.com/Swir/SwirEngine/actions/workflows/ci.yml"><img alt="CI" src="https://github.com/Swir/SwirEngine/actions/workflows/ci.yml/badge.svg"></a>
  <img alt="Roadmap progress" src="https://img.shields.io/badge/ROADMAP-100.0%25-2ea043?style=for-the-badge">
  <img alt="Completed" src="https://img.shields.io/badge/DONE-10%2F10-2ea043?style=for-the-badge">
  <img alt="Status" src="https://img.shields.io/badge/STATUS-COMPLETE-2ea043?style=for-the-badge">
</p>

## 📊 Overall progress

```text
████████████████████ 100.0%
```

| ✅ Completed | ⏳ Remaining | 📦 Total | 🎯 Progress |
|---:|---:|---:|---:|
| **10** | **0** | **10** | **100.0%** |

> Progress is derived only from the equal-weight verified deliverables below. A milestone becomes
> complete only after implementation, regression coverage, documentation synchronization and the
> relevant CI/runtime/performance validation are green.

- [x] **Terrain + World LOD** — heightmap terrain, chunked mesh generation, distance-based LOD,
      terrain materials/splat layers, collision integration and large-world streaming compatibility.
- [x] **Physics 2.0** — contact generation/response, friction and restitution, shape sweeps,
      constraints/joints, sleeping, continuous-collision foundations and a backend-ready public API.
- [x] **Character Controllers** — production first-person, third-person and platformer movement,
      step/slope handling, grounded state, jumping, camera rigs and physics/navigation integration.
      Verified by the dedicated controller regression, sweep-budget, integration-demo, Ruff and
      compileall gate plus the full cross-platform CI/export/demo matrix.
- [x] **Renderer 2.0** — additive creator-facing `Renderer2` / `Renderer2Settings` / `Decal3D` APIs,
      practical 1–4 cascade directional shadows with texel stabilization and 3×3 PCF, sampleable
      depth + view-normal prepass, SSAO with depth-aware blur and invalid-normal protection, HDR bloom,
      bounded screen-space decals, deterministic frame-pass diagnostics and compatibility with the
      established 1.x renderer. Verified by the dedicated headless EGL/OpenGL 3.3 execution gate,
      deterministic planner benchmark, strict Ruff/compileall, full Python/OS CI matrix, native
      Windows cp314 wheel selection, Desktop Export and real demo/Snake/instancing OpenGL regressions.
- [x] **GPU VFX + Particle Power** — additive `GPUParticleEmitter3D` and `Game.gpu_particles(...)`,
      OpenGL 3.3 transform-feedback ping-pong simulation, deterministic ring spawning, point/box/sphere
      emitters, GPU gravity/drag/lifetime/curves, HDR sprite particles with optional textures, additive
      and alpha blending, geometry-shader trails, built-in instanced mesh particles and bounded
      diagnostics/resource cleanup. Verified by the dedicated Mesa EGL sprite/texture/trail/mesh smoke,
      the capacity-independence scheduler performance contract, strict Ruff/compileall, full Python/OS
      CI including Windows Python 3.14 native-wheel validation, Desktop Export and real demo/Snake/
      Renderer2/instancing regression gates.
- [x] **Asset Pipeline 2.0** — dependency-aware bounded background import with caller-thread finalization,
      SHA-256 source/dependency fingerprints, transitive hot-reload/cache invalidation, persistent
      content-addressed derived artifacts, dependency-aware glTF/GLB import, stronger PBR preservation,
      conservative mesh cleanup, opt-in texture optimization and creator diagnostics. Verified by the
      dedicated Asset Pipeline 2.0 cold/warm/invalidate/refill workload, integration demo, focused
      race/cache/hot-reload/glTF/optimization regressions, strict Ruff/compileall, full Python/OS CI,
      native Windows cp314 wheel selection, Desktop Export and existing renderer/VFX/demo regressions.
- [x] **Scene Acceleration + Occlusion** — conservative world AABBs, deterministic static BVH,
      dynamic refit layer, cached scene-membership synchronization, broad frustum pruning, additive
      Renderer2 candidate-view integration, conservative CPU Hi-Z reference queries and a real
      OpenGL 3.3 GPU maximum-depth pyramid without CPU readback. Verified by focused visibility/
      runtime/Renderer2/Hi-Z regressions, a deterministic 16,384-object workload with only 32 leaf
      tests (99.80% object-test reduction for the validation layout), real Mesa EGL depth-texture Hi-Z
      reduction, integration demo, strict Ruff and compileall while preserving unsupported renderables
      through conservative fallback behavior.
- [x] **Editor Authoring Power** — additive ordered multi-select and range/toggle selection, grouped
      property/gizmo/asset authoring with transaction-safe undo/redo, persistent authoring sidecars,
      drag-and-drop asset path safety, material/physics/navigation inspector adapters, workspace/frontend
      integration, explicit Play/Edit authoring isolation and the opt-in `swirengine.editor14` public
      facade. Verified by the dedicated Editor Authoring 1.4 regression/Ruff/compile/demo gate, a
      500-target select/edit/undo/redo workload well below the 1.0s contract, plus the full CI, Creator
      Editor 1.3, Desktop Export, Demo Game 3D, Neon Snake 3D and Full Game 1.3 compatibility matrix.
- [x] **Multiplayer 2.0** — opt-in replicated-component schemas, canonical snapshots and sparse deltas,
      bounded out-of-order interpolation, deterministic client prediction and authoritative
      reconciliation, bounded server rewind for lag-compensation foundations, per-channel bandwidth
      diagnostics and a stable `NetworkPacket` bridge. Verified on Python 3.10/3.13/3.14 by focused
      multiplayer + legacy networking regressions, strict Ruff/compileall, the runnable integration
      demo, a 500-entity workload with a 2,493-byte sparse delta versus a 50,114-byte full snapshot,
      plus the full CI, Desktop Export, Demo Game 3D and Neon Snake 3D compatibility matrix.
- [x] **1.4 Showcase + Hardening + Release Gate** — integrated production showcase combining terrain,
      world streaming, Physics 2.0 character movement, Renderer 2.0, GPU VFX, editor authoring and
      Multiplayer 2.0; final API/docs/package hardening; all nine deterministic 1.4 performance
      contracts; real Mesa/OpenGL 3.3 Renderer2/VFX/Hi-Z execution; clean sdist/wheel verification;
      native desktop export; Windows CPython 3.14 native-wheel coverage; and a guarded production
      release workflow that cannot publish until the strict 10/10 verifier passes. The final
      non-publishing validation matrix is green before this milestone is marked complete.

<!-- ROADMAP-PROGRESS:END -->

## Direction

SwirEngine 1.4 is the **Production World & Engine Power** line. Version 1.3 established the engine as
more than a lightweight multimedia layer; 1.4 closes the gaps that matter when building larger,
more polished 2D/3D games: world authoring, movement, physics depth, visibility scale, modern rendering,
asset throughput and multiplayer production workflows.

The stable public 1.x API remains the compatibility baseline. New systems are additive or
backward-compatible wherever practical, with migration notes required for any unavoidable behavior
change.

## Performance policy

Every milestone explicitly assesses and, where practical, measures:

- per-frame Python overhead and allocations
- draw calls, state changes and GPU submissions
- scene/visibility query cost
- asset import/loading stalls and cache reuse
- physics/navigation broad-phase work
- network serialization/bandwidth work where applicable

Host timings remain diagnostics only. SwirEngine does not claim FPS improvements without direct,
repeatable evidence.

## Release policy

The SwirEngine 1.4 technical roadmap is complete at exactly **10/10 = 100.0%**. Publication remains a
separate explicit action: no PyPI upload, GitHub Release or stable tag is created merely by completing
this roadmap. The production release workflow is guarded by
`tools/verify_1_4_release_candidate.py --require-complete` and must rerun the final regression,
performance, real-OpenGL, packaging, native-export and compatibility gates before any publication
step can execute.

Historical roadmaps 1.0, 1.1, 1.2 and 1.3 remain locked at 100% and are not rewritten to inflate
1.4 progress.
