# SwirEngine 2.2.0 Release Notes

Prepared from the bound 2.2.0 candidate. Public availability is authoritative only from the
immutable `v2.2.0` tag, GitHub Release metadata and PyPI project metadata.

## Production tools and visual creation

- Deterministic material and shader assets with creator-facing editing and shipping-renderer
  preview paths.
- Visual node-graph authoring that keeps untrusted graph data separate from trusted Python
  execution.
- Terrain, foliage, animation state-machine and blend-tree authoring backed by runtime data.
- Particle/VFX, lighting, environment and post-processing authoring with isolated previews and
  project-confined resources.
- Responsive UI Designer workflows with reusable styles, interaction states and bounded
  animations over the shipping UI toolkit.
- Privacy-safe multiplayer diagnostics and a capability-gated Editor Extension SDK.

## Compatibility and qualification

- Preserves the published SwirEngine 2.1 project/runtime compatibility baseline.
- Supports the maintained 64-bit CPython 3.10–3.14 matrix on the explicitly tested Windows,
  Linux and macOS runners.
- Keeps public API compatibility, source/runtime version parity, deterministic package contents,
  clean-wheel installation and representative 2D, 3D and multiplayer projects under release
  gates.
- Excludes repository-only release evidence and publication-control markers from wheel and sdist
  payloads.

## Release identity

The guarded publication workflow binds the reviewed candidate source, required-workflow manifest,
publication marker chain, `v2.2.0` tag, PyPI files, checksums, provenance and GitHub Release assets.
Existing public objects are immutable; retry/resume may add only objects proven to be missing.
