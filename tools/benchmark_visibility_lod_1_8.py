from __future__ import annotations

from time import perf_counter

from swirengine.visibility18 import AABB3, VisibilityIndex, VisibilityItem, VisibilitySession

ITEMS = 12_000
FRAMES = 120
MAX_SECONDS = 5.0


def main() -> None:
    start = perf_counter()
    index = VisibilityIndex(
        cell_size=8.0,
        max_items=ITEMS,
        max_candidates=4_096,
        max_query_cells=1_024,
    )
    for item_number in range(ITEMS):
        column = item_number % 120
        row = item_number // 120
        x = float(column * 4)
        y = float(row * 4)
        index.register(
            VisibilityItem(
                f"prop-{item_number:05d}",
                AABB3(x, y, 0.0, x + 1.0, y + 1.0, 2.0),
                priority=item_number % 7,
                lod_thresholds=(30.0, 70.0, 140.0),
                lod_hysteresis=3.0,
                tags=("world", "static"),
            )
        )

    session = VisibilitySession(max_tracked=ITEMS)
    total_candidates = 0
    total_visible = 0
    total_transitions = 0
    for frame in range(FRAMES):
        x = float((frame * 7) % 380)
        y = float((frame * 5) % 300)
        query_bounds = AABB3(x, y, -4.0, x + 88.0, y + 88.0, 8.0)
        observer = (x + 44.0, y + 44.0, 2.0)
        plan = index.query(
            query_bounds,
            observer,
            session=session,
            required_tags=("world",),
        )
        total_candidates += plan.diagnostics.unique_candidates
        total_visible += plan.diagnostics.visible_items
        total_transitions += plan.diagnostics.lod_transitions

    elapsed = perf_counter() - start
    full_scan_work = ITEMS * FRAMES
    assert index.item_count == ITEMS
    assert total_visible > 20_000
    assert total_candidates < full_scan_work // 8
    assert session.tracked < ITEMS
    assert len(index.state_fingerprint()) == 64
    assert len(session.state_fingerprint()) == 64
    assert elapsed < MAX_SECONDS

    print(
        "visibility/LOD workload:",
        f"indexed_items={ITEMS}",
        f"frames={FRAMES}",
        f"full_scan_items={full_scan_work}",
        f"spatial_candidates={total_candidates}",
        f"visible_submissions={total_visible}",
        f"lod_transitions={total_transitions}",
        f"tracked_lods={session.tracked}",
        f"elapsed={elapsed:.4f}s",
        f"budget={MAX_SECONDS:.1f}s",
    )


if __name__ == "__main__":
    main()
