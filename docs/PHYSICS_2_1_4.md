# Physics 2.0 — SwirEngine 1.4

SwirEngine 1.4 milestone #2 adds an **additive production physics layer** without changing the established 1.x `RigidBody3D` / `PhysicsWorld3D` behavior.

The new API lives in `swirengine.physics.dynamics3d` and reuses the existing live targets plus `BoxCollider3D` / `SphereCollider3D` types.

## Core types

- `PhysicsMaterial3D` — friction and restitution.
- `PhysicsBody3D` — dynamic, kinematic or static body with forces, impulses, damping, optional continuous motion and sleeping.
- `Contact3D` — deterministic narrow-phase contact with point, normal and penetration.
- `SweepHit3D` — normalized time-of-impact result for box/sphere sweeps.
- `DistanceJoint3D` — positional distance constraint with stiffness and damping.
- `PhysicsScene3D` — fixed-step Physics 2.0 simulation.
- `PhysicsBackend3D` — runtime protocol for future alternative/back-end integrations.
- `PhysicsDiagnostics3D` — broad phase, contact, solver, sweep, joint and sleeping diagnostics.

## Contact response

Physics 2.0 generates contacts for:

- box / box
- sphere / sphere
- sphere / box

The impulse solver applies:

- penetration correction with configurable slop and correction percentage,
- normal impulses,
- restitution,
- tangent friction impulses.

Contacts and candidate pairs are deterministic for the same body order and transforms.

## Shared spatial broad phase

The legacy arcade path may rebuild collision broad-phase data for individual body queries. `PhysicsScene3D` instead rebuilds one spatial-hash index per fixed substep, deduplicates candidate pairs and then performs narrow-phase tests only for those candidates.

The benchmark in `tools/benchmark_physics2_1_4.py` verifies that a sparse thousands-of-bodies workload produces dramatically fewer candidate pairs than a naive all-pairs scan. Timing output is diagnostic only and is not presented as an FPS claim.

## Shape sweeps and continuous-motion foundation

`PhysicsScene3D.sweep_box()` uses an expanded-AABB time-of-impact test. `sweep_sphere()` uses a conservative sphere-vs-expanded-AABB test. Both return the earliest deterministic `SweepHit3D`.

Bodies created with `continuous=True` sweep their intended fixed-step displacement before committing movement. This provides a practical continuous-collision foundation for fast objects and prevents the validated thin-wall tunneling workload.

The sphere sweep is intentionally conservative for non-box target shapes in this milestone; future backends can provide exact convex sweeps behind the same public protocol.

## Sleeping

Dynamic bodies expose configurable speed/time thresholds. Stable low-speed bodies may enter a sleeping state, skipping force/position integration until an explicit external force, impulse or transform/velocity change wakes them.

Sleeping is observable through `PhysicsBody3D.is_sleeping` and `PhysicsDiagnostics3D.sleeping_bodies`.

## Constraints

`DistanceJoint3D` keeps two bodies near a target separation using deterministic positional correction plus optional relative-velocity damping. The solver runs a bounded configurable number of joint iterations per fixed step.

## Fixed step and bounded work

`PhysicsScene3D` retains SwirEngine's fixed-step contract:

- configurable `fixed_dt`,
- bounded `max_substeps`,
- dropped-time diagnostics,
- interpolation alpha,
- fixed solver and joint iteration counts.

This keeps simulation work bounded under frame stalls rather than allowing unbounded catch-up.

## Compatibility

Existing code using `RigidBody3D` and `PhysicsWorld3D` remains valid and unchanged. Projects opt into Physics 2.0 by constructing `PhysicsBody3D` and adding it to `PhysicsScene3D`.

```python
from swirengine.physics import BoxCollider3D
from swirengine.physics.dynamics3d import PhysicsBody3D, PhysicsMaterial3D, PhysicsScene3D

scene = PhysicsScene3D()
body = PhysicsBody3D(
    player,
    BoxCollider3D(player, width=1, height=2, depth=1),
    material=PhysicsMaterial3D(friction=0.8, restitution=0.1),
    continuous=True,
)
scene.add(body)
scene.step(dt)
```

See `examples/demo_physics2_contacts.py` for contacts, a distance joint and a high-speed continuous body.
