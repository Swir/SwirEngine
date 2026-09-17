from __future__ import annotations

import pytest

from swirengine.resource_budget17 import (
    AdmissionReason,
    BudgetVector,
    ResourceBudgetBroker,
    StaleBudgetPlanError,
)


def _budget(memory: int = 0, count: int = 0, work: int = 0) -> BudgetVector:
    return BudgetVector(memory_bytes=memory, count=count, work_units=work)


def test_budget_vector_validation_and_arithmetic() -> None:
    value = _budget(10, 2, 3)
    assert value.added(_budget(5, 1, 2)) == _budget(15, 3, 5)
    assert value.subtracted(_budget(4, 1, 1)) == _budget(6, 1, 2)
    assert value.component_min(_budget(7, 4, 1)) == _budget(7, 2, 1)
    assert value.fits_within(_budget(10, 3, 4))
    assert not value.fits_within(_budget(9, 3, 4))
    assert value.helps_excess(_budget(11, 2, 3), _budget(10, 2, 3))

    with pytest.raises(TypeError):
        BudgetVector(memory_bytes=True)
    with pytest.raises(ValueError):
        BudgetVector(count=-1)
    with pytest.raises(ValueError, match="negative"):
        _budget(1).subtracted(_budget(2))


def test_basic_admission_release_and_duplicate_rejection() -> None:
    broker = ResourceBudgetBroker(_budget(100, 10, 20))
    result = broker.admit(
        "texture:a",
        subsystem="assets",
        demand=_budget(25, 1, 2),
        priority=10,
    )
    assert result.admitted
    assert result.allocation is not None
    assert broker.usage() == _budget(25, 1, 2)

    duplicate = broker.admit(
        "texture:a",
        subsystem="assets",
        demand=_budget(10, 1, 1),
        priority=20,
    )
    assert not duplicate.admitted
    assert duplicate.reason is AdmissionReason.DUPLICATE_RESOURCE
    assert broker.usage() == _budget(25, 1, 2)

    released = broker.release("texture:a")
    assert released == result.allocation
    assert broker.release("texture:a") is None
    assert broker.usage() == _budget()


def test_higher_priority_request_evicts_lowest_priority_first() -> None:
    broker = ResourceBudgetBroker(_budget(count=2))
    low = broker.admit("low", subsystem="world", demand=_budget(count=1), priority=1)
    medium = broker.admit("medium", subsystem="world", demand=_budget(count=1), priority=5)
    high = broker.admit("high", subsystem="world", demand=_budget(count=1), priority=10)

    assert low.admitted and medium.admitted and high.admitted
    assert tuple(item.resource_id for item in high.evicted) == ("low",)
    assert tuple(item.resource_id for item in broker.allocations()) == ("medium", "high")


def test_equal_priority_does_not_churn_resident_resources() -> None:
    broker = ResourceBudgetBroker(_budget(count=1))
    assert broker.admit("resident", subsystem="world", demand=_budget(count=1), priority=5).admitted

    result = broker.admit("incoming", subsystem="world", demand=_budget(count=1), priority=5)
    assert not result.admitted
    assert result.reason is AdmissionReason.PRIORITY_PROTECTED
    assert broker.allocation("resident").resource_id == "resident"


def test_same_priority_eviction_order_is_newest_first_for_stability() -> None:
    broker = ResourceBudgetBroker(_budget(count=3))
    first = broker.admit("first", subsystem="world", demand=_budget(count=1), priority=1)
    second = broker.admit("second", subsystem="world", demand=_budget(count=1), priority=1)
    keep = broker.admit("keep", subsystem="world", demand=_budget(count=1), priority=20)
    assert first.admitted and second.admitted and keep.admitted

    result = broker.admit(
        "large",
        subsystem="world",
        demand=_budget(count=2),
        priority=10,
    )
    assert result.admitted
    assert tuple(item.resource_id for item in result.evicted) == ("second", "first")
    assert {item.resource_id for item in broker.allocations()} == {"keep", "large"}


def test_non_evictable_allocation_blocks_pressure_eviction() -> None:
    broker = ResourceBudgetBroker(_budget(count=1))
    assert broker.admit(
        "pinned",
        subsystem="renderer",
        demand=_budget(count=1),
        priority=-100,
        evictable=False,
    ).admitted

    result = broker.admit(
        "incoming",
        subsystem="renderer",
        demand=_budget(count=1),
        priority=100,
    )
    assert not result.admitted
    assert result.reason is AdmissionReason.PROTECTED_ALLOCATION


