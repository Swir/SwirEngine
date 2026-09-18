# SwirEngine 2.0.0 Release Notes

SwirEngine 2.0.0 is the next planned public release after 1.5.0. It consolidates the source-only 1.6–1.9 engineering checkpoints into a verified Python-first production path for complete 2D, 3D and multiplayer games.

These notes are committed before publication so the exact release candidate can validate them. Their presence does not mean 2.0.0 has already been published.

## Highlights

### Public API and migration contract

- Preserves the published 1.5.0 root API as the explicit compatibility floor.
- Ships a machine-verifiable 1.5.0 → 2.0 migration ledger and API-stability policy.
- Requires deliberate breaking changes to carry migration evidence and regression coverage.

### Integrated creator workflow

- Adds a coherent project creation, validation, preparation, run-session and shipping workflow.
- Validates scene/prefab, content, input/settings, save/profile and export configuration through creator-facing tooling.
- Provides deterministic JSON evidence and actionable diagnostics for malformed projects and missing content.

### Multiplayer and dedicated-server production contract

- Adds deterministic client/server compatibility fingerprints and reconnect/resume hardening.
- Separates authoritative gameplay state from player-local settings/save/profile data.
- Provides a validated fixed-tick headless dedicated-server path and multiplayer integration fixture.

### Runtime scalability and resource lifecycle

- Hardens asset streaming residency, cancellation, teardown, cache invalidation and pressure diagnostics.
- Verifies bounded transient render-resource reuse and deterministic cleanup.
- Locks representative 2D and 3D scale workloads to reproducible pruning/reuse invariants instead of unsupported FPS claims.

### Verified Python/platform matrix

- Base-engine support is verified on 64-bit CPython 3.10–3.14 across the documented Windows, Linux and macOS matrix.
- Clean-wheel verification runs outside the development checkout.
- Windows x86-64 CPython 3.14 uses the validated native-renderer wheel path.

### Real-game shipping gate

- Maintained 2D, 3D and multiplayer projects exercise the same production workflow as user projects.
- Fixtures validate input/UI, settings, save/profile, scenes, assets, diagnostics, export staging and failure paths.
- Source and staged entrypoints are verified rather than treating isolated subsystem demos as sufficient evidence.

### Packaging and native desktop shipping

- Builds wheel and sdist from exact candidate source and validates archive safety/inventory.
- Installs artifacts into isolated environments and executes maintained fixtures from the installed package.
- Verifies host-native packaged game execution on the supported desktop hosts covered by CI.

### Performance evidence

- Uses deterministic performance/scalability workloads with committed thresholds and exact runner context.
- Keeps shared-runner timings as regression evidence, not universal FPS marketing.
- Limits competitive comparisons to reproducible workflow facts where technically comparable.

### Export integrity and release safety

- Verifies staged export inventory and SHA-256 integrity, including missing/tampered/unexpected content rejection.
- Adds deterministic build-integrity seals covering generated native build inputs.
- Audits generated support bundles for bounded contents, safe paths, redaction/privacy declarations and build identity.

## Compatibility

- Published 1.4.0 and 1.5.0 releases remain immutable historical releases.
- Python requirement remains `>=3.10,<3.15`.
- The final supported platform statement is defined by `docs/SUPPORT_MATRIX_2_0.md`; combinations outside that verified matrix are not implied to be supported.
- Source-only 1.6–1.9 checkpoints are not separate public releases.

## Install

After successful publication, install the exact release from public PyPI:

```bash
python -m pip install -U swirengine==2.0.0
```

Optional audio support:

```bash
python -m pip install -U "swirengine[audio]==2.0.0"
```

## Verification

The final release is valid only after the repository's complete 2.0 gate passes on the exact tagged source and public PyPI installation is verified outside the development checkout.

See:

- `ROADMAP_2_0.md`
- `docs/RELEASE_GATE_2_0.md`
- `docs/MIGRATING_TO_2_0.md`
- `docs/SUPPORT_MATRIX_2_0.md`
- `docs/PACKAGING_SHIPPING_2_0.md`
- `docs/RELEASE_SAFETY_2_0.md`
