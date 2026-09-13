# SwirEngine 1.0 API stability

SwirEngine 1.0 is the first stable public API release.

## Compatibility promise

For the 1.x series, names exported from `swirengine.__all__` are treated as public API. Existing public call signatures and documented behavior should remain source-compatible within 1.x unless a change is required to fix a security issue or a clearly incorrect behavior. Additive APIs may be introduced in minor releases. Breaking public API changes are reserved for a future major release.

Modules, attributes and helpers that are not exported through `swirengine.__all__` are implementation details unless another project document explicitly marks them public.

## Stable subsystems

The 1.0 public surface covers the engine loop and scenes, 2D and 3D rendering, cameras, meshes and materials, glTF/OBJ loading, cubemap IBL, directional shadows, post-processing, animation, particles, audio, 2D collision/physics, UI, assets and hot reload, prefabs and scene serialization, ECS, plugins, editor/runtime models, networking and project export tooling.

## Versioning

SwirEngine follows semantic versioning from 1.0 onward:

- PATCH: backwards-compatible fixes and internal improvements.
- MINOR: backwards-compatible features and new public APIs.
- MAJOR: intentionally breaking public API changes.

`swirengine.__version__` and `[project].version` in `pyproject.toml` must always match. CI enforces this contract.

## Deprecation policy

When practical, a public API scheduled for removal should first remain available for at least one minor release with a documented replacement. Deprecated APIs should not silently change semantics.

## Release verification

Every supported Python/OS CI combination runs the test suite, Ruff and bytecode compilation. A dedicated packaging job also builds wheel and sdist artifacts and validates the built wheel by installing it into a clean virtual environment and importing `swirengine`. Tag builds beginning with `v` produce release artifacts through the release workflow.
