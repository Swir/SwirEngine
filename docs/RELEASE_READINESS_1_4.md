# SwirEngine 1.4 Release Readiness

SwirEngine 1.4 has completed its technical roadmap at exactly **10/10 = 100.0%**. The repository is
staged as **1.4.0** and the final non-publishing validation matrix has verified the integrated
showcase, focused regressions, deterministic performance contracts, real OpenGL execution,
packaging, clean-wheel installation, native export and stable 1.x compatibility.

Technical readiness does **not** by itself publish a package, create a GitHub Release or create a
stable tag. Publication remains a separate explicit action through the guarded production workflow.

## Complete gate

The final 1.4 state requires all of the following to stay synchronized:

- `ROADMAP_1_4.md` is exactly `10/10 = 100.0%` and `STATUS-COMPLETE`;
- `pyproject.toml` is exactly `1.4.0` and points its active Roadmap URL to `ROADMAP_1_4.md`;
- `README.md` identifies SwirEngine 1.4.0 and preserves the completed 1.3 compatibility record;
- `demo_projects/showcase_1_4/run_game.py`, `docs/SHOWCASE_1_4.md` and
  `tests/test_showcase_1_4.py` land together;
- `tools/verify_1_4_release_candidate.py --require-complete` passes;
- the non-publishing `1.4 Release Readiness` workflow enforces the complete contract on pull requests;
- the production release workflow executes the same complete verifier before any publication step;
- historical 1.2/1.3 contracts remain locked and compatible with a successor 1.x release gate.

## What the readiness workflow verifies

### Complete 1.4 regression matrix

The gate reruns milestone-critical terrain, Physics 2.0, character-controller, Renderer 2.0,
GPU VFX, Asset Pipeline 2.0, scene-acceleration, editor-authoring, Multiplayer 2.0 and final showcase
regressions together. It also reruns the historical release-contract tests so final 1.4 wiring cannot
silently invalidate the completed stable 1.x history.

### Performance-contract matrix

Every dedicated 1.4 deterministic workload is rerun:

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
benchmark defines a deterministic threshold.

### Real OpenGL execution

Mesa OpenGL 3.3 runs the Renderer 2.0, transform-feedback GPU-particle and GPU Hi-Z scene-acceleration
smokes. The integrated 1.4 production showcase also boots under Xvfb/Mesa and executes the real
Renderer2/VFX game path for a bounded frame budget.

### Integrated showcase

`demo_projects/showcase_1_4/run_game.py` combines generated terrain, `LargeWorldStreamer`, Physics 2.0
character traversal, Renderer 2.0 configuration, GPU VFX scheduling, editor authoring and Multiplayer
2.0 snapshot/delta/interpolation paths in one deterministic creator-facing scenario. Its headless path
is validated independently from the real OpenGL path.

### Packaging and native runtime

The gate builds an sdist and wheel, validates metadata with Twine, installs the wheel into a clean
virtual environment and imports it outside the repository tree. The normal cross-platform CI also
covers the wider Python/OS matrix and the Windows CPython 3.14 native renderer dependency wheel path.

Desktop Export validates one-file and one-directory native shipping smokes on Windows, macOS and
Linux. The production release workflow adds a Windows one-file SwirEngine 1.4 showcase probe before
publication can proceed.

### Stable 1.x compatibility

SwirEngine 1.4 remains on the 1.x compatibility line. The locked 1.3 contract, Neon Frontier 1.3
runtime/OpenGL validation and packaged Windows probe remain active. Historical verifiers are
successor-aware: they preserve their completed API/runtime guarantees without requiring the active
production workflow to keep using an obsolete release gate forever.

## Production publication gate

The production workflow must execute:

```bash
python tools/verify_1_4_release_candidate.py --require-complete
```

before publication. It then reruns the full regression suite, strict lint/compile checks, stable 1.x
performance compatibility workloads, all nine 1.4 performance contracts, the integrated showcase,
real OpenGL smokes, Windows packaged probes and the native CPython 3.14 wheel build.

Only after those jobs succeed can PyPI Trusted Publishing run, followed by GitHub Release creation and
post-release public-PyPI verification. Normal pull-request and readiness workflows contain no publisher.

## Release checklist

1. Roadmap: exactly 10/10, 100.0%, `STATUS-COMPLETE`.
2. Package metadata: exactly `1.4.0`, active Roadmap URL points to 1.4.
3. Runtime version: `swirengine.__version__` matches package metadata.
4. README: identifies SwirEngine 1.4.0 and preserves 1.3 compatibility history.
5. Final showcase: code, documentation and regression test present.
6. Release notes: at least one `CHANGELOG.d/1.4.0*.md` entry present.
7. PR readiness: complete verifier, focused/full regressions, all performance contracts, OpenGL,
   packaging, native export and Windows CPython 3.14 gates green.
8. Publication: performed only through the guarded production workflow with an explicit release
   action/tag; never as a side effect of roadmap completion.

## Safety property

`1.4 Release Readiness` is intentionally non-publishing and safe to run repeatedly. Completion of the
technical roadmap only enables the production gate to succeed; it does not call PyPI, create a release,
or create a tag. That separation lets the repository reach a verified 1.4.0 state before the final
irreversible public publication action is deliberately triggered.
