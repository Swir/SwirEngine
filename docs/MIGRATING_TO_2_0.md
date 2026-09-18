# Migrating from SwirEngine 1.5.0 to 2.0

## Status

SwirEngine 2.0 is under source development. The latest published stable package remains **1.5.0**. Source-only checkpoints 1.6 through 1.9 were engineering milestones and were intentionally not published as GitHub Releases or PyPI versions.

`Release/PyPI: frozen until SwirEngine 2.0`

This guide is the migration ledger for the future 2.0 release. It must describe every intentional public compatibility break before the release candidate is approved.

## Compatibility floor

The machine-readable root API floor is [`public_api_2_0.json`](public_api_2_0.json). It is derived from the published `v1.5.0` `swirengine.__all__` surface and is verified against the current source tree.

The following behavior contracts remain stable unless this guide explicitly records a deliberate 2.0 migration:

- `run`, `GameEngine`, `GameLogic`, `GameObject`
- `ECSWorld`, `EntityHandle`
- `Transform2D`, `Transform3D`
- `Velocity2D`, `Velocity3D`
- `Lifetime`, `ECSStats`

`__version__`, `System` and `Time` are also protected for root-import compatibility by the 2.0 manifest. Their detailed behavior remains governed by the subsystem documentation and the API stability policy rather than by a new promise invented in this migration guide.

## Current migration ledger

**No mandatory user-code migration has been identified at the start of the 2.0 roadmap.** Existing 1.5.0 root imports remain present in the current source tree.

This statement is deliberately narrow: it does not claim that every source-only 1.6–1.9 API is permanently stable, nor does it imply that 2.0 is release-ready.

## Rule for future breaking changes

A change that intentionally breaks a public 1.5.0 compatibility-floor contract must not land silently. The same pull request must:

1. explain the engineering reason and creator impact here;
2. update `docs/public_api_2_0.json`;
3. update `docs/API_STABILITY.md` where the stability classification changes;
4. add migration/regression tests for the old and new behavior where practical;
5. update the changelog/release notes source;
6. keep the 2.0 roadmap percentage unchanged until the relevant gate is verified.

Removing a root export merely because an internal module was reorganized is not an acceptable migration reason.

## Version metadata during development

`pyproject.toml` intentionally remains at **1.5.0** throughout intermediate source development. It must not be changed to a 1.6–1.9 public version. The final 2.0 version change belongs to the verified Milestone 10 release-candidate step, together with release/PyPI checks.

## Verification

Run the deterministic public API contract check:

```bash
python tools/verify_2_0_public_api.py
pytest -q tests/test_public_api_2_0.py
```

The dedicated CI workflow also runs this contract on the supported development Python matrix. A green API contract is necessary for Milestone 1, but it does not by itself make 2.0 beta-ready or release-ready.
