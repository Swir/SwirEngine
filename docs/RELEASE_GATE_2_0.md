# SwirEngine 2.0 Final Release Gate

SwirEngine 2.0 is the next public release after 1.5.0. Source-only 1.6–1.9 checkpoints remain engineering history and are not retroactively published.

This document defines the final Milestone 10 contract. It separates **preflight**, **finalization**, **publication**, **public verification**, and **post-release audit** so a green partial stage cannot be mistaken for a successful release.

## Release identity

- Final package version: `2.0.0`.
- Final tag: `v2.0.0`.
- Publication branch: `release/2.0.0-publish`.
- Supported base-engine runtime: 64-bit CPython 3.10–3.14 on the Windows/Linux/macOS cells already verified by the 2.0 support matrix.
- Python metadata: `>=3.10,<3.15`.
- Public releases 1.4.0 and 1.5.0 remain immutable historical releases.

## Phase A — 9/10 preflight

The implementation/preflight branch must stay at **9/10 = 90.0%** and keep package/runtime metadata at **1.5.0**. Preflight may add and validate release infrastructure, but it must not create a release tag or publish to PyPI.

The exact preflight head must prove:

1. `tools/verify_2_0_release_candidate.py` passes in preflight mode.
2. The 1.5.0 → 2.0 migration/public-API floor remains intact.
3. The complete supported OS/Python matrix remains green.
4. Representative 2D, 3D and multiplayer shipping workflows remain green.
5. Exact-source wheel/sdist build and clean-install verification remain green.
6. Host-native desktop package verification remains green for claimed platforms.
7. Performance/scalability evidence remains within committed thresholds.
8. Export/build integrity, build identity and support-bundle privacy/integrity checks remain green.
9. Full pytest, strict Ruff and compile validation pass.
10. README/roadmap progress uses only the canonical SVG presentation and still reports the release freeze truthfully.

## Phase B — finalization head

Only after Phase A is green may a dedicated finalization commit:

- mark Milestone 10 complete and set the roadmap to **10/10 = 100.0%**;
- set `pyproject.toml` and `swirengine.__version__` to `2.0.0`;
- update project metadata so the primary roadmap URL points to `ROADMAP_2_0.md`;
- update README to a truthful **2.0.0 RELEASE PREP** identity while still naming 1.5.0 as the latest public stable release;
- keep `Release/PyPI: frozen until SwirEngine 2.0` until public publication has actually succeeded;
- regenerate `progress-card.svg` and `progress-mini.svg` from the same roadmap source;
- keep the publication workflow branch-trigger-free and bound to the immutable `v2.0.0` source;
- pass `python tools/verify_2_0_release_candidate.py --require-final`.

The **exact finalization head** must pass the complete final release gate again. A previously green 9/10 implementation head is not sufficient. Reaching 10/10 authorizes the guarded publication path; it does not by itself make 2.0.0 a public stable release.

## Phase C — immutable tag creation and guarded dispatch

`tag-2-0.yml` is the repository publication bridge. It runs only from `release/2.0.0-publish`, requires the complete final contract, and proves that the publication branch points at the exact current `main` commit before it can create a tag or request publication.

On the first successful run it creates `v2.0.0` without moving or replacing history. If the immutable tag already exists, the bridge preserves it, resolves its original source commit, re-runs that tagged source's final release contract, and requires a successful `Final Release Gate 2.0` run for that exact tagged commit. This recovery path exists because GitHub suppresses ordinary workflow triggers caused by a repository `GITHUB_TOKEN`; publication is therefore requested explicitly through `workflow_dispatch`, which GitHub permits from another workflow.

Before dispatch, the bridge refuses to continue when a GitHub Release or public PyPI `swirengine==2.0.0` already exists. It then dispatches `release-2.0.yml` from `main`. The publication workflow itself checks out `refs/tags/v2.0.0` for every source-dependent job, so workflow maintenance on `main` cannot silently change the package source after the immutable tag exists.

The publication branch must never contain release-source changes that are absent from `main`.

## Phase D — exact-tag publication

`release-2.0.yml` is branch-trigger-free. It accepts either the original `v2.0.0` tag push or the explicit guarded `workflow_dispatch` recovery path, but every source-dependent job checks out the immutable `refs/tags/v2.0.0` source. The build gate also resolves the tag commit and proves that it equals the checked-out `HEAD` before any publication job may proceed.

It must:

1. enforce the complete 2.0 release contract against the tagged source;
2. re-run public API/migration, platform, real-game, packaging, performance and release-safety verification;
3. run the full test/lint/compile gate;
4. build wheel and sdist from the immutable tagged source;
5. verify clean installation outside the development checkout;
6. validate the dedicated Windows CPython 3.14 native-renderer wheel path;
7. run real Linux OpenGL 2D/3D smoke checks and packaged Windows probes;
8. publish to PyPI through Trusted Publishing/OIDC with no `skip-existing` masking;
9. create the GitHub Release only after PyPI publication succeeds;
10. poll public PyPI, install exactly `swirengine==2.0.0` from the public index and run runtime/quick-start smoke verification outside the editable checkout.

A tag, dispatch request or uploaded artifact alone is not a successful release.

## Phase E — post-release audit and public-doc closeout

After public-index verification succeeds, update the live documentation to name **SwirEngine 2.0.0** as the latest public stable release, remove the pre-publication freeze language, and then immediately start a dedicated post-release audit covering:

- public API consistency and migration quality;
- backwards compatibility and locked historical contracts;
- renderer/runtime resource lifetime and memory handling;
- audio, input, physics, navigation, networking and dedicated-server behavior;
- creator/editor workflows, project creation and diagnostics;
- packaging/export and supported platform/runtime matrix;
- representative 2D/3D/multiplayer game usability;
- documentation accuracy, CI reliability and security/privacy boundaries.

A published 2.0.0 release is not treated as literal perfection. High-impact defects found by this audit remain active engineering work.

## Failure policy

Any failure before tag creation keeps 2.0 unpublished. Fix the issue on the feature/finalization branch and re-run the exact-head gate.

If tag creation succeeds but publication dispatch does not start, preserve `v2.0.0` exactly where it is. Repair only the orchestration path, prove the immutable tagged source and its final gate again, and dispatch publication without moving or recreating the tag.

A failure after public publication is handled as a post-release defect: preserve the immutable 2.0.0 release history, document the failure precisely, and prepare the smallest justified maintenance response rather than rewriting the existing tag or PyPI files.
