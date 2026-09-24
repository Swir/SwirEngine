from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Sequence

from .animation15 import (
    AnimationCondition,
    AnimationParameter,
    AnimationParameters,
    AnimationTransition2,
    ParameterKind,
)
from .graphics.skeletal import (
    SkeletalAnimationClip3D,
    SkeletalPose,
    Skeleton3D,
    blend_skeletal_poses,
    sample_skeletal_clip,
)


def _finite(value: float, *, label: str) -> float:
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{label} must be finite")
    return result


def _name(value: str, *, label: str) -> str:
    result = str(value).strip()
    if not result:
        raise ValueError(f"{label} cannot be empty")
    return result


def _validate_clip_for_skeleton(skeleton: Skeleton3D, clip: SkeletalAnimationClip3D) -> None:
    for channel in clip.channels:
        if channel.node_index >= skeleton.node_count:
            raise ValueError(
                f"clip {clip.name!r} targets unknown skeleton node {channel.node_index}"
            )


@dataclass(frozen=True, slots=True)
class SkeletalBlendChild22:
    threshold: float
    clip: SkeletalAnimationClip3D

    def __post_init__(self) -> None:
        object.__setattr__(self, "threshold", _finite(self.threshold, label="blend threshold"))


@dataclass(frozen=True, slots=True)
class SkeletalBlendTree1D22:
    """One-dimensional synchronized blend tree backed by shipping skeletal clips."""

    parameter: str
    children: tuple[SkeletalBlendChild22, ...]

    def __post_init__(self) -> None:
        parameter = _name(self.parameter, label="blend parameter")
        children = tuple(sorted(self.children, key=lambda child: child.threshold))
        if not children:
            raise ValueError("blend tree must contain at least one child")
        thresholds = [child.threshold for child in children]
        if len(set(thresholds)) != len(thresholds):
            raise ValueError("blend tree thresholds must be unique")
        object.__setattr__(self, "parameter", parameter)
        object.__setattr__(self, "children", children)

    @property
    def duration(self) -> float:
        return max((float(child.clip.duration) for child in self.children), default=0.0)

    def validate(self, skeleton: Skeleton3D, parameters: AnimationParameters) -> None:
        spec = parameters.spec(self.parameter)
        if spec.kind not in {ParameterKind.FLOAT, ParameterKind.INT}:
            raise TypeError(f"blend parameter {self.parameter!r} must be numeric")
        for child in self.children:
            _validate_clip_for_skeleton(skeleton, child.clip)

    def sample(
        self,
        skeleton: Skeleton3D,
        time: float,
        parameters: AnimationParameters,
        *,
        loop: bool,
    ) -> SkeletalPose:
        value = float(parameters.get(self.parameter))
        left = self.children[0]
        right = self.children[-1]
        if value <= left.threshold:
            return self._sample_child(skeleton, left, time, loop=loop)
        if value >= right.threshold:
            return self._sample_child(skeleton, right, time, loop=loop)

        for candidate_right in self.children[1:]:
            if value <= candidate_right.threshold:
                right = candidate_right
                break
            left = candidate_right

        span = right.threshold - left.threshold
        amount = (value - left.threshold) / span
        left_pose = self._sample_child(skeleton, left, time, loop=loop)
        right_pose = self._sample_child(skeleton, right, time, loop=loop)
        return blend_skeletal_poses(left_pose, right_pose, amount)

    def _sample_child(
        self,
        skeleton: Skeleton3D,
        child: SkeletalBlendChild22,
        time: float,
        *,
        loop: bool,
    ) -> SkeletalPose:
        tree_duration = self.duration
        clip_duration = float(child.clip.duration)
        sample_time = float(time)
        if tree_duration > 0.0 and clip_duration > 0.0:
            phase = sample_time / tree_duration
            sample_time = phase * clip_duration
        return sample_skeletal_clip(skeleton, child.clip, sample_time, loop=loop)


