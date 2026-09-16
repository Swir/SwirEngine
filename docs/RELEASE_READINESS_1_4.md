# SwirEngine 1.4 Release Readiness

SwirEngine 1.4 is still an active development line. The public stable package remains **1.3.0**
until the 1.4 roadmap reaches exactly **10/10 = 100.0%** and every final release gate is green.

This document defines the technical release-readiness contract for milestone #10. Passing the
development readiness workflow does **not** authorize a PyPI upload, GitHub Release, stable tag, or
version bump.

## Current gate

The active 1.4 roadmap is expected to stay at **9/10 = 90.0%** while the final showcase,
hardening, and guarded publication work is incomplete. During this state:

- `pyproject.toml` must remain on `1.3.0`;
- `ROADMAP_1_4.md` must remain `STATUS-ACTIVE`;
- `tools/verify_1_4_release_candidate.py` must pass in development mode;
- `tools/verify_1_4_release_candidate.py --require-complete` must fail;
- the non-publishing `1.4 Release Readiness` workflow must exercise the integrated regression,
  performance, OpenGL, demo, and wheel-install contracts;
- the historical 1.3 release verifier remains intact so the stable 1.3 contract cannot silently drift.

## What the readiness workflow verifies

### Focused 1.4 regression matrix

The gate reruns the milestone-critical terrain, Physics 2.0, character-controller, Renderer 2.0,
GPU VFX, Asset Pipeline 2.0, scene-acceleration, editor-authoring, and Multiplayer 2.0 regressions
together. This catches integration breakage that individual milestone workflows can miss.

### Performance-contract matrix

The gate reruns every dedicated 1.4 deterministic workload:

- terrain + world LOD;
- Physics 2.0 broadphase/CCD;
- character-controller sweep budget;
- Renderer 2.0 planner;
- GPU VFX scheduler;
- Asset Pipeline 2.0 cold/warm/invalidation workload;
- scene visibility/acceleration;
- editor multi-selection authoring;
- Multiplayer 2.0 snapshot/delta workload.

These are contract checks, not FPS marketing claims. Host timings remain diagnostics except where a
benchmark already defines a deterministic threshold.

### Real OpenGL execution

Mesa OpenGL 3.3 runs the Renderer 2.0, transform-feedback GPU-particle, and GPU Hi-Z scene-
acceleration smoke programs. This is deliberately separate from headless planner/unit coverage.

### Integration demos

Asset-free/headless integration demos for terrain, physics, controllers, assets, scene
acceleration, editor authoring/runtime/specialized inspectors, and Multiplayer 2.0 are booted in one
gate so their public integration paths cannot rot independently.

### Packaging

A source distribution and wheel are built, checked with Twine, installed into a fresh virtual
environment, and imported outside the repository tree. The clean-wheel probe imports both stable
top-level engine APIs and opt-in 1.4 editor/network modules.

The normal cross-platform CI remains responsible for the broader Python/OS matrix and the native
Windows CPython 3.14 wheel path.

## Final 10/10 publication requirements

The complete release verifier intentionally refuses publication until all of the following are true:

1. `ROADMAP_1_4.md` is exactly 10/10, 100.0%, and explicitly marked `STATUS-COMPLETE`.
2. The package version is exactly `1.4.0`.
3. The final integrated showcase exists at `demo_projects/showcase_1_4/run_game.py`.
4. `docs/SHOWCASE_1_4.md` documents the integrated showcase and its runtime contract.
5. `README.md` identifies SwirEngine 1.4.0 as the stable release.
6. A `CHANGELOG.d/1.4.0*.md` release note exists.
7. The production release workflow calls
   `tools/verify_1_4_release_candidate.py --require-complete` before any publication step.
8. Final CI, OpenGL, demo, performance, packaging, Windows CPython 3.14, and public-install gates
   are green.

Until those conditions are satisfied, 1.4 must remain unreleased regardless of how many individual
subsystems are complete.

## Safety property

The readiness workflow contains no PyPI publisher and no GitHub release command. It is safe to run
repeatedly on pull requests while 1.4 is at 90%. The existing production release workflow remains
hard-gated by the 1.3 verifier until the final 1.4 publication wiring is deliberately introduced as
part of the last milestone.
