# SwirEngine 1.2 creator hardening and final release gate

This document defines the final creator-facing contract for SwirEngine 1.2. The goal is not to add one more isolated subsystem; it is to prove that the engine can be installed, learned, exercised, packaged and shipped as one coherent Python-first 2D/3D engine without breaking the stable 1.x API.

## Creator workflow

A 1.2 release candidate is considered creator-ready only when all of the following remain true on the exact release head:

1. `python -m pip install -e ".[dev]"` succeeds on the CI support matrix.
2. `pytest`, Ruff and `compileall` pass.
3. The wheel and sdist build successfully and the built wheel imports in a clean environment.
4. Windows x64 / CPython 3.14 builds and installs the verified native renderer dependency wheel path.
5. Neon Cube Hunt 3D and Neon Snake 3D boot through the real OpenGL renderer under CI.
6. Both complete 3D demos also pass packaged Windows runtime probes.
7. Desktop export produces runnable one-file and one-directory builds on Windows, Linux and macOS.
8. The active 1.2 roadmap, README, CHANGELOG, package metadata and release workflow agree about the target version and supported Python scope.
9. PyPI publication uses GitHub OIDC Trusted Publishing; no token-based fallback is accepted.
10. The release contract is re-run in the publication workflow before any artifact can reach PyPI or GitHub Releases.

## Stable 1.x API audit

The final gate explicitly checks that the high-level public surface still exposes the core creator entry points used by existing projects: `Game`, `Scene`, `ECSWorld`, `Prefab`, `AssetManager`, `AudioEngine`, `InputManager`, `GameplaySession` and `ProjectExporter`.

The 1.2 work is additive. Existing 1.x projects are not required to adopt the new camera rigs, gameplay networking layer, typed settings, scene mounts, asset streaming manager or native build execution path.

## Python and platform scope

The declared package range remains Python `>=3.10,<3.15`. Cross-platform CI covers Python 3.10-3.13 on Windows, Linux and macOS. Python 3.14 is declared only for the Windows x86-64 path that is built and imported in CI with the required native renderer dependencies.

Support claims must follow CI evidence. Linux/macOS Python 3.14 support is not claimed until the dependency path is reproducibly verified there.

## Performance claims

The release gate keeps performance claims narrow and measurable. Existing regression gates verify static 3D batching, asynchronous asset preload overlap, indexed ECS candidate reduction, streaming residency accounting and renderer/VFX frame-preparation reductions. These are workload assertions, not generic FPS promises.

## Final publication sequence

The final 1.2 publication is allowed only after `ROADMAP_1_2.md` is exactly 10/10 = 100.0%, the complete release contract passes and all runtime/demo/packaging workflows are green for the exact head being released.

After publication, verification must use the public PyPI artifact rather than the repository checkout: clean install, import/version sanity, core API sanity and representative runtime/demo smoke where the environment permits it. A failed post-release verification is a 1.2 blocker, not permission to begin 1.3 work.
