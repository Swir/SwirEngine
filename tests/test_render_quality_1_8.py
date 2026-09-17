from dataclasses import dataclass

import pytest

from swirengine.render_quality18 import (
    DynamicQualityController,
    RenderQualityPolicy,
    RenderQualityStep,
    default_render_quality_steps,
)


def steps():
    return (
        RenderQualityStep("high", 1.0, 1.0),
        RenderQualityStep("medium", 0.8, 0.8),
        RenderQualityStep("low", 0.6, 0.5),
    )


def policy(**overrides):
    values = dict(
        target_frame_ms=10.0,
        metric_source="max",
        degrade_ratio=1.1,
        recover_ratio=0.8,
        degrade_frames=2,
        recover_frames=3,
        cooldown_frames=2,
        sample_window=1,
    )
    values.update(overrides)
    return RenderQualityPolicy(**values)


def test_steps_are_validated_and_ordered():
    assert default_render_quality_steps()[0].name == "ultra"
    with pytest.raises(ValueError):
        RenderQualityStep("bad", 0.0)
    with pytest.raises(ValueError):
        DynamicQualityController(
            [RenderQualityStep("low", 0.5), RenderQualityStep("higher", 1.0)]
        )
    with pytest.raises(ValueError):
        DynamicQualityController(
            [RenderQualityStep("same", 1.0), RenderQualityStep("same", 0.5)]
        )


def test_policy_hysteresis_degrades_and_recovers_one_step_at_a_time():
    controller = DynamicQualityController(steps(), policy=policy())
    assert controller.observe(12.0).changed is False
    decision = controller.observe(12.0)
    assert decision.changed is True
    assert decision.direction == "degrade"
    assert decision.step.name == "medium"
    assert decision.cooldown_remaining == 2

    controller.observe(5.0)
    controller.observe(5.0)
    assert controller.current_step.name == "medium"
    controller.observe(5.0)
    controller.observe(5.0)
    decision = controller.observe(5.0)
    assert decision.changed is True
    assert decision.direction == "recover"
    assert decision.step.name == "high"


def test_neutral_samples_reset_streaks_and_prevent_thrashing():
    controller = DynamicQualityController(
        steps(), policy=policy(degrade_frames=3, cooldown_frames=0)
    )
    controller.observe(12.0)
    controller.observe(10.0)
    assert controller.diagnostics().overload_streak == 0
    controller.observe(12.0)
    controller.observe(12.0)
    assert controller.current_step.name == "high"
    controller.observe(12.0)
    assert controller.current_step.name == "medium"


def test_controller_holds_at_authored_bounds():
    controller = DynamicQualityController(
        steps(), policy=policy(cooldown_frames=0), initial_step="low"
    )
    for _ in range(6):
        decision = controller.observe(25.0)
    assert decision.changed is False
    assert controller.current_step.name == "low"
    assert controller.diagnostics().degradations_total == 0


def test_metric_source_gpu_and_max_fallback_are_deterministic():
    gpu = DynamicQualityController(
        steps(), policy=policy(metric_source="gpu", degrade_frames=1, cooldown_frames=0)
    )
    assert gpu.observe(20.0, gpu_ms=5.0).step.name == "high"
    assert gpu.observe(5.0, gpu_ms=20.0).step.name == "medium"

    maximum = DynamicQualityController(
        steps(), policy=policy(metric_source="max", degrade_frames=1, cooldown_frames=0)
    )
    assert maximum.observe(20.0, gpu_ms=5.0).step.name == "medium"
    fallback = DynamicQualityController(
        steps(), policy=policy(metric_source="gpu", degrade_frames=1, cooldown_frames=0)
    )
    assert fallback.observe(20.0).step.name == "medium"


def test_creator_override_pins_quality_until_cleared():
    controller = DynamicQualityController(steps(), policy=policy(cooldown_frames=0))
    controller.set_override("low")
    for _ in range(10):
        decision = controller.observe(2.0)
        assert decision.direction == "override"
        assert decision.overridden is True
        assert decision.step.name == "low"
    controller.clear_override()
    assert controller.override_active is False
    assert controller.cooldown_remaining == controller.policy.cooldown_frames


def test_manual_step_is_not_a_persistent_override():
    controller = DynamicQualityController(steps(), policy=policy(cooldown_frames=0))
    controller.set_step("medium", cooldown=False)
    assert controller.current_step.name == "medium"
    assert controller.override_active is False
    for _ in range(3):
        decision = controller.observe(2.0)
    assert decision.direction == "recover"
    assert controller.current_step.name == "high"


def test_invalid_sample_is_atomic():
    controller = DynamicQualityController(steps(), policy=policy())
    before = controller.fingerprint
    with pytest.raises(ValueError):
        controller.observe(float("nan"))
    assert controller.fingerprint == before
    with pytest.raises(ValueError):
        controller.observe(10.0, gpu_ms=-1.0)
    assert controller.fingerprint == before


@dataclass(frozen=True)
class Counter:
    domain: str
    name: str
    value: float


@dataclass(frozen=True)
class Frame:
    frame_ms: float
    counters: tuple[Counter, ...]


def test_performance_frame_helper_uses_explicit_gpu_frame_counter():
    controller = DynamicQualityController(
        steps(), policy=policy(metric_source="gpu", degrade_frames=1, cooldown_frames=0)
    )
    frame = Frame(4.0, (Counter("gpu", "frame_ms", 20.0),))
    decision = controller.observe_performance_frame(frame)
    assert decision.metric_ms == 20.0
    assert decision.step.name == "medium"


def test_portable_state_and_fingerprint_are_reproducible():
    left = DynamicQualityController(steps(), policy=policy())
    right = DynamicQualityController(steps(), policy=policy())
    for sample in (12.0, 12.0, 8.0, 7.0):
        left.observe(sample)
        right.observe(sample)
    assert left.portable_state() == right.portable_state()
    assert left.fingerprint == right.fingerprint
    right.observe(6.0)
    assert left.fingerprint != right.fingerprint
