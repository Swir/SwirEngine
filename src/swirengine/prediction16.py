from __future__ import annotations

import math
from collections import deque
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

from .multiplayer14 import PredictionCommand
from .networking import NetworkPacket

PREDICTION_CORRECTION_PACKET_KIND = "swir.prediction16.correction"

State = dict[str, Any]
SimulationStep = Callable[[State, PredictionCommand], Mapping[str, Any]]
CorrectionBlend = Callable[[State, State, float], Mapping[str, Any]]


def _portable(value: Any) -> Any:
    if value is None or isinstance(value, (bool, str, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("prediction state floats must be finite")
        return value
    if isinstance(value, (list, tuple)):
        return [_portable(item) for item in value]
    if isinstance(value, Mapping):
        result: dict[str, Any] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise TypeError("prediction state mapping keys must be strings")
            result[key] = _portable(item)
        return result
    raise TypeError(f"unsupported prediction state value type: {type(value).__name__}")


def _state(value: Mapping[str, Any]) -> State:
    normalized = _portable(value)
    if not isinstance(normalized, dict):
        raise TypeError("prediction state must be a mapping")
    return normalized


def _blend_value(older: Any, newer: Any, alpha: float) -> Any:
    if isinstance(older, bool) or isinstance(newer, bool):
        return newer if alpha >= 1.0 else older
    if isinstance(older, (int, float)) and isinstance(newer, (int, float)):
        return float(older) + (float(newer) - float(older)) * alpha
    if isinstance(older, list) and isinstance(newer, list) and len(older) == len(newer):
        return [_blend_value(left, right, alpha) for left, right in zip(older, newer, strict=True)]
    if isinstance(older, dict) and isinstance(newer, dict):
        result: dict[str, Any] = {}
        for key in sorted(older.keys() | newer.keys()):
            if key in older and key in newer:
                result[key] = _blend_value(older[key], newer[key], alpha)
            elif key in older and alpha < 1.0:
                result[key] = _portable(older[key])
            elif key in newer:
                result[key] = _portable(newer[key])
        return result
    return _portable(newer if alpha >= 1.0 else older)


@dataclass(slots=True, frozen=True)
class PredictionCorrection:
    """Authoritative state tied to a replication tick and command acknowledgement."""

    acknowledged_sequence: int
    replication_tick: int
    authoritative_state: State

    def __post_init__(self) -> None:
        if not isinstance(self.acknowledged_sequence, int) or isinstance(
            self.acknowledged_sequence, bool
        ):
            raise TypeError("acknowledged_sequence must be an integer")
        if self.acknowledged_sequence < 0:
            raise ValueError("acknowledged_sequence must not be negative")
        if not isinstance(self.replication_tick, int) or isinstance(self.replication_tick, bool):
            raise TypeError("replication_tick must be an integer")
        if self.replication_tick < 0:
            raise ValueError("replication_tick must not be negative")
        object.__setattr__(self, "authoritative_state", _state(self.authoritative_state))

    def to_packet(self) -> NetworkPacket:
        return NetworkPacket(
            PREDICTION_CORRECTION_PACKET_KIND,
            {
                "acknowledged_sequence": self.acknowledged_sequence,
                "replication_tick": self.replication_tick,
                "authoritative_state": _state(self.authoritative_state),
            },
        )

    @classmethod
    def from_packet(cls, packet: NetworkPacket) -> PredictionCorrection:
        if packet.kind != PREDICTION_CORRECTION_PACKET_KIND:
            raise ValueError(
                f"expected {PREDICTION_CORRECTION_PACKET_KIND}, got {packet.kind}"
            )
        payload = packet.payload
        state = payload.get("authoritative_state")
        if not isinstance(state, Mapping):
            raise TypeError("prediction correction state must be an object")
        return cls(
            acknowledged_sequence=payload.get("acknowledged_sequence"),
            replication_tick=payload.get("replication_tick"),
            authoritative_state=state,
        )


@dataclass(slots=True, frozen=True)
class CorrectionTransition:
    """Presentation-only transition from predicted state to corrected simulation truth."""

    previous_state: State
    corrected_state: State

    def __post_init__(self) -> None:
        object.__setattr__(self, "previous_state", _state(self.previous_state))
        object.__setattr__(self, "corrected_state", _state(self.corrected_state))

    def sample(self, alpha: float, *, blend: CorrectionBlend | None = None) -> State:
        alpha = float(alpha)
        if not math.isfinite(alpha) or not 0.0 <= alpha <= 1.0:
            raise ValueError("correction alpha must be finite and within [0, 1]")
        if blend is not None:
            return _state(blend(_state(self.previous_state), _state(self.corrected_state), alpha))
        result = _blend_value(self.previous_state, self.corrected_state, alpha)
        if not isinstance(result, dict):
            raise TypeError("correction blend must produce a state mapping")
        return result


@dataclass(slots=True, frozen=True)
class PredictionReconciliation:
    applied: bool
    stale: bool
    corrected: bool
    acknowledged_sequence: int
    replication_tick: int
    replayed_commands: int
    state: State
    transition: CorrectionTransition | None = None


@dataclass(slots=True)
class PredictionDiagnostics:
    predicted_commands: int = 0
    reconciliations: int = 0
    stale_corrections: int = 0
    corrected_reconciliations: int = 0
    replayed_commands: int = 0
    replay_budget_rejections: int = 0
    prediction_window_rejections: int = 0
    pending_overflow_rejections: int = 0
    peak_pending_commands: int = 0

    def snapshot(self) -> dict[str, int]:
        return {
            "predicted_commands": self.predicted_commands,
            "reconciliations": self.reconciliations,
            "stale_corrections": self.stale_corrections,
            "corrected_reconciliations": self.corrected_reconciliations,
            "replayed_commands": self.replayed_commands,
            "replay_budget_rejections": self.replay_budget_rejections,
            "prediction_window_rejections": self.prediction_window_rejections,
            "pending_overflow_rejections": self.pending_overflow_rejections,
            "peak_pending_commands": self.peak_pending_commands,
        }


class ReplayBudgetExceeded(RuntimeError):
    """Raised before reconciliation mutates state when deterministic replay exceeds its budget."""


class PredictionTimeline:
    """Bounded prediction/reconciliation timeline layered on the stable 1.4 command model.

    Simulation truth is corrected immediately. Visual smoothing is represented separately by the
    returned :class:`CorrectionTransition`, so rendering policy can never delay authoritative state.
    """

    def __init__(
        self,
        initial_state: Mapping[str, Any],
        simulate: SimulationStep,
        *,
        initial_authoritative_tick: int = 0,
        max_pending: int = 256,
        max_prediction_ticks: int = 8,
        max_replay_commands: int = 64,
    ) -> None:
        if not isinstance(initial_authoritative_tick, int) or isinstance(
            initial_authoritative_tick, bool
        ):
            raise TypeError("initial_authoritative_tick must be an integer")
        if initial_authoritative_tick < 0:
            raise ValueError("initial_authoritative_tick must not be negative")
        if max_pending < 1:
            raise ValueError("max_pending must be positive")
        if max_prediction_ticks < 0:
            raise ValueError("max_prediction_ticks must not be negative")
        if max_replay_commands < 0:
            raise ValueError("max_replay_commands must not be negative")
        self.state = _state(initial_state)
        self.simulate = simulate
        self.max_pending = int(max_pending)
        self.max_prediction_ticks = int(max_prediction_ticks)
        self.max_replay_commands = int(max_replay_commands)
        self._pending: deque[PredictionCommand] = deque()
        self._last_sequence = 0
        self._last_acknowledged_sequence = 0
        self._last_authoritative_tick = int(initial_authoritative_tick)
        self._diagnostics = PredictionDiagnostics()

    @property
    def pending_commands(self) -> tuple[PredictionCommand, ...]:
        return tuple(self._pending)

    @property
    def last_sequence(self) -> int:
        return self._last_sequence

    @property
    def last_acknowledged_sequence(self) -> int:
        return self._last_acknowledged_sequence

    @property
    def last_authoritative_tick(self) -> int:
        return self._last_authoritative_tick

    def diagnostics(self) -> dict[str, int]:
        return self._diagnostics.snapshot()

    def predict(self, command: PredictionCommand) -> State:
        if command.sequence <= self._last_sequence:
            raise ValueError("prediction command sequence must increase")
        if command.tick < self._last_authoritative_tick:
            self._diagnostics.prediction_window_rejections += 1
            raise ValueError("prediction command tick precedes the authoritative timeline")
        if command.tick > self._last_authoritative_tick + self.max_prediction_ticks:
            self._diagnostics.prediction_window_rejections += 1
            raise ValueError("prediction command exceeds the configured prediction window")
        if len(self._pending) >= self.max_pending:
            self._diagnostics.pending_overflow_rejections += 1
            raise OverflowError("prediction history is full")

        next_state = _state(self.simulate(_state(self.state), command))
        self._last_sequence = command.sequence
        self._pending.append(command)
        self.state = next_state
        self._diagnostics.predicted_commands += 1
        self._diagnostics.peak_pending_commands = max(
            self._diagnostics.peak_pending_commands, len(self._pending)
        )
        return _state(self.state)

    def reconcile(self, correction: PredictionCorrection) -> PredictionReconciliation:
        if correction.replication_tick <= self._last_authoritative_tick:
            self._diagnostics.stale_corrections += 1
            return PredictionReconciliation(
                applied=False,
                stale=True,
                corrected=False,
                acknowledged_sequence=self._last_acknowledged_sequence,
                replication_tick=self._last_authoritative_tick,
                replayed_commands=0,
                state=_state(self.state),
            )
        if correction.acknowledged_sequence < self._last_acknowledged_sequence:
            raise ValueError("newer authoritative tick cannot regress command acknowledgement")
        if correction.acknowledged_sequence > self._last_sequence:
            raise ValueError("server cannot acknowledge an unsent prediction command")
        if correction.acknowledged_sequence > self._last_acknowledged_sequence and not any(
            command.sequence == correction.acknowledged_sequence for command in self._pending
        ):
            raise ValueError("server cannot acknowledge a prediction command the client did not predict")

        remaining = tuple(
            command
            for command in self._pending
            if command.sequence > correction.acknowledged_sequence
        )
        if len(remaining) > self.max_replay_commands:
            self._diagnostics.replay_budget_rejections += 1
            raise ReplayBudgetExceeded(
                "reconciliation replay exceeds max_replay_commands; request a full prediction reset"
            )

        rebuilt = _state(correction.authoritative_state)
        for command in remaining:
            rebuilt = _state(self.simulate(rebuilt, command))

        previous = _state(self.state)
        corrected = previous != rebuilt
        self.state = rebuilt
        self._pending = deque(remaining)
        self._last_acknowledged_sequence = correction.acknowledged_sequence
        self._last_authoritative_tick = correction.replication_tick
        self._diagnostics.reconciliations += 1
        self._diagnostics.replayed_commands += len(remaining)
        if corrected:
            self._diagnostics.corrected_reconciliations += 1
        transition = CorrectionTransition(previous, rebuilt) if corrected else None
        return PredictionReconciliation(
            applied=True,
            stale=False,
            corrected=corrected,
            acknowledged_sequence=correction.acknowledged_sequence,
            replication_tick=correction.replication_tick,
            replayed_commands=len(remaining),
            state=_state(rebuilt),
            transition=transition,
        )

    def reconcile_packet(self, packet: NetworkPacket) -> PredictionReconciliation:
        return self.reconcile(PredictionCorrection.from_packet(packet))


__all__ = [
    "PREDICTION_CORRECTION_PACKET_KIND",
    "CorrectionBlend",
    "CorrectionTransition",
    "PredictionCorrection",
    "PredictionDiagnostics",
    "PredictionReconciliation",
    "PredictionTimeline",
    "ReplayBudgetExceeded",
]