AnimationMotion22 = SkeletalAnimationClip3D | SkeletalBlendTree1D22


@dataclass(frozen=True, slots=True)
class AnimationState22:
    name: str
    motion: AnimationMotion22
    speed: float = 1.0
    loop: bool = True

    def __post_init__(self) -> None:
        name = _name(self.name, label="animation state name")
        speed = _finite(self.speed, label="animation state speed")
        if speed <= 0.0:
            raise ValueError("animation state speed must be > 0")
        object.__setattr__(self, "name", name)
        object.__setattr__(self, "speed", speed)

    @property
    def duration(self) -> float:
        if isinstance(self.motion, SkeletalBlendTree1D22):
            return self.motion.duration
        return float(self.motion.duration)

    def validate(self, skeleton: Skeleton3D, parameters: AnimationParameters) -> None:
        if isinstance(self.motion, SkeletalBlendTree1D22):
            self.motion.validate(skeleton, parameters)
        else:
            _validate_clip_for_skeleton(skeleton, self.motion)

    def sample(
        self,
        skeleton: Skeleton3D,
        time: float,
        parameters: AnimationParameters,
    ) -> SkeletalPose:
        sample_time = max(0.0, float(time)) * self.speed
        if isinstance(self.motion, SkeletalBlendTree1D22):
            return self.motion.sample(skeleton, sample_time, parameters, loop=self.loop)
        return sample_skeletal_clip(skeleton, self.motion, sample_time, loop=self.loop)


@dataclass(frozen=True, slots=True)
class _ActiveTransition22:
    transition: AnimationTransition2
    source: str
    source_time: float
    target_time: float = 0.0
    elapsed: float = 0.0


class AnimationStateMachine22:
    """Compiled skeletal animation state machine for SwirEngine 2.2."""

    def __init__(
        self,
        skeleton: Skeleton3D,
        states: Sequence[AnimationState22],
        *,
        parameters: Sequence[AnimationParameter] = (),
        transitions: Sequence[AnimationTransition2] = (),
        initial: str | None = None,
    ) -> None:
        if not states:
            raise ValueError("animation state machine must contain at least one state")
        self.skeleton = skeleton
        self.states: dict[str, AnimationState22] = {}
        for state in states:
            if state.name in self.states:
                raise ValueError(f"duplicate animation state: {state.name}")
            self.states[state.name] = state

        self.parameters = tuple(parameters)
        probe = AnimationParameters(self.parameters)
        for state in self.states.values():
            state.validate(skeleton, probe)

        self.transitions = tuple(transitions)
        for transition in self.transitions:
            if transition.source != "*" and transition.source not in self.states:
                raise ValueError(f"unknown transition source: {transition.source}")
            if transition.target not in self.states:
                raise ValueError(f"unknown transition target: {transition.target}")
            for condition in transition.conditions:
                condition.evaluate(probe)

        initial_name = initial or next(iter(self.states))
        if initial_name not in self.states:
            raise ValueError(f"unknown initial animation state: {initial_name}")
        self.initial = initial_name

    def player(self) -> AnimationStateMachinePlayer22:
        return AnimationStateMachinePlayer22(self)


