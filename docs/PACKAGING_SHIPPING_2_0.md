# SwirEngine 2.0 Packaging, Clean Install & Native Desktop Shipping

This document defines the candidate contract for SwirEngine 2.0 Milestone 7. It does not mark the
milestone complete by itself. The exact implementation head must pass its dedicated workflow and the
required repository regression/compatibility gates before the roadmap can move from 6/10 to 7/10.

## Goal

Milestone 7 closes the gap between "the source tree works" and "a creator can consume built artifacts
and produce a host-native game package without depending on the development checkout."

The gate deliberately reuses the established 1.9 desktop-shipping implementation and the verified 2.0
platform matrix instead of creating a second exporter or packaging stack.

## Exact-source distributions

The dedicated gate builds both artifacts from the exact candidate checkout:

```bash
python -m build --wheel --sdist --outdir dist
python -m twine check dist/*
```

`tools/verify_packaging_shipping_2_0.py` then requires exactly one SwirEngine wheel and one source
distribution. Both archives are inspected before installation:

- paths must be relative and traversal-free;
- case-folded duplicate members are rejected;
- repository/build-state paths such as `.git`, `.venv` and `__pycache__` are rejected;
- the wheel must contain one SwirEngine `METADATA` record and `swirengine/__init__.py`;
- the sdist must contain one `PKG-INFO` record and `src/swirengine/__init__.py`;
- distribution name/version must remain `swirengine` / `1.5.0` while the 2.0 release freeze is active;
- sdist link/device members are rejected;
- SHA-256 digests are emitted for both candidate artifacts as verification evidence.

## Clean wheel and sdist installs

Wheel and sdist are installed independently into fresh virtual environments under temporary roots.
The verifier removes `PYTHONPATH`/`PYTHONHOME`, enables `PYTHONNOUSERSITE`, changes to an isolated
working directory and rejects a `swirengine` import or `sys.path` entry that resolves through the
development checkout.

Maintained 2D, 3D and multiplayer fixtures are copied into the temporary root before execution and run
against each clean installed artifact. This makes artifact verification independent of editable-install
or repository import behavior while preserving the same integration fixtures used by the real-game gate.

## Host-native game packaging

After clean distribution verification, the established
`tools/verify_clean_desktop_shipping_1_9.py` contract installs the built wheel in another fresh
environment, builds a minimal game through `build_desktop_shipping`, validates its plan and artifact
manifest, launches the produced executable and requires its runtime marker.

The workflow runs that package build natively on:

- Windows hosted runner / CPython 3.13;
- Linux hosted runner / CPython 3.13;
- macOS hosted runner / CPython 3.13.

This is a host-native claim only. It does not introduce or imply desktop cross-compilation. The wider
15-cell CPython 3.10–3.14 base-engine matrix remains the separate verified Milestone 5 contract.

## Failure semantics

The milestone is not complete if any of these occur:

- wheel or sdist metadata/inventory is malformed or ambiguous;
- an archive can escape its extraction root;
- a clean import resolves through the source checkout;
- copied 2D/3D/multiplayer fixtures fail from either installed distribution;
- host-native shipping cannot build, validate or launch its executable;
- a historical compatibility/source-checkpoint gate regresses;
- progress/README/SVG presentation becomes stale or reintroduces a retired text meter.

## Release policy

The public package and module version remain `1.5.0` during this source-development gate. No tag,
GitHub Release or PyPI publication is created by Milestone 7.

`Release/PyPI: frozen until SwirEngine 2.0`
