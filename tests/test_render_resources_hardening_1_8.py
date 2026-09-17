import pytest

from swirengine.render_graph18 import RenderGraphBuilder
from swirengine.render_resources18 import (
    RenderPlanPoolSession,
    RenderPlanResourceSchedule,
    RenderResourceDescriptor,
    RenderResourcePoolError,
    TransientRenderResourcePool,
)


def descriptor(name: str, size: int = 64) -> RenderResourceDescriptor:
    return RenderResourceDescriptor("texture", name, 4, 4, size_bytes=size)


def make_pool(*, destroy=None):
    created: list[object] = []

    def create(_spec):
        value = object()
        created.append(value)
        return value

    return (
        TransientRenderResourcePool(
            create=create,
            destroy=destroy or (lambda _resource: None),
            max_resources=4,
            max_bytes=1024,
        ),
        created,
    )


def test_handle_from_another_pool_is_rejected_even_when_slot_and_generation_match() -> None:
    first, _ = make_pool()
    second, _ = make_pool()
    first_lease = first.acquire(descriptor("a"))
    second_lease = second.acquire(descriptor("a"))

    assert first_lease.handle.slot == second_lease.handle.slot == 0
    assert first_lease.handle.generation == second_lease.handle.generation == 1

    with pytest.raises(RenderResourcePoolError) as error:
        second.release(first_lease.handle)

    assert error.value.code == "stale-handle"
    assert second.get(second_lease.handle) is second_lease.resource


def test_failed_eviction_keeps_idle_resource_reclaimable_for_explicit_retry() -> None:
    attempts = 0

    def destroy(_resource):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise RuntimeError("temporary device teardown failure")

    instance = TransientRenderResourcePool(
        create=lambda spec: {"format": spec.format},
        destroy=destroy,
        max_resources=1,
        max_bytes=128,
    )
    first = instance.acquire(descriptor("a"))
    instance.release(first.handle)

    with pytest.raises(RenderResourcePoolError) as error:
        instance.acquire(descriptor("b"))

    assert error.value.code == "destroy-failed"
    after_failure = instance.diagnostics()
    assert after_failure.resident_resources == 1
    assert after_failure.free_resources == 1
    assert after_failure.destroy_failures == 1

    replacement = instance.acquire(descriptor("b"))
    assert replacement.descriptor.format == "b"
    assert attempts == 2
    assert instance.diagnostics().resident_resources == 1


def test_factory_returning_none_is_rejected_without_residency_mutation() -> None:
    instance = TransientRenderResourcePool(
        create=lambda _spec: None,
        destroy=lambda _resource: None,
        max_resources=2,
        max_bytes=128,
    )

    with pytest.raises(RenderResourcePoolError) as error:
        instance.acquire(descriptor("a"))

    assert error.value.code == "create-failed"
    diagnostics = instance.diagnostics()
    assert diagnostics.create_failures == 1
    assert diagnostics.resident_resources == 0
    assert diagnostics.resident_bytes == 0


def test_trim_destroy_failure_does_not_report_resource_as_freed() -> None:
    instance = TransientRenderResourcePool(
        create=lambda spec: {"format": spec.format},
        destroy=lambda _resource: (_ for _ in ()).throw(RuntimeError("destroy failed")),
        max_resources=2,
        max_bytes=128,
    )
    lease = instance.acquire(descriptor("a"))
    instance.release(lease.handle)

    with pytest.raises(RenderResourcePoolError) as error:
        instance.trim(target_resources=0, target_bytes=0)

    assert error.value.code == "destroy-failed"
    diagnostics = instance.diagnostics()
    assert diagnostics.resident_resources == 1
    assert diagnostics.resident_bytes == 64
    assert diagnostics.free_resources == 1


def test_abort_releases_overlapping_render_graph_leases() -> None:
    graph = RenderGraphBuilder()
    graph.add_resource("source", external=True)
    graph.add_resource("a", transient=True, size_bytes=64)
    graph.add_resource("b", transient=True, size_bytes=64)
    graph.add_pass("produce-a", reads=("source",), writes=("a",))
    graph.add_pass("produce-b", reads=("a",), writes=("b",), side_effect=True)
    plan = graph.compile()
    spec = descriptor("rgba8")
    schedule = RenderPlanResourceSchedule.from_plan(plan, {"a": spec, "b": spec})
    instance, _ = make_pool()
    session = RenderPlanPoolSession(instance, schedule)

    session.begin_pass(0)
    session.end_pass(0)
    session.begin_pass(1)
    assert instance.diagnostics().leased_resources == 2

    session.abort()

    assert session.active_resources == {}
    assert instance.diagnostics().leased_resources == 0
