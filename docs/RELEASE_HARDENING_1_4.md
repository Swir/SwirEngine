# SwirEngine 1.4 — Showcase, Hardening and Release Gate

This document defines the final 1.4 release-candidate gate. It is intentionally stricter than an individual milestone workflow: 1.4 is not considered complete merely because its feature modules exist.

## Integrated production-scale validation

`demo_projects/neon_frontier_1_4/run_game.py` is the final integration project. A single runtime combines:

- generated heightmap terrain and terrain-backed large-world streaming;
- Physics 2.0 static/dynamic bodies;
- the 3D character controller using the same physics backend;
- Renderer 2.0 cascaded shadows, SSAO, bloom, decals, HDR and post-processing;
- GPU VFX scheduling and the real GPU particle renderer during OpenGL smoke runs;
- Editor Authoring multi-selection and grouped gizmo history against live scene objects;
- Multiplayer 2.0 snapshots, sparse deltas, interpolation and bandwidth accounting.

The project has three validation modes. `SWIR_1_4_HEADLESS_PROBE=1` exercises the complete integration surface without a window. `SWIR_1_4_SMOKE_FRAMES=N` boots the real OpenGL 3.3 path and exits deterministically. `SWIR_DEMO_RUNTIME_PROBE=1` is used inside the packaged Windows executable to verify native rendering dependencies plus the headless integration path.

## Release-candidate contract

`tools/verify_1_4_release_candidate.py` derives progress from `ROADMAP_1_4.md` rather than trusting a manually supplied percentage. During hardening it permits the stable package to remain `1.3.0` while the roadmap is 9/10. The strict `--require-complete` mode requires all of the following before publication can be wired to 1.4:

1. exactly 10/10 roadmap deliverables and a `STATUS-COMPLETE` roadmap;
2. package version `1.4.0`;
3. the complete 1.4 documentation and showcase surface;
4. a release workflow that invokes the strict 1.4 verifier and validates Neon Frontier 1.4;
5. Trusted Publishing without duplicate-artifact masking.

This prevents a version bump, tag or release from being used as evidence of completion. Completion must exist first and be verifiable from the repository.

## Dedicated hardening workflow

`.github/workflows/showcase-hardening-1-4.yml` adds four final checks on top of the normal repository matrix:

- Python 3.10 and 3.13 contract/test/lint/compile validation plus the headless integration probe;
- a deterministic integrated performance contract for the headless showcase;
- a real Linux OpenGL 3.3 Renderer 2.0/VFX smoke under Xvfb/Mesa;
- a one-file Windows PyInstaller build followed by its native runtime/integration probe.

The normal CI and all milestone workflows remain independent compatibility gates. A green final workflow does not excuse regressions elsewhere.

## Performance contract

`tools/benchmark_showcase_1_4.py` times repeated complete headless integration runs. The default CI contract caps the worst of three runs at 2500 ms. This is deliberately a broad end-to-end budget rather than a microbenchmark; the milestone-specific benchmarks remain the source of tighter per-system limits.

The benchmark also reports terrain triangle workload, Renderer 2.0 estimated draw calls and Multiplayer 2.0 encoded bytes so a suspiciously cheap run cannot silently stop exercising core systems.

## Compatibility and publication policy

SwirEngine 1.3.0 remains the stable public package throughout the 90% hardening phase. Existing root imports and 1.x behavior must not be changed to make the showcase pass. The 1.4 version, final roadmap checkbox, strict release verifier and publication workflow are synchronized only after the complete hardening and repository regression matrix is green.

No `v1.4.0` tag, PyPI upload or GitHub Release is permitted before that 10/10 state is real and verified.
