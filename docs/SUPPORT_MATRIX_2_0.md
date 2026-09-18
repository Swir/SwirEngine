# SwirEngine 2.0 — Python and Platform Support Matrix

This document defines the candidate support contract for SwirEngine 2.0 Milestone 5. It does not by itself mark the milestone complete or authorize a release. The exact implementation head and the later roadmap-marked closeout head must pass the required CI matrix before the claims become verified project state.

## Candidate public base-engine matrix

SwirEngine 2.0 targets the base package on 64-bit CPython across these desktop operating-system families:

| Operating system | CPython 3.10 | 3.11 | 3.12 | 3.13 | 3.14 | Packaging path |
|---|---:|---:|---:|---:|---|
| Windows | candidate | candidate | candidate | candidate | candidate | standard wheel for 3.10–3.13; dedicated native-bundled x86-64 wheel for 3.14 |
| Linux | candidate | candidate | candidate | candidate | candidate | standard wheel/sdist dependency resolution |
| macOS | candidate | candidate | candidate | candidate | candidate | standard wheel/sdist dependency resolution |

The repository metadata remains `>=3.10,<3.15`. The public package version remains `1.5.0` until the final SwirEngine 2.0 release gate; this source-development matrix must not be confused with a published 2.0 package.

## What “supported” means for Milestone 5

A matrix cell is verified only when the corresponding GitHub-hosted job completes all of the following from the exact candidate source:

1. install the development package and required verification tools;
2. run focused API/project/runtime regression tests;
3. run a platform probe that verifies CPython, the actual OS family, 64-bit interpreter, Python minor version, package metadata and required base runtime dependencies;
4. build the appropriate wheel from that source;
5. create a clean virtual environment and install that wheel without relying on the editable checkout;
6. repeat the platform probe from a temporary working directory with source-path environment overrides removed, and prove `swirengine` resolves outside the checkout;
7. run the maintained 2D and 3D game fixtures headlessly from that isolated clean-wheel environment;
8. keep the ordinary repository CI green so Python 3.10–3.13 still receive the full test suite on Windows, Linux and macOS.

The dedicated Milestone 5 workflow deliberately repeats packaging/runtime verification across the matrix instead of treating one Linux wheel build as proof for every operating system.

## CPython 3.14

Python 3.14 is part of the candidate 2.0 range, but Windows requires an explicit packaging path because the normal dependency declaration intentionally does not pull the renderer-native pair on Windows x86-64 for Python 3.14.

The Windows 3.14 job therefore:

- builds the pinned `moderngl==5.12.0` and `glcontext==3.0.0` native wheels from source;
- feeds those wheels into the existing `tools/build_vendored_wheel.py` path;
- installs the resulting `cp314-cp314-win_amd64` SwirEngine wheel in a clean environment;
- proves the vendored renderer modules are imported from the installed SwirEngine package before running headless game fixtures.

Linux and macOS Python 3.14 continue through normal dependency resolution and clean-wheel installation. If either platform cannot reproducibly install the required native dependencies, that cell must be removed from the final claim rather than bypassing the failure.

## Architecture boundaries

Milestone 5 validates only 64-bit interpreters on the actual GitHub-hosted runner architectures used by the workflow. It does **not** claim universal support for every CPU architecture.

- Windows Python 3.14 native packaging is explicitly `win_amd64` / x86-64.
- Linux and macOS architecture claims are limited to the 64-bit hosted runner architecture actually reported by the successful gate.
- 32-bit Python is unsupported by this matrix.
- PyPy, free-threaded CPython, Linux ARM boards, Windows ARM64 and additional macOS architectures are not claimed unless a later dedicated gate is added and passes.
- Cross-compilation is not implied; native desktop packaging remains host-native.

Milestone 7 performs the final host-native game-package shipping validation. Milestone 5 validates the engine package/runtime support matrix and does not pre-approve every final executable packaging target.

## Optional dependencies

The matrix above is the **base engine** contract. Optional extras such as `swirengine[audio]` are not silently promoted to the same support claim unless their own dependency/runtime evidence passes on the target combination. The final 2.0 documentation must keep optional-component limitations explicit.

## Deterministic local probes

From an installed development environment:

```bash
python tools/verify_platform_matrix_2_0.py
python -m pytest -q tests/test_platform_matrix_2_0.py
```

The clean-wheel verifier is intended for CI or an explicitly built wheel directory:

```bash
python tools/verify_clean_wheel_2_0.py --wheel-dir dist --expected-system Linux --expected-python 3.13
```

The runtime probe reports the detected Python implementation, system, machine, pointer width and Python version. It rejects non-CPython interpreters, 32-bit interpreters, unsupported Python minors, contradictory metadata and missing base runtime dependencies. The clean-wheel verifier additionally removes `PYTHONPATH`/`PYTHONHOME`, executes from a temporary working directory and rejects an import that resolves from the source checkout.

## Release policy

This milestone changes source-development support evidence only. Published SwirEngine 1.4.0 and 1.5.0 remain historical releases, and no intermediate 1.6–1.9 package is published.

`Release/PyPI: frozen until SwirEngine 2.0`
