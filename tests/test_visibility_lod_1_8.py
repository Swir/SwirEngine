from __future__ import annotations

import pytest

from swirengine.visibility18 import (
    AABB3,
    VisibilityError,
    VisibilityIndex,
    VisibilityItem,
    VisibilitySession,
)


def _box(x: float, y: float = 0.0, z: float = 0.0, size: float = 1.0) -> AABB3:
    return AABB3(x, y, z, x + size, y + size, z + size)


def _item(name: str, x: float, **kwargs: object) -> VisibilityItem:
    return VisibilityItem(name, _box(x), **kwargs)


def test_aabb_intersection_supports_2d_and_3d_bounds() -> None:
    assert AABB3(0, 0, 0, 10, 10, 0).intersects(AABB3(9, 9, 0, 20, 20, 0))
    assert not AABB3(0, 0, 0, 1, 1, 1).intersects(AABB3(2, 2, 2, 3, 3, 3))


def test_item_normalizes_tags_and_has_deterministic_fingerprint() -> None:
    first = VisibilityItem(" hero ", _box(0), tags=("enemy", "boss", "enemy"))
    second = VisibilityItem("hero", _box(0), tags=("boss", "enemy"))
    assert first.tags == ("boss", "enemy")
    assert first.fingerprint == second.fingerprint


def test_lod_thresholds_must_be_strictly_increasing() -> None:
    with pytest.raises(ValueError):
        VisibilityItem("bad", _box(0), lod_thresholds=(10.0, 10.0))


def test_index_register_query_and_remove_are_deterministic() -> None:
    index = VisibilityIndex(cell_size=8.0)
    index.register(_item("b", 2))
    index.register(_item("a", 1))
    index.register(_item("far", 100))

    plan = index.query(AABB3(0, -1, -1, 20, 2, 2), (0.0, 0.0, 0.0))
    assert [entry.item_id for entry in plan.submissions] == ["a", "b"]
    assert plan.diagnostics.visible_items == 2
    assert plan.diagnostics.unique_candidates >= 2
    assert index.remove("a")
    assert not index.remove("a")
    assert [entry.item_id for entry in index.query(AABB3(0, -1, -1, 20, 2, 2), (0.0, 0.0, 0.0)).submissions] == ["b"]


def test_query_exact_bounds_filter_removes_conservative_cell_false_positive() -> None:
    index = VisibilityIndex(cell_size=100.0)
    index.register(_item("outside", 80))
    plan = index.query(AABB3(0, 0, 0, 10, 10, 10), (0.0, 0.0, 0.0))
    assert plan.submissions == ()
    assert plan.diagnostics.bounds_culled == 1


def test_predicate_and_tag_filter_are_creator_owned() -> None:
    index = VisibilityIndex(cell_size=16.0)
    index.register(VisibilityItem("boss", _box(1), tags=("enemy", "boss")))
    index.register(VisibilityItem("minion", _box(2), tags=("enemy",)))
    plan = index.query(
        AABB3(0, 0, 0, 8, 8, 8),
        (0.0, 0.0, 0.0),
        required_tags=("enemy",),
        predicate=lambda item: "boss" in item.tags,
    )
    assert [entry.item_id for entry in plan.submissions] == ["boss"]
    assert plan.diagnostics.predicate_culled == 1


def test_predicate_failures_are_contained() -> None:
    index = VisibilityIndex()
    index.register(_item("x", 0))

    def fail(_: VisibilityItem) -> bool:
        raise RuntimeError("camera unavailable")

    with pytest.raises(VisibilityError) as exc:
        index.query(_box(0, size=20), (0.0, 0.0, 0.0), predicate=fail)
    assert exc.value.code == "predicate-failed"


def test_default_lod_selection_and_hysteresis_are_stable() -> None:
    index = VisibilityIndex(cell_size=64.0)
    index.register(
        VisibilityItem(
            "tree",
            _box(0),
            lod_thresholds=(10.0, 20.0),
            lod_hysteresis=2.0,
        )
    )
    session = VisibilitySession()
    bounds = AABB3(-100, -10, -10, 100, 10, 10)

    first = index.query(bounds, (-8.5, 0.5, 0.5), session=session)
    assert first.submissions[0].lod == 0
    assert index.query(bounds, (-10.0, 0.5, 0.5), session=session).submissions[0].lod == 0
    crossed = index.query(bounds, (-12.0, 0.5, 0.5), session=session)
    assert crossed.submissions[0].lod == 1
    assert crossed.diagnostics.lod_transitions == 1
    assert index.query(bounds, (-9.0, 0.5, 0.5), session=session).submissions[0].lod == 1
    assert index.query(bounds, (-7.0, 0.5, 0.5), session=session).submissions[0].lod == 0


