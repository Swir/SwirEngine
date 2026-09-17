from __future__ import annotations

from collections import deque

from swirengine.frame_budget17 import FrameTimeBudgetController
from swirengine.performance15 import PerformanceDiagnostics2


def queue_drain(queue: deque[str], label: str):
    def drain(limit: int) -> int:
        consumed = min(limit, len(queue))
        for _ in range(consumed):
            queue.popleft()
        if consumed:
            print(f"{label}: drained {consumed}, remaining {len(queue)}")
        return consumed

    return drain


def main() -> None:
    shader_finalize = deque(f"shader-{index}" for index in range(7))
    scene_activation = deque(f"scene-{index}" for index in range(5))
    save_commits = deque(f"save-{index}" for index in range(3))

    controller = FrameTimeBudgetController(
        frame_budget_ms=2.0,
        max_items_per_frame=6,
        max_drain_calls_per_frame=6,
    )
    controller.register(
        "shader_finalize",
        queue_drain(shader_finalize, "shader"),
        priority=20,
        max_items_per_frame=3,
        reserved_items=1,
    )
    controller.register(
        "scene_activation",
        queue_drain(scene_activation, "scene"),
        priority=10,
        max_items_per_frame=2,
        reserved_items=1,
    )
    controller.register(
        "save_commits",
        queue_drain(save_commits, "save"),
        priority=0,
        max_items_per_frame=1,
        reserved_items=1,
    )

    performance = PerformanceDiagnostics2(history=8)
    controller.bind_performance(performance)

    for _ in range(8):
        if not (shader_finalize or scene_activation or save_commits):
            break
        frame = controller.run_frame()
        performance.begin_frame()
        captured = performance.end_frame(frame_seconds=1.0 / 60.0)
        budget_counters = {
            metric.name: metric.value
            for metric in captured.counters
            if metric.domain == "frame_budget17"
        }
        print(
            "frame_budget",
            {
                "frame": frame.frame_index,
                "items": frame.items_drained,
                "calls": frame.drain_calls,
                "deferred": frame.deferred_lanes,
                "budget_exhausted": frame.budget_exhausted,
                "diagnostics_items": budget_counters["last_frame_items"],
            },
        )

    if shader_finalize or scene_activation or save_commits:
        raise RuntimeError("demo queues did not drain within the bounded frame sequence")


if __name__ == "__main__":
    main()
