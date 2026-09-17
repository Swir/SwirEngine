from __future__ import annotations

from time import perf_counter

from swirengine.frame_budget17 import FrameTimeBudgetController

FRAMES = 10_000
LANES = 4
ITEMS_PER_LANE = 8
EXPECTED_CALLS = FRAMES * LANES
EXPECTED_ITEMS = EXPECTED_CALLS * ITEMS_PER_LANE
BUDGET_SECONDS = 5.0


def main() -> None:
    calls = [0 for _ in range(LANES)]

    def make_drain(index: int):
        def drain(limit: int) -> int:
            calls[index] += 1
            return limit

        return drain

    controller = FrameTimeBudgetController(
        frame_budget_ms=50.0,
        max_items_per_frame=LANES * ITEMS_PER_LANE,
        max_drain_calls_per_frame=LANES,
        max_lanes=LANES,
    )
    for index in range(LANES):
        controller.register(
            f"lane-{index}",
            make_drain(index),
            priority=0,
            max_items_per_frame=ITEMS_PER_LANE,
        )

    started = perf_counter()
    for _ in range(FRAMES):
        frame = controller.run_frame()
        if frame.items_drained != LANES * ITEMS_PER_LANE:
            raise RuntimeError("frame budget workload failed to drain its deterministic item budget")
        if frame.drain_calls != LANES:
            raise RuntimeError("frame budget workload changed its deterministic drain-call count")
    elapsed = perf_counter() - started
    diagnostics = controller.diagnostics()

    if sum(calls) != EXPECTED_CALLS:
        raise RuntimeError("frame budget workload did not invoke every expected lane")
    if diagnostics.drain_calls_total != EXPECTED_CALLS:
        raise RuntimeError("frame budget diagnostics reported an unexpected drain-call count")
    if diagnostics.items_drained_total != EXPECTED_ITEMS:
        raise RuntimeError("frame budget diagnostics reported an unexpected item count")
    if diagnostics.lane_errors_total != 0:
        raise RuntimeError("frame budget workload unexpectedly reported lane errors")
    if elapsed >= BUDGET_SECONDS:
        raise RuntimeError(
            f"frame budget workload exceeded {BUDGET_SECONDS:.1f}s budget: {elapsed:.4f}s"
        )

    print(
        "frame_budget_1_7: "
        f"{FRAMES} frames / {EXPECTED_CALLS} drain calls / {EXPECTED_ITEMS} items "
        f"in {elapsed:.4f}s (budget {BUDGET_SECONDS:.1f}s)"
    )


if __name__ == "__main__":
    main()