def test_custom_lod_policy_can_override_default_within_item_range() -> None:
    index = VisibilityIndex()
    index.register(VisibilityItem("hero", _box(0), lod_thresholds=(5.0, 10.0)))
    plan = index.query(
        _box(0, size=100),
        (50.0, 0.5, 0.5),
        lod_policy=lambda item, distance, previous, default: 0,
    )
    assert plan.submissions[0].lod == 0


def test_custom_lod_policy_out_of_range_is_rejected_without_session_mutation() -> None:
    index = VisibilityIndex()
    index.register(VisibilityItem("hero", _box(0), lod_thresholds=(5.0,)))
    session = VisibilitySession()
    with pytest.raises(VisibilityError) as exc:
        index.query(
            _box(0, size=100),
            (0.0, 0.0, 0.0),
            session=session,
            lod_policy=lambda item, distance, previous, default: 2,
        )
    assert exc.value.code == "lod-policy-range"
    assert session.tracked == 0


def test_session_bound_is_explicit_and_atomic() -> None:
    index = VisibilityIndex()
    index.register(_item("a", 0))
    index.register(_item("b", 2))
    session = VisibilitySession(max_tracked=1)
    with pytest.raises(VisibilityError) as exc:
        index.query(_box(0, size=10), (0.0, 0.0, 0.0), session=session)
    assert exc.value.code == "lod-state-limit"
    assert session.tracked == 0


def test_ordering_is_layer_priority_lod_distance_then_id() -> None:
    index = VisibilityIndex()
    index.register(VisibilityItem("low", _box(1), layer=0, priority=1))
    index.register(VisibilityItem("high", _box(3), layer=0, priority=10))
    index.register(VisibilityItem("later-layer", _box(0), layer=1, priority=999))
    plan = index.query(_box(0, size=20), (0.0, 0.0, 0.0))
    assert [entry.item_id for entry in plan.submissions] == ["high", "low", "later-layer"]


def test_replace_updates_spatial_occupancy_without_duplicates() -> None:
    index = VisibilityIndex(cell_size=4.0)
    index.register(_item("moving", 0))
    index.replace(_item("moving", 100))
    assert index.query(_box(0, size=10), (0.0, 0.0, 0.0)).submissions == ()
    assert [entry.item_id for entry in index.query(_box(90, size=20), (0.0, 0.0, 0.0)).submissions] == ["moving"]
    assert index.item_count == 1


def test_item_and_query_cell_limits_fail_before_mutation() -> None:
    index = VisibilityIndex(cell_size=1.0, max_cells_per_item=4, max_query_cells=8)
    with pytest.raises(VisibilityError) as exc:
        index.register(VisibilityItem("huge", AABB3(0, 0, 0, 10, 10, 10)))
    assert exc.value.code == "item-cell-limit"
    assert index.item_count == 0

    with pytest.raises(VisibilityError) as exc:
        index.query(AABB3(0, 0, 0, 10, 10, 10), (0.0, 0.0, 0.0))
    assert exc.value.code == "query-cell-limit"


def test_item_and_candidate_limits_are_explicit() -> None:
    limited = VisibilityIndex(max_items=1)
    limited.register(_item("a", 0))
    with pytest.raises(VisibilityError) as exc:
        limited.register(_item("b", 1))
    assert exc.value.code == "item-limit"

    candidates = VisibilityIndex(cell_size=100.0, max_candidates=1)
    candidates.register(_item("a", 0))
    candidates.register(_item("b", 1))
    with pytest.raises(VisibilityError) as exc:
        candidates.query(_box(0, size=10), (0.0, 0.0, 0.0))
    assert exc.value.code == "candidate-limit"


def test_plan_and_index_fingerprints_are_reproducible() -> None:
    def build() -> tuple[str, str]:
        index = VisibilityIndex(cell_size=8.0)
        for name, x in (("a", 1), ("b", 4), ("c", 20)):
            index.register(_item(name, x, lod_thresholds=(5.0, 12.0)))
        plan = index.query(AABB3(0, 0, 0, 16, 4, 4), (0.0, 0.0, 0.0))
        return index.state_fingerprint(), plan.fingerprint

    assert build() == build()


def test_session_fingerprint_and_forget_are_deterministic() -> None:
    index = VisibilityIndex()
    index.register(_item("a", 0))
    session = VisibilitySession()
    index.query(_box(0, size=5), (0.0, 0.0, 0.0), session=session)
    before = session.state_fingerprint()
    assert session.last_lod("a") == 0
    assert session.forget("a")
    assert not session.forget("a")
    assert session.state_fingerprint() != before
