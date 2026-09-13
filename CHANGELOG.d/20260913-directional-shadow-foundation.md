## Directional shadow-map foundation

- add validated `DirectionalShadowSettings` and deterministic directional-light view/projection frame generation
- add a lazy GPU depth texture/framebuffer pass for visible `Mesh3D` shadow casters
- reuse position-only mesh GPU buffers across frames, restore the caller viewport after the pass, expose explicit texture binding, and release GPU resources deterministically
- add regression coverage for settings validation, vertical-light camera stability, rendering/filtering, cache reuse, binding and cleanup

This establishes the reusable depth-map pass needed for renderer-side shadow sampling. The roadmap `0.4 shadows` deliverable remains open until the main forward shader consumes the map and applies shadow visibility to directional lighting.
