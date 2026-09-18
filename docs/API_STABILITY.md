# SwirEngine API stability

SwirEngine 1.0 established the first stable public API line. The published **1.5.0** package remains the public compatibility baseline while source development proceeds toward 2.0.

## Compatibility promise

For the 1.x series, names exported from `swirengine.__all__` are treated as public API. Existing public call signatures and documented behavior should remain source-compatible within 1.x unless a change is required to fix a security issue or clearly incorrect behavior. Additive APIs may be introduced in minor releases. Breaking public API changes are reserved for a major release.

Modules, attributes and helpers that are not exported through `swirengine.__all__` are implementation details unless another project document explicitly marks them public.

## SwirEngine 2.0 migration floor

The 2.0 line starts from the published `v1.5.0` root API rather than inventing a new compatibility baseline from source-only checkpoints. [`public_api_2_0.json`](public_api_2_0.json) is the machine-readable contract and [`MIGRATING_TO_2_0.md`](MIGRATING_TO_2_0.md) is the human migration ledger.

Every root export recorded in that manifest must remain importable through the 2.0 release candidate unless a deliberate breaking migration is documented, justified and covered by tests. Stable behavior guarantees remain those already established by the version in which an API became stable; recording a name for import compatibility does not silently promote an experimental behavior to stable.

The published 1.5.0 baseline fingerprint is historical evidence and must not be rewritten to hide a removal. A deliberate 2.0 breaking change must update the migration ledger, relevant stability classification, migration/regression tests and changelog/release-note source together. `public_api_2_0.json` changes are allowed only when the recorded baseline evidence itself is proven incorrect. Internal refactors are not sufficient justification for silently removing a compatibility-floor export.

## Stable subsystems

The 1.0 public surface covers the engine loop and scenes, 2D and 3D rendering, cameras, meshes and materials, glTF/OBJ loading, cubemap IBL, directional shadows, post-processing, animation, particles, audio, 2D collision/physics, UI, assets and hot reload, prefabs and scene serialization, ECS, plugins, editor/runtime models, networking and project export tooling.

Additional root-level ECS compatibility names introduced before or in the 1.5.0 public baseline are classified explicitly in `public_api_2_0.json`; detailed subsystem stability remains governed by the documentation and regression contracts that introduced them.

## Versioning

SwirEngine follows semantic versioning from 1.0 onward:

- PATCH: backwards-compatible fixes and internal improvements.
- MINOR: backwards-compatible features and new public APIs.
- MAJOR: intentionally breaking public API changes.

During published 1.x releases, `swirengine.__version__` and `[project].version` in `pyproject.toml` must match. During the source-only 1.6–1.9/2.0-development phase, package metadata intentionally remains at the latest public stable **1.5.0** until the verified final 2.0 release gate. CI/verifiers enforce the appropriate phase contract rather than publishing intermediate versions.

## Deprecation policy

When practical, a public API scheduled for removal should first remain available with a documented replacement. A deliberate 2.0 break must be entered in the migration ledger before the release candidate is approved. Deprecated APIs must not silently change semantics.

## Release verification

Every claimed supported Python/OS combination must run the relevant test/runtime contract, Ruff and bytecode compilation. Packaging verification must build wheel and sdist artifacts and validate clean installation independently of the source checkout. SwirEngine 2.0 additionally requires representative real-game workflows, native shipping checks, migration validation and public PyPI installation verification before release.
