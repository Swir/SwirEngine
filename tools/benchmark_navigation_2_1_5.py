from __future__ import annotations

from time import perf_counter

from swirengine.navigation15 import (
    NavigationAgent,
    NavigationAgentSettings,
    NavigationEdge,
    NavigationGraph,
    NavigationNode,
    NavigationRuntime,
)

GRID = 20
QUERY_COUNT = 80
AGENT_COUNT = 128
STEPS = 90
BUDGET_SECONDS = 2.0


def grid_graph(size: int = GRID) -> NavigationGraph:
    nodes = tuple(
        NavigationNode(f"{x}:{z}", (float(x), 0.0, float(z)))
        for z in range(size)
        for x in range(size)
    )
    edges = []
    for z in range(size):
        for x in range(size):
            if x + 1 < size:
                edges.append(NavigationEdge(f"{x}:{z}", f"{x + 1}:{z}"))
            if z + 1 < size:
                edges.append(NavigationEdge(f"{x}:{z}", f"{x}:{z + 1}"))
    return NavigationGraph(nodes, tuple(edges))


def main() -> None:
    graph = grid_graph()
    runtime = NavigationRuntime(graph)

    started = perf_counter()
    for index in range(QUERY_COUNT):
        offset = index % GRID
        result = runtime.query_path(
            (0.0, 0.0, float(offset)),
            (float(GRID - 1), 0.0, float(GRID - 1 - offset)),
        )
        if result.path is None:
            raise RuntimeError("benchmark route unexpectedly missing")

    for index in range(AGENT_COUNT):
        x = float((index * 5) % GRID)
        z = float((index * 11) % GRID)
        agent = NavigationAgent(
            f"agent-{index:03d}",
            (x, 0.0, z),
            settings=NavigationAgentSettings(
                radius=0.3,
                max_speed=3.0,
                neighbor_distance=1.5,
                avoidance_strength=0.8,
                max_neighbors=6,
            ),
        )
        runtime.add_agent(agent)
        target = (
            float(GRID - 1) - x,
            0.0,
            float(GRID - 1) - z,
        )
        result = runtime.set_target(agent.agent_id, target)
        if result.path is None:
            raise RuntimeError("benchmark agent route unexpectedly missing")

    for _ in range(STEPS):
        runtime.step(1.0 / 60.0)

    elapsed = perf_counter() - started
    diagnostics = runtime.diagnostics()
    print(
        f"{QUERY_COUNT + AGENT_COUNT} navigation queries + "
        f"{AGENT_COUNT} agents x {STEPS} steps: {elapsed:.6f}s "
        f"(budget {BUDGET_SECONDS}s)"
    )
    print(
        f"expanded={diagnostics.expanded_nodes} "
        f"peak_candidates={diagnostics.peak_avoidance_candidate_checks} "
        f"fingerprint={runtime.state_fingerprint()[:16]}"
    )
    if elapsed > BUDGET_SECONDS:
        raise SystemExit(
            f"navigation workload exceeded budget: {elapsed:.6f}s > {BUDGET_SECONDS}s"
        )


if __name__ == "__main__":
    main()
