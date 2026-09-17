# SwirEngine 1.5 Release Hardening

SwirEngine 1.5 closes only after the complete 10/10 roadmap is implemented, the exact release-candidate head passes the full compatibility/runtime/packaging gate, and the tag-only publication workflow verifies the public package after upload.

This document defines the Milestone 10 release contract. It does not grant permission to tag or publish while `ROADMAP_1_5.md` is below 10/10.

## Release identity

- Final package version: `1.5.0`.
- Final tag: `v1.5.0`.
- Supported Python range: `>=3.10,<3.15`.
- Normal compatibility matrix: Python 3.10-3.13 on Windows, Linux and macOS.
- Dedicated native-wheel path: CPython 3.14 on Windows x86-64.
- Previous stable release `1.4.0` remains locked and continues to be validated as a compatibility contract.

## Required 1.5 systems

The release candidate must contain and validate all additive 1.5 milestone modules:

1. `swirengine.simulation15` — deterministic simulation and replay.
2. `swirengine.storage15` — Save & Profile 2.0.
3. `swirengine.audio15` — Audio 2.0.
4. `swirengine.animation15` — Animation Graphs 2.0.
5. `swirengine.navigation15` — Navigation 2.0.
6. `swirengine.world_streaming15` / `world_streaming_easy15` — World Streaming 2.0.
7. `swirengine.ui15` — UI Toolkit 2.0.
8. `swirengine.editor15` — Editor Productivity 2.0.
9. `swirengine.performance15` — Runtime Diagnostics & Profiling 2.0.

These systems remain additive or opt-in. Stable 1.x imports and behavior remain protected by the normal regression suite and the locked 1.4 release contract.

## Full release-candidate gate

The dedicated `showcase-hardening-1-5.yml` workflow must validate the exact candidate head through all of the following before Milestone 10 can be marked complete:

- `tools/verify_1_5_release_candidate.py` contract audit;
- complete pytest suite;
- strict Ruff validation of `src`, `tests`, `examples`, `demo_projects` and `tools`;
- compile validation of all Python sources;
- the nine deterministic/workload-specific SwirEngine 1.5 benchmark contracts;
- headless execution of both source-only SwirEngine 2D Game Demo and SwirEngine 3D Game Demo;
- real Linux OpenGL 3.3 execution of both source demos under Xvfb/Mesa;
- portable wheel/sdist build and `twine check`;
- clean virtual-environment installation of the built wheel outside the editable source installation;
- source-demo probes against the clean installed wheel;
- Windows one-file packaging/runtime probing for the 2D and 3D source demos;
- the repository's normal CI, Desktop Export, game demos and locked 1.4 hardening workflows remaining green.

Benchmark timings are workload budgets, not FPS claims. Real renderer correctness is validated separately through actual OpenGL smoke execution.

## Finalization gate

Only after the implementation candidate above is green may the finalization commit:

- mark Milestone 10 complete and set `ROADMAP_1_5.md` to 10/10 = 100.0%;
- set `pyproject.toml` and `swirengine.__version__` to `1.5.0`;
- move project metadata to the 1.5 roadmap;
- update the root README and release notes for the stable 1.5 line;
- switch the tag-only release workflow from `v1.4.0` to `v1.5.0`;
- run `tools/verify_1_5_release_candidate.py --require-complete` as a hard gate.

The finalization head must then pass the complete release-candidate gate again. A green implementation-only head is not enough.

## Publication workflow

Publication is tag-only. Creating `v1.5.0` is permitted only from the verified 10/10 finalization commit. The release workflow must:

1. enforce the strict complete 1.5 contract;
2. run the full tests, lint, compile and all 1.5 workload gates;
3. run both source-only game demos headlessly and through real Linux OpenGL;
4. build portable distributions and the dedicated Windows CPython 3.14 native wheel;
5. verify clean installation before publication;
6. publish to PyPI through Trusted Publishing/OIDC without `skip-existing` masking;
7. create the GitHub Release only after PyPI publication succeeds;
8. poll public PyPI, install `swirengine==1.5.0` from the public index on Linux/Python 3.13 and Windows/Python 3.14, then verify runtime imports and game-demo probes.

A tag alone is not considered a successful release. Public-index installation and runtime verification must complete successfully.

## Failure policy

Any failure keeps SwirEngine 1.5 unpublished. Fix the regression on the release branch, rerun the complete gate on the new exact head, and only then reconsider completion. Do not lower workload budgets merely to make a failing runner green unless the contract itself is shown to be invalid and the replacement is documented with equivalent or stronger coverage.
