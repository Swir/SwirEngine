from __future__ import annotations

import threading

import pytest

from swirengine.frame_budget17 import FrameTimeBudgetController
from swirengine.performance15 import PerformanceDiagnostics2


class FakeClock:
    def __init__(self) -> None:
        self.seconds = 0.0

    def __call__(self) -> float:
        return self.seconds

    def advance_ms(self, value: float) -> None:
        self.seconds += value / 1000.0


def test_priority_order_and_global_item_budget_are_bounded() -> None:
    calls: list[tuple[str, int]] = []
    controller = FrameTimeBudgetController(
        frame_budget_ms=10.0,
        max_items_per_frame=3,
        max_drain_calls_per_frame=8,
        clock=FakeClock(),
    )
    controller.register(
        "low",
        lambda limit: calls.append(("low", limit)) or limit,
        priority=0,
        max_items_per_frame=3,
    )
    controller.register(
        "high",
        lambda limit: calls.append(("high", limit)) or limit,
        priority=10,
        max_items_per_frame=3,
    )

    frame = controller.run_frame()

    assert calls == [("high", 3)]
    assert frame.items_drained == 3
    assert frame.drain_calls == 1
    assert frame.budget_exhausted
    assert frame.deferred_lanes == ("low",)


def test_reserved_work_rotates_start_lane_across_tight_frames() -> None:
    clock = FakeClock()
    calls: list[str] = []

    def drain(name: str):
        def callback(limit: int) -> int:
            assert limit == 1
            calls.append(name)
            clock.advance_ms(0.6)
            return 1

        return callback

    controller = FrameTimeBudgetController(
        frame_budget_ms=0.5,
        max_items_per_frame=8,
        max_drain_calls_per_frame=8,
        clock=clock,
    )
    controller.register("a", drain("a"), reserved_items=1, max_items_per_frame=1)
    controller.register("b", drain("b"), reserved_items=1, max_items_per_frame=1)

    first = controller.run_frame()
    second = controller.run_frame()

    assert calls == ["a", "b"]
    assert first.deferred_lanes == ("b",)
    assert second.deferred_lanes == ("a",)
    assert first.overrun_ms == pytest.approx(0.1)
    assert second.overrun_ms == pytest.approx(0.1)


def test_equal_priority_main_pass_rotates_deterministically() -> None:
    calls: list[str] = []
    controller = FrameTimeBudgetController(
        frame_budget_ms=10.0,
        max_items_per_frame=1,
        max_drain_calls_per_frame=1,
    )
    for name in ("a", "b", "c"):
        controller.register(
            name,
            lambda limit, current=name: calls.append(current) or limit,
            priority=5,
            max_items_per_frame=1,
        )

    controller.run_frame()
    controller.run_frame()
    controller.run_frame()

    assert calls == ["a", "b", "c"]


def test_callback_underfill_marks_lane_exhausted_without_false_deferral() -> None:
    controller = FrameTimeBudgetController(frame_budget_ms=10.0)
    controller.register("assets", lambda limit: min(limit, 2), max_items_per_frame=8)

    frame = controller.run_frame()

    assert frame.items_drained == 2
    assert not frame.budget_exhausted
    assert frame.deferred_lanes == ()
    diagnostics = controller.diagnostics()
    assert diagnostics.lanes["assets"]["exhausted_frames"] == 1


def test_lane_diagnostics_report_full_frame_totals_across_multiple_calls() -> None:
    clock = FakeClock()

    def drain(limit: int) -> int:
        clock.advance_ms(0.1)
        return limit

    controller = FrameTimeBudgetController(frame_budget_ms=5.0, clock=clock)
    controller.register(
        "assets",
        drain,
        max_items_per_frame=3,
        reserved_items=1,
    )

    frame = controller.run_frame()
    diagnostics = controller.diagnostics().lanes["assets"]

    assert frame.items_drained == 3
    assert frame.lane_reports[0].calls == 2
    assert frame.lane_reports[0].elapsed_ms == pytest.approx(0.2)
    assert diagnostics["calls_total"] == 2
    assert diagnostics["items_total"] == 3
    assert diagnostics["last_items"] == 3
    assert diagnostics["last_elapsed_ms"] == pytest.approx(0.2)
    assert diagnostics["max_elapsed_ms"] == pytest.approx(0.2)


def test_callback_failure_is_isolated_and_later_lane_continues() -> None:
    calls: list[str] = []

    def fail(limit: int) -> int:
        calls.append("bad")
        raise RuntimeError("creator drain failed")

    controller = FrameTimeBudgetController(frame_budget_ms=10.0)
    controller.register("bad", fail, priority=10)
    controller.register(
        "good",
        lambda limit: calls.append("good") or 0,
        priority=0,
    )

    frame = controller.run_frame()

    assert calls == ["bad", "good"]
    reports = {report.name: report for report in frame.lane_reports}
    assert reports["bad"].error_type == "RuntimeError"
    assert reports["bad"].error_message == "creator drain failed"
    assert not reports["good"].failed
    assert controller.diagnostics().lane_errors_total == 1


