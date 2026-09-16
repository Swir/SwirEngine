from __future__ import annotations

import pytest

from swirengine.navigation15 import (
    NavPoint,
    NavigationAgent,
    NavigationAgentSettings,
    NavigationEdge,
    NavigationGraph,
    NavigationNeighbor,
    NavigationNode,
    NavigationQueryFilter,
    NavigationRuntime,
    nav_point,
)


def sample_graph() -> NavigationGraph:
    return NavigationGraph(
        (
            NavigationNode("a", (0.0, 0.0, 0.0)),
            NavigationNode("b", (1.0, 0.0, 0.0)),
            NavigationNode("c", (0.0, 0.0, 2.0)),
            NavigationNode("d", (2.0, 0.0, 0.0)),
        ),
        (
            NavigationEdge("a", "b", area="mud"),
            NavigationEdge("b", "d", area="mud"),
            NavigationEdge("a", "c"),
            NavigationEdge("c", "d"),
        ),
    )


def line_graph(count: int = 6) -> NavigationGraph:
    nodes = tuple(
        NavigationNode(f"n{index}", (float(index), 0.0, 0.0))
        for index in range(count)
    )
    edges = tuple(
        NavigationEdge(f"n{index}", f"n{index + 1}")
        for index in range(count - 1)
    )
    return NavigationGraph(nodes, edges)


def test_point_validation_and_vector_contract() -> None:
    point = nav_point((3.0, 4.0, 0.0))
    assert point.length == pytest.approx(5.0)
    assert point.normalized().length == pytest.approx(1.0)
    assert point.distance_to(NavPoint(0.0, 0.0, 0.0)) == pytest.approx(5.0)
    with pytest.raises(ValueError):
        nav_point((1.0, 2.0))
    with pytest.raises(ValueError):
        NavPoint(float("nan"), 0.0, 0.0)


def test_graph_prefers_lowest_cost_and_area_costs_can_reroute() -> None:
    graph = sample_graph()
    direct = graph.find_path("a", "d")
    assert direct.path is not None
    assert direct.path.node_ids == ("a", "b", "d")
    assert direct.path.total_cost == pytest.approx(2.0)

    rerouted = graph.find_path(
        "a",
        "d",
        query_filter=NavigationQueryFilter(area_costs=(("mud", 10.0),)),
    )
    assert rerouted.path is not None
    assert rerouted.path.node_ids == ("a", "c", "d")
    assert rerouted.path.total_cost > direct.path.total_cost


def test_query_filters_block_nodes_edges_and_areas() -> None:
    graph = sample_graph()
    blocked_node = graph.find_path(
        "a",
        "d",
        query_filter=NavigationQueryFilter(blocked_nodes=frozenset({"b"})),
    )
    assert blocked_node.path is not None
    assert blocked_node.path.node_ids == ("a", "c", "d")

    blocked_edge = graph.find_path(
        "a",
        "d",
        query_filter=NavigationQueryFilter(
            blocked_edges=frozenset({("a", "c"), ("b", "d")})
        ),
    )
    assert blocked_edge.path is None

    only_mud = graph.find_path(
        "a",
        "d",
        query_filter=NavigationQueryFilter(allowed_areas=frozenset({"mud"})),
    )
    assert only_mud.path is not None
    assert only_mud.path.node_ids == ("a", "b", "d")


def test_position_query_snaps_and_preserves_requested_endpoints() -> None:
    graph = line_graph(4)
    result = graph.query_path((-0.25, 0.0, 0.0), (3.25, 0.0, 0.0))
    assert result.path is not None
    assert result.path.points[0] == NavPoint(-0.25, 0.0, 0.0)
    assert result.path.points[-1] == NavPoint(3.25, 0.0, 0.0)
    assert result.diagnostics.start_node == "n0"
    assert result.diagnostics.goal_node == "n3"
    assert result.diagnostics.start_snap_distance == pytest.approx(0.25)
    assert result.diagnostics.goal_snap_distance == pytest.approx(0.25)


def test_position_query_respects_snap_limit() -> None:
    graph = line_graph(3)
    result = graph.query_path(
        (100.0, 0.0, 0.0),
        (2.0, 0.0, 0.0),
        max_snap_distance=1.0,
    )
    assert result.path is None
    assert result.diagnostics.start_node is None
    assert result.diagnostics.goal_node == "n2"


def test_graph_validation_and_fingerprint_are_deterministic() -> None:
    nodes = (
        NavigationNode("a", (0.0, 0.0, 0.0)),
        NavigationNode("b", (1.0, 0.0, 0.0)),
        NavigationNode("c", (2.0, 0.0, 0.0)),
    )
    first = NavigationGraph(
        nodes,
        (
            NavigationEdge("a", "b"),
            NavigationEdge("b", "c", cost=2.0, area="stairs"),
        ),
    )
    second = NavigationGraph(
        reversed(nodes),
        (
            NavigationEdge("b", "c", cost=2.0, area="stairs"),
            NavigationEdge("a", "b"),
        ),
    )
    assert first.fingerprint() == second.fingerprint()
    with pytest.raises(ValueError):
        NavigationGraph((nodes[0], nodes[0]), ())
    with pytest.raises(KeyError):
        NavigationGraph(nodes, (NavigationEdge("a", "missing"),))


