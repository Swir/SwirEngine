from __future__ import annotations

import threading
import time

import pytest

from swirengine.jobs17 import JobRejectedError, JobScheduler, JobSchedulerError, JobState


def test_priority_then_fifo_dispatch_is_deterministic_after_worker_frees() -> None:
    gate = threading.Event()
    started = threading.Event()
    order: list[str] = []

    def blocker(context):
        started.set()
        assert gate.wait(2.0)
        order.append(context.job_id)
        return "blocker"

    def record(context):
        order.append(context.job_id)
        return context.job_id

    with JobScheduler(max_workers=1, max_pending=8) as scheduler:
        scheduler.submit("blocker", blocker)
        assert started.wait(1.0)
        scheduler.submit("low", record, priority=-5)
        scheduler.submit("high-a", record, priority=10)
        scheduler.submit("high-b", record, priority=10)
        gate.set()
        outcomes = scheduler.wait_all(timeout=3.0)

    assert [outcome.state for outcome in outcomes] == [JobState.SUCCEEDED] * 4
    assert order == ["blocker", "high-a", "high-b", "low"]


def test_dependencies_run_only_after_success_and_failure_blocks_descendants() -> None:
    executed: list[str] = []

    def ok(context):
        executed.append(context.job_id)
        return context.sequence

    def fail(context):
        executed.append(context.job_id)
        raise RuntimeError("expected failure")

    with JobScheduler(max_workers=2, max_pending=10) as scheduler:
        scheduler.submit("root", ok)
        scheduler.submit("child", ok, dependencies=["root"])
        scheduler.submit("failure", fail)
        scheduler.submit("blocked", ok, dependencies=["failure"])
        scheduler.submit("blocked-child", ok, dependencies=["blocked"])
        scheduler.wait_all(timeout=3.0)

        assert scheduler.state("root") is JobState.SUCCEEDED
        assert scheduler.state("child") is JobState.SUCCEEDED
        assert scheduler.state("failure") is JobState.FAILED
        assert scheduler.state("blocked") is JobState.BLOCKED
        assert scheduler.state("blocked-child") is JobState.BLOCKED
        assert scheduler.outcome("failure").error_type == "RuntimeError"
        assert scheduler.outcome("blocked").error_type == "DependencyBlocked"

    assert "blocked" not in executed
    assert "blocked-child" not in executed
    assert executed.index("root") < executed.index("child")


def test_missing_duplicate_and_self_dependencies_are_rejected_atomically() -> None:
    with JobScheduler(max_workers=1, max_pending=4) as scheduler:
        with pytest.raises(JobRejectedError) as missing:
            scheduler.submit("child", lambda context: None, dependencies=["missing"])
        assert missing.value.code == "missing_dependency"

        scheduler.submit("root", lambda context: None)
        with pytest.raises(JobRejectedError) as duplicate:
            scheduler.submit("dup", lambda context: None, dependencies=["root", "root"])
        assert duplicate.value.code == "duplicate_dependency"

        with pytest.raises(JobRejectedError) as self_dependency:
            scheduler.submit("self", lambda context: None, dependencies=["self"])
        assert self_dependency.value.code == "self_dependency"

        assert scheduler.diagnostics().accepted_total == 1
        assert scheduler.diagnostics().rejected_total == 3


def test_backpressure_is_hard_and_does_not_consume_job_id() -> None:
    gate = threading.Event()
    started = threading.Event()

    def blocker(context):
        started.set()
        assert gate.wait(2.0)
        return context.job_id

    with JobScheduler(max_workers=1, max_pending=2) as scheduler:
        scheduler.submit("running", blocker)
        assert started.wait(1.0)
        scheduler.submit("queued", lambda context: context.job_id)
        with pytest.raises(JobRejectedError) as rejected:
            scheduler.submit("overflow", lambda context: context.job_id)
        assert rejected.value.code == "backpressure"
        gate.set()
        scheduler.wait_all(timeout=3.0)
        scheduler.submit("overflow", lambda context: context.job_id)
        assert scheduler.wait("overflow", timeout=2.0).successful


