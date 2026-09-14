# SwirEngine 1.1.0

SwirEngine 1.1.0 is the first release produced after the complete 1.1 roadmap reached **10/10 = 100.0%** and passed its creator-facing release gate.

## Major 1.1 milestones

- standardized gamepad/controller API with hot-plug, edge queries, analog deadzones and triggers;
- semantic input actions, rebinding and persistent control profiles;
- static 3D larger-batch rendering with a deterministic draw-call/frame-preparation regression gate;
- async/preload asset pipeline with coalesced loading and deterministic diagnostics;
- responsive UI anchors/layout/focus/navigation for mouse, keyboard and gamepad workflows;
- expanded audio mixer buses, fades, spatial controls and runtime diagnostics;
- shared tween/timeline/state-machine animation runtime for 2D, 3D, UI and gameplay;
- spatial-hash physics broad phase plus richer overlap/point/raycast creator queries;
- project/editor workflow support for scenes, prefabs, input setup and reversible Play/Edit iteration;
- creator hardening with executable release contracts, complete demo validation, packaging/runtime probes and release-freeze enforcement.

## Verification contract

The final release workflow is required to pass before publication:

- full pytest suite, Ruff and compileall;
- Windows, Linux and macOS validation on Python 3.10-3.13;
- Windows x64 Python 3.14 validation and dedicated native-renderer wheel selection;
- wheel/sdist build plus `twine check` and clean installation;
- static-3D batching and async-preload performance regression gates;
- real Mesa/Xvfb OpenGL boots for Neon Cube Hunt 3D and Neon Snake 3D;
- PyInstaller packaged Windows runtime probes for both complete 3D games;
- release contract requiring `ROADMAP_1_1.md` to remain exactly 10/10 = 100.0%;
- PyPI publication only through GitHub OIDC Trusted Publishing.

## Compatibility

SwirEngine 1.1 keeps the public 1.x API additive and creator-focused. Breaking redesigns are deferred to an explicitly planned future line instead of being slipped into the 1.1 release.

Verified support scope remains Python 3.10-3.13 on Windows/Linux/macOS and Python 3.14 on Windows x86-64. Broader Python 3.14 platform claims are intentionally withheld until native dependency packaging is equally reproducible and tested.

See `README.md`, `ROADMAP_1_1.md`, `CHANGELOG.md`, `CHANGELOG.d/`, and `docs/RELEASE_CANDIDATE_1_1.md` for the complete development and verification history.
