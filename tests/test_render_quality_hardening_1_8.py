from dataclasses import dataclass

import pytest

from swirengine.performance15 import PerformanceDiagnostics2
from swirengine.render_quality18 import (
    DynamicQualityController,
    RenderQualityPolicy,
    RenderQualityStep,
)


def steps():
    return (
        RenderQualityStep("native", 1.0, 1.0),
        RenderQualityStep("balanced", 0.8, 0.75),
        RenderQualityStep("performance", 0.6, 0.5),
    )


def policy(**overrides):
    values = {
        "target_frame_ms": 16.0,
        "degrade_ratio": 1.05,
        "recover_ratio": 0.8,
        "degrade_frames": 2,
        "recover_frames": 3,
        "cooldown_frames": 0,
        "sample_window": 1,
    }
    values.update(overrides)
    return RenderQualityPolicy(**values)


def test_policy_limits_are_bounded():
    with pytest.raises(ValueError):
        RenderQualityPolicy(sample_window=241)
    with pytest.raises(ValueError):
        RenderQualityPolicy(max_steps=65)
    with pytest.raises(ValueError):
        RenderQualityPolicy(recover_ratio=1.0)
    with pytest.raises(ValueError):
        RenderQualityPolicy(degrade_ratio=0.99)
    with pytest.raises(ValueError):
        DynamicQualityController(steps(), policy=RenderQualityPolicy(max_steps=2))


def test_rolling_window_requires_sustained_average_pressure():
    controller = DynamicQualityController(
        steps(),
        policy=policy(sample_window=3, degrade_frames=2),
    )
    controller.observe(30.0)
    controller.observe(2.0)
    assert controller.current_step_index == 0
    controller.observe(30.0)
    controller.observe(30.0)
    assert controller.current_step_index == 1


def test_cooldown_requires_fresh_evidence_after_transition():
    controller = DynamicQualityController(
        steps(), policy=policy(degrade_frames=1, recover_frames=1, cooldown_frames=2)
    )
    controller.observe(30.0)
    assert controller.current_step_index == 1
    controller.observe(1.0)
    controller.observe(1.0)
    assert controller.current_step_index == 1
    controller.observe(1.0)
    assert controller.current_step_index == 0


def test_disabled_controller_observes_but_never_adapts():
    controller = DynamicQualityController(steps(), policy=policy(degrade_frames=1), enabled=False)
    for _ in range(20):
        decision = controller.observe(100.0)
    assert decision.reason == "dynamic quality disabled"
    assert controller.current_step_index == 0
    assert controller.diagnostics().frames_observed == 20


def test_performance_diagnostics_binding_exports_numeric_state():
    performance = PerformanceDiagnostics2(history=4)
    controller = DynamicQualityController(steps(), policy=policy())
    controller.bind_diagnostics(performance)
    controller.observe(20.0)
    performance.begin_frame()
    frame = performance.end_frame(frame_seconds=0.020)
    values = {(counter.domain, counter.name): counter.value for counter in frame.counters}
    assert values[("render_quality", "current_step")] == 0
    assert values[("render_quality", "frames_observed")] == 1
    assert values[("render_quality", "resolution_scale")] == 1.0
    assert controller.unbind_diagnostics() is True
    assert controller.unbind_diagnostics() is False


def test_binding_replaces_previous_domain_without_leaving_stale_provider():
    performance = PerformanceDiagnostics2(history=2)
    controller = DynamicQualityController(steps(), policy=policy())
    controller.bind_diagnostics(performance, domain="quality_a")
    controller.bind_diagnostics(performance, domain="quality_b")
    performance.begin_frame()
    frame = performance.end_frame(frame_seconds=0.016)
    domains = {counter.domain for counter in frame.counters}
    assert "quality_b" in domains
    assert "quality_a" not in domains


def test_reset_history_preserves_selected_step_and_configuration():
    controller = DynamicQualityController(
        steps(), policy=policy(degrade_frames=1, cooldown_frames=0)
    )
    controller.observe(30.0)
    assert controller.current_step_index == 1
    controller.reset_history()
    diagnostics = controller.diagnostics()
    assert diagnostics.current_step == 1
    assert diagnostics.frames_observed == 0
    assert diagnostics.changes_total == 0
    assert diagnostics.sample_count == 0


def test_override_change_is_counted_as_manual_not_adaptive_degradation():
    controller = DynamicQualityController(steps(), policy=policy())
    controller.set_override("performance")
    diagnostics = controller.diagnostics()
    assert diagnostics.manual_changes == 1
    assert diagnostics.changes_total == 1
    assert diagnostics.degradations_total == 0
    assert diagnostics.recoveries_total == 0


def test_step_lookup_and_bad_inputs_fail_explicitly():
    controller = DynamicQualityController(steps(), policy=policy())
    with pytest.raises(KeyError):
        controller.set_step("missing")
    with pytest.raises(IndexError):
        controller.set_step(99)
    with pytest.raises(TypeError):
        controller.set_step(True)
    with pytest.raises(TypeError):
        controller.observe("16")


@dataclass(frozen=True)
class BadFrame:
    counters: tuple[object, ...] = ()


def test_performance_frame_requires_frame_ms():
    controller = DynamicQualityController(steps(), policy=policy())
    with pytest.raises(TypeError):
        controller.observe_performance_frame(BadFrame())
