# Migrating from SwirEngine 1.5.0 to 2.0

## Status

SwirEngine 2.0 is under source development. The latest published stable package remains **1.5.0**. Source-only checkpoints 1.6 through 1.9 were engineering milestones and were intentionally not published as GitHub Releases or PyPI versions.

`Release/PyPI: frozen until SwirEngine 2.0`

This guide is the migration ledger for the future 2.0 release. It must describe every intentional public compatibility break before the release candidate is approved.

## Compatibility floor

The machine-readable root API floor is [`public_api_2_0.json`](public_api_2_0.json). It fingerprints the actual `swirengine.__all__` surface from the published `v1.5.0` tag instead of duplicating a hand-maintained list. The verifier reads that tagged source, checks its Git blob SHA, export count and deterministic export-list digest, then proves every baseline root export is still present in the current source tree. Additive 2.0 root exports remain possible without mutating the historical baseline fingerprint.

According to the established API stability policy, every name exported through the published 1.5.0 `swirengine.__all__` is public API. `swirengine.__version__` is additionally guarded as the package version attribute even though it is not part of `__all__`.

## Current migration ledger

**No mandatory user-code migration has been identified at the start of the 2.0 roadmap.** At Milestone 1 kickoff, the current root export set preserves all 271 exports fingerprinted from the published `v1.5.0` root module, with no additional root exports reported by the verifier.

This statement is deliberately narrow: it does not claim byte-for-byte identity outside the measured public-root contract, it does not claim that every source-only 1.6–1.9 API is permanently stable, and it does not imply that 2.0 is beta-ready or release-ready.

## Rule for future breaking changes

A change that intentionally breaks a public 1.5.0 compatibility-floor contract must not land silently. The same pull request must:

1. explain the engineering reason and creator impact here;
2. update `docs/public_api_2_0.json` only if the baseline evidence itself was incorrect — never to hide a removal;
3. update `docs/API_STABILITY.md` where the stability classification changes;
4. add migration/regression tests for the old and new behavior where practical;
5. update the changelog/release-notes source;
6. keep the 2.0 roadmap percentage unchanged until the relevant gate is verified.

Removing a root export merely because an internal module was reorganized is not an acceptable migration reason.

## Version metadata during development

`pyproject.toml` and `swirengine.__version__` intentionally remain at **1.5.0** throughout intermediate source development. The final 2.0 version change belongs to the verified Milestone 10 release-candidate step together with release/PyPI checks.

## Verification

The verifier requires a Git checkout containing the published `v1.5.0` tag. CI uses a full checkout deliberately.

```bash
git fetch --tags
python tools/verify_2_0_public_api.py
pytest -q tests/test_public_api_2_0.py
```

The dedicated CI workflow runs this contract on Python 3.10, 3.13 and 3.14. A green API contract is necessary for Milestone 1, but it does not by itself make 2.0 beta-ready or release-ready.
