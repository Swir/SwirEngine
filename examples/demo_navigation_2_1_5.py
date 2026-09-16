from __future__ import annotations

from swirengine.navigation15 import (
    NavigationAgent,
    NavigationAgentSettings,
    NavigationEdge,
    NavigationGraph,
    NavigationNode,
    NavigationQueryFilter,
    NavigationRuntime,
)


def build_graph() -> NavigationGraph:
    return NavigationGraph(
        (
            NavigationNode("start", (0.0, 0.0, 0.0)),
            NavigationNode("lower", (2.0, 0.0, -1.5)),
            NavigationNode("upper", (2.0, 0.0, 1.5)),
            NavigationNode("center", (4.0, 0.0, 0.0)),
            NavigationNode("exit", (6.0, 0.0, 0.0)),
        ),
        (
            NavigationEdge("start", "lower", area="hazard"),
            NavigationEdge("lower", "center", area="hazard"),
            NavigationEdge("start", "upper"),
            NavigationEdge("upper", "center"),
            NavigationEdge("center", "exit"),
        ),
    )


def main() -> None:
    graph = build_graph()
    runtime = NavigationRuntime(graph)
    filter_safe = NavigationQueryFilter(area_costs=(("hazard", 4.0),))

    scout = runtime.add_agent(
        NavigationAgent(
            "scout",
            (0.0, 0.0, 0.0),
            settings=NavigationAgentSettings(
                max_speed=2.4,
                radius=0.35,
                neighbor_distance=1.25,
                avoidance_strength=0.8,
            ),
        )
    )
    escort = runtime.add_agent(
        NavigationAgent(
            "escort",
            (0.0, 0.0, 0.35),
            settings=NavigationAgentSettings(
                max_speed=2.2,
                radius=0.35,
                neighbor_distance=1.25,
                avoidance_strength=0.8,
            ),
        )
    )

    scout_route = runtime.set_target(
        scout.agent_id,
        (6.0, 0.0, 0.0),
        query_filter=filter_safe,
    )
    escort_route = runtime.set_target(
        escort.agent_id,
        (6.0, 0.0, 0.0),
        query_filter=filter_safe,
    )
    if scout_route.path is None or escort_route.path is None:
        raise RuntimeError("demo navigation route unexpectedly missing")

    for _ in range(180):
        runtime.step(1.0 / 60.0)

    diagnostics = runtime.diagnostics()
    print("SwirEngine 1.5 Navigation 2.0 demo")
    print("scout route:", " -> ".join(scout_route.path.node_ids))
    print("escort route:", " -> ".join(escort_route.path.node_ids))
    print(
        "agents:",
        diagnostics.agent_count,
        "arrived:",
        diagnostics.arrived_agents,
        "moving:",
        diagnostics.moving_agents,
    )
    print(
        "queries:",
        diagnostics.query_count,
        "expanded:",
        diagnostics.expanded_nodes,
        "peak avoidance candidates:",
        diagnostics.peak_avoidance_candidate_checks,
    )
    print("runtime fingerprint:", runtime.state_fingerprint())


if __name__ == "__main__":
    main()
