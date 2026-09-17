import pytest

from swirengine.render_graph18 import RenderGraphBuilder
from swirengine.render_resources18 import (
    RenderPlanPoolSession,
    RenderPlanResourceSchedule,
    RenderResourceDescriptor,
    RenderResourceHandle,
    RenderResourcePoolError,
    TransientRenderResourcePool,
)


def descriptor(name: str = "rgba8", size: int = 64) -> RenderResourceDescriptor:
    return RenderResourceDescriptor("texture", name, 4, 4, size_bytes=size)


def pool(*, max_resources: int = 4, max_bytes: int = 1024):
    created = []
    destroyed = []

    def create(spec):
        resource = {"id": len(created), "spec": spec}
        created.append(resource)
        return resource

    def destroy(resource):
        destroyed.append(resource["id"])

    instance = TransientRenderResourcePool(
        create=create,
        destroy=destroy,
        max_resources=max_resources,
        max_bytes=max_bytes,
    )
    return instance, created, destroyed


def test_exact_descriptor_is_reused_with_new_generation() -> None:
    instance, created, _ = pool()
    first = instance.acquire(descriptor())
    instance.release(first.handle)
    second = instance.acquire(descriptor())

    assert second.reused is True
    assert second.resource is first.resource
    assert second.handle.slot == first.handle.slot
    assert second.handle.generation == first.handle.generation + 1
    assert len(created) == 1
    assert instance.diagnostics().reuses == 1


def test_stale_handle_cannot_release_reacquired_resource() -> None:
    instance, _, _ = pool()
    first = instance.acquire(descriptor())
    instance.release(first.handle)
    second = instance.acquire(descriptor())

    with pytest.raises(RenderResourcePoolError) as error:
        instance.release(first.handle)

    assert error.value.code == "stale-handle"
    assert instance.get(second.handle) is second.resource
    assert instance.diagnostics().stale_handle_failures == 1


def test_different_descriptors_do_not_alias_live_backend_objects() -> None:
    instance, created, _ = pool()
    first = instance.acquire(descriptor("rgba8"))
    instance.release(first.handle)
    second = instance.acquire(descriptor("rgba16f"))

    assert second.reused is False
    assert len(created) == 2
    assert first.resource is not second.resource


def test_capacity_evicts_oldest_free_resource_deterministically() -> None:
    instance, _, destroyed = pool(max_resources=2)
    first = instance.acquire(descriptor("a"))
    second = instance.acquire(descriptor("b"))
    instance.release(first.handle)
    instance.release(second.handle)

    third = instance.acquire(descriptor("c"))

    assert third.reused is False
    assert destroyed == [0]
    diagnostics = instance.diagnostics()
    assert diagnostics.evictions == 1
    assert diagnostics.resident_resources == 2


def test_byte_capacity_can_evict_multiple_free_resources() -> None:
    instance, _, destroyed = pool(max_resources=8, max_bytes=100)
    first = instance.acquire(descriptor("a", 40))
    second = instance.acquire(descriptor("b", 40))
    instance.release(first.handle)
    instance.release(second.handle)

    third = instance.acquire(descriptor("c", 90))

    assert third.descriptor.size_bytes == 90
    assert destroyed == [0, 1]
    assert instance.diagnostics().resident_bytes == 90


def test_fully_leased_capacity_fails_without_destroying_live_resources() -> None:
    instance, _, destroyed = pool(max_resources=1)
    live = instance.acquire(descriptor("a"))

    with pytest.raises(RenderResourcePoolError) as error:
        instance.acquire(descriptor("b"))

    assert error.value.code == "capacity-exhausted"
    assert destroyed == []
    assert instance.get(live.handle) is live.resource


def test_resource_larger_than_byte_limit_is_rejected_before_factory() -> None:
    instance, created, _ = pool(max_bytes=32)

    with pytest.raises(RenderResourcePoolError) as error:
        instance.acquire(descriptor(size=33))

    assert error.value.code == "resource-too-large"
    assert created == []


def test_factory_failure_is_contained_and_accounted() -> None:
    def create(_):
        raise RuntimeError("backend unavailable")

    instance = TransientRenderResourcePool(
        create=create,
        destroy=lambda _resource: None,
        max_resources=2,
        max_bytes=100,
    )

    with pytest.raises(RenderResourcePoolError) as error:
        instance.acquire(descriptor())

    assert error.value.code == "create-failed"
    assert instance.diagnostics().create_failures == 1
    assert instance.diagnostics().resident_resources == 0


