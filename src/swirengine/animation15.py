from __future__ import annotations

import hashlib
import json
import math
from bisect import bisect_right
from collections.abc import Mapping, MutableMapping, Sequence
from dataclasses import dataclass, field
from enum import Enum
from types import MappingProxyType
from typing import Any

from .animation_runtime import interpolate


def _finite(value: float, *, label: str) -> float:
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{label} must be finite")
    return result


def _nonempty(value: str, *, label: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{label} must be a string")
    result = value.strip()
    if not result:
        raise ValueError(f"{label} must not be empty")
    return result


def _canonical(value: Any) -> Any:
    if value is None or isinstance(value, (bool, int, str)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("diagnostic values must be finite")
        return value
    if isinstance(value, Mapping):
        return {str(key): _canonical(value[key]) for key in sorted(value, key=str)}
    if isinstance(value, (tuple, list)):
        return [_canonical(item) for item in value]
    raise TypeError(f"unsupported portable animation value: {type(value).__name__}")


def _set_path(target: Any, path: str, value: Any) -> None:
    parts = path.split(".")
    parent = target
    for part in parts[:-1]:
        parent = parent[part] if isinstance(parent, Mapping) else getattr(parent, part)
    final = parts[-1]
    if isinstance(parent, MutableMapping):
        parent[final] = value
    else:
        setattr(parent, final, value)


class InterpolationMode(str, Enum):
    LINEAR = "linear"
    STEP = "step"


@dataclass(frozen=True, slots=True)
class AnimationKeyframe:
    time: float
    value: Any

    def __post_init__(self) -> None:
        time = _finite(self.time, label="keyframe time")
        if time < 0.0:
            raise ValueError("keyframe time must be >= 0")
        object.__setattr__(self, "time", time)


@dataclass(frozen=True, slots=True)
class AnimationTrack:
    binding: str
    keyframes: tuple[AnimationKeyframe, ...]
    interpolation: InterpolationMode | str = InterpolationMode.LINEAR
    _times: tuple[float, ...] = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        binding = _nonempty(self.binding, label="animation binding")
        keyframes = tuple(self.keyframes)
        if not keyframes:
            raise ValueError("animation track must contain at least one keyframe")
        times = tuple(keyframe.time for keyframe in keyframes)
        if any(current <= previous for previous, current in zip(times, times[1:])):
            raise ValueError("animation keyframe times must be strictly increasing")
        object.__setattr__(self, "binding", binding)
        object.__setattr__(self, "keyframes", keyframes)
        object.__setattr__(self, "interpolation", InterpolationMode(self.interpolation))
        object.__setattr__(self, "_times", times)

    def sample(self, time: float) -> Any:
        time = _finite(time, label="animation sample time")
        if time <= self._times[0]:
            return self.keyframes[0].value
        if time >= self._times[-1]:
            return self.keyframes[-1].value
        right = bisect_right(self._times, time)
        left_frame = self.keyframes[right - 1]
        right_frame = self.keyframes[right]
        if self.interpolation is InterpolationMode.STEP:
            return left_frame.value
        span = right_frame.time - left_frame.time
        weight = (time - left_frame.time) / span
        return interpolate(left_frame.value, right_frame.value, weight)


@dataclass(frozen=True, slots=True)
class AnimationPose:
    values: Mapping[str, Any]

    def __post_init__(self) -> None:
        normalized: dict[str, Any] = {}
        for binding, value in self.values.items():
            normalized[_nonempty(binding, label="pose binding")] = value
        object.__setattr__(self, "values", MappingProxyType(normalized))

    def blend(self, target: AnimationPose, weight: float) -> AnimationPose:
        weight = max(0.0, min(1.0, _finite(weight, label="blend weight")))
        result: dict[str, Any] = {}
        for binding in sorted(set(self.values) | set(target.values)):
            source_value = self.values.get(binding)
            target_value = target.values.get(binding)
            if binding in self.values and binding in target.values:
                result[binding] = interpolate(source_value, target_value, weight)
            elif binding in target.values:
                result[binding] = target_value
            elif weight < 1.0:
                result[binding] = source_value
        return AnimationPose(result)

    def apply(self, target: Any) -> None:
        for binding, value in self.values.items():
            _set_path(target, binding, value)

    def fingerprint(self) -> str:
        payload = json.dumps(_canonical(self.values), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class AnimationClip:
    name: str
    duration: float
    tracks: tuple[AnimationTrack, ...]

    def __post_init__(self) -> None:
        name = _nonempty(self.name, label="clip name")
        duration = _finite(self.duration, label="clip duration")
        if duration <= 0.0:
            raise ValueError("clip duration must be > 0")
        tracks = tuple(self.tracks)
        bindings = [track.binding for track in tracks]
        if len(set(bindings)) != len(bindings):
            raise ValueError("animation clip bindings must be unique")
        if any(track.keyframes[-1].time > duration for track in tracks):
            raise ValueError("animation keyframes must not exceed clip duration")
        object.__setattr__(self, "name", name)
        object.__setattr__(self, "duration", duration)
        object.__setattr__(self, "tracks", tracks)

    def sample(self, time: float, *, loop: bool = False) -> AnimationPose:
        time = _finite(time, label="clip sample time")
        if time < 0.0:
            raise ValueError("clip sample time must be >= 0")
        local_time = time % self.duration if loop else min(time, self.duration)
        return AnimationPose({track.binding: track.sample(local_time) for track in self.tracks})


class ParameterKind(str, Enum):
    BOOL = "bool"
    FLOAT = "float"
    INT = "int"
    TRIGGER = "trigger"


def _validate_parameter_value(kind: ParameterKind, value: Any, *, label: str) -> Any:
    if kind in {ParameterKind.BOOL, ParameterKind.TRIGGER}:
        if not isinstance(value, bool):
            raise TypeError(f"{label} must be bool")
        return value
    if kind is ParameterKind.INT:
        if not isinstance(value, int) or isinstance(value, bool):
            raise TypeError(f"{label} must be int")
        return value
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{label} must be numeric")
    return _finite(value, label=label)


@dataclass(frozen=True, slots=True)
class AnimationParameter:
    name: str
    kind: ParameterKind | str
    default: Any = None

    def __post_init__(self) -> None:
        name = _nonempty(self.name, label="parameter name")
        kind = ParameterKind(self.kind)
        default = self.default
        if default is None:
            default = {
                ParameterKind.BOOL: False,
                ParameterKind.FLOAT: 0.0,
                ParameterKind.INT: 0,
                ParameterKind.TRIGGER: False,
            }[kind]
        default = _validate_parameter_value(kind, default, label=f"parameter {name!r}")
        if kind is ParameterKind.TRIGGER and default:
            raise ValueError("trigger parameters must default to False")
        object.__setattr__(self, "name", name)
        object.__setattr__(self, "kind", kind)
        object.__setattr__(self, "default", default)


class AnimationParameters:
    def __init__(self, specs: Sequence[AnimationParameter]) -> None:
        self._specs: dict[str, AnimationParameter] = {}
        self._values: dict[str, Any] = {}
        for spec in specs:
            if spec.name in self._specs:
                raise ValueError(f"duplicate animation parameter: {spec.name}")
            self._specs[spec.name] = spec
            self._values[spec.name] = spec.default

    def spec(self, name: str) -> AnimationParameter:
        try:
            return self._specs[name]
        except KeyError as exc:
            raise KeyError(f"unknown animation parameter: {name}") from exc

    def get(self, name: str) -> Any:
        self.spec(name)
        return self._values[name]

    def set(self, name: str, value: Any) -> None:
        spec = self.spec(name)
        self._values[name] = _validate_parameter_value(
            spec.kind,
            value,
            label=f"parameter {name!r}",
        )

    def trigger(self, name: str) -> None:
        spec = self.spec(name)
        if spec.kind is not ParameterKind.TRIGGER:
            raise TypeError(f"parameter {name!r} is not a trigger")
        self._values[name] = True

    def reset_trigger(self, name: str) -> None:
        spec = self.spec(name)
        if spec.kind is not ParameterKind.TRIGGER:
            raise TypeError(f"parameter {name!r} is not a trigger")
        self._values[name] = False

    def snapshot(self) -> Mapping[str, Any]:
        return MappingProxyType(dict(self._values))


class ConditionOperator(str, Enum):
    EQ = "eq"
    NE = "ne"
    GT = "gt"
    GE = "ge"
    LT = "lt"
    LE = "le"
    TRUE = "true"
    FALSE = "false"
    TRIGGER = "trigger"


@dataclass(frozen=True, slots=True)
class AnimationCondition:
    parameter: str
    operator: ConditionOperator | str
    value: Any = None

    def __post_init__(self) -> None:
        parameter = _nonempty(self.parameter, label="condition parameter")
        object.__setattr__(self, "parameter", parameter)
        object.__setattr__(self, "operator", ConditionOperator(self.operator))

    def evaluate(self, parameters: AnimationParameters) -> bool:
        spec = parameters.spec(self.parameter)
        current = parameters.get(self.parameter)
        if self.operator is ConditionOperator.TRIGGER:
            if spec.kind is not ParameterKind.TRIGGER:
                raise TypeError(f"parameter {self.parameter!r} is not a trigger")
            return bool(current)
        if self.operator in {ConditionOperator.TRUE, ConditionOperator.FALSE}:
            if spec.kind is not ParameterKind.BOOL:
                raise TypeError(f"parameter {self.parameter!r} is not bool")
            return bool(current) is (self.operator is ConditionOperator.TRUE)
        expected = _validate_parameter_value(
            spec.kind,
            self.value,
            label=f"condition value for {self.parameter!r}",
        )
        if self.operator is ConditionOperator.EQ:
            return current == expected
        if self.operator is ConditionOperator.NE:
            return current != expected
        if spec.kind not in {ParameterKind.FLOAT, ParameterKind.INT}:
            raise TypeError(f"ordered comparison requires numeric parameter: {self.parameter!r}")
        if self.operator is ConditionOperator.GT:
            return current > expected
        if self.operator is ConditionOperator.GE:
            return current >= expected
        if self.operator is ConditionOperator.LT:
            return current < expected
        return current <= expected


@dataclass(frozen=True, slots=True)
class AnimationState2:
    name: str
    clip: AnimationClip
    speed: float = 1.0
    loop: bool = True

    def __post_init__(self) -> None:
        name = _nonempty(self.name, label="animation state name")
        speed = _finite(self.speed, label="animation state speed")
        if speed <= 0.0:
            raise ValueError("animation state speed must be > 0")
        object.__setattr__(self, "name", name)
        object.__setattr__(self, "speed", speed)

    def sample(self, time: float) -> AnimationPose:
        return self.clip.sample(time, loop=self.loop)


@dataclass(frozen=True, slots=True)
class AnimationTransition2:
    source: str
    target: str
    conditions: tuple[AnimationCondition, ...] = ()
    duration: float = 0.0
    exit_time: float | None = None
    priority: int = 0
    consume_triggers: bool = True
    allow_self: bool = False

    def __post_init__(self) -> None:
        source = (
            self.source
            if self.source == "*"
            else _nonempty(self.source, label="transition source")
        )
        target = _nonempty(self.target, label="transition target")
        duration = _finite(self.duration, label="transition duration")
        if duration < 0.0:
            raise ValueError("transition duration must be >= 0")
        exit_time = self.exit_time
        if exit_time is not None:
            exit_time = _finite(exit_time, label="transition exit time")
            if not 0.0 <= exit_time <= 1.0:
                raise ValueError("transition exit time must be between 0 and 1")
        object.__setattr__(self, "source", source)
        object.__setattr__(self, "target", target)
        object.__setattr__(self, "conditions", tuple(self.conditions))
        object.__setattr__(self, "duration", duration)
        object.__setattr__(self, "exit_time", exit_time)


class AnimationGraph2:
    def __init__(
        self,
        states: Sequence[AnimationState2],
        *,
        parameters: Sequence[AnimationParameter] = (),
        transitions: Sequence[AnimationTransition2] = (),
        initial: str | None = None,
    ) -> None:
        if not states:
            raise ValueError("animation graph must contain at least one state")
        self.states: dict[str, AnimationState2] = {}
        for state in states:
            if state.name in self.states:
                raise ValueError(f"duplicate animation state: {state.name}")
            self.states[state.name] = state
        self.parameters = tuple(parameters)
        probe = AnimationParameters(self.parameters)
        self.transitions = tuple(transitions)
        for transition in self.transitions:
            if transition.source != "*" and transition.source not in self.states:
                raise KeyError(f"unknown transition source: {transition.source}")
            if transition.target not in self.states:
                raise KeyError(f"unknown transition target: {transition.target}")
            for condition in transition.conditions:
                condition.evaluate(probe)
        self.initial = initial or next(iter(self.states))
        if self.initial not in self.states:
            raise KeyError(f"unknown initial animation state: {self.initial}")


@dataclass(slots=True)
class _TransitionRuntime:
    definition: AnimationTransition2
    source_state: str
    source_time: float
    target_time: float = 0.0
    elapsed: float = 0.0


@dataclass(frozen=True, slots=True)
class AnimationGraphDiagnostics:
    current_state: str
    next_state: str | None
    state_time: float
    normalized_time: float
    transition_progress: float | None
    transitions_taken: int
    parameters: Mapping[str, Any]
    pose_fingerprint: str

    def portable(self) -> dict[str, Any]:
        return {
            "current_state": self.current_state,
            "next_state": self.next_state,
            "state_time": self.state_time,
            "normalized_time": self.normalized_time,
            "transition_progress": self.transition_progress,
            "transitions_taken": self.transitions_taken,
            "parameters": dict(self.parameters),
            "pose_fingerprint": self.pose_fingerprint,
        }


class AnimationGraphPlayer:
    def __init__(self, graph: AnimationGraph2) -> None:
        self.graph = graph
        self.parameters = AnimationParameters(graph.parameters)
        self.current_state = graph.initial
        self.state_time = 0.0
        self._transition: _TransitionRuntime | None = None
        self.transitions_taken = 0

    @property
    def state(self) -> AnimationState2:
        return self.graph.states[self.current_state]

    @property
    def next_state(self) -> str | None:
        if self._transition is None:
            return None
        return self._transition.definition.target

    @property
    def normalized_time(self) -> float:
        runtime = self._transition
        if runtime is None:
            state = self.state
            state_time = self.state_time
        else:
            state = self.graph.states[runtime.source_state]
            state_time = runtime.source_time
        if state.loop:
            return (state_time % state.clip.duration) / state.clip.duration
        return min(1.0, state_time / state.clip.duration)

    def set_parameter(self, name: str, value: Any) -> None:
        self.parameters.set(name, value)

    def trigger(self, name: str) -> None:
        self.parameters.trigger(name)

    def force_state(self, name: str, *, time: float = 0.0, reset_triggers: bool = True) -> None:
        if name not in self.graph.states:
            raise KeyError(f"unknown animation state: {name}")
        time = _finite(time, label="animation state time")
        if time < 0.0:
            raise ValueError("animation state time must be >= 0")
        self.current_state = name
        self.state_time = time
        self._transition = None
        if reset_triggers:
            for parameter in self.graph.parameters:
                if parameter.kind is ParameterKind.TRIGGER:
                    self.parameters.reset_trigger(parameter.name)

    def _exit_reached(self, transition: AnimationTransition2) -> bool:
        if transition.exit_time is None:
            return True
        state = self.state
        threshold = transition.exit_time * state.clip.duration
        return self.state_time >= threshold

    def _choose_transition(self) -> AnimationTransition2 | None:
        candidates: list[tuple[int, int, AnimationTransition2]] = []
        for index, transition in enumerate(self.graph.transitions):
            if transition.source not in {"*", self.current_state}:
                continue
            if transition.target == self.current_state and not transition.allow_self:
                continue
            if not self._exit_reached(transition):
                continue
            if all(condition.evaluate(self.parameters) for condition in transition.conditions):
                candidates.append((-transition.priority, index, transition))
        if not candidates:
            return None
        candidates.sort(key=lambda item: (item[0], item[1]))
        return candidates[0][2]

    def _consume_transition_triggers(self, transition: AnimationTransition2) -> None:
        if not transition.consume_triggers:
            return
        for condition in transition.conditions:
            spec = self.parameters.spec(condition.parameter)
            if spec.kind is ParameterKind.TRIGGER and self.parameters.get(condition.parameter):
                self.parameters.reset_trigger(condition.parameter)

    def _begin_transition(self, transition: AnimationTransition2) -> None:
        self._consume_transition_triggers(transition)
        self.transitions_taken += 1
        if transition.duration == 0.0:
            self.current_state = transition.target
            self.state_time = 0.0
            self._transition = None
            return
        self._transition = _TransitionRuntime(
            definition=transition,
            source_state=self.current_state,
            source_time=self.state_time,
        )

    def sample(self) -> AnimationPose:
        runtime = self._transition
        if runtime is None:
            return self.state.sample(self.state_time)
        source = self.graph.states[runtime.source_state]
        target = self.graph.states[runtime.definition.target]
        weight = min(1.0, runtime.elapsed / runtime.definition.duration)
        return source.sample(runtime.source_time).blend(target.sample(runtime.target_time), weight)

    def update(self, dt: float) -> AnimationPose:
        dt = _finite(dt, label="animation dt")
        if dt < 0.0:
            raise ValueError("animation dt must be >= 0")
        runtime = self._transition
        if runtime is not None:
            source_state = self.graph.states[runtime.source_state]
            target_state = self.graph.states[runtime.definition.target]
            runtime.source_time += dt * source_state.speed
            runtime.target_time += dt * target_state.speed
            runtime.elapsed += dt
            if runtime.elapsed >= runtime.definition.duration:
                self.current_state = runtime.definition.target
                self.state_time = runtime.target_time
                self._transition = None
                return self.state.sample(self.state_time)
            return self.sample()

        self.state_time += dt * self.state.speed
        transition = self._choose_transition()
        if transition is not None:
            self._begin_transition(transition)
        return self.sample()

    def diagnostics(self) -> AnimationGraphDiagnostics:
        runtime = self._transition
        if runtime is None:
            progress = None
            state_time = self.state_time
        else:
            progress = min(1.0, runtime.elapsed / runtime.definition.duration)
            state_time = runtime.source_time
        pose = self.sample()
        return AnimationGraphDiagnostics(
            current_state=self.current_state,
            next_state=self.next_state,
            state_time=state_time,
            normalized_time=self.normalized_time,
            transition_progress=progress,
            transitions_taken=self.transitions_taken,
            parameters=self.parameters.snapshot(),
            pose_fingerprint=pose.fingerprint(),
        )

    def state_fingerprint(self) -> str:
        payload = json.dumps(
            _canonical(self.diagnostics().portable()),
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()
