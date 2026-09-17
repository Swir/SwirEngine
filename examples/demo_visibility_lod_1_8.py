from __future__ import annotations

from swirengine.visibility18 import AABB3, VisibilityIndex, VisibilityItem, VisibilitySession


def main() -> None:
    index = VisibilityIndex(cell_size=16.0)
    index.register(
        VisibilityItem(
            "hero",
            AABB3(-1, -1, 0, 1, 1, 2),
            layer=2,
            priority=100,
            lod_thresholds=(25.0, 60.0),
            lod_hysteresis=2.0,
            tags=("actor", "player"),
        )
    )
    for number, x in enumerate((8.0, 24.0, 48.0, 96.0)):
        index.register(
            VisibilityItem(
                f"tree-{number}",
                AABB3(x, -2, 0, x + 3, 2, 12),
                priority=10 - number,
                lod_thresholds=(20.0, 50.0, 90.0),
                lod_hysteresis=3.0,
                tags=("world", "tree"),
            )
        )

    session = VisibilitySession()
    camera_region = AABB3(-12, -20, -5, 70, 20, 30)
    plan = index.query(camera_region, (0.0, 0.0, 2.0), session=session)

    print("visible submissions:")
    for submission in plan.submissions:
        print(
            f"  {submission.item_id}: lod={submission.lod} "
            f"distance={submission.distance:.1f} layer={submission.layer}"
        )
    print("candidates:", plan.diagnostics.unique_candidates)
    print("visible:", plan.diagnostics.visible_items)
    print("tracked LOD states:", plan.diagnostics.tracked_lods)
    print("plan fingerprint:", plan.fingerprint)

    # A creator/backend can supply a stricter test after the conservative grid/AABB filter.
    trees_only = index.query(
        camera_region,
        (0.0, 0.0, 2.0),
        session=session,
        predicate=lambda item: "tree" in item.tags,
    )
    print("tree-only visible:", [item.item_id for item in trees_only.submissions])


if __name__ == "__main__":
    main()
