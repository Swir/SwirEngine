from swirengine.render_quality18 import (
    DynamicQualityController,
    RenderQualityPolicy,
    default_render_quality_steps,
)


def main() -> None:
    controller = DynamicQualityController(
        default_render_quality_steps(),
        policy=RenderQualityPolicy(
            target_frame_ms=16.6667,
            degrade_frames=2,
            recover_frames=4,
            cooldown_frames=1,
            sample_window=2,
        ),
    )

    print("start:", controller.current_step)
    for frame_ms, gpu_ms in [(23.0, 21.0)] * 8 + [(9.0, 8.0)] * 20:
        decision = controller.observe(frame_ms, gpu_ms=gpu_ms)
        if decision.changed:
            print(
                f"frame {decision.frame_index}: {decision.direction} -> "
                f"{decision.step.name} ({decision.step.resolution_scale:.2f}x)"
            )

    controller.set_override("high")
    pinned = controller.observe(30.0, gpu_ms=28.0)
    print("override:", pinned.step.name, pinned.reason)
    controller.clear_override()
    print("fingerprint:", controller.fingerprint[:16])


if __name__ == "__main__":
    main()