def test_destroy_failure_during_eviction_keeps_accounting_coherent() -> None:
    def destroy(_):
        raise RuntimeError("device lost")

    instance = TransientRenderResourcePool(
        create=lambda spec: {"spec": spec},
        destroy=destroy,
        max_resources=1,
        max_bytes=100,
    )
    lease = instance.acquire(descriptor("a"))
    instance.release(lease.handle)

    with pytest.raises(RenderResourcePoolError) as error:
        instance.acquire(descriptor("b"))

    assert error.value.code == "destroy-failed"
    diagnostics = instance.diagnostics()
    assert diagnostics.destroy_failures == 1
    assert diagnostics.resident_resources == 1
    assert diagnostics.free_resources == 1


def test_trim_removes_only_free_resources() -> None:
    instance, _, destroyed = pool(max_resources=3)
    live = instance.acquire(descriptor("live"))
    first = instance.acquire(descriptor("free-a"))
    second = instance.acquire(descriptor("free-b"))
    instance.release(first.handle)
    instance.release(second.handle)

    removed = instance.trim(target_resources=1, target_bytes=0)

    assert removed == 2
    assert destroyed == [1, 2]
    assert instance.get(live.handle) is live.resource
    assert instance.diagnostics().resident_resources == 1


def test_close_destroys_all_resources_once_and_is_idempotent() -> None:
    instance, _, destroyed = pool()
    first = instance.acquire(descriptor("a"))
    second = instance.acquire(descriptor("b"))
    instance.release(first.handle)

    instance.close()
    instance.close()

    assert destroyed == [0, 1]
    assert instance.closed is True
    with pytest.raises(RenderResourcePoolError) as error:
        instance.get(second.handle)
    assert error.value.code == "pool-closed"


def test_close_reports_destroy_failures_after_attempting_all_resources() -> None:
    attempted = []

    def destroy(resource):
        attempted.append(resource)
        if resource == 0:
            raise RuntimeError("first fails")

    instance = TransientRenderResourcePool(
        create=lambda _spec: len(attempted) if False else object(),
        destroy=lambda _resource: None,
        max_resources=2,
        max_bytes=128,
    )
    # Use a second pool with stable integer resources to make the assertion explicit.
    next_id = 0

    def create_integer(_spec):
        nonlocal next_id
        value = next_id
        next_id += 1
        return value

    instance = TransientRenderResourcePool(
        create=create_integer,
        destroy=destroy,
        max_resources=2,
        max_bytes=128,
    )
    instance.acquire(descriptor("a"))
    instance.acquire(descriptor("b"))

    with pytest.raises(RenderResourcePoolError) as error:
        instance.close()

    assert error.value.code == "destroy-failed"
    assert attempted == [0, 1]
    assert instance.closed is True


def graph_plan():
    graph = RenderGraphBuilder()
    graph.add_resource("camera", external=True)
    graph.add_resource("first", transient=True, size_bytes=64)
    graph.add_resource("bridge", transient=True, size_bytes=64)
    graph.add_resource("second", transient=True, size_bytes=64)
    graph.add_pass("first-pass", reads=("camera",), writes=("first",))
    graph.add_pass("bridge-pass", reads=("first",), writes=("bridge",))
    graph.add_pass("second-pass", reads=("bridge",), writes=("second",))
    graph.add_pass("consume", reads=("second",), side_effect=True)
    return graph.compile()


def test_schedule_consumes_transient_lifetimes_only() -> None:
    plan = graph_plan()
    spec = descriptor(size=64)
    schedule = RenderPlanResourceSchedule.from_plan(
        plan,
        {"first": spec, "bridge": spec, "second": spec},
    )

    assert schedule.pass_count == 4
    assert [event.resource_name for event in schedule.acquire_events[0]] == ["first"]
    assert [event.resource_name for event in schedule.release_events[1]] == ["first"]
    assert [event.resource_name for event in schedule.acquire_events[2]] == ["second"]


def test_schedule_requires_every_transient_descriptor() -> None:
    with pytest.raises(RenderResourcePoolError) as error:
        RenderPlanResourceSchedule.from_plan(graph_plan(), {})
    assert error.value.code == "missing-descriptor"


