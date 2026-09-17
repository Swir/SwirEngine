from __future__ import annotations

import threading

import pytest

from swirengine.work_graph17 import (
    StreamingWorkGraph,
    StreamingWorkGraphError,
    WorkAffinity,
    WorkGraphRejectedError,
    WorkNodeState,
    WorkPhase,
)


def test_four_stage_pipeline_preserves_dependency_values_and_thread_affinity() -> None:
    main_thread = threading.get_ident()
    threads: dict[str, int] = {}
    graph = StreamingWorkGraph(max_workers=2)

    def prefetch(context):
        threads["prefetch"] = threading.get_ident()
        assert context.affinity is WorkAffinity.BACKGROUND
        return b"raw"

    def decode(context):
        threads["decode"] = threading.get_ident()
        assert context.dependency_values["prefetch"] == b"raw"
        return context.dependency_values["prefetch"].decode().upper()

    def instantiate(context):
        threads["instantiate"] = threading.get_ident()
        assert context.affinity is WorkAffinity.MAIN_THREAD
        return f"entity:{context.dependency_values['decode']}"

    def unload(context):
        threads["unload"] = threading.get_ident()
        return f"released:{context.dependency_values['instantiate']}"

    graph.add("prefetch", WorkPhase.PREFETCH, prefetch)
    graph.add("decode", WorkPhase.DECODE, decode, dependencies=["prefetch"])
    graph.add("instantiate", WorkPhase.INSTANTIATE, instantiate, dependencies=["decode"])
    graph.add("unload", WorkPhase.UNLOAD, unload, dependencies=["instantiate"])

    try:
        results = graph.run_until_complete(timeout=2.0)
    finally:
        graph.shutdown()

    assert all(result.successful for result in results)
    assert results[-1].value == "released:entity:RAW"
    assert threads["prefetch"] != main_thread
    assert threads["decode"] != main_thread
    assert threads["instantiate"] == main_thread
    assert threads["unload"] == main_thread


def test_poll_enforces_main_thread_callback_budget() -> None:
    graph = StreamingWorkGraph()
    calls: list[str] = []
    for node_id in ("first", "second", "third"):
        graph.add(
            node_id,
            WorkPhase.INSTANTIATE,
            lambda _ctx, value=node_id: calls.append(value),
        )
    graph.start()

    try:
        graph.poll(max_items=1)
        diagnostics = graph.diagnostics()
        assert len(calls) == 1
        assert diagnostics.main_thread_callbacks_last_poll == 1
        assert diagnostics.ready_main == 2
        graph.poll(max_items=1)
        assert len(calls) == 2
        graph.poll(max_items=1)
        assert len(calls) == 3
        assert graph.complete
    finally:
        graph.shutdown()


def test_poll_enforces_one_shared_background_submission_budget() -> None:
    graph = StreamingWorkGraph(
        max_workers=1,
        max_pending_background=8,
        max_background_submissions_per_poll=1,
    )
    graph.add("root", WorkPhase.INSTANTIATE, lambda _ctx: "ready")
    for index in range(3):
        graph.add(
            f"decode:{index}",
            WorkPhase.DECODE,
            lambda _ctx, value=index: value,
            dependencies=["root"],
        )
    graph.start()

    try:
        assert graph.diagnostics().submitted_background_total == 0
        graph.poll(max_items=1)
        diagnostics = graph.diagnostics()
        assert diagnostics.background_submissions_last_poll == 1
        assert diagnostics.submitted_background_total == 1
        assert diagnostics.scheduled == 1
        assert diagnostics.waiting == 2
    finally:
        graph.shutdown()


def test_higher_priority_main_work_runs_first_with_fifo_tie_breaking() -> None:
    graph = StreamingWorkGraph()
    order: list[str] = []
    graph.add(
        "low", WorkPhase.INSTANTIATE, lambda _ctx: order.append("low"), priority=0
    )
    graph.add(
        "high-a",
        WorkPhase.INSTANTIATE,
        lambda _ctx: order.append("high-a"),
        priority=5,
    )
    graph.add(
        "high-b",
        WorkPhase.INSTANTIATE,
        lambda _ctx: order.append("high-b"),
        priority=5,
    )
    graph.start()

    try:
        graph.poll(max_items=3)
    finally:
        graph.shutdown()

    assert order == ["high-a", "high-b", "low"]


def test_failure_blocks_only_dependent_branch() -> None:
    graph = StreamingWorkGraph(max_workers=2)

    def fail(_context):
        raise ValueError("decode exploded")

    graph.add("bad", WorkPhase.DECODE, fail)
    graph.add(
        "blocked",
        WorkPhase.INSTANTIATE,
        lambda _ctx: "never",
        dependencies=["bad"],
    )
    graph.add("independent", WorkPhase.INSTANTIATE, lambda _ctx: "ok")

    try:
        graph.run_until_complete(timeout=2.0)
        bad = graph.result("bad")
        blocked = graph.result("blocked")
        independent = graph.result("independent")
    finally:
        graph.shutdown()

    assert bad.state is WorkNodeState.FAILED
    assert bad.error_type == "ValueError"
    assert blocked.state is WorkNodeState.BLOCKED
    assert blocked.error_type == "DependencyBlocked"
    assert independent.successful
    assert independent.value == "ok"


