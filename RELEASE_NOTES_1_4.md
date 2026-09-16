# SwirEngine 1.4.0 Release Notes

SwirEngine 1.4.0 — **Production World & Engine Power** — is the next stable 1.x release. It expands the engine from the 1.3 gameplay/creator foundation into larger-world authoring, deeper physics and movement, modern rendering/VFX, scalable scene processing, a stronger asset pipeline, editor authoring and opt-in multiplayer production foundations.

The release remains backward-compatible with the established stable 1.x API wherever practical. New 1.4 systems are additive and can be adopted incrementally.

## Highlights

### Terrain + World LOD

- Generated heightmap terrain and chunk mesh building.
- Distance-based LOD with bounded local selection and cache reuse.
- Terrain material/splat metadata, heightfield ground queries and large-world streaming integration.

### Physics 2.0 + Character Controllers

- Additive `PhysicsScene3D` / `PhysicsBody3D` APIs.
- Deterministic contacts, friction, restitution, sleeping, shape sweeps, joints and continuous-collision foundations.
- First-person, third-person and platformer controllers with jumping, coyote time, step/slope handling, ground snapping, camera integration and navigation steering.

### Renderer 2.0 + GPU VFX

- Opt-in `Renderer2`, `Renderer2Settings` and `Decal3D` APIs.
- Cascaded directional shadows with stabilization and PCF.
- Sampleable depth/view-normal prepass, SSAO, HDR bloom and screen-space decals.
- OpenGL 3.3 transform-feedback GPU particles with sprite, texture, trail and instanced-mesh paths.

### Asset Pipeline 2.0

- Dependency-aware bounded background import with caller-thread finalization.
- SHA-256 source/dependency fingerprints and transitive invalidation.
- Persistent content-addressed derived cache.
- Improved glTF/GLB dependency and PBR preservation.
- Conservative mesh cleanup and opt-in texture optimization.

### Scene Acceleration + Occlusion

- Deterministic static BVH plus dynamic refits.
- Conservative world bounds and broad frustum pruning.
- Renderer2 candidate-view integration.
- CPU Hi-Z reference queries and a real GPU maximum-depth pyramid without CPU readback.

### Editor Authoring Power

- Ordered multi-selection and range/toggle selection.
- Grouped property/gizmo/asset editing with transaction-safe undo/redo.
- Persistent authoring sidecars and safe asset drag/drop paths.
- Material, physics and navigation inspector adapters.
- Explicit Play/Edit authoring isolation.
- Opt-in `swirengine.editor14` facade.

### Multiplayer 2.0

- Replicated-component schemas.
- Canonical snapshots and sparse deltas.
- Bounded out-of-order interpolation.
- Client prediction with authoritative reconciliation.
- Bounded server rewind foundations and per-channel bandwidth diagnostics.
- Stable `NetworkPacket` bridge.

## Integrated validation

`demo_projects/neon_frontier_1_4` is the 1.4 release-validation project. It combines terrain/LOD, Physics 2.0, Character Controllers, Renderer 2.0, GPU VFX, large-world streaming, Editor Authoring and Multiplayer 2.0 in one asset-free project.

The final release gate covers:

- full pytest, strict Ruff and compile validation;
- Python 3.10-3.13 across the supported desktop matrix;
- Windows x86-64 CPython 3.14 native-wheel build, selection and import validation;
- deterministic milestone and integrated performance contracts;
- real Linux OpenGL 3.3 execution under Xvfb/Mesa;
- clean wheel installation outside the source tree;
- Windows one-file packaged runtime probing;
- strict `tools/verify_1_4_release_candidate.py --require-complete` validation;
- Trusted Publishing to PyPI;
- public-PyPI clean-install verification after publication.

## Compatibility

SwirEngine 1.4.0 preserves established 1.x root imports and keeps the new major 1.4 systems additive or opt-in. Projects using stable 1.3 APIs do not need to migrate simply to install 1.4.0.

Python support is `>=3.10,<3.15`. The normal cross-platform matrix covers Python 3.10-3.13; Windows x86-64 additionally has the dedicated CPython 3.14 native-wheel path.

## Install / upgrade

```bash
python -m pip install -U swirengine==1.4.0
```

Optional audio support:

```bash
python -m pip install -U "swirengine[audio]==1.4.0"
```

## Documentation

See [`ROADMAP_1_4.md`](ROADMAP_1_4.md) for the verified 10/10 roadmap and [`docs/RELEASE_HARDENING_1_4.md`](docs/RELEASE_HARDENING_1_4.md) for the final release-gate contract.
