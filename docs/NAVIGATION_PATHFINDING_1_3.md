# SwirEngine 1.3 — Navigation & Pathfinding

This milestone adds deterministic Python-first navigation for both 2D games and ground-plane 3D games. It is intentionally additive to the stable 1.x API and lives in the dedicated `swirengine.navigation` creator namespace.

## Public API

- `NavigationGrid2D`
- `NavigationGrid3D`
- `NavigationPath2D`
- `NavigationPath3D`
- `NavigationAgent2D`
- `NavigationAgent3D`
- `NavigationDiagnostics`
- `NavigationProvider2D`
- `NavigationProvider3D`

The provider protocols are deliberate: creator-facing agents depend on a path-provider contract rather than the grid implementation itself. A future authored/generated navigation-mesh backend can implement the same provider interface without replacing agent gameplay code.

## Deterministic A*

`NavigationGrid2D` uses weighted A* with deterministic neighbor ordering and tie breaking. Cardinal and diagonal movement are supported. Diagonal corner cutting is disabled by default so agents cannot pass between two touching blocked cells.

Traversal costs must be finite and at least `1.0`, keeping the Manhattan/octile heuristics admissible. `set_cost()` can therefore model mud, roads, dangerous zones or preferred routes without changing the path-query API.

```python
from swirengine import Vec2
from swirengine.navigation import NavigationGrid2D

nav = NavigationGrid2D(64, 64, cell_size=32, diagonal=True)
nav.set_blocked((10, 12))
nav.set_cost((15, 8), 4.0)
path = nav.find_path(Vec2(32, 32), Vec2(1200, 600))
```

## Dynamic obstacles and route cache

Every obstacle/cost mutation increments the provider `revision` and clears the bounded LRU route cache. Stable repeated routes skip A* expansion entirely; agents with `auto_repath=True` automatically request a fresh route after a revision change.

The regression contract performs one cold 64x64 A* query followed by 999 identical requests and requires exactly one cache miss, 999 hits and zero node expansions on the final cached query.

`max_expansions=` is available for budgeted queries. Budget-limited results are not inserted into the stable route cache, so an intentionally aborted search cannot poison a later unrestricted request.

## 3D navigation plane

`NavigationGrid3D` maps the same deterministic search core onto the XZ plane. `origin.y` defines the navigation-plane height. This is suitable for arenas, top-down/third-person levels, RTS-style worlds and other mostly-grounded movement.

```python
from swirengine import Cube3D, Vec3
from swirengine.navigation import NavigationAgent3D, NavigationGrid3D

nav = NavigationGrid3D(128, 128, cell_size=1.0)
actor = Cube3D(position=Vec3(1, 0, 1))
agent = NavigationAgent3D(actor, nav, speed=4.0)
agent.set_destination(Vec3(40, 0, 25))

# in your update callback
agent.update(dt)
```

The agent changes X/Z only and preserves the target's current Y value. Vertical navigation, slopes and arbitrary navmesh polygons are intentionally not claimed by this milestone.

## Agent behavior

Both agents:

- keep a current destination and immutable path snapshot,
- consume movement using a distance budget so large `dt` values may cross several waypoints without one-waypoint-per-frame stalls,
- support configurable speed and stopping distance,
- auto-repath when provider revision changes,
- can be cleared without modifying the underlying grid.

The 2D agent supports targets exposing either `x/y` directly or `position.x/position.y`. The 3D agent supports `position.x/y/z` and plain `x/y/z` objects.

## Performance boundaries

This milestone focuses on algorithmic work reduction rather than FPS claims:

- repeated stable routes reuse a bounded revision-aware cache,
- obstacle changes invalidate only route-cache state rather than rebuilding a global graph,
- A* uses tuples/cell dictionaries only for the current query and does not allocate scene/render objects,
- the benchmark reports cold-search and 1,000 cached-query host timings as diagnostic data only.

Run:

```bash
pytest tests/test_navigation.py
python tools/benchmark_navigation.py
python examples/demo_navigation_pathfinding.py
```

## Current boundary / future navmesh route

This is a grid-navigation milestone, not a claim of a full polygonal navmesh system. Current limitations are explicit:

- 2D grid and 3D XZ-plane navigation only,
- no polygon navmesh generation, off-mesh links or crowd steering yet,
- no local avoidance/RVO,
- no heightfield slope traversal.

The `NavigationProvider2D` / `NavigationProvider3D` protocols are the compatibility seam for later authored or generated navmesh providers. Existing `NavigationAgent*` gameplay code will not need to be rewritten when such a provider is added.

The published package remains `1.2.0` until the complete 1.3 roadmap reaches 10/10 and passes the final release gate.
