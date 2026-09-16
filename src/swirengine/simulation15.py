from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

REPLAY_FORMAT = "swirengine.replay"
REPLAY_VERSION = 1

Portable = None | bool | int | float | str | list["Portable"] | dict[str, "Portable"]
ReplayStep = Callable[[int, float, dict[str, Portable]], Any]
StateProvider = Callable[[], Mapping[str, Any]]
StateRestorer = Callable[[Mapping[str, Any]], None]


def _portable(value: Any) -> Portable:
    if value is None or isinstance(value, (bool, str, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("replay floats must be finite")
        return 0.0 if value == 0.0 else value
    if isinstance(value, (list, tuple)):
        return [_portable(item) for item in value]
    if isinstance(value, Mapping):
        result: dict[str, Portable] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise TypeError("replay mapping keys must be strings")
            result[key] = _portable(item)
        return result
    raise TypeError(f"unsupported replay value type: {type(value).__name__}")


def portable_state(value: Mapping[str, Any]) -> dict[str, Portable]:
    normalized = _portable(value)
    if not isinstance(normalized, dict):
        raise TypeError("state must be a mapping")
    return normalized


def canonical_json(value: Any) -> str:
    return json.dumps(
        _portable(value),
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    )


def state_fingerprint(state: Mapping[str, Any]) -> str:
    payload = canonical_json(portable_state(state)).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


@dataclass(slots=True, frozen=True)
class SimulationTick:
    tick: int
    dt: float
    simulation_time: float

    def __post_init__(self) -> None:
        if self.tick < 1:
            raise ValueError("tick must be at least 1")
        if not math.isfinite(self.dt) or self.dt <= 0.0:
            raise ValueError("dt must be finite and positive")
        if not math.isfinite(self.simulation_time) or self.simulation_time < 0.0:
            raise ValueError("simulation_time must be finite and non-negative")


class FixedStepClock:
    """Convert variable wall-clock advances into bounded deterministic simulation ticks."""

    def __init__(self, step_seconds: float = 1.0 / 60.0, max_steps_per_advance: int = 8) -> None:
        if not math.isfinite(step_seconds) or step_seconds <= 0.0:
            raise ValueError("step_seconds must be finite and positive")
        if max_steps_per_advance < 1:
            raise ValueError("max_steps_per_advance must be at least 1")
        self.step_seconds = float(step_seconds)
        self.max_steps_per_advance = int(max_steps_per_advance)
        self.tick = 0
        self.accumulator = 0.0
        self.dropped_steps = 0

    @property
    def simulation_time(self) -> float:
        return self.tick * self.step_seconds

    @property
    def alpha(self) -> float:
        return min(1.0, max(0.0, self.accumulator / self.step_seconds))

    def reset(self, *, tick: int = 0, accumulator: float = 0.0) -> None:
        if tick < 0:
            raise ValueError("tick must be non-negative")
        if not math.isfinite(accumulator) or not 0.0 <= accumulator < self.step_seconds:
            raise ValueError("accumulator must be finite and smaller than step_seconds")
        self.tick = int(tick)
        self.accumulator = float(accumulator)
        self.dropped_steps = 0

    def advance(self, elapsed_seconds: float) -> tuple[SimulationTick, ...]:
        if not math.isfinite(elapsed_seconds) or elapsed_seconds < 0.0:
            raise ValueError("elapsed_seconds must be finite and non-negative")
        self.accumulator += elapsed_seconds
        ready = int((self.accumulator + self.step_seconds * 1e-12) / self.step_seconds)
        executed = min(ready, self.max_steps_per_advance)
        dropped = ready - executed
        self.accumulator -= ready * self.step_seconds
        if self.accumulator < 0.0 and abs(self.accumulator) <= self.step_seconds * 1e-9:
            self.accumulator = 0.0
        self.dropped_steps += dropped

        ticks: list[SimulationTick] = []
        for _ in range(executed):
            self.tick += 1
            ticks.append(
                SimulationTick(
                    tick=self.tick,
                    dt=self.step_seconds,
                    simulation_time=self.simulation_time,
                )
            )
        return tuple(ticks)


@dataclass(slots=True, frozen=True)
class ReplayFrame:
    tick: int
    input_payload: dict[str, Portable]
    state_hash: str | None = None

    def __post_init__(self) -> None:
        if self.tick < 1:
            raise ValueError("replay frame tick must be at least 1")
        object.__setattr__(self, "input_payload", portable_state(self.input_payload))
        if self.state_hash is not None:
            if len(self.state_hash) != 64 or any(
                ch not in "0123456789abcdef" for ch in self.state_hash
            ):
                raise ValueError("state_hash must be a lowercase SHA-256 hex digest")

    def to_payload(self) -> dict[str, Any]:
        result: dict[str, Any] = {"tick": self.tick, "input": self.input_payload}
        if self.state_hash is not None:
            result["state_hash"] = self.state_hash
        return result

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> ReplayFrame:
        tick = payload.get("tick")
        input_payload = payload.get("input")
        state_hash = payload.get("state_hash")
        if not isinstance(tick, int) or isinstance(tick, bool):
            raise TypeError("replay frame tick must be an integer")
        if not isinstance(input_payload, Mapping):
            raise TypeError("replay frame input must be a mapping")
        if state_hash is not None and not isinstance(state_hash, str):
            raise TypeError("replay frame state_hash must be a string or null")
        return cls(tick=tick, input_payload=dict(input_payload), state_hash=state_hash)


@dataclass(slots=True, frozen=True)
class ReplayCheckpoint:
    tick: int
    state: dict[str, Portable]

    def __post_init__(self) -> None:
        if self.tick < 0:
            raise ValueError("checkpoint tick must be non-negative")
        object.__setattr__(self, "state", portable_state(self.state))

    def to_payload(self) -> dict[str, Any]:
        return {"tick": self.tick, "state": self.state}

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> ReplayCheckpoint:
        tick = payload.get("tick")
        state = payload.get("state")
        if not isinstance(tick, int) or isinstance(tick, bool):
            raise TypeError("checkpoint tick must be an integer")
        if not isinstance(state, Mapping):
            raise TypeError("checkpoint state must be a mapping")
        return cls(tick=tick, state=dict(state))


@dataclass(slots=True, frozen=True)
class ReplayRecording:
    step_seconds: float
    frames: tuple[ReplayFrame, ...]
    checkpoints: tuple[ReplayCheckpoint, ...] = ()
    metadata: dict[str, Portable] | None = None

    def __post_init__(self) -> None:
        if not math.isfinite(self.step_seconds) or self.step_seconds <= 0.0:
            raise ValueError("step_seconds must be finite and positive")
        frame_ticks = [frame.tick for frame in self.frames]
        if frame_ticks != sorted(frame_ticks) or len(frame_ticks) != len(set(frame_ticks)):
            raise ValueError("replay frame ticks must be unique and increasing")
        checkpoint_ticks = [checkpoint.tick for checkpoint in self.checkpoints]
        if checkpoint_ticks != sorted(checkpoint_ticks) or len(checkpoint_ticks) != len(
            set(checkpoint_ticks)
        ):
            raise ValueError("checkpoint ticks must be unique and increasing")
        object.__setattr__(self, "metadata", portable_state(self.metadata or {}))

    @property
    def first_tick(self) -> int | None:
        return self.frames[0].tick if self.frames else None

    @property
    def last_tick(self) -> int | None:
        return self.frames[-1].tick if self.frames else None

    def to_payload(self) -> dict[str, Any]:
        return {
            "format": REPLAY_FORMAT,
            "version": REPLAY_VERSION,
            "step_seconds": self.step_seconds,
            "metadata": self.metadata,
            "frames": [frame.to_payload() for frame in self.frames],
            "checkpoints": [checkpoint.to_payload() for checkpoint in self.checkpoints],
        }

    def to_json(self, *, pretty: bool = False) -> str:
        if pretty:
            return json.dumps(
                self.to_payload(),
                ensure_ascii=False,
                allow_nan=False,
                indent=2,
                sort_keys=True,
            )
        return canonical_json(self.to_payload())

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> ReplayRecording:
        if payload.get("format") != REPLAY_FORMAT:
            raise ValueError("unsupported replay format")
        if payload.get("version") != REPLAY_VERSION:
            raise ValueError("unsupported replay version")
        step_seconds = payload.get("step_seconds")
        frames = payload.get("frames")
        checkpoints = payload.get("checkpoints", [])
        metadata = payload.get("metadata", {})
        if not isinstance(step_seconds, (int, float)) or isinstance(step_seconds, bool):
            raise TypeError("step_seconds must be numeric")
        if not isinstance(frames, list):
            raise TypeError("frames must be a list")
        if not isinstance(checkpoints, list):
            raise TypeError("checkpoints must be a list")
        if not isinstance(metadata, Mapping):
            raise TypeError("metadata must be a mapping")
        return cls(
            step_seconds=float(step_seconds),
            frames=tuple(ReplayFrame.from_payload(item) for item in frames),
            checkpoints=tuple(ReplayCheckpoint.from_payload(item) for item in checkpoints),
            metadata=dict(metadata),
        )

    @classmethod
    def from_json(cls, text: str) -> ReplayRecording:
        payload = json.loads(text)
        if not isinstance(payload, Mapping):
            raise TypeError("replay JSON root must be an object")
        return cls.from_payload(payload)


class ReplayRecorder:
    """Capture deterministic inputs plus optional hashes/checkpoints without owning game state."""

    def __init__(
        self,
        step_seconds: float = 1.0 / 60.0,
        *,
        max_frames: int | None = None,
        checkpoint_interval: int = 0,
    ) -> None:
        if not math.isfinite(step_seconds) or step_seconds <= 0.0:
            raise ValueError("step_seconds must be finite and positive")
        if max_frames is not None and max_frames < 1:
            raise ValueError("max_frames must be at least 1")
        if checkpoint_interval < 0:
            raise ValueError("checkpoint_interval must be non-negative")
        self.step_seconds = float(step_seconds)
        self.max_frames = max_frames
        self.checkpoint_interval = int(checkpoint_interval)
        self._frames: list[ReplayFrame] = []
        self._checkpoints: list[ReplayCheckpoint] = []

    @property
    def frame_count(self) -> int:
        return len(self._frames)

    def add_checkpoint(self, tick: int, state: Mapping[str, Any]) -> ReplayCheckpoint:
        checkpoint = ReplayCheckpoint(tick=tick, state=portable_state(state))
        if self._checkpoints and tick <= self._checkpoints[-1].tick:
            raise ValueError("checkpoint ticks must be strictly increasing")
        self._checkpoints.append(checkpoint)
        self._prune_checkpoints()
        return checkpoint

    def record(
        self,
        tick: int,
        input_payload: Mapping[str, Any],
        *,
        state: Mapping[str, Any] | None = None,
        checkpoint: bool = False,
    ) -> ReplayFrame:
        if self._frames and tick <= self._frames[-1].tick:
            raise ValueError("replay frame ticks must be strictly increasing")
        fingerprint = state_fingerprint(state) if state is not None else None
        frame = ReplayFrame(
            tick=tick,
            input_payload=portable_state(input_payload),
            state_hash=fingerprint,
        )
        self._frames.append(frame)
        should_checkpoint = checkpoint or (
            state is not None
            and self.checkpoint_interval > 0
            and tick % self.checkpoint_interval == 0
        )
        if should_checkpoint:
            if state is None:
                raise ValueError("checkpoint recording requires state")
            self.add_checkpoint(tick, state)
        if self.max_frames is not None and len(self._frames) > self.max_frames:
            del self._frames[: len(self._frames) - self.max_frames]
            self._prune_checkpoints()
        return frame

    def _prune_checkpoints(self) -> None:
        if not self._frames:
            return
        first_tick = self._frames[0].tick
        self._checkpoints[:] = [
            item for item in self._checkpoints if item.tick >= first_tick - 1
        ]

    def build(self, *, metadata: Mapping[str, Any] | None = None) -> ReplayRecording:
        return ReplayRecording(
            step_seconds=self.step_seconds,
            frames=tuple(self._frames),
            checkpoints=tuple(self._checkpoints),
            metadata=portable_state(metadata or {}),
        )


@dataclass(slots=True, frozen=True)
class ReplayStepResult:
    tick: int
    expected_state_hash: str | None
    actual_state_hash: str | None

    @property
    def verified(self) -> bool:
        return (
            self.expected_state_hash is not None
            and self.expected_state_hash == self.actual_state_hash
        )


@dataclass(slots=True, frozen=True)
class ReplayReport:
    frames_played: int
    first_tick: int | None
    last_tick: int | None
    verified_frames: int


class ReplayDivergenceError(RuntimeError):
    def __init__(self, result: ReplayStepResult) -> None:
        self.result = result
        super().__init__(
            "replay diverged at tick "
            f"{result.tick}: expected {result.expected_state_hash}, got {result.actual_state_hash}"
        )


class ReplayPlayer:
    """Drive a creator-owned deterministic simulation from a versioned recording."""

    def __init__(
        self,
        recording: ReplayRecording,
        step: ReplayStep,
        *,
        state_provider: StateProvider | None = None,
        state_restorer: StateRestorer | None = None,
    ) -> None:
        self.recording = recording
        self.step_callback = step
        self.state_provider = state_provider
        self.state_restorer = state_restorer
        self._index = 0

    @property
    def remaining(self) -> int:
        return len(self.recording.frames) - self._index

    def reset(self) -> None:
        self._index = 0

    def step_once(self, *, verify: bool = True) -> ReplayStepResult | None:
        if self._index >= len(self.recording.frames):
            return None
        frame = self.recording.frames[self._index]
        self.step_callback(frame.tick, self.recording.step_seconds, dict(frame.input_payload))
        actual_hash: str | None = None
        if verify and frame.state_hash is not None:
            if self.state_provider is None:
                raise RuntimeError("state_provider is required to verify recorded state hashes")
            actual_hash = state_fingerprint(self.state_provider())
        result = ReplayStepResult(
            tick=frame.tick,
            expected_state_hash=frame.state_hash,
            actual_state_hash=actual_hash,
        )
        self._index += 1
        if verify and frame.state_hash is not None and actual_hash != frame.state_hash:
            raise ReplayDivergenceError(result)
        return result

    def play(self, *, max_frames: int | None = None, verify: bool = True) -> ReplayReport:
        if max_frames is not None and max_frames < 0:
            raise ValueError("max_frames must be non-negative")
        played = 0
        verified = 0
        first_tick: int | None = None
        last_tick: int | None = None
        while self.remaining and (max_frames is None or played < max_frames):
            result = self.step_once(verify=verify)
            if result is None:
                break
            if first_tick is None:
                first_tick = result.tick
            last_tick = result.tick
            played += 1
            verified += int(result.verified)
        return ReplayReport(
            frames_played=played,
            first_tick=first_tick,
            last_tick=last_tick,
            verified_frames=verified,
        )

    def seek(self, tick: int, *, verify: bool = True) -> ReplayReport:
        if tick < 0:
            raise ValueError("tick must be non-negative")
        if self.state_restorer is None:
            raise RuntimeError("state_restorer is required for replay seeking")
        checkpoint = next(
            (item for item in reversed(self.recording.checkpoints) if item.tick <= tick),
            None,
        )
        if checkpoint is None:
            raise ValueError(f"no checkpoint available at or before tick {tick}")
        self.state_restorer(dict(checkpoint.state))
        self._index = 0
        while (
            self._index < len(self.recording.frames)
            and self.recording.frames[self._index].tick <= checkpoint.tick
        ):
            self._index += 1
        played = 0
        verified = 0
        first_tick: int | None = None
        last_tick: int | None = None
        while self.remaining and self.recording.frames[self._index].tick <= tick:
            result = self.step_once(verify=verify)
            if result is None:
                break
            if first_tick is None:
                first_tick = result.tick
            last_tick = result.tick
            played += 1
            verified += int(result.verified)
        return ReplayReport(played, first_tick, last_tick, verified)
