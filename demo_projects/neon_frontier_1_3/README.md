# Neon Frontier 1.3

Neon Frontier is the integrated asset-free validation game for the final SwirEngine 1.3 hardening milestone. It exists to prove that the major 1.3 systems can coexist inside one ordinary application, not just pass isolated unit tests.

## Systems exercised together

- real `Game` / OpenGL 3D renderer
- native `InstancedCube3D` batching and frustum-aware rendering
- `ShaderMesh3D` + `shader_material_3d()` custom uniform/hook path
- `CollisionWorld3D` broad phase
- `NavigationGrid3D` + `NavigationAgent3D`
- `LargeWorldStreamer` bounded local residency
- `GameplayRuntime` deterministic scheduler/timer path
- existing directional/point lighting and camera APIs

The game is deliberately asset-free so final CI failures point at engine/runtime integration rather than downloads or external content.

## Run interactively

```bash
python demo_projects/neon_frontier_1_3/run_game.py
```

## Deterministic OpenGL smoke

```bash
SWIR_1_3_SMOKE_FRAMES=12 python demo_projects/neon_frontier_1_3/run_game.py
```

Linux CI runs the smoke under Xvfb/software OpenGL. The smoke asserts that the game rendered its requested frames while the instancing, navigation, collision, large-world and gameplay systems remain live.

This project is a validation game, not a performance FPS claim. Individual 1.3 performance contracts remain enforced by their dedicated deterministic benchmarks.