def test_schedule_rejects_descriptor_larger_than_graph_contract() -> None:
    plan = graph_plan()
    oversized = descriptor(size=65)
    mapping = {name: oversized for name in ("first", "bridge", "second")}

    with pytest.raises(RenderResourcePoolError) as error:
        RenderPlanResourceSchedule.from_plan(plan, mapping)

    assert error.value.code == "descriptor-too-large"


def test_pool_session_reuses_resource_after_graph_lifetime_ends() -> None:
    plan = graph_plan()
    spec = descriptor(size=64)
    schedule = RenderPlanResourceSchedule.from_plan(
        plan,
        {"first": spec, "bridge": spec, "second": spec},
    )
    instance, created, _ = pool(max_resources=2)
    session = RenderPlanPoolSession(instance, schedule)

    for index in range(schedule.pass_count):
        session.begin_pass(index)
        session.end_pass(index)

    assert len(created) == 2
    assert instance.diagnostics().reuses == 1
    assert session.active_resources == {}
    assert session.next_pass == schedule.pass_count


def test_pool_session_enforces_pass_order() -> None:
    plan = graph_plan()
    spec = descriptor(size=64)
    schedule = RenderPlanResourceSchedule.from_plan(
        plan,
        {"first": spec, "bridge": spec, "second": spec},
    )
    instance, _, _ = pool()
    session = RenderPlanPoolSession(instance, schedule)

    with pytest.raises(RenderResourcePoolError) as error:
        session.begin_pass(1)
    assert error.value.code == "pass-order"

    session.begin_pass(0)
    with pytest.raises(RenderResourcePoolError) as error:
        session.begin_pass(0)
    assert error.value.code == "pass-active"


def test_pool_session_rolls_back_acquires_if_backend_fails_mid_pass() -> None:
    graph = RenderGraphBuilder()
    graph.add_resource("a", transient=True, size_bytes=10)
    graph.add_resource("b", transient=True, size_bytes=10)
    graph.add_pass("both", writes=("a", "b"), side_effect=True)
    plan = graph.compile()
    a = descriptor("a", 10)
    b = descriptor("b", 10)
    schedule = RenderPlanResourceSchedule.from_plan(plan, {"a": a, "b": b})
    calls = 0

    def create(spec):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise RuntimeError("fail second")
        return spec

    instance = TransientRenderResourcePool(
        create=create,
        destroy=lambda _resource: None,
        max_resources=4,
        max_bytes=100,
    )
    session = RenderPlanPoolSession(instance, schedule)

    with pytest.raises(RenderResourcePoolError) as error:
        session.begin_pass(0)

    assert error.value.code == "create-failed"
    assert session.active_resources == {}
    assert session.next_pass == 0
    assert instance.diagnostics().leased_resources == 0


def test_abort_releases_all_active_graph_resources() -> None:
    plan = graph_plan()
    spec = descriptor(size=64)
    schedule = RenderPlanResourceSchedule.from_plan(
        plan,
        {"first": spec, "bridge": spec, "second": spec},
    )
    instance, _, _ = pool()
    session = RenderPlanPoolSession(instance, schedule)
    session.begin_pass(0)

    session.abort()

    assert session.active_resources == {}
    assert instance.diagnostics().leased_resources == 0


def test_descriptor_validation_is_strict() -> None:
    with pytest.raises(ValueError):
        RenderResourceDescriptor("texture", "rgba8", 0, 4)
    with pytest.raises(TypeError):
        RenderResourceDescriptor("texture", "rgba8", True, 4)
    with pytest.raises(ValueError):
        RenderResourceDescriptor("", "rgba8", 4, 4)


def test_handle_validation_is_strict() -> None:
    with pytest.raises(ValueError):
        RenderResourceHandle(0, 0)
    with pytest.raises(TypeError):
        RenderResourceHandle(True, 1)


def test_diagnostics_are_portable_numeric_data() -> None:
    instance, _, _ = pool()
    lease = instance.acquire(descriptor())
    instance.release(lease.handle)

    portable = instance.diagnostics().portable()

    assert portable["creates"] == 1
    assert portable["releases"] == 1
    assert portable["resident_resources"] == 1
