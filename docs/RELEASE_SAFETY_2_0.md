# SwirEngine 2.0 — Export Integrity, Diagnostics & Release Safety

This document defines the candidate contract for SwirEngine 2.0 Milestone 9. It does **not** mark the milestone complete by itself. The exact implementation head and a later roadmap closeout head must pass their required CI/regression matrices before progress can move from 8/10 to 9/10.

## Why this gate exists

A successful build command is not enough evidence that a game is safe to ship. Release-quality output must prove that required content was staged, staged bytes still match the export inventory, generated build inputs have not silently changed, crash/support data respects privacy boundaries, and a support report can be tied back to the exact verified build identity.

Milestone 9 therefore hardens the boundary between project/export systems from earlier checkpoints and the final SwirEngine 2.0 release gate.

## Staged export integrity

`swirengine.release_safety20.verify_export_staging()` validates an existing `ProjectExporter` staging directory without executing the game or build tool.

The verifier requires:

- `swir-export.json` format/version 2;
- one portable, relative, unambiguous path for every declared staged file;
- no duplicate paths or cross-platform case-fold collisions;
- an exact SHA-256 for every declared staged file;
- every declared file to exist as a regular non-symlink file;
- every staged file checksum to match the export manifest;
- the generated `swirengine-build.spec`, when declared, to exist and participate in build identity;
- no undeclared extra staged files in strict pre-build verification;
- native build/work outputs to be tolerated only through the explicit `allow_native_outputs=True` post-build mode.

The existing exporter remains responsible for semantic preflight of declared scene packages and the production content graph. That means missing declared scene/prefab/generated content fails before staging; Milestone 9 adds a second boundary that verifies the resulting staged bytes cannot silently drift afterward.

## Deterministic build identity and seal

A build identity is SHA-256 over canonical release evidence:

- export-manifest SHA-256;
- target, entrypoint and app identity;
- ordered declared file inventory and checksums;
- native build command/spec declaration;
- project packaging metadata;
- hashes of generated build inputs such as the PyInstaller spec.

`seal_export_staging()` first verifies the stage and then writes `swir-build-integrity.json`. The seal stores the build ID, manifest hash, declared file count and generated-file checksums. A later verification recomputes the identity from bytes on disk and rejects a stale/tampered seal.

The seal is deterministic integrity evidence, not a cryptographic publisher signature. Code signing and publisher identity remain separate release concerns.

## Support-bundle privacy and integrity audit

`verify_support_bundle()` audits the opt-in diagnostic ZIP produced by the existing 1.9 runtime diagnostics system. The audit accepts only the generated entries:

- `bundle.json`
- `report.json`

It rejects duplicate/injected/unsafe ZIP entries, encrypted entries, oversized uncompressed payloads, report-hash mismatches, report-fingerprint mismatches and broken diagnostic schemas.

The privacy declaration must explicitly keep all of these disabled:

- automatic environment capture;
- automatic argv capture;
- automatic arbitrary user-file capture;
- traceback source-line capture.

Sensitive diagnostic field names must remain redacted, obvious secret-like assignment text must not survive the audit, and trace filenames must remain relative/sanitized rather than exposing arbitrary absolute filesystem paths.

When `expected_build_id` is supplied, the support report must identify exactly the verified build that produced the report. This gives maintainers actionable build correlation without automatically collecting private user files or process state.

## Deterministic verification

Run the focused contract with:

```bash
python -m pytest -q \
  tests/test_release_safety_2_0.py \
  tests/test_runtime_diagnostics_1_9.py \
  tests/test_exporting.py
python tools/verify_release_safety_2_0.py
```

The deterministic verifier creates a temporary project and desktop export, seals and re-verifies it, links an opt-in privacy-safe crash bundle to that build identity, then proves that staged-content tampering and injected support-bundle files are rejected.

The dedicated `Release Safety 2.0` GitHub Actions workflow runs the same contract on Python 3.10, 3.13 and 3.14. Full repository CI, locked 1.4/1.5 contracts, source checkpoints 1.6–1.9, platform/package gates, representative game workflows and existing export/runtime diagnostics regressions remain required before Milestone 9 may close.

## Release policy

This is source-development hardening toward SwirEngine 2.0. It does not create an intermediate release, tag or PyPI package and it does not alter published 1.4.0/1.5.0 history.

`Release/PyPI: frozen until SwirEngine 2.0`
