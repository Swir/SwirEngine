# SwirEngine API stability

SwirEngine 1.0 established the first stable public API. SwirEngine 1.5.0 is the latest published stable package and is the explicit compatibility baseline for the 2.0 migration process.

## 1.x compatibility promise

For the 1.x series, names exported from `swirengine.__all__` are treated as public API. Existing public call signatures and documented behavior should remain source-compatible within 1.x unless a change is required to fix a security issue or a clearly incorrect behavior. Additive APIs may be introduced in minor source development. Breaking public API changes are reserved for a major release.

Modules, attributes and helpers that are not exported through `swirengine.__all__` are implementation details unless another project document explicitly marks them public.

## Stable baseline for 2.0

The released `v1.5.0` root API is stored in `docs/api-contracts/swirengine-1.5-public-api.json`. The 2.0 line must not silently rewrite that baseline. New root exports and intentional removals are tracked separately in `docs/api-contracts/swirengine-2.0-migration.json` and verified by `tools/verify_api_contract_2_0.py`.

This distinction matters because source-only systems developed after 1.5.0 are not automatically public API. A subsystem graduates into the public 2.0 root surface only when the migration ledger, focused tests, creator documentation and active roadmap gate explicitly support it.

See [`API_MIGRATION_2_0.md`](API_MIGRATION_2_0.md) for the migration rules.

## Stable subsystems

The original stable public surface covers the engine loop and scenes, 2D and 3D rendering, cameras, meshes and materials, glTF/OBJ loading, cubemap IBL, directional shadows, post-processing, animation, particles, audio, 2D collision/physics, UI, assets and hot reload, prefabs and scene serialization, ECS, plugins, editor/runtime models, networking and project export tooling.

## Versioning

SwirEngine follows semantic versioning from 1.0 onward:

- PATCH: backwards-compatible fixes and internal improvements.
- MINOR: backwards-compatible features and new public APIs.
- MAJOR: intentionally breaking public API changes with explicit migration guidance.

`swirengine.__version__` and `[project].version` in `pyproject.toml` must always match. CI enforces this contract.

During normal 2.0 source development both remain `1.5.0` so source checkpoints cannot be mistaken for public packages. The final 2.0 release-candidate gate changes both to `2.0.0` together and verifies the migration ledger before publication.

## Deprecation and migration policy

When practical, a public API scheduled for removal should first remain available with a documented replacement. Deprecated APIs should not silently change semantics. For the 2.0 major transition, any intentional 1.5.0 root removal must be machine-recorded with a migration rationale; a named replacement must actually exist in the candidate public surface.

## Release verification

Every supported Python/OS combination claimed for a public release must pass its documented CI/runtime contract. Packaging verification builds wheel and sdist artifacts and validates clean installation outside the source tree. The SwirEngine 2.0 release additionally requires the dedicated 2.0 roadmap to reach verified 10/10, the full real-game/export matrix to be green, and the published PyPI package to be reinstalled from the public index successfully.
