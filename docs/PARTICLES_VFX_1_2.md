# Particle/VFX runtime (SwirEngine 1.2)

SwirEngine 1.2 expands `ParticleEmitter2D` without breaking the existing 1.x constructor. The emitter remains renderer-native and pooled, but now avoids scanning the full pool every frame and exposes creator-facing VFX controls.

## What changed

- sparse active-index updates instead of a full `max_particles` scan
- stable cached `children` tuple to avoid repeat allocations on renderer access
- point, box, circle and ring spawn regions
- color interpolation over lifetime
- size-over-life through `end_size_scale`
- linear drag, gravity, initial rotation and angular velocity
- deterministic seeded emission
- runtime `ParticleDiagnostics` for alive/capacity/emission/recycling/update-work counters

## Example

```python
from swirengine import Color
from swirengine.particles import ParticleEmissionShape2D, ParticleEmitter2D

sparks = ParticleEmitter2D(
    640,
    360,
    max_particles=2048,
    rate=240,
    lifetime=(0.25, 0.8),
    speed=(80, 280),
    angle=(15, 165),
    size=(2, 8),
    gravity=(0, -420),
    color=Color(1.0, 0.8, 0.15, 1.0),
    end_color=Color(1.0, 0.1, 0.0, 0.0),
    end_size_scale=0.15,
    drag=1.4,
    rotation=(0, 360),
    angular_velocity=(-480, 480),
    emission_shape=ParticleEmissionShape2D.RING,
    emission_size=(28, 28),
    seed=7,
)
```

Add the emitter to a scene/game as before. Its `children` stay renderer-native `Rectangle2D` objects.

## Performance contract

The old update loop visited every pooled particle each frame. The 1.2 runtime keeps an active-index list and visits only live particles. A regression test uses a pool of 10,000 particles with 8 live particles and requires exactly 8 update visits for the measured frame. This is a reduction in Python-side particle-update work for sparse pools, not a blanket FPS claim.

Pool recycling remains bounded by `max_particles`; when the cursor wraps, live slots are recycled rather than allocating new visual objects. `diagnostics.recycled_total` makes this visible during tuning.

## Compatibility

All pre-1.2 keyword arguments and defaults remain valid. With no new options supplied, particles still spawn at the emitter origin, retain their RGB values and fade to transparent over their lifetime.
