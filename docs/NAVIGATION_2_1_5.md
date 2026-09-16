# Navigation 2.0 — SwirEngine 1.5

SwirEngine 1.5 adds an opt-in, renderer-independent navigation runtime in `swirengine.navigation15`.
It is intentionally a portable waypoint-graph layer rather than a claim of automatic navmesh generation.
The goal is to provide reliable runtime queries, path-following agents, bounded local avoidance and
scalable diagnostics while preserving all stable 1.x APIs.

## Graph and query model

A `NavigationGraph` is built from validated `NavigationNode` and `NavigationEdge` records. Nodes carry
finite 3D positions. Edges may be bidirectional or directed, enabled or disabled, assigned to a named
area, and may either use their geometric distance as traversal cost or specify an explicit
non-negative cost.

```python
from swirengine.navigation15 import NavigationEdge, NavigationGraph, NavigationNode

graph = NavigationGraph(
    (
        NavigationNode("spawn", (0.0, 0.0, 0.0)),
        NavigationNode("hall", (4.0, 0.0, 0.0)),
        NavigationNode("exit", (8.0, 0.0, 0.0)),
    ),
    (
        NavigationEdge("spawn", "hall"),
        NavigationEdge("hall", "exit"),
    ),
)
```

`find_path(start_node, goal_node)` performs a deterministic A*-style graph query. Adjacency is sorted,
queue tie breaking includes the stable node id, and the heuristic is derived conservatively from the
lowest edge-cost/distance ratio so explicit cheap edges do not make it overestimate the remaining
cost.

`query_path(start_position, goal_position)` first snaps each requested world position to the nearest
allowed node, runs the graph query and then preserves the exact requested start and goal as path
endpoints. `max_snap_distance` can reject requests that are too far away from the authored graph.

## Dynamic query filters

`NavigationQueryFilter` keeps common runtime restrictions outside the immutable graph definition:

- blocked node ids;
- blocked directed edge pairs;
- an optional allowed-area set;
- positive per-area cost multipliers.

```python
from swirengine.navigation15 import NavigationQueryFilter

safe_route = NavigationQueryFilter(
    blocked_nodes=frozenset({"collapsed_bridge"}),
    area_costs=(("hazard", 4.0), ("mud", 1.5)),
)

result = graph.query_path(
    player_position,
    destination,
    query_filter=safe_route,
)
```

This lets games close doors, discourage dangerous terrain or temporarily exclude regions without
rebuilding the authored graph.

## Path-following agents

`NavigationAgent` consumes a `NavigationPath` or an explicit point sequence. The follower uses a
bounded movement budget so one large frame may pass through multiple short waypoints without
overshooting or accumulating a stop at every node.

```python
from swirengine.navigation15 import NavigationAgent, NavigationAgentSettings

agent = NavigationAgent(
    "worker-01",
    player_position,
    settings=NavigationAgentSettings(max_speed=3.5),
)
agent.set_path(result.path)
agent.step(1 / 60)
```

`arrival_tolerance` controls waypoint completion, `remaining_distance()` exposes useful gameplay and
diagnostic information, and the final velocity is reset once the route is complete.

## Deterministic local avoidance

Agents can incorporate nearby `NavigationNeighbor` snapshots when computing velocity. The avoidance
contract is deliberately conservative: it is bounded local separation, not an ORCA/RVO claim.
Nearby agents contribute a deterministic separation vector ordered by distance and id, capped by
`max_neighbors`, and the final velocity remains bounded by `max_speed`.

`NavigationRuntime.step()` snapshots every registered agent before advancing any of them. This keeps
avoidance independent of dictionary/update order inside a frame. For larger crowds the runtime uses
a spatial grid so agents only inspect nearby buckets instead of blindly performing an all-pairs scan.
The number of broadphase candidate checks is included in diagnostics to make scaling regressions
visible.

## Runtime orchestration

`NavigationRuntime` combines path queries and agent management:

```python
from swirengine.navigation15 import NavigationRuntime

runtime = NavigationRuntime(graph)
runtime.add_agent(agent)
route = runtime.set_target("worker-01", destination, query_filter=safe_route)

for _ in range(60):
    runtime.step(1 / 60)
```

`set_target()` queries from the agent's current world position and installs the path only when the
query succeeds. Failed queries clear the current route rather than leaving a stale destination active.

## Diagnostics and reproducibility

Every path query returns `NavigationQueryDiagnostics`, including snapped nodes, snap distances,
expanded/visited node counts, queue pushes, path-node count and final traversal cost.

`NavigationRuntimeDiagnostics` aggregates:

- successful/failed query counts;
- total expanded graph nodes;
- agent, moving and arrived counts;
- total remaining path distance;
- simulation step count;
- current and peak spatial-broadphase candidate checks.

The graph and runtime expose SHA-256 fingerprints over canonical portable state. These are intended for
CI, replay/regression tests and headless server diagnostics rather than cryptographic authentication.

## Compatibility

Navigation 2.0 is additive through `swirengine.navigation15`. It does not change stable root imports,
scene transforms, character controllers or the released 1.x APIs. The published package remains
SwirEngine 1.4.0 while the 1.5 roadmap is in development.

This milestone does **not** claim automatic navmesh baking, polygon-mesh generation, ORCA/RVO crowd
simulation or dynamic obstacle carving. Those can be added later as separate adapters or higher-level
systems without weakening this runtime contract.

## Validation

The dedicated Navigation 2.0 gate targets Python 3.10, 3.13 and 3.14 and covers:

- finite point/vector contracts and invalid input rejection;
- deterministic cheapest-path selection and area-cost rerouting;
- blocked nodes/edges and area filtering;
- nearest-node snapping and exact world endpoint preservation;
- graph validation and deterministic graph fingerprints;
- multi-waypoint following without overshoot;
- bounded deterministic local avoidance;
- no drift after arrival;
- runtime target assignment and diagnostics;
- spatial broadphase behavior on separated crowds;
- reproducible runtime fingerprints;
- a 400-node graph query + 128-agent crowd workload;
- the runnable Navigation 2.0 demo.

Run locally:

```bash
pytest tests/test_navigation_2_1_5.py
ruff check src/swirengine/navigation15.py tests/test_navigation_2_1_5.py \
  tools/benchmark_navigation_2_1_5.py examples/demo_navigation_2_1_5.py
python -m compileall -q src/swirengine/navigation15.py tests/test_navigation_2_1_5.py \
  tools/benchmark_navigation_2_1_5.py examples/demo_navigation_2_1_5.py
python tools/benchmark_navigation_2_1_5.py
python examples/demo_navigation_2_1_5.py
```