def test_cascade_cancel_does_not_cancel_independent_branch() -> None:
    gate = threading.Event()
    graph = StreamingWorkGraph(max_workers=1)

    def slow(context):
        gate.wait(timeout=0.2)
        if context.cancelled:
            return "discarded"
        return "unexpected"

    graph.add("root", WorkPhase.PREFETCH, slow)
    graph.add(
        "child", WorkPhase.DECODE, lambda _ctx: "child", dependencies=["root"]
    )
    graph.add("independent", WorkPhase.INSTANTIATE, lambda _ctx: "ok")
    graph.start()

    try:
        cancelled = graph.cancel("root", cascade=True)
        gate.set()
        assert cancelled == ("root", "child")
        graph.run_until_complete(timeout=2.0)
        assert graph.result("root").state is WorkNodeState.CANCELLED
        assert graph.result("child").state is WorkNodeState.CANCELLED
        assert graph.result("independent").successful
    finally:
        gate.set()
        graph.shutdown()


def test_cancel_without_cascade_blocks_dependent_after_cancelled_root() -> None:
    graph = StreamingWorkGraph()
    graph.add("root", WorkPhase.INSTANTIATE, lambda _ctx: "root")
    graph.add(
        "child", WorkPhase.INSTANTIATE, lambda _ctx: "child", dependencies=["root"]
    )
    graph.start()

    try:
        assert graph.cancel("root", cascade=False) == ("root",)
        graph.run_until_complete(timeout=2.0)
        assert graph.result("root").state is WorkNodeState.CANCELLED
        assert graph.result("child").state is WorkNodeState.BLOCKED
    finally:
        graph.shutdown()


def test_graph_capacity_and_dependency_validation_are_atomic() -> None:
    graph = StreamingWorkGraph(max_nodes=2)
    graph.add("one", WorkPhase.PREFETCH, lambda _ctx: 1)

    with pytest.raises(WorkGraphRejectedError) as missing:
        graph.add("bad", WorkPhase.DECODE, lambda _ctx: 2, dependencies=["missing"])
    assert missing.value.code == "missing_dependency"

    graph.add("two", WorkPhase.DECODE, lambda _ctx: 2, dependencies=["one"])
    with pytest.raises(WorkGraphRejectedError) as capacity:
        graph.add("three", WorkPhase.INSTANTIATE, lambda _ctx: 3)
    assert capacity.value.code == "graph_capacity"
    assert graph.diagnostics().total_nodes == 2
    graph.shutdown()


def test_nodes_cannot_be_added_after_start() -> None:
    graph = StreamingWorkGraph()
    graph.add("one", WorkPhase.INSTANTIATE, lambda _ctx: 1)
    graph.start()
    try:
        with pytest.raises(WorkGraphRejectedError) as rejected:
            graph.add("late", WorkPhase.INSTANTIATE, lambda _ctx: 2)
        assert rejected.value.code == "already_started"
    finally:
        graph.shutdown()


def test_empty_graph_cannot_start() -> None:
    graph = StreamingWorkGraph()
    try:
        with pytest.raises(StreamingWorkGraphError):
            graph.start()
    finally:
        graph.shutdown()


def test_diagnostics_are_payload_free_and_report_progress() -> None:
    secret = object()
    graph = StreamingWorkGraph()
    graph.add("node", WorkPhase.INSTANTIATE, lambda _ctx: secret)
    graph.start()
    try:
        before = graph.diagnostics().portable()
        assert before["progress"] == 0.0
        assert "value" not in before
        graph.poll(max_items=1)
        after = graph.diagnostics().portable()
        assert after["progress"] == 1.0
        assert after["complete"] is True
        assert graph.result("node").value is secret
        assert "value" not in after
    finally:
        graph.shutdown()


def test_phase_strings_are_normalized_and_affinity_is_fixed() -> None:
    graph = StreamingWorkGraph()
    prefetch = graph.add("prefetch", "prefetch", lambda _ctx: None)
    unload = graph.add(
        "unload", "unload", lambda _ctx: None, dependencies=["prefetch"]
    )
    assert prefetch.phase is WorkPhase.PREFETCH
    assert prefetch.affinity is WorkAffinity.BACKGROUND
    assert unload.affinity is WorkAffinity.MAIN_THREAD
    graph.shutdown()


def test_run_until_complete_can_start_graph_automatically() -> None:
    graph = StreamingWorkGraph()
    graph.add("node", WorkPhase.INSTANTIATE, lambda _ctx: 42)
    try:
        results = graph.run_until_complete(timeout=1.0)
        assert results[0].value == 42
        assert graph.complete
    finally:
        graph.shutdown()
