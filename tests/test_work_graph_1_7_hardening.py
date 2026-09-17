from __future__ import annotations

import threading

import pytest

from swirengine.work_graph17 import (
    StreamingWorkGraph,
    WorkGraphRejectedError,
    WorkNodeState,
    WorkPhase,
)


def test_background_submission_uses_priority_then_authored_order() -> None:
    gate = threading.Event()
    execution_order: list[str] = []
    graph = StreamingWorkGraph(
        max_workers=1,
        max_pending_background=8,
        max_background_submissions_per_poll=8,
    )
    graph.add("root", WorkPhase.INSTANTIATE, lambda _ctx: "ready")

    def decode(_context, name: str) -> str:
        execution_order.append(name)
        gate.wait(timeout=0.2)
        return name

    graph.add(
        "low",
        WorkPhase.DECODE,
        lambda ctx: decode(ctx, "low"),
        dependencies=["root"],
        priority=0,
    )
    graph.add(
        "high-a",
        WorkPhase.DECODE,
        lambda ctx: decode(ctx, "high-a"),
        dependencies=["root"],
        priority=5,
    )
    graph.add(
        "high-b",
        WorkPhase.DECODE,
        lambda ctx: decode(ctx, "high-b"),
        dependencies=["root"],
        priority=5,
    )
    graph.start()

    try:
        graph.poll(max_items=1)
        gate.set()
        graph.run_until_complete(timeout=2.0)
    finally:
        gate.set()
        graph.shutdown()

    assert execution_order == ["high-a", "high-b", "low"]


def test_dependency_values_mapping_is_read_only() -> None:
    graph = StreamingWorkGraph()
    graph.add("source", WorkPhase.INSTANTIATE, lambda _ctx: 7)

    def consume(context) -> int:
        with pytest.raises(TypeError):
            context.dependency_values["source"] = 99
        return int(context.dependency_values["source"])

    graph.add(
        "consumer",
        WorkPhase.INSTANTIATE,
        consume,
        dependencies=["source"],
    )

    try:
        results = graph.run_until_complete(timeout=1.0)
    finally:
        graph.shutdown()

    assert all(result.successful for result in results)
    assert results[-1].value == 7


def test_main_callback_failure_isolated_from_independent_branch() -> None:
    graph = StreamingWorkGraph()

    def fail(_context) -> None:
        raise RuntimeError("instantiate failed")

    graph.add("bad", WorkPhase.INSTANTIATE, fail)
    graph.add(
        "blocked",
        WorkPhase.UNLOAD,
        lambda _ctx: "never",
        dependencies=["bad"],
    )
    graph.add("independent", WorkPhase.INSTANTIATE, lambda _ctx: "ok")

    try:
        graph.run_until_complete(timeout=1.0)
        bad = graph.result("bad")
        blocked = graph.result("blocked")
        independent = graph.result("independent")
    finally:
        graph.shutdown()

    assert bad.state is WorkNodeState.FAILED
    assert bad.error_type == "RuntimeError"
    assert blocked.state is WorkNodeState.BLOCKED
    assert independent.successful
    assert independent.value == "ok"


def test_self_and_duplicate_dependencies_are_rejected_without_graph_mutation() -> None:
    graph = StreamingWorkGraph()
    graph.add("source", WorkPhase.PREFETCH, lambda _ctx: 1)

    with pytest.raises(WorkGraphRejectedError) as self_dependency:
        graph.add(
            "self",
            WorkPhase.DECODE,
            lambda _ctx: 2,
            dependencies=["self"],
        )
    assert self_dependency.value.code == "self_dependency"

    with pytest.raises(WorkGraphRejectedError) as duplicate_dependency:
        graph.add(
            "duplicate",
            WorkPhase.DECODE,
            lambda _ctx: 2,
            dependencies=["source", "source"],
        )
    assert duplicate_dependency.value.code == "duplicate_dependency"
    assert graph.diagnostics().total_nodes == 1
    graph.shutdown()
