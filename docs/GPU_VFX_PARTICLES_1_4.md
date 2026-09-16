# SwirEngine 1.4 — GPU VFX + Particle Power

This document tracks milestone #5 of the guarded SwirEngine 1.4 roadmap. The milestone is still in development and **does not increase the 1.4 roadmap beyond 4/10 = 40.0% until its full validation gate is complete**.

## Goal

SwirEngine already has a production-friendly pooled `ParticleEmitter2D`. Milestone #5 adds a separate GPU-oriented path for high-count 3D effects without changing that stable API.

The first production path is `GPUParticleEmitter3D` + `Renderer2`. Particle position, velocity, age, lifetime and recycling live in ping-pong GPU buffers. Python only schedules elapsed time and emission batches; it does not iterate through every GPU particle each frame.

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
)
fire.burst(1200)

game.run()
```

`Game.gpu_particles(...)` requires a 3D game. The emitter is rendered only by the opt-in Renderer2 path, so call `game.configure_renderer2(True, ...)` before running the game.

## Current GPU architecture

### CPU scheduling

`GPUParticleEmitter3D.update(dt)` performs constant-size scheduling work:

- accumulates at most one render-frame delta
- converts emission rate into a bounded spawn count
- advances one ring cursor when the renderer consumes the frame
- records low-cost diagnostics

It does **not** own one Python object per GPU particle and does not scan the particle pool during updates.

### GPU simulation

The Renderer2 GPU VFX pass uses OpenGL 3.3 transform feedback:

1. particle state is stored in two interleaved buffers
2. one buffer is the source and one is the destination
3. the simulation vertex shader updates every particle in one transform-feedback pass
4. the source/destination buffers swap after the step
5. a deterministic ring range is respawned for new emissions

The state currently contains position + age, velocity + lifetime and per-particle size metadata.

### GPU rendering

Each emitter is submitted as one `GL_POINTS` batch. The vertex shader computes color/size over lifetime, and the fragment shader turns each point into a feathered circular sprite using `gl_PointCoord`.

The pass supports:

- additive blending for fire, sparks and energy
- alpha blending for smoke-like effects
- scene-depth testing without depth writes
- point, box and sphere emission shapes
- deterministic seeded velocity/lifetime/size randomization
- gravity and drag
- color-over-life and size-over-life

The pass runs **after decals and before bloom**, allowing bright additive effects to participate in Renderer2 HDR bloom.

## Diagnostics

`GPUParticleEmitter3D.diagnostics` reports CPU scheduling state:

- capacity
- queued emissions
- emitted/submitted totals
- bounded/recycled emissions
- simulation frame count
- current ring cursor

`Renderer2.gpu_particle_diagnostics` reports render-side work:

- visible GPU emitters
- particles processed by transform feedback
- particle instances submitted for drawing
- particle draw calls

These counters describe work performed; they are not converted into synthetic FPS claims.

## Validation policy

Milestone #5 has a dedicated `GPU VFX 1.4 Validation` workflow. The required real-GPU-path smoke uses a software Mesa EGL OpenGL 3.3 context and must prove that:

- the transform-feedback shaders compile
- the ping-pong simulation executes
- an exact burst creates the expected number of live GPU states
- one emitter uses one particle draw call
- the particle draw modifies an HDR render target
- unit tests, strict Ruff and compileall remain green

Repository-wide CI, desktop export and existing game/render regression workflows must also remain green before milestone completion.

## Compatibility

The existing `ParticleEmitter2D` path is untouched. `GPUParticleEmitter3D` is additive and requires Renderer2. Stable SwirEngine remains version 1.3.0 while the guarded 1.4 roadmap is under development.

## Remaining milestone work

Before this milestone can become 5/10 = 50.0%, the branch still needs the complete GPU gate plus the remaining VFX scope, including stronger diagnostics/resource lifecycle coverage, trails, texture-backed sprite particles, a mesh-particle submission path, performance contracts, final documentation synchronization and full repository regressions.