def test_reservation_class_protects_resident_floor_but_allows_surplus_eviction() -> None:
    broker = ResourceBudgetBroker(_budget(count=4))
    broker.register_reservation_class("critical", reserved=_budget(count=2))

    assert broker.admit(
        "critical-a",
        subsystem="world",
        reservation_class="critical",
        demand=_budget(count=1),
        priority=1,
    ).admitted
    assert broker.admit(
        "critical-b",
        subsystem="world",
        reservation_class="critical",
        demand=_budget(count=1),
        priority=1,
    ).admitted
    assert broker.admit(
        "critical-surplus",
        subsystem="world",
        reservation_class="critical",
        demand=_budget(count=1),
        priority=1,
    ).admitted
    assert broker.admit(
        "background",
        subsystem="world",
        demand=_budget(count=1),
        priority=50,
    ).admitted

    result = broker.admit(
        "replacement",
        subsystem="world",
        demand=_budget(count=1),
        priority=10,
    )
    assert result.admitted
    assert tuple(item.resource_id for item in result.evicted) == ("critical-surplus",)
    assert broker.reservation_usage("critical") == _budget(count=2)


def test_reservation_floor_can_block_other_class_even_at_higher_priority() -> None:
    broker = ResourceBudgetBroker(_budget(count=2))
    broker.register_reservation_class("critical", reserved=_budget(count=2))
    for name in ("a", "b"):
        assert broker.admit(
            name,
            subsystem="world",
            reservation_class="critical",
            demand=_budget(count=1),
            priority=1,
        ).admitted

    result = broker.admit(
        "background",
        subsystem="assets",
        demand=_budget(count=1),
        priority=100,
    )
    assert not result.admitted
    assert result.reason is AdmissionReason.RESERVATION_PROTECTED
    assert {item.resource_id for item in broker.allocations()} == {"a", "b"}


def test_reservation_totals_cannot_exceed_global_capacity() -> None:
    broker = ResourceBudgetBroker(_budget(memory=100, count=10, work=10))
    broker.register_reservation_class("world", reserved=_budget(memory=60, count=4, work=5))
    with pytest.raises(ValueError, match="cannot exceed"):
        broker.register_reservation_class(
            "assets", reserved=_budget(memory=50, count=2, work=1)
        )


def test_subsystem_limit_isolates_exhaustion_from_other_subsystems() -> None:
    broker = ResourceBudgetBroker(_budget(count=10))
    broker.set_subsystem_limit("assets", _budget(count=2))
    assert broker.admit("a", subsystem="assets", demand=_budget(count=1), priority=5).admitted
    assert broker.admit("b", subsystem="assets", demand=_budget(count=1), priority=5).admitted

    rejected = broker.admit(
        "c", subsystem="assets", demand=_budget(count=1), priority=5
    )
    assert not rejected.admitted
    assert rejected.reason in {
        AdmissionReason.PRIORITY_PROTECTED,
        AdmissionReason.SUBSYSTEM_LIMIT,
    }

    other = broker.admit("world", subsystem="world", demand=_budget(count=5), priority=0)
    assert other.admitted
    assert broker.subsystem_usage("assets") == _budget(count=2)
    assert broker.subsystem_usage("world") == _budget(count=5)


def test_higher_priority_request_can_replace_within_subsystem_limit() -> None:
    broker = ResourceBudgetBroker(_budget(count=5))
    broker.set_subsystem_limit("assets", _budget(count=2))
    assert broker.admit("old-a", subsystem="assets", demand=_budget(count=1), priority=1).admitted
    assert broker.admit("old-b", subsystem="assets", demand=_budget(count=1), priority=10).admitted

    result = broker.admit("new", subsystem="assets", demand=_budget(count=1), priority=5)
    assert result.admitted
    assert tuple(item.resource_id for item in result.evicted) == ("old-a",)
    assert broker.subsystem_usage("assets") == _budget(count=2)


def test_multi_dimension_pressure_requires_enough_evictions_for_all_dimensions() -> None:
    broker = ResourceBudgetBroker(_budget(memory=100, count=3, work=10))
    assert broker.admit(
        "memory",
        subsystem="world",
        demand=_budget(memory=60, count=1, work=1),
        priority=1,
    ).admitted
    assert broker.admit(
        "work",
        subsystem="world",
        demand=_budget(memory=10, count=1, work=7),
        priority=2,
    ).admitted

    result = broker.admit(
        "incoming",
        subsystem="world",
        demand=_budget(memory=50, count=2, work=5),
        priority=10,
    )
    assert result.admitted
    assert tuple(item.resource_id for item in result.evicted) == ("memory", "work")
    assert broker.usage() == _budget(memory=50, count=2, work=5)


