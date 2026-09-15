# SwirEngine 1.3 Full Game, Hardening & Release Gate

Milestone 10/10 is the final release gate for SwirEngine 1.3. It does not become complete merely because individual feature milestones are green. The exact final release head must prove that the complete engine, packaging and public-artifact workflow remain coherent together.

## Integrated validation game

`demo_projects/neon_frontier_1_3/run_game.py` is the final asset-free integration game. A single ordinary SwirEngine application exercises:

- the production OpenGL `Game` renderer
- GPU-instanced cubes
- a real `ShaderMesh3D` custom material/uniform path
- 3D collision queries
- 3D navigation and an active navigation agent
- bounded large-world chunk residency
- the deterministic gameplay scheduler
- established camera and lighting APIs

The smoke mode stops after a deterministic frame count and asserts that the integrated systems remained live. This complements, rather than replaces, the subsystem-specific deterministic performance gates.

## Release-contract verifier

`tools/verify_1_3_release_candidate.py` checks the repository contract in two phases.

During development it accepts the published 1.2.0 package version while validating the 1.3 roadmap structure, documentation, API namespaces, final-game source and release/CI wiring.

The `--require-complete` mode is intentionally stricter and refuses publication unless:

- the package version is exactly `1.3.0`
- `ROADMAP_1_3.md` is exactly 10/10 = 100.0%
- the roadmap status badge is `STATUS-COMPLETE`
- README metadata describes the final 1.3 release
- the integrated validation game and 1.3 documentation are present
- the release workflow uses the 1.3 verifier and Trusted Publishing
- Windows CPython 3.14 native-wheel validation remains enabled
- the final full-game gate includes real OpenGL and packaged Windows validation

## Performance policy

The release workflow re-runs the deterministic regression workloads for instancing, collision, navigation, large-world locality, shader caching, 2D renderer locality, gameplay scheduling/object reuse and creator/editor filtering, plus the established static-batching and asynchronous-preload gates.

Host elapsed times remain diagnostic. SwirEngine does not turn CI runner timing into an FPS claim.

## Packaging and runtime gates

Before publication, the release workflow must pass:

1. complete pytest, Ruff and compileall validation
2. wheel/sdist build and `twine check`
3. real software-OpenGL boot of Neon Frontier 1.3, Neon Cube Hunt 3D and Neon Snake 3D
4. one-file Windows PyInstaller runtime probes
5. dedicated `cp314-cp314-win_amd64` build with vendored native renderer dependencies
6. clean CPython 3.14 Windows installation proving pip selects the native wheel candidate

## Public-artifact verification

Publication uses GitHub Trusted Publishing. After PyPI and GitHub Release creation, CI installs **only the public PyPI artifact** and verifies metadata/import/API behavior. Linux runs Neon Frontier against the public package under software OpenGL. Windows Python 3.14 verifies the native renderer imports from the public wheel and runs the packaged-runtime probe path.

If any public-artifact check fails, only the final 1.3 release blocker is fixed and the release is re-verified. No 1.4/2.0 work starts as part of this milestone.
