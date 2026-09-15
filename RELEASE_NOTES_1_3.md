# SwirEngine 1.3.0 Release Notes

SwirEngine 1.3.0 completes the **Gameplay & Creator Power** roadmap at **10/10 = 100.0%** while preserving the stable public 1.x API.

## Highlights

- Native GPU instancing with conservative frustum culling and deterministic draw/cull diagnostics.
- glTF skeletal animation with clips, crossfades and production GPU skinning.
- 3D collision queries and deterministic fixed-step gameplay physics foundations.
- Weighted deterministic 2D/3D A* navigation with bounded route caching and navigation agents.
- Bounded large-world chunk streaming with local residency windows and lifecycle hooks.
- Controlled shader/material variants, safe custom hooks and bounded shader-program caching.
- A 2D renderer power pass with viewport-local tilemap work, dirty transform sync and reusable staging buffers.
- Deterministic gameplay utilities: timers, signals, object pools, cooldowns, spawning and `GameplayRuntime`.
- Creator/editor integration through the existing SwirEngine editor model with lazy subsystem diagnostics.
- **Neon Frontier 1.3**, the integrated full-game validation project used by the final release gate.

## Release validation

The final 1.3 release workflow requires:

- strict `tools/verify_1_3_release_candidate.py --require-complete`
- full pytest, Ruff and compileall validation
- Windows/Linux/macOS packaging checks
- Windows x64 / CPython 3.14 native-wheel selection and import validation
- real software-OpenGL runtime validation
- one-file Windows Neon Frontier packaged-runtime probe
- deterministic performance regression contracts
- GitHub OIDC Trusted Publishing
- public PyPI metadata, clean-install and runtime verification after publication

Performance claims remain workload-specific and measurable; no FPS increase is claimed without direct evidence.

## Publication

This release is published only through the repository's guarded 1.3 Trusted Publishing workflow after the completed 10/10 roadmap and exact-head validation matrix are green.
