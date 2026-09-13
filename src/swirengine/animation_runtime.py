from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping, MutableMapping
from dataclasses import dataclass, field
from enum import Enum
from math import cos, pi
from numbers import Real
from typing import Any


class Ease(str, Enum):
    LINEAR = "linear"
    IN_QUAD = "in_quad"
    OUT_QUAD = "out_quad"
    IN_OUT_QUAD = "in_out_quad"
    IN_OUT_SINE = "in_out_sine"


def ease_value(kind: Ease | str, t: float) -> float:
    t = max(0.0, min(1.0, float(t)))
    kind = Ease(kind)
    if kind is Ease.LINEAR:
        return t
    if kind is Ease.IN_QUAD:
        return t * t
    if kind is Ease.OUT_QUAD:
        return 1.0 - (1.0 - t) * (1.0 - t)
    if kind is Ease.IN_OUT_QUAD:
        return 2.0 * t * t if t < 0.5 else 1.0 - ((-2.0 * t + 2.0) ** 2) / 2.0
    return -(cos(pi * t) - 1.0) / 2.0


def interpolate(start: Any, end: Any, t: float) -> Any:
    t = max(0.0, min(1.0, float(t)))
    if isinstance(start, Real) and isinstance(end, Real):
        return start + (end - start) * t
    if isinstance(start, tuple) and isinstance(end, tuple) and len(start) == len(end):
        return tuple(interpolate(a, b, t) for a, b in zip(start, end))
    if isinstance(start, list) and isinstance(end, list) and len(start) == len(end):
        return [interpolate(a, b, t) for a, b in zip(start, end)]
    try:
        return start + (end - start) * t
    except (TypeError, ValueError):
        return end if t >= 1.0 else start


def _get_path(target: Any, path: str) -> Any:
    value = target
    for part in path.split("."):
        value = value[part] if isinstance(value, Mapping) else getattr(value, part)
    return value


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


