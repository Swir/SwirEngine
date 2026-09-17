from __future__ import annotations

from time import perf_counter

from swirengine.render_graph18 import RenderGraphBuilder
from swirengine.render_timing18 import GpuTimingRecorder

FRAMES = 500
PASSES = 128
LIMIT_SECONDS = 5.0


class ImmediateProvider:
    def begin(self, frame_index: int, pass_name: str) -> object | None:
        return frame_index, pass_name

    def end(self, token: object) -> None:
        return None

    def poll(self, token: object) -> float | None:
        _frame, pass_name = token
        index = int(str(pass_name).split("-")[1])
        return (index + 1) * 0.000001


def build_plan():
    graph = RenderGraphBuilder(max_passes=PASSES)
    previous = None
    for index in range(PASSES):
        name = f"pass-{index}"
        graph.add_pass(name, depends_on=() if previous is None else (previous,))
        previous = name
    return graph.compile()


def main() -> None:
    plan = build_plan()
    recorder = GpuTimingRecorder(
        ImmediateProvider(),
        history=FRAMES,
        max_passes_per_frame=PASSES,
        max_pending_queries=PASSES * 2,
    )

    started = perf_counter()
    for frame_index in range(FRAMES):
        recorder.begin_frame(plan, frame_index=frame_index)
        for pass_name in plan.passes:
            recorder.begin_pass(pass_name)
            recorder.end_pass()
        recorder.end_frame()
        committed = recorder.poll_ready(max_queries=PASSES)
        if len(committed) != 1:
            raise SystemExit("GPU timing workload failed to resolve one frame")
    elapsed = perf_counter() - started

    diagnostics = recorder.diagnostics()
    expected_queries = FRAMES * PASSES
    if diagnostics.resolved_queries != expected_queries:
        raise SystemExit(
            f"resolved query mismatch: {diagnostics.resolved_queries} != {expected_queries}"
        )
    if elapsed >= LIMIT_SECONDS:
        raise SystemExit(
            f"GPU timing workload regression: {elapsed:.4f}s >= {LIMIT_SECONDS:.1f}s"
        )

    print(
        "gpu-timing-capture workload:",
        f"{FRAMES} frames x {PASSES} passes = {expected_queries} queries;",
        f"{elapsed:.4f}s;",
        f"history={diagnostics.history_frames};",
        f"pending={diagnostics.pending_queries}",
    )


if __name__ == "__main__":
    main()
