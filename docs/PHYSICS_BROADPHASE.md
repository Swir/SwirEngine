# Physics broad-phase and creator queries

SwirEngine 1.1 keeps the existing `BoxCollider2D` / `CollisionWorld2D` API additive while replacing brute-force world scans for overlap and pair discovery with a deterministic spatial-hash broad phase.

## Spatial broad phase

`CollisionWorld2D(cell_size=128.0)` rebuilds its spatial index from live collider bounds before each public query. Moving a target therefore remains immediately visible to collision queries without a manual synchronization call.

```python
from swirengine import BoxCollider2D, CollisionWorld2D, Rectangle2D

world = CollisionWorld2D(cell_size=64)
player = world.add(BoxCollider2D(Rectangle2D(0, 0, 32, 32), tag="player"))
world.add(BoxCollider2D(Rectangle2D(24, 0, 32, 32), tag="enemy"))

for hit in world.query(player):
    print(hit.tag)
```

`query()` and `pairs()` generate local candidates from occupied cells and only then perform AABB narrow-phase tests. Layer/mask behavior and registry-order results remain compatible with the existing 1.x collision API.

## Region, point and ray queries

```python
from swirengine import AABB

nearby = world.overlap_aabb(AABB(0, 0, 256, 256), tag="enemy")
under_cursor = world.query_point(mouse_x, mouse_y)
hits = world.raycast(
    player_x,
    player_y,
    aim_x,
    aim_y,
    max_distance=1200,
    layer_mask=0b0010,
)

if hits:
    first = hits[0]
    print(first.collider.tag, first.distance, first.x, first.y)
```

Ray hits are sorted nearest-first and include world-space hit coordinates plus an AABB surface normal.

## Diagnostics and regression measurement

`world.diagnostics` reports collider count, occupied spatial cells, broad-phase candidate count, actual narrow-phase tests and hit count for the most recent operation.

The regression suite builds 1,000 sparse colliders. A brute-force pair pass would consider 499,500 pairs; the spatial broad phase must reduce candidates by at least two orders of magnitude in that deterministic scenario. This is a candidate/narrow-phase workload guarantee, not an FPS claim.

## Choosing a cell size

Use a cell size near the common size of interactive colliders. Very large cells increase candidate counts; extremely small cells make large colliders occupy more cells. The default `128.0` favors ordinary arcade/gameplay objects while allowing projects to tune the world explicitly.
