from __future__ import annotations

import time

from swirengine import TileMap2D


def main() -> None:
    width = height = 192
    tile_size = 16
    tilemap = TileMap2D(
        "tiles.png",
        width,
        height,
        tile_size,
        tile_size,
        4,
        4,
    ).fill(1)

    tilemap.diagnostics.reset()
    start = time.perf_counter()
    for _ in range(1_000):
        tilemap.update(1 / 120)
    unchanged_seconds = time.perf_counter() - start
    if tilemap.diagnostics.transform_sprite_visits != 0:
        raise AssertionError("unchanged tilemap updates must not rescan the sprite pool")

    camera_x = 640.0
    camera_y = 360.0
    queries = 500
    visible_total = 0
    max_candidates = 0
    start = time.perf_counter()
    for step in range(queries):
        x = camera_x + (step % 11) * 8.0
        visible_total += sum(
            1
            for _ in tilemap.iter_visible_sprites(
                x,
                camera_y,
                640,
                360,
                zoom=1.0,
            )
        )
        max_candidates = max(max_candidates, tilemap.diagnostics.last_visibility_candidates)
    visibility_seconds = time.perf_counter() - start

    full_cells = width * height
    if max_candidates >= full_cells // 8:
        raise AssertionError(
            f"viewport query considered too much of the map: {max_candidates}/{full_cells}"
        )

    print(
        "2D power benchmark: "
        f"cells={full_cells}, unchanged_updates=1000/{unchanged_seconds:.6f}s, "
        f"viewport_queries={queries}/{visibility_seconds:.6f}s, "
        f"max_candidates={max_candidates}, visible_total={visible_total}"
    )


if __name__ == "__main__":
    main()
