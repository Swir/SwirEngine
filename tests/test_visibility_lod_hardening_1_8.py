from __future__ import annotations

import math

import pytest

from swirengine.visibility18 import (
    AABB3,
    VisibilityError,
    VisibilityIndex,
    VisibilityItem,
    VisibilitySession,
)


def _item(name: str, x: float, *, size: float = 1.0) -> VisibilityItem:
    return VisibilityItem(name, AABB3(x, 0, 0, x + size, size, size))


def test_non_finite_bounds_and_observer_coordinates_are_rejected() -> None:
    with pytest.raises(ValueError):
        AABB3(0, 0, 0, math.inf, 1, 1)

    index = VisibilityIndex()
    index.register(_item("safe", 0))
    with pytest.raises(ValueError):
        index.query(AABB3(0, 0, 0, 2, 2, 2), (math.nan, 0.0, 0.0))


def test_duplicate_registration_does_not_mutate_existing_item() -> None:
    index = VisibilityIndex()
    original = _item("same", 0)
    index.register(original)
    with pytest.raises(VisibilityError) as exc:
        index.register(_item("same", 100))
    assert exc.value.code == "duplicate-item"
    assert index.get("same") == original


def test_replace_capacity_failure_keeps_original_spatial_state() -> None:
    index = VisibilityIndex(cell_size=1.0, max_cells=8, max_cells_per_item=8)
    original = _item("moving", 0)
    index.register(original)
    oversized = VisibilityItem("moving", AABB3(0, 0, 0, 10, 0, 0))
    with pytest.raises(VisibilityError) as exc:
        index.replace(oversized)
    assert exc.value.code == "item-cell-limit"
    assert index.get("moving") == original
    assert index.query(AABB3(0, 0, 0, 2, 2, 2), (0.0, 0.0, 0.0)).diagnostics.visible_items == 1


def test_global_cell_capacity_failure_is_atomic() -> None:
    index = VisibilityIndex(cell_size=1.0, max_cells=2, max_cells_per_item=2)
    index.register(VisibilityItem("a", AABB3(0, 0, 0, 0, 0, 0)))
    with pytest.raises(VisibilityError) as exc:
        index.register(VisibilityItem("b", AABB3(10, 0, 0, 11, 0, 0)))
    assert exc.value.code == "cell-limit"
    assert index.item_count == 1
    assert index.get("b") is None


def test_duplicate_bucket_references_are_reported_without_duplicate_submissions() -> None:
    index = VisibilityIndex(cell_size=2.0)
    index.register(VisibilityItem("large", AABB3(0, 0, 0, 5, 1, 1)))
    plan = index.query(AABB3(0, 0, 0, 5, 1, 1), (0.0, 0.0, 0.0))
    assert [item.item_id for item in plan.submissions] == ["large"]
    assert plan.diagnostics.bucket_references > 1
    assert plan.diagnostics.duplicate_bucket_hits > 0
    assert plan.diagnostics.unique_candidates == 1


def test_tag_filter_is_order_independent_and_part_of_culling_only() -> None:
    index = VisibilityIndex()
    index.register(
        VisibilityItem("target", AABB3(0, 0, 0, 1, 1, 1), tags=("boss", "enemy"))
    )
    region = AABB3(-1, -1, -1, 2, 2, 2)
    first = index.query(region, (0.0, 0.0, 0.0), required_tags=("enemy", "boss"))
    second = index.query(region, (0.0, 0.0, 0.0), required_tags=("boss", "enemy"))
    assert first.fingerprint == second.fingerprint


def test_predicate_must_return_bool_and_does_not_commit_lod_state() -> None:
    index = VisibilityIndex()
    index.register(_item("x", 0))
    session = VisibilitySession()
    with pytest.raises(VisibilityError) as exc:
        index.query(
            AABB3(-1, -1, -1, 2, 2, 2),
            (0.0, 0.0, 0.0),
            session=session,
            predicate=lambda item: 1,  # type: ignore[return-value]
        )
    assert exc.value.code == "predicate-result"
    assert session.tracked == 0


def test_lod_policy_exception_does_not_commit_partial_session_state() -> None:
    index = VisibilityIndex()
    index.register(_item("a", 0))
    index.register(_item("b", 2))
    session = VisibilitySession()

    def policy(item: VisibilityItem, distance: float, previous: int | None, default: int) -> int:
        if item.item_id == "b":
            raise RuntimeError("quality controller unavailable")
        return default

    with pytest.raises(VisibilityError) as exc:
        index.query(AABB3(-1, -1, -1, 10, 2, 2), (0.0, 0.0, 0.0), session=session, lod_policy=policy)
    assert exc.value.code == "lod-policy-failed"
    assert session.tracked == 0


def test_hysteresis_can_cross_multiple_lod_bands_deterministically() -> None:
    index = VisibilityIndex()
    index.register(
        VisibilityItem(
            "mountain",
            AABB3(0, 0, 0, 0, 0, 0),
            lod_thresholds=(10.0, 20.0, 30.0),
            lod_hysteresis=1.0,
        )
    )
    session = VisibilitySession()
    region = AABB3(-100, -1, -1, 100, 1, 1)
    assert index.query(region, (0.0, 0.0, 0.0), session=session).submissions[0].lod == 0
    far = index.query(region, (-50.0, 0.0, 0.0), session=session)
    assert far.submissions[0].lod == 3
    assert far.diagnostics.lod_transitions == 1
    near = index.query(region, (-5.0, 0.0, 0.0), session=session)
    assert near.submissions[0].lod == 0


def test_session_forget_allows_reuse_of_bounded_state_capacity() -> None:
    index = VisibilityIndex()
    index.register(_item("a", 0))
    index.register(_item("b", 10))
    session = VisibilitySession(max_tracked=1)
    index.query(AABB3(-1, -1, -1, 2, 2, 2), (0.0, 0.0, 0.0), session=session)
    assert session.tracked == 1
    assert session.forget("a")
    plan = index.query(AABB3(9, -1, -1, 12, 2, 2), (10.0, 0.0, 0.0), session=session)
    assert [item.item_id for item in plan.submissions] == ["b"]


def test_query_fingerprint_changes_when_visible_lod_changes() -> None:
    index = VisibilityIndex()
    index.register(
        VisibilityItem("tree", AABB3(0, 0, 0, 0, 0, 0), lod_thresholds=(10.0,))
    )
    region = AABB3(-100, -1, -1, 100, 1, 1)
    near = index.query(region, (0.0, 0.0, 0.0))
    far = index.query(region, (-50.0, 0.0, 0.0))
    assert near.submissions[0].lod == 0
    assert far.submissions[0].lod == 1
    assert near.fingerprint != far.fingerprint