class AnimationStateMachinePlayer22:
    """Runtime player with parameters, trigger transitions and pose crossfades."""

    def __init__(self, machine: AnimationStateMachine22) -> None:
        self.machine = machine
        self.parameters = AnimationParameters(machine.parameters)
        self.current = machine.initial
        self.state_time = 0.0
        self._active_transition: _ActiveTransition22 | None = None

    @property
    def next_state(self) -> str | None:
        active = self._active_transition
        return active.transition.target if active is not None else None

    @property
    def normalized_time(self) -> float:
        state = self.machine.states[self.current]
        duration = state.duration
        if duration <= 0.0:
            return 1.0
        return min(1.0, max(0.0, self.state_time * state.speed / duration))

    @property
    def transitioning(self) -> bool:
        return self._active_transition is not None

    def set_parameter(self, name: str, value: object) -> None:
        self.parameters.set(name, value)

    def trigger(self, name: str) -> None:
        self.parameters.trigger(name)

    def force_state(self, name: str, *, restart: bool = True) -> None:
        if name not in self.machine.states:
            raise KeyError(f"unknown animation state: {name}")
        same = name == self.current
        self.current = name
        if restart or not same:
            self.state_time = 0.0
        self._active_transition = None

    def update(self, dt: float) -> SkeletalPose:
        delta = _finite(dt, label="animation delta time")
        if delta < 0.0:
            raise ValueError("animation delta time must be >= 0")

        active = self._active_transition
        if active is not None:
            self._advance_transition(delta)
            return self.sample()

        self.state_time += delta
        transition = self._choose_transition()
        if transition is not None:
            self._begin_transition(transition)
        return self.sample()

    def sample(self) -> SkeletalPose:
        active = self._active_transition
        if active is None:
            state = self.machine.states[self.current]
            return state.sample(self.machine.skeleton, self.state_time, self.parameters)

        source_state = self.machine.states[active.source]
        target_state = self.machine.states[active.transition.target]
        source_pose = source_state.sample(
            self.machine.skeleton,
            active.source_time,
            self.parameters,
        )
        target_pose = target_state.sample(
            self.machine.skeleton,
            active.target_time,
            self.parameters,
        )
        duration = active.transition.duration
        amount = 1.0 if duration <= 0.0 else min(1.0, active.elapsed / duration)
        return blend_skeletal_poses(source_pose, target_pose, amount)

    def _choose_transition(self) -> AnimationTransition2 | None:
        candidates = []
        for index, transition in enumerate(self.machine.transitions):
            if transition.source not in {"*", self.current}:
                continue
            if transition.target == self.current and not transition.allow_self:
                continue
            if transition.exit_time is not None and self.normalized_time < transition.exit_time:
                continue
            if not all(condition.evaluate(self.parameters) for condition in transition.conditions):
                continue
            candidates.append((-int(transition.priority), index, transition))
        if not candidates:
            return None
        candidates.sort(key=lambda item: (item[0], item[1]))
        return candidates[0][2]

    def _begin_transition(self, transition: AnimationTransition2) -> None:
        if transition.consume_triggers:
            self._consume_transition_triggers(transition)
        if transition.duration <= 0.0:
            self.current = transition.target
            self.state_time = 0.0
            self._active_transition = None
            return
        self._active_transition = _ActiveTransition22(
            transition=transition,
            source=self.current,
            source_time=self.state_time,
        )

    def _advance_transition(self, delta: float) -> None:
        active = self._active_transition
        if active is None:
            return
        source_time = active.source_time + delta
        target_time = active.target_time + delta
        elapsed = active.elapsed + delta
        if elapsed >= active.transition.duration:
            self.current = active.transition.target
            self.state_time = target_time
            self._active_transition = None
            return
        self._active_transition = _ActiveTransition22(
            transition=active.transition,
            source=active.source,
            source_time=source_time,
            target_time=target_time,
            elapsed=elapsed,
        )

    def _consume_transition_triggers(self, transition: AnimationTransition2) -> None:
        for condition in transition.conditions:
            spec = self.parameters.spec(condition.parameter)
            if spec.kind is ParameterKind.TRIGGER:
                self.parameters.reset_trigger(condition.parameter)


def make_transition22(
    source: str,
    target: str,
    *,
    conditions: Sequence[AnimationCondition] = (),
    duration: float = 0.0,
    exit_time: float | None = None,
    priority: int = 0,
) -> AnimationTransition2:
    """Convenience constructor retained as a stable creator-facing runtime entry point."""

    return AnimationTransition2(
        source,
        target,
        conditions=tuple(conditions),
        duration=duration,
        exit_time=exit_time,
        priority=priority,
    )