def test_pending_and_running_jobs_support_cooperative_cancellation() -> None:
    gate = threading.Event()
    started = threading.Event()
    queued_executed = False

    def running(context):
        started.set()
        while not context.cancelled:
            time.sleep(0.001)
        context.raise_if_cancelled()

    def queued(context):
        nonlocal queued_executed
        queued_executed = True
        gate.set()
        return context.job_id

    with JobScheduler(max_workers=1, max_pending=4) as scheduler:
        scheduler.submit("running", running)
        assert started.wait(1.0)
        scheduler.submit("queued", queued)
        assert scheduler.cancel("queued") is True
        assert scheduler.cancel("running") is True
        assert scheduler.wait("queued", timeout=2.0).state is JobState.CANCELLED
        assert scheduler.wait("running", timeout=2.0).state is JobState.CANCELLED
        assert scheduler.cancel("queued") is False

    assert queued_executed is False
    assert gate.is_set() is False


def test_worker_failure_isolated_and_later_job_still_runs() -> None:
    with JobScheduler(max_workers=1, max_pending=4) as scheduler:
        scheduler.submit("bad", lambda context: 1 / 0)
        scheduler.submit("good", lambda context: 42)
        assert scheduler.wait("bad", timeout=2.0).state is JobState.FAILED
        good = scheduler.wait("good", timeout=2.0)

    assert good.successful
    assert good.value == 42


def test_drain_is_bounded_ordered_and_diagnostics_do_not_include_payloads() -> None:
    secret = "payload-that-must-not-enter-diagnostics"
    with JobScheduler(max_workers=2, max_pending=8) as scheduler:
        for index in range(4):
            scheduler.submit(f"job-{index}", lambda context, value=index: (secret, value))
        scheduler.wait_all(timeout=2.0)
        first = scheduler.drain_completed(max_items=2)
        second = scheduler.drain_completed(max_items=2)
        diagnostics = scheduler.diagnostics()

        assert [outcome.sequence for outcome in first] == sorted(
            outcome.sequence for outcome in first
        )
        assert [outcome.sequence for outcome in second] == sorted(
            outcome.sequence for outcome in second
        )
        assert len(first) == 2
        assert len(second) == 2
        assert scheduler.drain_completed() == ()
        assert diagnostics.undrained == 0
        assert diagnostics.delivered_total == 4
        assert secret not in repr(diagnostics.portable())


def test_forget_requires_delivery_and_no_retained_dependents() -> None:
    with JobScheduler(max_workers=1, max_pending=4) as scheduler:
        scheduler.submit("root", lambda context: 1)
        scheduler.submit("child", lambda context: 2, dependencies=["root"])
        scheduler.wait_all(timeout=2.0)

        with pytest.raises(JobSchedulerError):
            scheduler.forget("root")
        scheduler.drain_completed()
        with pytest.raises(JobSchedulerError):
            scheduler.forget("root")
        scheduler.forget("child")
        scheduler.forget("root")
        with pytest.raises(KeyError):
            scheduler.state("root")


def test_closed_scheduler_rejects_new_work() -> None:
    scheduler = JobScheduler(max_workers=1, max_pending=2)
    scheduler.shutdown()
    with pytest.raises(JobRejectedError) as rejected:
        scheduler.submit("late", lambda context: None)
    assert rejected.value.code == "closed"


def test_nonblocking_shutdown_cancels_not_started_work_without_stranding_it() -> None:
    gate = threading.Event()
    started = threading.Event()

    def running(context):
        started.set()
        assert gate.wait(2.0)
        return "done"

    scheduler = JobScheduler(max_workers=1, max_pending=4)
    scheduler.submit("running", running)
    assert started.wait(1.0)
    scheduler.submit("queued", lambda context: "should-not-run")
    scheduler.shutdown(wait=False, cancel_pending=False)

    assert scheduler.state("queued") is JobState.CANCELLED
    gate.set()
    assert scheduler.wait("running", timeout=2.0).state is JobState.SUCCEEDED
    assert scheduler.wait_all(timeout=2.0)[1].state is JobState.CANCELLED
