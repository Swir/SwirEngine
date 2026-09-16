# SwirEngine 1.4 — Showcase, Hardening and Release Gate

This document defines the final SwirEngine 1.4.0 release contract. Feature completion and publication are deliberately separate states: reaching 10/10 makes the release candidate eligible for the strict publication matrix, but PyPI and the GitHub Release are created only after that synchronized candidate passes every final gate.

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

The implementation/hardening branch completed the full triggered Showcase + Hardening, CI, Renderer 2.0, Desktop Export and locked 1.3 regression matrices before the final roadmap checkbox was closed.

## Strict release-candidate contract

`tools/verify_1_4_release_candidate.py --require-complete` derives progress from `ROADMAP_1_4.md` and rejects publication unless all synchronized release facts are true:

1. exactly 10/10 roadmap deliverables, the exact 100% progress bar and `STATUS-COMPLETE`;
2. `pyproject.toml` package version `1.4.0`;
3. runtime `swirengine.__version__ == "1.4.0"`;
4. the complete 1.4 documentation and integrated showcase surface;
5. README and release notes synchronized to 1.4.0 / 10-of-10;
6. the final hardening workflow invoking the strict verifier;
7. a tag-only release workflow that invokes the strict verifier and validates Neon Frontier 1.4;
8. Trusted Publishing without duplicate-artifact masking.

This prevents a version bump, tag or upload from being used as evidence of completion. Completion must exist first and be verifiable from the repository.

## Dedicated final hardening workflow

`.github/workflows/showcase-hardening-1-4.yml` adds four release-candidate checks on top of the repository-wide compatibility matrix:

- Python 3.10 and 3.13 strict contract/test/lint/compile validation plus the complete headless integration probe;
- a deterministic integrated performance contract for the headless showcase;
- a real Linux OpenGL 3.3 Renderer 2.0/VFX smoke under Xvfb/Mesa;
- clean-wheel metadata/install/import/integration validation and a one-file Windows PyInstaller runtime probe.

The normal CI and milestone workflows remain independent compatibility gates. A green final workflow never excuses regressions elsewhere.

## Performance contract

`tools/benchmark_showcase_1_4.py` times repeated complete headless integration runs. The CI contract caps the worst of three runs at 2500 ms. This is deliberately a broad end-to-end budget rather than a microbenchmark; milestone-specific benchmarks remain the source of tighter per-system limits.

The benchmark also reports terrain triangle workload, Renderer 2.0 estimated draw calls and Multiplayer 2.0 encoded bytes so a suspiciously cheap run cannot silently stop exercising core systems. Host timings are diagnostic and are not converted into unmeasured FPS claims.

## Publication workflow

Publication is possible only from the exact `v1.4.0` tag. The release workflow:

1. reruns the strict 10/10 contract, full pytest, Ruff and compile gates;
2. reruns the 1.4 milestone and integrated deterministic performance contracts;
3. builds and checks the portable wheel/sdist;
4. proves that the tag, project metadata and runtime version are identical;
5. runs the real Linux OpenGL 1.4 showcase plus locked 1.3/3D regression projects;
6. builds and executes `NeonFrontier14.exe` on Windows;
7. builds, selects, installs and imports the dedicated `cp314-cp314-win_amd64` native wheel;
8. publishes all distributions to PyPI through OIDC Trusted Publishing;
9. creates the GitHub Release using `RELEASE_NOTES_1_4.md` only after PyPI publication succeeds;
10. installs `swirengine==1.4.0` from public PyPI on Linux/Python 3.13 and Windows/Python 3.14 and re-runs runtime/showcase probes.

There is no main-branch publication backdoor and no `skip-existing` behavior. A duplicate or partially published release is surfaced as an error instead of being hidden.

## Compatibility policy

The 1.3 API remains the compatibility baseline and its regression contract remains in normal CI after the 1.4 version bump. New 1.4 systems stay additive or opt-in wherever practical, including Renderer 2.0, Physics 2.0, Editor Authoring and Multiplayer 2.0.

Historical 1.0-1.3 roadmaps stay locked. SwirEngine 1.4.0 is considered fully published only after the tag-triggered workflow confirms both the GitHub Release and the public PyPI installation path.
