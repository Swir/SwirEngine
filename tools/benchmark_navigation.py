from __future__ import annotations

from time import perf_counter

from swirengine import Vec2
from swirengine.navigation import NavigationGrid2D


def main() -> None:
    grid = NavigationGrid2D(128, 128, diagonal=True, cache_size=512)
    wall = tuple((64, y) for y in range(128) if y != 63)
    grid.set_blocked_many(wall)
    start = Vec2(1.1, 1.1)
    goal = Vec2(126.1, 126.1)

    started = perf_counter()
    path = grid.find_path(start, goal)
    cold_seconds = perf_counter() - started
    if path is None:
        raise RuntimeError("navigation benchmark could not find the expected route")
    cold_expanded = grid.diagnostics.expanded_nodes

    started = perf_counter()
    for _ in range(1000):
        cached = grid.find_path(start, goal)
        if cached is None:
            raise RuntimeError("cached route unexpectedly disappeared")
    cached_seconds = perf_counter() - started

    diagnostics = grid.diagnostics
    if diagnostics.cache_hits != 1000:
        raise RuntimeError(f"expected 1000 cache hits, got {diagnostics.cache_hits}")
    if diagnostics.cache_misses != 1:
        raise RuntimeError(f"expected one cold cache miss, got {diagnostics.cache_misses}")
    if diagnostics.expanded_nodes != 0:
        raise RuntimeError("cached query repeated A* node expansion")

    print(
        "Navigation benchmark:",
        f"path_cells={len(path.cells)}",
        f"cold_expanded={cold_expanded}",
        f"cold_ms={cold_seconds * 1000.0:.3f}",
        f"1000_cached_ms={cached_seconds * 1000.0:.3f}",
        "cache_hits=1000",
    )
    print("Timing is host diagnostic data only; this benchmark makes no FPS claim.")


if __name__ == "__main__":
    main()