def test_oversized_request_rejects_without_evicting_anything() -> None:
    broker = ResourceBudgetBroker(_budget(memory=100, count=2, work=2))
    assert broker.admit(
        "resident", subsystem="world", demand=_budget(memory=50, count=1, work=1), priority=1
    ).admitted

    result = broker.admit(
        "too-large",
        subsystem="world",
        demand=_budget(memory=101, count=1, work=1),
        priority=100,
    )
    assert not result.admitted
    assert result.reason is AdmissionReason.REQUEST_EXCEEDS_CAPACITY
    assert tuple(item.resource_id for item in broker.allocations()) == ("resident",)


def test_two_phase_plan_commit_and_stale_plan_detection() -> None:
    broker = ResourceBudgetBroker(_budget(count=2))
    plan = broker.plan_admission("planned", subsystem="world", demand=_budget(count=1))
    assert plan.admitted
    result = broker.commit(plan)
    assert result.admitted
    assert result.allocation is not None

    stale = broker.plan_admission("stale", subsystem="world", demand=_budget(count=1))
    assert stale.admitted
    assert broker.admit("other", subsystem="world", demand=_budget(count=1)).admitted
    with pytest.raises(StaleBudgetPlanError, match="stale"):
        broker.commit(stale)


def test_rejected_plan_cannot_be_committed() -> None:
    broker = ResourceBudgetBroker(_budget(count=1))
    assert broker.admit("resident", subsystem="world", demand=_budget(count=1), priority=5).admitted
    plan = broker.plan_admission(
        "blocked", subsystem="world", demand=_budget(count=1), priority=5
    )
    assert not plan.admitted
    with pytest.raises(ValueError, match="rejected"):
        broker.commit(plan)


def test_lowering_subsystem_limit_below_live_usage_is_refused_atomically() -> None:
    broker = ResourceBudgetBroker(_budget(count=5))
    assert broker.admit("a", subsystem="assets", demand=_budget(count=2)).admitted
    before = broker.revision

    with pytest.raises(ValueError, match="current subsystem usage"):
        broker.set_subsystem_limit("assets", _budget(count=1))
    assert broker.revision == before
    assert broker.subsystem_usage("assets") == _budget(count=2)


def test_diagnostics_are_deterministic_and_payload_free() -> None:
    broker = ResourceBudgetBroker(_budget(memory=100, count=4, work=8))
    broker.register_reservation_class("critical", reserved=_budget(memory=20, count=1))
    broker.set_subsystem_limit("assets", _budget(memory=60, count=2, work=4))
    assert broker.admit(
        "asset-a",
        subsystem="assets",
        reservation_class="critical",
        demand=_budget(memory=30, count=1, work=2),
        priority=5,
    ).admitted
    rejected = broker.admit(
        "asset-b",
        subsystem="assets",
        demand=_budget(memory=40, count=2, work=3),
        priority=5,
    )
    assert not rejected.admitted

    diagnostics = broker.diagnostics()
    portable = diagnostics.portable()
    assert diagnostics.used == _budget(memory=30, count=1, work=2)
    assert diagnostics.available == _budget(memory=70, count=3, work=6)
    assert diagnostics.allocations == 1
    assert diagnostics.admitted_total == 1
    assert diagnostics.rejected_total == 1
    assert portable["pressure"] == {"memory": 0.3, "count": 0.25, "work": 0.25}
    assert tuple(portable["subsystems"]) == ("assets",)
    assert tuple(portable["reservation_classes"]) == ("critical", "default")
    assert "asset-a" not in repr(portable)


def test_eviction_and_release_counters_are_exact() -> None:
    broker = ResourceBudgetBroker(_budget(count=2))
    first = broker.admit("first", subsystem="world", demand=_budget(count=1), priority=1)
    second = broker.admit("second", subsystem="world", demand=_budget(count=1), priority=2)
    assert first.admitted and second.admitted
    incoming = broker.admit("incoming", subsystem="world", demand=_budget(count=1), priority=10)
    assert incoming.admitted and len(incoming.evicted) == 1
    assert broker.release("second") is not None

    diagnostics = broker.diagnostics()
    assert diagnostics.admitted_total == 3
    assert diagnostics.evicted_total == 1
    assert diagnostics.released_total == 1
    assert diagnostics.allocations == 1