@dataclass(slots=True)
class Tween:
    target: Any
    path: str
    end: Any
    duration: float
    start: Any | None = None
    ease: Ease | str = Ease.LINEAR
    delay: float = 0.0
    repeat: int = 0
    yoyo: bool = False
    on_complete: Callable[[Tween], None] | None = None
    elapsed: float = 0.0
    completed: bool = False
    _resolved_start: Any = field(default=None, init=False, repr=False)
    _cycle: int = field(default=0, init=False, repr=False)

    def __post_init__(self) -> None:
        if self.duration < 0.0:
            raise ValueError("duration must be >= 0")
        if self.delay < 0.0:
            raise ValueError("delay must be >= 0")
        if self.repeat < 0:
            raise ValueError("repeat must be >= 0")

    def reset(self) -> Tween:
        self.elapsed = 0.0
        self.completed = False
        self._cycle = 0
        self._resolved_start = None
        return self

    @property
    def total_duration(self) -> float:
        return self.delay + self.duration * (self.repeat + 1)

    def update(self, dt: float) -> bool:
        if self.completed:
            return True
        if dt < 0.0:
            raise ValueError("dt must be >= 0")
        if self._resolved_start is None:
            self._resolved_start = _get_path(self.target, self.path) if self.start is None else self.start

        self.elapsed += dt
        active = self.elapsed - self.delay
        if active < 0.0:
            return False

        if self.duration == 0.0:
            progress = 1.0
            cycle = self.repeat
        else:
            raw_cycle = int(active // self.duration)
            cycle = min(raw_cycle, self.repeat)
            cycle_time = active - cycle * self.duration
            if raw_cycle > self.repeat or active >= self.duration * (self.repeat + 1):
                progress = 1.0
            else:
                progress = min(1.0, cycle_time / self.duration)

        self._cycle = cycle
        eased = ease_value(self.ease, progress)
        reverse = self.yoyo and cycle % 2 == 1
        start, end = (self.end, self._resolved_start) if reverse else (self._resolved_start, self.end)
        _set_path(self.target, self.path, interpolate(start, end, eased))

        if active >= self.duration * (self.repeat + 1):
            final_reverse = self.yoyo and self.repeat % 2 == 1
            final_value = self._resolved_start if final_reverse else self.end
            _set_path(self.target, self.path, final_value)
            self.completed = True
            if self.on_complete is not None:
                self.on_complete(self)
        return self.completed


@dataclass(slots=True)
class TweenSequence:
    tweens: list[Tween] = field(default_factory=list)
    loop: bool = False
    playing: bool = True
    index: int = 0

    def append(self, tween: Tween) -> TweenSequence:
        self.tweens.append(tween)
        return self

    def reset(self) -> TweenSequence:
        self.index = 0
        self.playing = True
        for tween in self.tweens:
            tween.reset()
        return self

    def update(self, dt: float) -> bool:
        if not self.playing or not self.tweens:
            return not self.playing
        remaining = dt
        while self.index < len(self.tweens):
            tween = self.tweens[self.index]
            before = tween.elapsed
            done = tween.update(remaining)
            consumed = max(0.0, tween.elapsed - before)
            remaining = max(0.0, remaining - consumed)
            if not done:
                return False
            self.index += 1
            if remaining <= 0.0:
                break
        if self.index >= len(self.tweens):
            if self.loop:
                self.reset()
                if remaining > 0.0:
                    return self.update(remaining)
                return False
            self.playing = False
            return True
        return False


@dataclass(frozen=True, slots=True)
class TimelineMarker:
    time: float
    name: str
    payload: Any = None


@dataclass(slots=True)
class AnimationTimeline:
    tracks: list[Tween] = field(default_factory=list)
    markers: list[TimelineMarker] = field(default_factory=list)
    time: float = 0.0
    playing: bool = True
    loop: bool = False
    speed: float = 1.0
    on_marker: Callable[[TimelineMarker], None] | None = None
    _fired_markers: set[int] = field(default_factory=set, init=False, repr=False)

    @property
    def duration(self) -> float:
        track_end = max((track.total_duration for track in self.tracks), default=0.0)
        marker_end = max((marker.time for marker in self.markers), default=0.0)
        return max(track_end, marker_end)

    def add(self, tween: Tween) -> AnimationTimeline:
        self.tracks.append(tween)
        return self

    def add_marker(self, time: float, name: str, payload: Any = None) -> AnimationTimeline:
        if time < 0.0:
            raise ValueError("marker time must be >= 0")
        self.markers.append(TimelineMarker(float(time), name, payload))
        self.markers.sort(key=lambda marker: marker.time)
        return self

    def seek(self, time: float) -> None:
        self.time = max(0.0, min(float(time), self.duration))
        self._fired_markers.clear()
        for track in self.tracks:
            track.reset()
            track.update(self.time)
        for index, marker in enumerate(self.markers):
            if marker.time <= self.time:
                self._fired_markers.add(index)

    def reset(self) -> AnimationTimeline:
        self.time = 0.0
        self.playing = True
        self._fired_markers.clear()
        for track in self.tracks:
            track.reset()
        return self

    def update(self, dt: float) -> bool:
        if not self.playing:
            return True
        if dt < 0.0:
            raise ValueError("dt must be >= 0")
        previous = self.time
        scaled = dt * self.speed
        self.time += scaled
        for track in self.tracks:
            track.update(scaled)
        for index, marker in enumerate(self.markers):
            if index not in self._fired_markers and previous < marker.time <= self.time:
                self._fired_markers.add(index)
                if self.on_marker is not None:
                    self.on_marker(marker)
        if self.time >= self.duration:
            if self.loop and self.duration > 0.0:
                overflow = self.time - self.duration
                self.reset()
                if overflow > 0.0:
                    return self.update(overflow)
                return False
            self.playing = False
            return True
        return False


@dataclass(slots=True)
class State:
    name: str
    on_enter: Callable[[str | None], None] | None = None
    on_update: Callable[[float], None] | None = None
    on_exit: Callable[[str], None] | None = None


@dataclass(frozen=True, slots=True)
class Transition:
    source: str
    target: str
    condition: Callable[[], bool]
    priority: int = 0


class StateMachine:
    def __init__(self, states: Iterable[State] = (), initial: str | None = None) -> None:
        self.states: dict[str, State] = {state.name: state for state in states}
        self.transitions: list[Transition] = []
        self.current: str | None = None
        self.time_in_state = 0.0
        if initial is not None:
            self.set_state(initial)

    @property
    def state(self) -> State | None:
        return self.states.get(self.current) if self.current is not None else None

    def add_state(self, state: State) -> StateMachine:
        self.states[state.name] = state
        return self

    def add_transition(
        self,
        source: str,
        target: str,
        condition: Callable[[], bool],
        priority: int = 0,
    ) -> StateMachine:
        if target not in self.states:
            raise KeyError(f"unknown target state: {target}")
        if source != "*" and source not in self.states:
            raise KeyError(f"unknown source state: {source}")
        self.transitions.append(Transition(source, target, condition, priority))
        self.transitions.sort(key=lambda transition: transition.priority, reverse=True)
        return self

    def set_state(self, name: str) -> None:
        if name not in self.states:
            raise KeyError(f"unknown state: {name}")
        previous = self.current
        if previous == name:
            return
        if previous is not None:
            old = self.states[previous]
            if old.on_exit is not None:
                old.on_exit(name)
        self.current = name
        self.time_in_state = 0.0
        state = self.states[name]
        if state.on_enter is not None:
            state.on_enter(previous)

    def update(self, dt: float) -> str | None:
        if dt < 0.0:
            raise ValueError("dt must be >= 0")
        if self.current is None:
            return None
        self.time_in_state += dt
        state = self.states[self.current]
        if state.on_update is not None:
            state.on_update(dt)
        for transition in self.transitions:
            if transition.source not in {"*", self.current}:
                continue
            if transition.condition():
                self.set_state(transition.target)
                break
        return self.current


class AnimationSystem:
    def __init__(self) -> None:
        self.timelines: list[AnimationTimeline] = []
        self.sequences: list[TweenSequence] = []
        self.state_machines: list[StateMachine] = []

    def add(self, item: AnimationTimeline | TweenSequence | StateMachine) -> Any:
        if isinstance(item, AnimationTimeline):
            self.timelines.append(item)
        elif isinstance(item, TweenSequence):
            self.sequences.append(item)
        elif isinstance(item, StateMachine):
            self.state_machines.append(item)
        else:
            raise TypeError(f"unsupported animation item: {type(item).__name__}")
        return item

    def update(self, dt: float) -> None:
        for timeline in tuple(self.timelines):
            timeline.update(dt)
        for sequence in tuple(self.sequences):
            sequence.update(dt)
        for machine in tuple(self.state_machines):
            machine.update(dt)

    def prune_finished(self) -> None:
        self.timelines[:] = [timeline for timeline in self.timelines if timeline.playing]
        self.sequences[:] = [sequence for sequence in self.sequences if sequence.playing]
