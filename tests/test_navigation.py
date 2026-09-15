import pytest

from swirengine import Cube3D, Rectangle2D, Vec2, Vec3
from swirengine.navigation import (
    NavigationAgent2D,
    NavigationAgent3D,
    NavigationGrid2D,
    NavigationGrid3D,
    NavigationProvider2D,
)


def test_grid2d_finds_deterministic_path_around_blockers():
    grid = NavigationGrid2D(6, 5, diagonal=False)
    grid.set_blocked_many(((2, 0), (2, 1), (2, 2), (2, 4)))

    path = grid.find_path(Vec2(0.1, 0.1), Vec2(5.1, 0.1))

    assert path is not None
    assert path.cells[0] == (0, 0)
    assert path.cells[-1] == (5, 0)
    assert (2, 3) in path.cells
    assert path.points[0] == Vec2(0.1, 0.1)
    assert path.points[-1] == Vec2(5.1, 0.1)


def test_weighted_cells_choose_cheaper_route():
    grid = NavigationGrid2D(3, 2, diagonal=False)
    grid.set_cost((1, 0), 100.0)

    path = grid.find_path(Vec2(0.1, 0.1), Vec2(2.1, 0.1))

    assert path is not None
    assert (1, 0) not in path.cells
    assert path.cost == pytest.approx(4.0)


def test_diagonal_navigation_prevents_corner_cutting_by_default():
    blocked = ((1, 0), (0, 1))
    safe = NavigationGrid2D(3, 3, diagonal=True)
    safe.set_blocked_many(blocked)
    permissive = NavigationGrid2D(3, 3, diagonal=True, allow_corner_cutting=True)
    permissive.set_blocked_many(blocked)

    assert safe.find_path(Vec2(0.1, 0.1), Vec2(1.1, 1.1)) is None
    assert permissive.find_path(Vec2(0.1, 0.1), Vec2(1.1, 1.1)) is not None


def test_route_cache_avoids_repeating_astar_expansion():
    grid = NavigationGrid2D(64, 64, diagonal=True)
    start = Vec2(0.1, 0.1)
    goal = Vec2(63.1, 63.1)

    first = grid.find_path(start, goal)
    assert first is not None
    first_expanded = grid.diagnostics.expanded_nodes
    assert first_expanded > 0

    for _ in range(999):
        assert grid.find_path(start, goal) is not None

    diagnostics = grid.diagnostics
    assert diagnostics.searches == 1000
    assert diagnostics.cache_misses == 1
    assert diagnostics.cache_hits == 999
    assert diagnostics.expanded_nodes == 0
    assert diagnostics.queued_nodes == 0


def test_dynamic_obstacle_revision_invalidates_cached_route():
    grid = NavigationGrid2D(8, 3, diagonal=False)
    start = Vec2(0.1, 1.1)
    goal = Vec2(7.1, 1.1)

    direct = grid.find_path(start, goal)
    assert direct is not None
    original_revision = grid.revision
    grid.find_path(start, goal)
    assert grid.diagnostics.cache_hits == 1

    grid.set_blocked((3, 1))
    assert grid.revision == original_revision + 1
    rerouted = grid.find_path(start, goal)

    assert rerouted is not None
    assert (3, 1) not in rerouted.cells
    assert grid.diagnostics.cache_misses == 2


def test_failed_paths_are_cached_and_revision_safe():
    grid = NavigationGrid2D(3, 1, diagonal=False)
    grid.set_blocked((1, 0))

    assert grid.find_path(Vec2(0.1, 0.1), Vec2(2.1, 0.1)) is None
    assert grid.find_path(Vec2(0.1, 0.1), Vec2(2.1, 0.1)) is None
    assert grid.diagnostics.cache_hits == 1

    grid.set_blocked((1, 0), False)
    assert grid.find_path(Vec2(0.1, 0.1), Vec2(2.1, 0.1)) is not None


def test_max_expansion_budget_can_abort_expensive_query_without_poisoning_cache():
    grid = NavigationGrid2D(20, 20, diagonal=False)

    assert grid.find_path(Vec2(0.1, 0.1), Vec2(19.1, 19.1), max_expansions=1) is None
    assert grid.find_path(Vec2(0.1, 0.1), Vec2(19.1, 19.1)) is not None
    assert grid.diagnostics.cache_misses == 2


def test_grid_rejects_invalid_cells_costs_and_options():
    with pytest.raises(ValueError, match="width and height"):
        NavigationGrid2D(0, 1)
    with pytest.raises(ValueError, match="cell_size"):
        NavigationGrid2D(1, 1, cell_size=0)
    with pytest.raises(ValueError, match="cache_size"):
        NavigationGrid2D(1, 1, cache_size=0)

    grid = NavigationGrid2D(2, 2)
    with pytest.raises(ValueError, match="outside"):
        grid.set_blocked((2, 0))
    with pytest.raises(ValueError, match=">= 1.0"):
        grid.set_cost((0, 0), 0.5)
    with pytest.raises(ValueError, match="max_expansions"):
        grid.find_path(Vec2(0.1, 0.1), Vec2(1.1, 1.1), max_expansions=0)


def test_grid3d_maps_xz_plane_and_preserves_navigation_height():
    grid = NavigationGrid3D(5, 5, cell_size=2.0, origin=Vec3(-4, 3, -4), diagonal=False)
    grid.set_blocked((2, 1))

    path = grid.find_path(Vec3(-3.5, 10, -3.5), Vec3(3.5, -5, 3.5))

    assert path is not None
    assert path.cells[0] == (0, 0)
    assert path.cells[-1] == (3, 3)
    assert all(point.y == 3 for point in path.points)
    assert (2, 1) not in path.cells


def test_navigation_provider_protocol_is_future_navmesh_friendly():
    grid = NavigationGrid2D(4, 4)
    assert isinstance(grid, NavigationProvider2D)


def test_agent2d_follows_path_and_auto_repaths_after_revision_change():
    target = Rectangle2D(0.1, 0.1, 1, 1)
    grid = NavigationGrid2D(6, 3, diagonal=False)
    agent = NavigationAgent2D(target, grid, speed=4.0, stopping_distance=0.0)

    assert agent.set_destination(Vec2(5.1, 0.1))
    agent.update(0.5)
    assert target.x > 0.1

    grid.set_blocked((3, 0))
    previous_revision = grid.revision
    agent.update(0.5)
    assert grid.revision == previous_revision
    assert agent.path is not None
    assert (3, 0) not in agent.path.cells


def test_agent3d_moves_on_xz_plane_without_changing_target_height():
    cube = Cube3D(position=Vec3(0.1, 7.0, 0.1))
    grid = NavigationGrid3D(8, 2, diagonal=False)
    agent = NavigationAgent3D(cube, grid, speed=10.0, stopping_distance=0.0)

    assert agent.set_destination(Vec3(6.1, 99.0, 0.1))
    agent.update(0.25)

    assert cube.position.x > 0.1
    assert cube.position.y == pytest.approx(7.0)
    assert cube.position.z >= 0.1
