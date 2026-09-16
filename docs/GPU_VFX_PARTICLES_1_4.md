# SwirEngine 1.4 — GPU VFX + Particle Power

This document covers milestone #5 of the guarded SwirEngine 1.4 roadmap. The implementation and required validation gates are complete on the feature branch, so the synchronized 1.4 development roadmap is now **5/10 = 50.0%**. Stable SwirEngine remains 1.3.0 until the full 1.4 roadmap reaches its guarded release gate.

## Goal

SwirEngine already has a production-friendly pooled `ParticleEmitter2D`. Milestone #5 adds a separate GPU-oriented path for high-count 3D effects without changing that stable API.

`GPUParticleEmitter3D` works with the opt-in `Renderer2` path. Particle position, previous position, velocity, age, lifetime, size and recycling live in ping-pong GPU buffers. Python schedules elapsed time and emission batches; it does not iterate through every GPU particle each frame.

## Quick start

```python
from swirengine import Color, Game, GPUParticleEmissionShape3D, Vec3


game = Game("GPU particles", 1280, 720, mode="3d")
game.configure_renderer2(True, bloom=True, bloom_threshold=0.7)

fire = game.gpu_particles(
    position=Vec3(0.0, 1.0, -3.0),
    capacity=8192,
    rate=1800.0,
    lifetime=(0.8, 1.8),
    velocity_min=Vec3(-1.5, 1.0, -1.5),
    velocity_max=Vec3(1.5, 5.0, 1.5),
    gravity=Vec3(0.0, -4.0, 0.0),
    start_color=Color(1.0, 0.65, 0.1, 1.0),
    end_color=Color(1.0, 0.05, 0.01, 0.0),
    emission_shape=GPUParticleEmissionShape3D.SPHERE,
    emission_extent=Vec3(0.4, 0.4, 0.4),
    emissive_strength=3.0,
    trail_enabled=True,
)
fire.burst(1200)

game.run()
```

`Game.gpu_particles(...)` requires a 3D game. The emitter is rendered only by the opt-in Renderer2 path, so call `game.configure_renderer2(True, ...)` before running the game.

## CPU scheduling

`GPUParticleEmitter3D.update(dt)` performs constant-size scheduling work:

- accumulates at most one bounded render-frame delta
- converts emission rate into a bounded spawn count
- advances a deterministic ring cursor when the renderer consumes the frame
- records low-cost diagnostics

It does **not** own one Python object per GPU particle and does not scan the particle pool during updates.

The dedicated scheduler benchmark compares capacities of 128 and 65,536 particles. It is a regression contract for capacity independence, not an FPS claim.

## GPU simulation

The Renderer2 GPU VFX pass uses OpenGL 3.3 transform feedback:

1. particle state is stored in two interleaved buffers
2. one buffer is the source and one is the destination
3. the simulation vertex shader updates the pool in one transform-feedback pass
4. source and destination buffers swap after the step
5. a deterministic ring range is respawned for new emissions
6. previous position is retained in the same GPU state for trail generation

Simulation features include:

- point, box and sphere emission regions
- deterministic seeded velocity, lifetime and size randomization
- gravity and drag
- bounded lifetime and recycling
- color-over-life and size-over-life

## GPU rendering paths

The same transform-feedback state can feed multiple rendering paths without creating per-particle Python objects.

### Sprite particles

The default `GPUParticleRenderMode3D.SPRITE` path submits one `GL_POINTS` batch per emitter. It supports feathered circular point sprites and optional texture-backed sprites through `texture="path/to/particle.png"`.

The pass keeps a GPU texture cache and releases cached particle textures with the render pass lifecycle.

### Mesh particles

`GPUParticleRenderMode3D.MESH` submits the built-in particle mesh as an instanced draw. Per-particle size from the GPU state contributes to mesh scale, while `mesh_scale` controls the creator-facing world-space multiplier.

This milestone validates the built-in mesh-particle submission path. It does not claim arbitrary user-supplied particle meshes yet.

### Trails

`trail_enabled=True` adds a geometry-shader trail submission using current and previous GPU positions. Trail opacity is controlled with `trail_alpha_scale`, and trails use the same blend mode and HDR color curve as the emitter.

## HDR, blending and bloom

GPU VFX supports:

- additive blending for fire, sparks and energy
- alpha blending for smoke-like effects
- scene-depth testing without depth writes
- `emissive_strength` values above 1.0 for HDR effects
- participation in Renderer2 bloom

The pass runs **after decals and before bloom**, so bright effects are present in the HDR color target before bloom extraction.

## Diagnostics

`GPUParticleEmitter3D.diagnostics` reports CPU scheduling state:

- capacity
- queued emissions
- emitted/submitted totals
- bounded/recycled emissions
- simulation frame count
- current ring cursor

`Renderer2.gpu_particle_diagnostics` reports render-side work, including:

- visible GPU emitters
- particles processed by transform feedback
- particle instances submitted
- total particle draw calls
- sprite draw calls
- mesh draw calls
- trail draw calls

These counters describe work performed; they are not converted into synthetic FPS claims.

## Validation policy

Milestone #5 has a dedicated `GPU VFX 1.4 Validation` workflow. Its real rendering smoke uses software Mesa EGL with an OpenGL 3.3 context and validates the production GPU path rather than only shader compilation.

The smoke proves that:

- transform-feedback shaders compile and execute
- ping-pong simulation updates GPU buffers
- an exact burst creates the expected number of live GPU states
- textured sprite rendering modifies an HDR target
- HDR emissive output can exceed 1.0
- trail geometry executes from previous/current GPU positions
- instanced mesh particles render from the same simulation state
- render-side diagnostics match the submitted paths

The milestone gate also runs focused unit regressions, the capacity-independence scheduler benchmark, strict Ruff and compileall. Repository-wide CI, desktop export and existing physics/render/game regression workflows must remain green before merge.

## Compatibility

The existing `ParticleEmitter2D` path is untouched. `GPUParticleEmitter3D` is additive and requires Renderer2. Stable SwirEngine remains version 1.3.0 while the guarded 1.4 roadmap is under development.

## Milestone result

Milestone #5 passed its dedicated Mesa EGL/OpenGL 3.3 GPU gate, scheduler performance contract, full Python/OS CI matrix, Windows Python 3.14 native-wheel path, Desktop Export and existing Renderer2, physics, instancing, Demo Game 3D and Neon Snake 3D regressions. The synchronized SwirEngine 1.4 roadmap therefore advances to **5/10 = 50.0%**. The next guarded milestone is **Asset Pipeline 2.0**.
