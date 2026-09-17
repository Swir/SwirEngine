from __future__ import annotations

import hashlib
import json
import math
from collections import deque
from dataclasses import dataclass
from types import MappingProxyType
from typing import Literal, Protocol

MetricSource = Literal["frame", "gpu", "max"]
DecisionDirection = Literal["hold", "degrade", "recover", "override", "manual"]


class DiagnosticsBindable(Protocol):
    def bind_provider(self, domain: str, provider: object) -> None: ...

    def unbind_provider(self, domain: str) -> bool: ...


class PerformanceFrameLike(Protocol):
    frame_ms: float
    counters: tuple[object, ...]


class RenderQualityError(RuntimeError):
    """Stable creator-facing error raised by the 1.8 quality controller."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def _finite(value: float, *, label: str, minimum: float | None = None) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{label} must be a real number")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{label} must be finite")
    if minimum is not None and result < minimum:
        raise ValueError(f"{label} must be >= {minimum}")
    return result


def _positive_int(value: int, *, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{label} must be an integer")
    if value < 1:
        raise ValueError(f"{label} must be >= 1")
    return value


def _nonnegative_int(value: int, *, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{label} must be an integer")
    if value < 0:
        raise ValueError(f"{label} must be >= 0")
    return value


def _name(value: str, *, label: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{label} must be a string")
    result = value.strip()
    if not result:
        raise ValueError(f"{label} must not be empty")
    if len(result) > 96:
        raise ValueError(f"{label} must contain at most 96 characters")
    return result


@dataclass(frozen=True, slots=True)
class RenderQualityStep:
    """One authored quality tier, ordered from highest quality to lowest quality."""

    name: str
    resolution_scale: float
    quality_scale: float = 1.0

    def __post_init__(self) -> None:
        object.__setattr__(self, "name", _name(self.name, label="quality step name"))
        resolution = _finite(self.resolution_scale, label="resolution_scale", minimum=0.1)
        quality = _finite(self.quality_scale, label="quality_scale", minimum=0.0)
        if resolution > 2.0:
            raise ValueError("resolution_scale must be <= 2.0")
        if quality > 1.0:
            raise ValueError("quality_scale must be <= 1.0")
        object.__setattr__(self, "resolution_scale", resolution)
        object.__setattr__(self, "quality_scale", quality)

    def portable(self) -> dict[str, object]:
        return {
            "name": self.name,
            "resolution_scale": self.resolution_scale,
            "quality_scale": self.quality_scale,
        }


@dataclass(frozen=True, slots=True)
class RenderQualityPolicy:
    """Deterministic frame-budget policy for opt-in render-quality adaptation."""

    target_frame_ms: float = 16.6667
    metric_source: MetricSource = "max"
    degrade_ratio: float = 1.08
    recover_ratio: float = 0.82
    degrade_frames: int = 4
    recover_frames: int = 45
    cooldown_frames: int = 30
    sample_window: int = 6
    max_steps: int = 16

    def __post_init__(self) -> None:
        target = _finite(self.target_frame_ms, label="target_frame_ms", minimum=0.001)
        degrade = _finite(self.degrade_ratio, label="degrade_ratio", minimum=1.0)
        recover = _finite(self.recover_ratio, label="recover_ratio", minimum=0.0)
        if recover >= 1.0:
            raise ValueError("recover_ratio must be < 1.0")
        if self.metric_source not in {"frame", "gpu", "max"}:
            raise ValueError("metric_source must be 'frame', 'gpu', or 'max'")
        degrade_frames = _positive_int(self.degrade_frames, label="degrade_frames")
        recover_frames = _positive_int(self.recover_frames, label="recover_frames")
        cooldown = _nonnegative_int(self.cooldown_frames, label="cooldown_frames")
        sample_window = _positive_int(self.sample_window, label="sample_window")
        max_steps = _positive_int(self.max_steps, label="max_steps")
        if sample_window > 240:
            raise ValueError("sample_window must be <= 240")
        if max_steps > 64:
            raise ValueError("max_steps must be <= 64")
        object.__setattr__(self, "target_frame_ms", target)
        object.__setattr__(self, "degrade_ratio", degrade)
        object.__setattr__(self, "recover_ratio", recover)
        object.__setattr__(self, "degrade_frames", degrade_frames)
        object.__setattr__(self, "recover_frames", recover_frames)
        object.__setattr__(self, "cooldown_frames", cooldown)
        object.__setattr__(self, "sample_window", sample_window)
        object.__setattr__(self, "max_steps", max_steps)

    @property
    def degrade_threshold_ms(self) -> float:
        return self.target_frame_ms * self.degrade_ratio

    @property
    def recover_threshold_ms(self) -> float:
        return self.target_frame_ms * self.recover_ratio

    def portable(self) -> dict[str, object]:
        return {
            "target_frame_ms": self.target_frame_ms,
            "metric_source": self.metric_source,
            "degrade_ratio": self.degrade_ratio,
            "recover_ratio": self.recover_ratio,
            "degrade_frames": self.degrade_frames,
            "recover_frames": self.recover_frames,
            "cooldown_frames": self.cooldown_frames,
            "sample_window": self.sample_window,
            "max_steps": self.max_steps,
        }


@dataclass(frozen=True, slots=True)
class RenderQualityDecision:
    frame_index: int
    step_index: int
    step: RenderQualityStep
    changed: bool
    direction: DecisionDirection
    reason: str
    metric_ms: float
    rolling_ms: float
    cooldown_remaining: int
    overridden: bool

    def portable(self) -> dict[str, object]:
        return {
            "frame_index": self.frame_index,
            "step_index": self.step_index,
            "step": self.step.portable(),
            "changed": self.changed,
            "direction": self.direction,
            "reason": self.reason,
            "metric_ms": self.metric_ms,
            "rolling_ms": self.rolling_ms,
            "cooldown_remaining": self.cooldown_remaining,
            "overridden": self.overridden,
        }


@dataclass(frozen=True, slots=True)
class RenderQualityDiagnostics:
    current_step: int
    step_count: int
    resolution_scale: float
    quality_scale: float
    frames_observed: int
    changes_total: int
    degradations_total: int
    recoveries_total: int
    overload_samples: int
    recovery_samples: int
    neutral_samples: int
    override_frames: int
    manual_changes: int
    cooldown_remaining: int
    overload_streak: int
    recovery_streak: int
    sample_count: int
    last_metric_ms: float
    rolling_metric_ms: float
    override_active: bool

    def portable(self) -> MappingProxyType[str, int | float | bool]:
        return MappingProxyType(
            {
                "current_step": self.current_step,
                "step_count": self.step_count,
                "resolution_scale": self.resolution_scale,
                "quality_scale": self.quality_scale,
                "frames_observed": self.frames_observed,
                "changes_total": self.changes_total,
                "degradations_total": self.degradations_total,
                "recoveries_total": self.recoveries_total,
                "overload_samples": self.overload_samples,
                "recovery_samples": self.recovery_samples,
                "neutral_samples": self.neutral_samples,
                "override_frames": self.override_frames,
                "manual_changes": self.manual_changes,
                "cooldown_remaining": self.cooldown_remaining,
                "overload_streak": self.overload_streak,
                "recovery_streak": self.recovery_streak,
                "sample_count": self.sample_count,
                "last_metric_ms": self.last_metric_ms,
                "rolling_metric_ms": self.rolling_metric_ms,
                "override_active": self.override_active,
            }
        )


class DynamicQualityController:
    """Opt-in deterministic dynamic-resolution and render-quality controller.

    The controller is intentionally renderer independent. It observes timing evidence and returns an
    authored :class:`RenderQualityStep`; it never mutates renderer state, simulation clocks, physics,
    gameplay, or fixed-step truth. A renderer/backend may apply the returned resolution/quality values
    at a safe frame boundary.
    """

    def __init__(
        self,
        steps: tuple[RenderQualityStep, ...] | list[RenderQualityStep],
        *,
        policy: RenderQualityPolicy | None = None,
        initial_step: int | str = 0,
        enabled: bool = True,
    ) -> None:
        self.policy = RenderQualityPolicy() if policy is None else policy
        if not isinstance(self.policy, RenderQualityPolicy):
            raise TypeError("policy must be RenderQualityPolicy or None")
        authored = tuple(steps)
        if not authored:
            raise ValueError("at least one render quality step is required")
        if len(authored) > self.policy.max_steps:
            raise ValueError("quality step count exceeds policy max_steps")
        if not all(isinstance(step, RenderQualityStep) for step in authored):
            raise TypeError("steps must contain RenderQualityStep values")
        if len({step.name for step in authored}) != len(authored):
            raise ValueError("quality step names must be unique")
        for previous, current in zip(authored, authored[1:]):
            if current.resolution_scale > previous.resolution_scale:
                raise ValueError("quality steps must not increase resolution_scale as quality drops")
            if current.quality_scale > previous.quality_scale:
                raise ValueError("quality steps must not increase quality_scale as quality drops")
        if not isinstance(enabled, bool):
            raise TypeError("enabled must be a boolean")
        self.steps = authored
        self.enabled = enabled
        self._index = self._resolve_step(initial_step)
        self._override_index: int | None = None
        self._samples: deque[float] = deque(maxlen=self.policy.sample_window)
        self._frame_index = 0
        self._cooldown_remaining = 0
        self._overload_streak = 0
        self._recovery_streak = 0
        self._frames_observed = 0
        self._changes_total = 0
        self._degradations_total = 0
        self._recoveries_total = 0
        self._overload_samples = 0
        self._recovery_samples = 0
        self._neutral_samples = 0
        self._override_frames = 0
        self._manual_changes = 0
        self._last_metric_ms = 0.0
        self._rolling_metric_ms = 0.0
        self._diagnostics_binding: tuple[DiagnosticsBindable, str] | None = None

    @property
    def current_step_index(self) -> int:
        return self._index

    @property
    def current_step(self) -> RenderQualityStep:
        return self.steps[self._index]

    @property
    def override_active(self) -> bool:
        return self._override_index is not None

    @property
    def cooldown_remaining(self) -> int:
        return self._cooldown_remaining

    def _resolve_step(self, step: int | str) -> int:
        if isinstance(step, bool):
            raise TypeError("quality step must be an integer index or step name")
        if isinstance(step, int):
            if step < 0 or step >= len(self.steps):
                raise IndexError("quality step index is out of range")
            return step
        if isinstance(step, str):
            normalized = _name(step, label="quality step")
            for index, candidate in enumerate(self.steps):
                if candidate.name == normalized:
                    return index
            raise KeyError(f"unknown quality step: {normalized}")
        raise TypeError("quality step must be an integer index or step name")

    def _reset_adaptation(self, *, cooldown: bool) -> None:
        self._overload_streak = 0
        self._recovery_streak = 0
        self._samples.clear()
        self._cooldown_remaining = self.policy.cooldown_frames if cooldown else 0

    def set_step(self, step: int | str, *, cooldown: bool = True) -> RenderQualityStep:
        """Set the adaptive baseline directly without enabling a persistent override."""

        index = self._resolve_step(step)
        changed = index != self._index
        self._index = index
        if changed:
            self._changes_total += 1
            self._manual_changes += 1
        self._reset_adaptation(cooldown=cooldown)
        return self.current_step

    def set_override(self, step: int | str) -> RenderQualityStep:
        """Pin an explicit creator-selected quality step until :meth:`clear_override`."""

        index = self._resolve_step(step)
        changed = index != self._index
        self._override_index = index
        self._index = index
        if changed:
            self._changes_total += 1
            self._manual_changes += 1
        self._reset_adaptation(cooldown=False)
        return self.current_step

    def clear_override(self) -> None:
        self._override_index = None
        self._reset_adaptation(cooldown=True)

    def reset_history(self) -> None:
        """Forget timing evidence/counters while preserving the selected quality step."""

        self._samples.clear()
        self._frame_index = 0
        self._cooldown_remaining = 0
        self._overload_streak = 0
        self._recovery_streak = 0
        self._frames_observed = 0
        self._changes_total = 0
        self._degradations_total = 0
        self._recoveries_total = 0
        self._overload_samples = 0
        self._recovery_samples = 0
        self._neutral_samples = 0
        self._override_frames = 0
        self._manual_changes = 0
        self._last_metric_ms = 0.0
        self._rolling_metric_ms = 0.0

    def _metric(self, frame_ms: float, gpu_ms: float | None) -> float:
        frame = _finite(frame_ms, label="frame_ms", minimum=0.0)
        gpu = None if gpu_ms is None else _finite(gpu_ms, label="gpu_ms", minimum=0.0)
        source = self.policy.metric_source
        if source == "frame":
            return frame
        if source == "gpu":
            return frame if gpu is None else gpu
        return frame if gpu is None else max(frame, gpu)

    def observe(self, frame_ms: float, *, gpu_ms: float | None = None) -> RenderQualityDecision:
        """Observe one rendered frame and return the quality step for the next safe boundary."""

        metric = self._metric(frame_ms, gpu_ms)
        self._samples.append(metric)
        rolling = sum(self._samples) / len(self._samples)
        self._last_metric_ms = metric
        self._rolling_metric_ms = rolling
        self._frames_observed += 1
        frame_index = self._frame_index
        self._frame_index += 1

        if self._override_index is not None:
            self._override_frames += 1
            self._overload_streak = 0
            self._recovery_streak = 0
            return self._decision(
                frame_index,
                changed=False,
                direction="override",
                reason="creator override active",
                metric=metric,
                rolling=rolling,
            )

        if not self.enabled:
            self._overload_streak = 0
            self._recovery_streak = 0
            return self._decision(
                frame_index,
                changed=False,
                direction="hold",
                reason="dynamic quality disabled",
                metric=metric,
                rolling=rolling,
            )

        if self._cooldown_remaining > 0:
            self._cooldown_remaining -= 1
            self._overload_streak = 0
            self._recovery_streak = 0
            return self._decision(
                frame_index,
                changed=False,
                direction="hold",
                reason="quality transition cooldown",
                metric=metric,
                rolling=rolling,
            )

        if rolling > self.policy.degrade_threshold_ms:
            self._overload_samples += 1
            self._overload_streak += 1
            self._recovery_streak = 0
            if self._overload_streak >= self.policy.degrade_frames:
                if self._index < len(self.steps) - 1:
                    self._index += 1
                    self._changes_total += 1
                    self._degradations_total += 1
                    self._reset_adaptation(cooldown=True)
                    return self._decision(
                        frame_index,
                        changed=True,
                        direction="degrade",
                        reason="sustained frame-budget pressure",
                        metric=metric,
                        rolling=rolling,
                    )
                self._overload_streak = self.policy.degrade_frames
                return self._decision(
                    frame_index,
                    changed=False,
                    direction="hold",
                    reason="already at lowest authored quality step",
                    metric=metric,
                    rolling=rolling,
                )
        elif rolling < self.policy.recover_threshold_ms:
            self._recovery_samples += 1
            self._recovery_streak += 1
            self._overload_streak = 0
            if self._recovery_streak >= self.policy.recover_frames:
                if self._index > 0:
                    self._index -= 1
                    self._changes_total += 1
                    self._recoveries_total += 1
                    self._reset_adaptation(cooldown=True)
                    return self._decision(
                        frame_index,
                        changed=True,
                        direction="recover",
                        reason="sustained frame-budget headroom",
                        metric=metric,
                        rolling=rolling,
                    )
                self._recovery_streak = self.policy.recover_frames
                return self._decision(
                    frame_index,
                    changed=False,
                    direction="hold",
                    reason="already at highest authored quality step",
                    metric=metric,
                    rolling=rolling,
                )
        else:
            self._neutral_samples += 1
            self._overload_streak = 0
            self._recovery_streak = 0

        return self._decision(
            frame_index,
            changed=False,
            direction="hold",
            reason="quality hysteresis holding current step",
            metric=metric,
            rolling=rolling,
        )

    def _decision(
        self,
        frame_index: int,
        *,
        changed: bool,
        direction: DecisionDirection,
        reason: str,
        metric: float,
        rolling: float,
    ) -> RenderQualityDecision:
        return RenderQualityDecision(
            frame_index=frame_index,
            step_index=self._index,
            step=self.current_step,
            changed=changed,
            direction=direction,
            reason=reason,
            metric_ms=metric,
            rolling_ms=rolling,
            cooldown_remaining=self._cooldown_remaining,
            overridden=self.override_active,
        )

    @staticmethod
    def gpu_ms_from_performance_frame(frame: PerformanceFrameLike) -> float | None:
        """Extract the explicit ``gpu.frame_ms`` counter written by GPU Timing Capture 1.8."""

        counters = getattr(frame, "counters", ())
        for counter in counters:
            if getattr(counter, "domain", None) != "gpu":
                continue
            if getattr(counter, "name", None) != "frame_ms":
                continue
            value = getattr(counter, "value", None)
            return _finite(value, label="gpu.frame_ms", minimum=0.0)
        return None

    def observe_performance_frame(self, frame: PerformanceFrameLike) -> RenderQualityDecision:
        """Consume a PerformanceDiagnostics2 frame without changing its simulation timing."""

        frame_ms = getattr(frame, "frame_ms", None)
        if frame_ms is None:
            raise TypeError("performance frame must expose frame_ms")
        gpu_ms = self.gpu_ms_from_performance_frame(frame)
        return self.observe(frame_ms, gpu_ms=gpu_ms)

    def diagnostics(self) -> RenderQualityDiagnostics:
        return RenderQualityDiagnostics(
            current_step=self._index,
            step_count=len(self.steps),
            resolution_scale=self.current_step.resolution_scale,
            quality_scale=self.current_step.quality_scale,
            frames_observed=self._frames_observed,
            changes_total=self._changes_total,
            degradations_total=self._degradations_total,
            recoveries_total=self._recoveries_total,
            overload_samples=self._overload_samples,
            recovery_samples=self._recovery_samples,
            neutral_samples=self._neutral_samples,
            override_frames=self._override_frames,
            manual_changes=self._manual_changes,
            cooldown_remaining=self._cooldown_remaining,
            overload_streak=self._overload_streak,
            recovery_streak=self._recovery_streak,
            sample_count=len(self._samples),
            last_metric_ms=self._last_metric_ms,
            rolling_metric_ms=self._rolling_metric_ms,
            override_active=self.override_active,
        )

    def bind_diagnostics(
        self,
        performance: DiagnosticsBindable,
        *,
        domain: str = "render_quality",
    ) -> None:
        """Expose numeric quality state through PerformanceDiagnostics2 provider sampling."""

        domain = _name(domain, label="diagnostics domain")
        bind = getattr(performance, "bind_provider", None)
        unbind = getattr(performance, "unbind_provider", None)
        if not callable(bind) or not callable(unbind):
            raise TypeError("performance must expose bind_provider() and unbind_provider()")
        if self._diagnostics_binding is not None:
            self.unbind_diagnostics()
        bind(domain, self.diagnostics)
        self._diagnostics_binding = (performance, domain)

    def unbind_diagnostics(self) -> bool:
        binding = self._diagnostics_binding
        if binding is None:
            return False
        performance, domain = binding
        self._diagnostics_binding = None
        return bool(performance.unbind_provider(domain))

    def portable_state(self) -> dict[str, object]:
        return {
            "format": "swirengine.render-quality.state",
            "format_version": 1,
            "policy": self.policy.portable(),
            "steps": [step.portable() for step in self.steps],
            "enabled": self.enabled,
            "current_step": self._index,
            "override_step": self._override_index,
            "cooldown_remaining": self._cooldown_remaining,
            "overload_streak": self._overload_streak,
            "recovery_streak": self._recovery_streak,
            "samples": list(self._samples),
            "frames_observed": self._frames_observed,
            "changes_total": self._changes_total,
            "degradations_total": self._degradations_total,
            "recoveries_total": self._recoveries_total,
            "overload_samples": self._overload_samples,
            "recovery_samples": self._recovery_samples,
            "neutral_samples": self._neutral_samples,
            "override_frames": self._override_frames,
            "manual_changes": self._manual_changes,
            "last_metric_ms": self._last_metric_ms,
            "rolling_metric_ms": self._rolling_metric_ms,
        }

    @property
    def fingerprint(self) -> str:
        canonical = json.dumps(
            self.portable_state(),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def default_render_quality_steps() -> tuple[RenderQualityStep, ...]:
    """Balanced creator defaults; no backend applies them unless explicitly wired by the creator."""

    return (
        RenderQualityStep("ultra", 1.0, 1.0),
        RenderQualityStep("high", 0.9, 0.9),
        RenderQualityStep("medium", 0.75, 0.75),
        RenderQualityStep("low", 0.6, 0.55),
    )