def test_invalid_callback_count_is_isolated() -> None:
    controller = FrameTimeBudgetController(frame_budget_ms=10.0)
    controller.register("invalid", lambda limit: limit + 1)
    controller.register("next", lambda limit: 0)

    frame = controller.run_frame()

    reports = {report.name: report for report in frame.lane_reports}
    assert reports["invalid"].error_type == "ValueError"
    assert reports["next"].calls == 1


def test_configure_disable_unregister_and_lane_limit() -> None:
    controller = FrameTimeBudgetController(max_lanes=2)
    controller.register("a", lambda limit: 0)
    controller.register("b", lambda limit: 0, reserved_items=1, max_items_per_frame=2)
    with pytest.raises(RuntimeError, match="max_lanes"):
        controller.register("c", lambda limit: 0)

    updated = controller.configure(
        "b",
        priority=7,
        max_items_per_frame=4,
        reserved_items=2,
        enabled=False,
    )
    assert updated.priority == 7
    assert updated.max_items_per_frame == 4
    assert updated.reserved_items == 2
    assert not updated.enabled
    assert [lane.name for lane in controller.lanes()] == ["a", "b"]
    assert controller.unregister("a")
    assert not controller.unregister("a")


def test_configuration_and_run_are_owner_thread_only() -> None:
    controller = FrameTimeBudgetController()
    errors: list[BaseException] = []

    def other_thread() -> None:
        for operation in (
            lambda: controller.register("bad", lambda limit: 0),
            controller.run_frame,
        ):
            try:
                operation()
            except BaseException as exc:  # noqa: BLE001 - public thread contract test.
                errors.append(exc)

    thread = threading.Thread(target=other_thread)
    thread.start()
    thread.join(timeout=2.0)

    assert len(errors) == 2
    assert all(isinstance(error, RuntimeError) for error in errors)


def test_lane_configuration_cannot_mutate_reentrantly() -> None:
    controller = FrameTimeBudgetController(clock=FakeClock())
    errors: list[BaseException] = []

    def drain(limit: int) -> int:
        try:
            controller.configure("self", enabled=False)
        except BaseException as exc:  # noqa: BLE001 - public reentrancy contract test.
            errors.append(exc)
        return 0

    controller.register("self", drain)
    controller.run_frame()

    assert len(errors) == 1
    assert isinstance(errors[0], RuntimeError)
    assert "during run_frame" in str(errors[0])


def test_diagnostics_bind_into_performance_diagnostics_2() -> None:
    controller = FrameTimeBudgetController(frame_budget_ms=3.0)
    controller.register("assets", lambda limit: 0, max_items_per_frame=4)
    controller.run_frame()

    performance = PerformanceDiagnostics2(history=2)
    controller.bind_performance(performance)
    performance.begin_frame()
    captured = performance.end_frame(frame_seconds=1.0 / 60.0)

    counters = {(item.domain, item.name): item.value for item in captured.counters}
    assert counters[("frame_budget17", "frames_total")] == 1
    assert counters[("frame_budget17", "lanes.assets.max_items_per_frame")] == 4
    assert counters[("frame_budget17", "registered_lanes")] == 1
    assert controller.unbind_performance(performance)
    assert not controller.unbind_performance(performance)


def test_drain_call_budget_defers_remaining_lanes() -> None:
    calls: list[str] = []
    controller = FrameTimeBudgetController(
        frame_budget_ms=10.0,
        max_items_per_frame=20,
        max_drain_calls_per_frame=1,
    )
    controller.register("a", lambda limit: calls.append("a") or 1, max_items_per_frame=5)
    controller.register("b", lambda limit: calls.append("b") or 1, max_items_per_frame=5)

    frame = controller.run_frame()

    assert calls == ["a"]
    assert frame.drain_calls == 1
    assert frame.budget_exhausted
    assert frame.deferred_lanes == ("b",)


def test_validation_rejects_malformed_budgets() -> None:
    with pytest.raises(ValueError, match="frame_budget_ms"):
        FrameTimeBudgetController(frame_budget_ms=0.0)
    with pytest.raises(TypeError, match="frame_budget_ms"):
        FrameTimeBudgetController(frame_budget_ms=True)
    with pytest.raises(TypeError, match="max_items_per_frame"):
        FrameTimeBudgetController(max_items_per_frame=True)

    controller = FrameTimeBudgetController()
    with pytest.raises(ValueError, match="reserved_items"):
        controller.register(
            "bad",
            lambda limit: 0,
            max_items_per_frame=1,
            reserved_items=2,
        )
    with pytest.raises(TypeError, match="priority"):
        controller.register("bad-priority", lambda limit: 0, priority=True)

    controller.register("valid", lambda limit: 0)
    with pytest.raises(TypeError, match="enabled"):
        controller.configure("valid", enabled=1)  # type: ignore[arg-type]