def test_agent_consumes_multiple_waypoints_without_overshoot() -> None:
    agent = NavigationAgent(
        "runner",
        (0.0, 0.0, 0.0),
        settings=NavigationAgentSettings(max_speed=4.0, arrival_tolerance=0.001),
    )
    agent.set_path(
        (
            (0.0, 0.0, 0.0),
            (1.0, 0.0, 0.0),
            (2.0, 0.0, 0.0),
            (3.0, 0.0, 0.0),
        )
    )
    agent.step(0.5)
    assert agent.position == NavPoint(2.0, 0.0, 0.0)
    assert not agent.arrived
    agent.step(0.25)
    assert agent.position == NavPoint(3.0, 0.0, 0.0)
    assert agent.arrived
    assert agent.velocity == NavPoint(0.0, 0.0, 0.0)


def test_avoidance_is_deterministic_and_speed_bounded() -> None:
    settings = NavigationAgentSettings(
        radius=0.5,
        max_speed=3.0,
        neighbor_distance=2.0,
        avoidance_strength=1.0,
    )
    agent = NavigationAgent("a", (0.0, 0.0, 0.0), settings=settings)
    agent.set_path(((0.0, 0.0, 0.0), (10.0, 0.0, 0.0)))
    neighbor = NavigationNeighbor("b", (0.0, 0.0, 0.0), radius=0.5)
    first = agent.compute_velocity((neighbor,))
    second = agent.compute_velocity((neighbor,))
    assert first == second
    assert first.length <= settings.max_speed + 1e-9
    assert agent.avoidance_neighbors == 1


def test_arrived_agent_does_not_drift_due_to_avoidance() -> None:
    agent = NavigationAgent("idle", (0.0, 0.0, 0.0))
    neighbor = NavigationNeighbor("other", (0.0, 0.0, 0.0))
    before = agent.position
    agent.step(1.0, (neighbor,))
    assert agent.position == before
    assert agent.velocity == NavPoint(0.0, 0.0, 0.0)


def test_runtime_queries_assign_paths_and_track_diagnostics() -> None:
    runtime = NavigationRuntime(line_graph(8))
    runtime.add_agent(
        NavigationAgent(
            "agent",
            (0.0, 0.0, 0.0),
            settings=NavigationAgentSettings(max_speed=5.0),
        )
    )
    result = runtime.set_target("agent", (7.0, 0.0, 0.0))
    assert result.path is not None
    for _ in range(120):
        runtime.step(1.0 / 60.0)
    diagnostics = runtime.diagnostics()
    assert diagnostics.query_count == 1
    assert diagnostics.failed_queries == 0
    assert diagnostics.expanded_nodes > 0
    assert diagnostics.arrived_agents == 1
    assert diagnostics.total_remaining_distance == pytest.approx(0.0)


def test_runtime_spatial_broadphase_avoids_naive_all_pairs() -> None:
    runtime = NavigationRuntime(line_graph(2))
    for index in range(64):
        runtime.add_agent(
            NavigationAgent(
                f"a{index:02d}",
                (float(index) * 10.0, 0.0, 0.0),
                settings=NavigationAgentSettings(neighbor_distance=1.0),
            )
        )
    runtime.step(1.0 / 60.0)
    assert runtime.last_avoidance_candidate_checks == 0


def test_runtime_state_fingerprint_is_reproducible() -> None:
    def build() -> NavigationRuntime:
        runtime = NavigationRuntime(line_graph(5))
        runtime.add_agent(
            NavigationAgent(
                "agent",
                (0.0, 0.0, 0.0),
                settings=NavigationAgentSettings(max_speed=2.0),
            )
        )
        runtime.set_target("agent", (4.0, 0.0, 0.0))
        for _ in range(30):
            runtime.step(1.0 / 60.0)
        return runtime

    assert build().state_fingerprint() == build().state_fingerprint()


def test_invalid_runtime_inputs_are_rejected() -> None:
    with pytest.raises(ValueError):
        NavigationEdge("a", "b", cost=-1.0)
    with pytest.raises(ValueError):
        NavigationQueryFilter(area_costs=(("mud", 0.0),))
    with pytest.raises(ValueError):
        NavigationAgentSettings(max_speed=-1.0)
    with pytest.raises(ValueError):
        NavigationAgent("a", (0.0, 0.0, 0.0)).step(-0.1)
