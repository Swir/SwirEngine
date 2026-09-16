# Neon Frontier 1.4

Neon Frontier 1.4 is the integrated production-scale validation project for the final SwirEngine 1.4 roadmap milestone. It intentionally uses only generated geometry and data so CI, source checkouts and packaged Windows probes do not depend on external assets.

## Systems exercised together

- Terrain + World LOD: generated heightmap, chunk LOD meshes and terrain-backed large-world streaming.
- Physics 2.0: static/dynamic 3D bodies and deterministic stepping.
- Character Controllers: sweep-based 3D character movement on the same physics world.
- Renderer 2.0: cascaded shadows, SSAO, bloom, decals, HDR and post-processing.
- GPU VFX: GPU-particle scheduling and the real Renderer 2.0 particle path during OpenGL smoke runs.
- Editor Authoring: multi-selection and one grouped gizmo transaction against live scene objects.
- Multiplayer 2.0: replicated-component snapshots, sparse deltas, interpolation and bandwidth accounting.

## Validation modes

```bash
SWIR_1_4_HEADLESS_PROBE=1 python demo_projects/neon_frontier_1_4/run_game.py
```

The headless mode creates no OpenGL context and is suitable for fast integration checks and benchmarks.

```bash
SWIR_1_4_SMOKE_FRAMES=16 xvfb-run -a python demo_projects/neon_frontier_1_4/run_game.py
```

The Linux smoke mode boots the real OpenGL 3.3 Renderer 2.0/VFX path and exits after the requested frame count.

```powershell
$env:SWIR_DEMO_RUNTIME_PROBE = "1"
.\NeonFrontier14.exe
```

The packaged probe verifies native renderer imports and then runs the complete headless integration surface from the one-file executable.

This project is a release gate, not a new public API surface. Stable 1.x imports remain unchanged until the 1.4 roadmap, packaging and publication gates are all complete.
