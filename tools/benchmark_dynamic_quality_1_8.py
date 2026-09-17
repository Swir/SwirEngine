from __future__ import annotations

from time import perf_counter

from swirengine.render_quality18 import (
    DynamicQualityController,
    RenderQualityPolicy,
    RenderQualityStep,
)

FRAMES = 200_000
LIMIT_SECONDS = 5.0


def main() -> None:
    controller = DynamicQualityController(
        (
            RenderQualityStep("ultra", 1.0, 1.0),
            RenderQualityStep("high", 0.9, 0.9),
            RenderQualityStep("medium", 0.75, 0.75),
            RenderQualityStep("low", 0.6, 0.55),
        ),
        policy=RenderQualityPolicy(
            target_frame_ms=16.6667,
            degrade_ratio=1.06,
            recover_ratio=0.78,
            degrade_frames=4,
            recover_frames=24,
            cooldown_frames=10,
            sample_window=6,
        ),
    )
    started = perf_counter()
    changed = 0
    for index in range(FRAMES):
        phase = index % 240
        if phase < 80:
            frame_ms, gpu_ms = 22.0, 20.0
        elif phase < 160:
            frame_ms, gpu_ms = 15.5, 14.0
        else:
            frame_ms, gpu_ms = 9.5, 8.5
        decision = controller.observe(frame_ms, gpu_ms=gpu_ms)
        changed += int(decision.changed)
    elapsed = perf_counter() - started
    diagnostics = controller.diagnostics()
    assert diagnostics.frames_observed == FRAMES
    assert diagnostics.changes_total == changed
    assert 0 <= diagnostics.current_step < diagnostics.step_count
    assert elapsed < LIMIT_SECONDS, (
        f"dynamic quality workload exceeded {LIMIT_SECONDS:.1f}s ceiling: {elapsed:.4f}s"
    )
    print(
        f"dynamic quality workload: {FRAMES} frames; {changed} transitions; "
        f"final={controller.current_step.name}; {elapsed:.4f}s"
    )


if __name__ == "__main__":
    main()
