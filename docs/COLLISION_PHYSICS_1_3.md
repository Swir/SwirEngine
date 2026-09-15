# SwirEngine 1.3 — 3D Collision / Physics Foundation

SwirEngine 1.3 adds a Python-first 3D gameplay collision layer alongside the established 2D physics APIs. The goal of this milestone is deterministic creator-facing queries and a practical fixed-step arcade foundation without introducing a heavyweight native physics dependency or changing stable 1.x behavior.

## Public API

The root `swirengine` package and `swirengine.physics` expose:

- `AABB3D` — center-based axis-aligned box bounds
- `SphereBounds3D` — center/radius bounds
- `BoxCollider3D` and `SphereCollider3D`
- `CollisionWorld3D`
- `CollisionDiagnostics3D`
- `RaycastHit3D`
- `RigidBody3D`
- `PhysicsWorld3D`

The package version intentionally remains `1.2.0` while the 1.3 roadmap is in development.

## Live transform tracking

Colliders read their target transform when a query is performed. `Cube3D` works directly through `position` plus scalar `size`. Objects exposing a `position` and `scale` can also use inferred axis-aligned dimensions, but explicit `width`, `height` and `depth` are recommended for arbitrary mesh geometry because this foundation does not infer a transformed mesh hull.

```python
from swirengine import BoxCollider3D, CollisionWorld3D, Cube3D, Vec3

world = CollisionWorld3D(cell_size=4.0)
player = Cube3D(position=Vec3(0, 0, 0), size=1.0)
wall = Cube3D(position=Vec3(3, 0, 0), size=2.0)

player_hitbox = world.add(BoxCollider3D(player, tag="player", layer=1, mask=2))
world.add(BoxCollider3D(wall, tag="world", layer=2, mask=1))

player.position.x = 2.0
print(world.query(player_hitbox))
```

There is no manual transform-sync call to forget. The spatial index is rebuilt from live collider bounds for public queries so creator code stays correct when objects move.

## Broad phase and narrow phase

`CollisionWorld3D` uses a 3D spatial hash. Colliders are inserted into every occupied cell and local cell membership creates deterministic candidate sets before narrow-phase tests.

Supported narrow-phase combinations are:

- box vs box
- sphere vs sphere
- sphere vs box

Layers, masks and optional tags filter gameplay queries without forcing users to maintain separate collision worlds.

The regression contract includes 1,000 sparse box colliders and requires candidate-pair generation to stay at least 100x below brute-force all-pairs enumeration. `tools/benchmark_collision3d.py` expands that workload to 10,000 colliders. Its wall-clock output is diagnostic only and is not converted into an FPS claim.

## Creator queries

`CollisionWorld3D` provides:

```python
world.query(collider)
world.overlap_box(bounds)
world.overlap_sphere(center, radius)
world.query_point(point)
world.raycast(origin, direction, max_distance=...)
world.pairs()
```

Finite raycasts derive a world-space ray AABB and query only intersected spatial cells before exact ray/shape tests. The regression workload with 1,000 sparse colliders requires a short finite ray to visit fewer than ten candidates instead of scanning the full registry.

`RaycastHit3D` includes the hit collider, distance, world-space point and surface normal. Hits are returned in deterministic distance order.

## Fixed-step gameplay physics

`RigidBody3D` is an intentionally compact gameplay body for axis-aligned box colliders. It supports:

- `dynamic`, `kinematic` and `static` body types
- mass-aware forces and impulses
- gravity scale
- linear damping
- restitution
- axis-separated box collision response

`PhysicsWorld3D` owns bodies and their colliders and advances them with a fixed timestep. Variable render-frame `dt` is accumulated into deterministic substeps. `max_substeps` caps catch-up work to avoid an unbounded spiral after a stall; discarded excess time is visible through `dropped_time`, and the remaining accumulator is exposed as `interpolation_alpha` for creator-side interpolation.

```python
from swirengine import BoxCollider3D, Cube3D, PhysicsWorld3D, RigidBody3D, Vec3

player = Cube3D(position=Vec3(0, 4, 0), size=1)
physics = PhysicsWorld3D(gravity=Vec3(0, -9.81, 0), fixed_dt=1 / 60)
body = physics.add(RigidBody3D(player, BoxCollider3D(player)))
body.apply_impulse(3, 0, 0)

# Call once per game update; the world decides how many fixed substeps are needed.
physics.step(frame_dt)
```

## Deliberate boundaries

This milestone is a deterministic gameplay foundation, not a claim of a full general-purpose rigid-body solver.

- box colliders are axis-aligned; object visual rotation does not create an OBB
- `RigidBody3D` collision response currently resolves box-vs-box contacts only
- sphere colliders participate fully in overlap, pair and ray queries but are not yet rigid bodies
- there is no triangle-mesh collider, convex hull solver, joints/constraints, angular dynamics or continuous collision detection in this milestone
- arbitrary mesh local bounds are not inferred automatically; supply explicit collider dimensions when needed

These boundaries keep the public 1.x API additive and predictable while leaving clear extension points for later consciously planned physics work.

## Verification

Focused checks:

```bash
pytest tests/test_collision3d.py tests/test_rigidbody3d.py
ruff check src/swirengine/physics/collision3d.py src/swirengine/physics/rigidbody3d.py tests/test_collision3d.py tests/test_rigidbody3d.py examples/demo_collision3d_physics.py tools/benchmark_collision3d.py
python -m compileall -q src/swirengine/physics examples/demo_collision3d_physics.py tools/benchmark_collision3d.py
python tools/benchmark_collision3d.py
python examples/demo_collision3d_physics.py
```

The dedicated GitHub Actions workflow runs the focused regression/benchmark contract, while normal CI continues to validate the whole package, supported Python/platform matrix, packaging and representative 3D demos.
