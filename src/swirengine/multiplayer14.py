from __future__ import annotations

import bisect
import json
import math
from collections import deque
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any

from .networking import NetworkPacket

SNAPSHOT_PACKET_KIND = "swir.multiplayer.snapshot"
DELTA_PACKET_KIND = "swir.multiplayer.delta"

State = dict[str, Any]
SimulationStep = Callable[[State, "PredictionCommand"], Mapping[str, Any]]


def _portable(value: Any) -> Any:
    if value is None or isinstance(value, (bool, str, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("replicated floats must be finite")
        return value
    if isinstance(value, (list, tuple)):
        return [_portable(item) for item in value]
    if isinstance(value, Mapping):
        result: dict[str, Any] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise TypeError("replicated mapping keys must be strings")
            result[key] = _portable(item)
        return result
    raise TypeError(f"unsupported replicated value type: {type(value).__name__}")


def _state(value: Mapping[str, Any]) -> State:
    normalized = _portable(value)
    if not isinstance(normalized, dict):
        raise TypeError("state must be a mapping")
    return normalized


def _lerp_value(older: Any, newer: Any, alpha: float) -> Any:
    if isinstance(older, bool) or isinstance(newer, bool):
        return newer if alpha >= 1.0 else older
    if isinstance(older, (int, float)) and isinstance(newer, (int, float)):
        return float(older) + (float(newer) - float(older)) * alpha
    if isinstance(older, list) and isinstance(newer, list) and len(older) == len(newer):
        return [_lerp_value(left, right, alpha) for left, right in zip(older, newer, strict=True)]
    if isinstance(older, dict) and isinstance(newer, dict):
        result: dict[str, Any] = {}
        for key in sorted(older.keys() | newer.keys()):
            if key in older and key in newer:
                result[key] = _lerp_value(older[key], newer[key], alpha)
            elif key in older:
                result[key] = _portable(older[key])
            elif alpha >= 1.0:
                result[key] = _portable(newer[key])
        return result
    return _portable(newer if alpha >= 1.0 else older)


@dataclass(slots=True, frozen=True)
class ReplicationField:
    name: str
    interpolate: bool = True

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("replication field name must not be empty")


@dataclass(slots=True, frozen=True)
class ReplicationComponent:
    name: str
    fields: tuple[ReplicationField, ...]

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("replication component name must not be empty")
        names = [item.name for item in self.fields]
        if not names:
            raise ValueError("replication component requires at least one field")
        if len(set(names)) != len(names):
            raise ValueError("replication component field names must be unique")

    def capture(self, source: Mapping[str, Any]) -> State:
        captured: State = {}
        for item in self.fields:
            if item.name not in source:
                raise KeyError(f"missing replicated field {self.name}.{item.name}")
            captured[item.name] = _portable(source[item.name])
        return captured


@dataclass(slots=True, frozen=True)
class ReplicatedEntity:
    net_id: int
    components: dict[str, State]

    def __post_init__(self) -> None:
        if self.net_id < 1:
            raise ValueError("net_id must be a positive integer")
        normalized: dict[str, State] = {}
        for name, component_state in self.components.items():
            if not isinstance(name, str) or not name.strip():
                raise ValueError("component names must be non-empty strings")
            normalized[name] = _state(component_state)
        object.__setattr__(self, "components", normalized)

    def to_payload(self) -> dict[str, Any]:
        return {"id": self.net_id, "components": _portable(self.components)}

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> ReplicatedEntity:
        net_id = payload.get("id")
        components = payload.get("components")
        if not isinstance(net_id, int) or isinstance(net_id, bool):
            raise TypeError("replicated entity id must be an integer")
        if not isinstance(components, Mapping):
            raise TypeError("replicated entity components must be a mapping")
        return cls(net_id=net_id, components=dict(components))


class ReplicationRegistry:
    """Explicit schema registry for deterministic creator-owned replicated components."""

    def __init__(self) -> None:
        self._components: dict[str, ReplicationComponent] = {}

    def register(self, component: ReplicationComponent) -> ReplicationComponent:
        if component.name in self._components:
            raise ValueError(f"replication component already registered: {component.name}")
        self._components[component.name] = component
        return component

    def define(
        self,
        name: str,
        fields: Iterable[str | ReplicationField],
    ) -> ReplicationComponent:
        component = ReplicationComponent(
            name=name,
            fields=tuple(
                field if isinstance(field, ReplicationField) else ReplicationField(field)
                for field in fields
            ),
        )
        return self.register(component)

    def capture(
        self,
        net_id: int,
        components: Mapping[str, Mapping[str, Any]],
    ) -> ReplicatedEntity:
        captured: dict[str, State] = {}
        for name, source in components.items():
            try:
                component = self._components[name]
            except KeyError as exc:
                raise KeyError(f"unregistered replication component: {name}") from exc
            captured[name] = component.capture(source)
        return ReplicatedEntity(net_id=net_id, components=captured)

    def interpolate(
        self,
        older: ReplicatedEntity,
        newer: ReplicatedEntity,
        alpha: float,
    ) -> ReplicatedEntity:
        if older.net_id != newer.net_id:
            raise ValueError("cannot interpolate different replicated entities")
        result: dict[str, State] = {}
        component_names = older.components.keys() | newer.components.keys()
        for name in sorted(component_names):
            if name not in older.components:
                if alpha >= 1.0:
                    result[name] = _state(newer.components[name])
                continue
            if name not in newer.components:
                result[name] = _state(older.components[name])
                continue
            older_state = older.components[name]
            newer_state = newer.components[name]
            spec = self._components.get(name)
            if spec is None:
                result[name] = _state(
                    _lerp_value(older_state, newer_state, alpha)
                    if alpha < 1.0
                    else newer_state
                )
                continue
            state: State = {}
            for field in spec.fields:
                left = older_state.get(field.name)
                right = newer_state.get(field.name)
                if field.name not in older_state or field.name not in newer_state:
                    state[field.name] = _portable(
                        right if alpha >= 1.0 and field.name in newer_state else left
                    )
                elif field.interpolate:
                    state[field.name] = _lerp_value(left, right, alpha)
                else:
                    state[field.name] = _portable(right if alpha >= 1.0 else left)
            result[name] = state
        return ReplicatedEntity(net_id=older.net_id, components=result)

    def __contains__(self, name: object) -> bool:
        return name in self._components


@dataclass(slots=True, frozen=True)
class WorldSnapshot:
    tick: int
    server_time: float
    entities: tuple[ReplicatedEntity, ...]

    def __post_init__(self) -> None:
        if self.tick < 0:
            raise ValueError("snapshot tick must not be negative")
        if not math.isfinite(self.server_time) or self.server_time < 0.0:
            raise ValueError("snapshot server_time must be finite and non-negative")
        ordered = tuple(sorted(self.entities, key=lambda item: item.net_id))
        ids = [item.net_id for item in ordered]
        if len(set(ids)) != len(ids):
            raise ValueError("snapshot entity ids must be unique")
        object.__setattr__(self, "entities", ordered)

    def entity_map(self) -> dict[int, ReplicatedEntity]:
        return {entity.net_id: entity for entity in self.entities}

    def to_payload(self) -> dict[str, Any]:
        return {
            "tick": self.tick,
            "server_time": self.server_time,
            "entities": [entity.to_payload() for entity in self.entities],
        }

    def to_bytes(self) -> bytes:
        return json.dumps(
            self.to_payload(),
            separators=(",", ":"),
            sort_keys=True,
            allow_nan=False,
        ).encode("utf-8")

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> WorldSnapshot:
        tick = payload.get("tick")
        server_time = payload.get("server_time")
        entities = payload.get("entities")
        if not isinstance(tick, int) or isinstance(tick, bool):
            raise TypeError("snapshot tick must be an integer")
        if not isinstance(server_time, (int, float)) or isinstance(server_time, bool):
            raise TypeError("snapshot server_time must be numeric")
        if not isinstance(entities, list):
            raise TypeError("snapshot entities must be a list")
        return cls(
            tick=tick,
            server_time=float(server_time),
            entities=tuple(ReplicatedEntity.from_payload(item) for item in entities),
        )

    @classmethod
    def from_bytes(cls, data: bytes | bytearray | memoryview) -> WorldSnapshot:
        decoded = json.loads(bytes(data).decode("utf-8"))
        if not isinstance(decoded, dict):
            raise TypeError("snapshot payload must decode to an object")
        return cls.from_payload(decoded)


@dataclass(slots=True, frozen=True)
class SnapshotDelta:
    baseline_tick: int
    tick: int
    server_time: float
    upserts: tuple[ReplicatedEntity, ...] = ()
    removed: tuple[int, ...] = ()

    def __post_init__(self) -> None:
        if self.baseline_tick < 0 or self.tick < 0:
            raise ValueError("delta ticks must not be negative")
        if self.tick <= self.baseline_tick:
            raise ValueError("delta tick must be newer than baseline_tick")
        if not math.isfinite(self.server_time) or self.server_time < 0.0:
            raise ValueError("delta server_time must be finite and non-negative")
        upserts = tuple(sorted(self.upserts, key=lambda item: item.net_id))
        removed = tuple(sorted(set(self.removed)))
        if any(net_id < 1 for net_id in removed):
            raise ValueError("removed entity ids must be positive")
        if set(removed) & {entity.net_id for entity in upserts}:
            raise ValueError("an entity cannot be both upserted and removed")
        object.__setattr__(self, "upserts", upserts)
        object.__setattr__(self, "removed", removed)

    @classmethod
    def between(cls, baseline: WorldSnapshot, current: WorldSnapshot) -> SnapshotDelta:
        if current.tick <= baseline.tick:
            raise ValueError("current snapshot must be newer than baseline")
        old = baseline.entity_map()
        new = current.entity_map()
        upserts = tuple(entity for net_id, entity in new.items() if old.get(net_id) != entity)
        removed = tuple(net_id for net_id in old if net_id not in new)
        return cls(
            baseline_tick=baseline.tick,
            tick=current.tick,
            server_time=current.server_time,
            upserts=upserts,
            removed=removed,
        )

    def apply(self, baseline: WorldSnapshot) -> WorldSnapshot:
        if baseline.tick != self.baseline_tick:
            raise ValueError(
                f"delta baseline mismatch: expected {self.baseline_tick}, got {baseline.tick}"
            )
        entities = baseline.entity_map()
        for net_id in self.removed:
            entities.pop(net_id, None)
        for entity in self.upserts:
            entities[entity.net_id] = entity
        return WorldSnapshot(
            tick=self.tick,
            server_time=self.server_time,
            entities=tuple(entities.values()),
        )

    def to_payload(self) -> dict[str, Any]:
        return {
            "baseline_tick": self.baseline_tick,
            "tick": self.tick,
            "server_time": self.server_time,
            "upserts": [entity.to_payload() for entity in self.upserts],
            "removed": list(self.removed),
        }

    def to_bytes(self) -> bytes:
        return json.dumps(
            self.to_payload(),
            separators=(",", ":"),
            sort_keys=True,
            allow_nan=False,
        ).encode("utf-8")

    @classmethod
    def from_bytes(cls, data: bytes | bytearray | memoryview) -> SnapshotDelta:
        decoded = json.loads(bytes(data).decode("utf-8"))
        if not isinstance(decoded, dict):
            raise TypeError("delta payload must decode to an object")
        return cls.from_payload(decoded)

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> SnapshotDelta:
        baseline_tick = payload.get("baseline_tick")
        tick = payload.get("tick")
        server_time = payload.get("server_time")
        upserts = payload.get("upserts")
        removed = payload.get("removed")
        if not isinstance(baseline_tick, int) or isinstance(baseline_tick, bool):
            raise TypeError("delta baseline_tick must be an integer")
        if not isinstance(tick, int) or isinstance(tick, bool):
            raise TypeError("delta tick must be an integer")
        if not isinstance(server_time, (int, float)) or isinstance(server_time, bool):
            raise TypeError("delta server_time must be numeric")
        if not isinstance(upserts, list) or not isinstance(removed, list):
            raise TypeError("delta upserts and removed must be lists")
        if not all(isinstance(item, int) and not isinstance(item, bool) for item in removed):
            raise TypeError("delta removed ids must be integers")
        return cls(
            baseline_tick=baseline_tick,
            tick=tick,
            server_time=float(server_time),
            upserts=tuple(ReplicatedEntity.from_payload(item) for item in upserts),
            removed=tuple(removed),
        )


@dataclass(slots=True, frozen=True)
class SnapshotSample:
    server_time: float
    older_tick: int
    newer_tick: int
    alpha: float
    entities: tuple[ReplicatedEntity, ...]
    clamped: bool = False


def _sample_snapshots(
    snapshots: list[WorldSnapshot],
    render_time: float,
    registry: ReplicationRegistry | None,
) -> SnapshotSample:
    if not snapshots:
        raise LookupError("snapshot buffer is empty")
    if not math.isfinite(render_time):
        raise ValueError("render_time must be finite")
    times = [snapshot.server_time for snapshot in snapshots]
    if render_time <= times[0]:
        first = snapshots[0]
        return SnapshotSample(
            server_time=render_time,
            older_tick=first.tick,
            newer_tick=first.tick,
            alpha=0.0,
            entities=first.entities,
            clamped=render_time < times[0],
        )
    if render_time >= times[-1]:
        last = snapshots[-1]
        return SnapshotSample(
            server_time=render_time,
            older_tick=last.tick,
            newer_tick=last.tick,
            alpha=1.0,
            entities=last.entities,
            clamped=render_time > times[-1],
        )
    index = bisect.bisect_right(times, render_time)
    older = snapshots[index - 1]
    newer = snapshots[index]
    duration = newer.server_time - older.server_time
    alpha = 1.0 if duration <= 0.0 else (render_time - older.server_time) / duration
    old_entities = older.entity_map()
    new_entities = newer.entity_map()
    entities: list[ReplicatedEntity] = []
    for net_id in sorted(old_entities.keys() | new_entities.keys()):
        left = old_entities.get(net_id)
        right = new_entities.get(net_id)
        if left is None:
            continue
        if right is None:
            entities.append(left)
            continue
        if registry is None:
            components = _lerp_value(left.components, right.components, alpha)
            entities.append(ReplicatedEntity(net_id, components))
        else:
            entities.append(registry.interpolate(left, right, alpha))
    return SnapshotSample(
        server_time=render_time,
        older_tick=older.tick,
        newer_tick=newer.tick,
        alpha=alpha,
        entities=tuple(entities),
    )


class SnapshotBuffer:
    """Bounded, out-of-order-tolerant snapshot interpolation buffer."""

    def __init__(
        self,
        *,
        registry: ReplicationRegistry | None = None,
        max_snapshots: int = 32,
    ) -> None:
        if max_snapshots < 2:
            raise ValueError("max_snapshots must be at least 2")
        self.registry = registry
        self.max_snapshots = int(max_snapshots)
        self._snapshots: list[WorldSnapshot] = []

    def __len__(self) -> int:
        return len(self._snapshots)

    @property
    def ticks(self) -> tuple[int, ...]:
        return tuple(snapshot.tick for snapshot in self._snapshots)

    def push(self, snapshot: WorldSnapshot) -> None:
        self._snapshots = [item for item in self._snapshots if item.tick != snapshot.tick]
        key = (snapshot.server_time, snapshot.tick)
        keys = [(item.server_time, item.tick) for item in self._snapshots]
        index = bisect.bisect_right(keys, key)
        self._snapshots.insert(index, snapshot)
        overflow = len(self._snapshots) - self.max_snapshots
        if overflow > 0:
            del self._snapshots[:overflow]

    def sample(self, render_time: float) -> SnapshotSample:
        return _sample_snapshots(self._snapshots, render_time, self.registry)


@dataclass(slots=True, frozen=True)
class PredictionCommand:
    sequence: int
    tick: int
    payload: State = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.sequence < 1:
            raise ValueError("prediction command sequence must be positive")
        if self.tick < 0:
            raise ValueError("prediction command tick must not be negative")
        object.__setattr__(self, "payload", _state(self.payload))


@dataclass(slots=True, frozen=True)
class ReconciliationResult:
    corrected: bool
    acknowledged_sequence: int
    replayed_commands: int
    state: State


class ClientPredictor:
    """Deterministic prediction history with authoritative reconciliation and replay."""

    def __init__(
        self,
        initial_state: Mapping[str, Any],
        simulate: SimulationStep,
        *,
        max_pending: int = 256,
    ) -> None:
        if max_pending < 1:
            raise ValueError("max_pending must be positive")
        self.state = _state(initial_state)
        self.simulate = simulate
        self.max_pending = int(max_pending)
        self._pending: deque[PredictionCommand] = deque()
        self._last_sequence = 0

    @property
    def pending_commands(self) -> tuple[PredictionCommand, ...]:
        return tuple(self._pending)

    def predict(self, command: PredictionCommand) -> State:
        if command.sequence <= self._last_sequence:
            raise ValueError("prediction command sequence must increase")
        if len(self._pending) >= self.max_pending:
            raise OverflowError("prediction history is full")
        self._last_sequence = command.sequence
        self._pending.append(command)
        self.state = _state(self.simulate(_state(self.state), command))
        return _state(self.state)

    def reconcile(
        self,
        acknowledged_sequence: int,
        authoritative_state: Mapping[str, Any],
    ) -> ReconciliationResult:
        if acknowledged_sequence < 0:
            raise ValueError("acknowledged_sequence must not be negative")
        previous = _state(self.state)
        while self._pending and self._pending[0].sequence <= acknowledged_sequence:
            self._pending.popleft()
        rebuilt = _state(authoritative_state)
        for command in self._pending:
            rebuilt = _state(self.simulate(rebuilt, command))
        self.state = rebuilt
        return ReconciliationResult(
            corrected=previous != rebuilt,
            acknowledged_sequence=acknowledged_sequence,
            replayed_commands=len(self._pending),
            state=_state(rebuilt),
        )


class LagCompensationHistory:
    """Bounded authoritative snapshot history for server-side rewind foundations."""

    def __init__(
        self,
        *,
        registry: ReplicationRegistry | None = None,
        max_seconds: float = 1.0,
        max_frames: int = 128,
    ) -> None:
        if not math.isfinite(max_seconds) or max_seconds <= 0.0:
            raise ValueError("max_seconds must be positive and finite")
        if max_frames < 2:
            raise ValueError("max_frames must be at least 2")
        self.registry = registry
        self.max_seconds = float(max_seconds)
        self.max_frames = int(max_frames)
        self._frames: list[WorldSnapshot] = []

    def __len__(self) -> int:
        return len(self._frames)

    @property
    def oldest_time(self) -> float | None:
        return self._frames[0].server_time if self._frames else None

    @property
    def newest_time(self) -> float | None:
        return self._frames[-1].server_time if self._frames else None

    def record(self, snapshot: WorldSnapshot) -> None:
        if self._frames and snapshot.server_time < self._frames[-1].server_time:
            raise ValueError("lag compensation snapshots must be recorded in time order")
        self._frames.append(snapshot)
        if len(self._frames) > self.max_frames:
            del self._frames[: len(self._frames) - self.max_frames]
        cutoff = snapshot.server_time - self.max_seconds
        while len(self._frames) > 2 and self._frames[0].server_time < cutoff:
            del self._frames[0]

    def rewind(self, client_server_time: float) -> SnapshotSample:
        return _sample_snapshots(self._frames, client_server_time, self.registry)


@dataclass(slots=True)
class _ChannelTotals:
    sent_packets: int = 0
    sent_bytes: int = 0
    received_packets: int = 0
    received_bytes: int = 0


@dataclass(slots=True, frozen=True)
class BandwidthReport:
    elapsed_seconds: float
    sent_packets: int
    sent_bytes: int
    received_packets: int
    received_bytes: int
    sent_bytes_per_second: float
    received_bytes_per_second: float
    channels: dict[str, dict[str, int]]


class MultiplayerBandwidthDiagnostics:
    """Explicit byte accounting with caller-supplied elapsed time for deterministic rates."""

    def __init__(self) -> None:
        self.sent_packets = 0
        self.sent_bytes = 0
        self.received_packets = 0
        self.received_bytes = 0
        self._channels: dict[str, _ChannelTotals] = {}

    @staticmethod
    def _size(payload: bytes | bytearray | memoryview | int) -> int:
        size = payload if isinstance(payload, int) else len(payload)
        if size < 0:
            raise ValueError("payload size must not be negative")
        return int(size)

    def record_sent(
        self,
        payload: bytes | bytearray | memoryview | int,
        *,
        channel: str = "default",
    ) -> None:
        size = self._size(payload)
        if not channel.strip():
            raise ValueError("channel must not be empty")
        totals = self._channels.setdefault(channel, _ChannelTotals())
        self.sent_packets += 1
        self.sent_bytes += size
        totals.sent_packets += 1
        totals.sent_bytes += size

    def record_received(
        self,
        payload: bytes | bytearray | memoryview | int,
        *,
        channel: str = "default",
    ) -> None:
        size = self._size(payload)
        if not channel.strip():
            raise ValueError("channel must not be empty")
        totals = self._channels.setdefault(channel, _ChannelTotals())
        self.received_packets += 1
        self.received_bytes += size
        totals.received_packets += 1
        totals.received_bytes += size

    def report(self, elapsed_seconds: float) -> BandwidthReport:
        if not math.isfinite(elapsed_seconds) or elapsed_seconds <= 0.0:
            raise ValueError("elapsed_seconds must be positive and finite")
        channels = {
            name: {
                "sent_packets": totals.sent_packets,
                "sent_bytes": totals.sent_bytes,
                "received_packets": totals.received_packets,
                "received_bytes": totals.received_bytes,
            }
            for name, totals in sorted(self._channels.items())
        }
        return BandwidthReport(
            elapsed_seconds=float(elapsed_seconds),
            sent_packets=self.sent_packets,
            sent_bytes=self.sent_bytes,
            received_packets=self.received_packets,
            received_bytes=self.received_bytes,
            sent_bytes_per_second=self.sent_bytes / elapsed_seconds,
            received_bytes_per_second=self.received_bytes / elapsed_seconds,
            channels=channels,
        )


class MultiplayerPacketCodec:
    """Bridge the 1.4 replication model onto the stable 1.x NetworkPacket transport."""

    @staticmethod
    def snapshot_packet(snapshot: WorldSnapshot) -> NetworkPacket:
        return NetworkPacket(SNAPSHOT_PACKET_KIND, snapshot.to_payload())

    @staticmethod
    def delta_packet(delta: SnapshotDelta) -> NetworkPacket:
        return NetworkPacket(DELTA_PACKET_KIND, delta.to_payload())

    @staticmethod
    def decode_snapshot(packet: NetworkPacket) -> WorldSnapshot:
        if packet.kind != SNAPSHOT_PACKET_KIND:
            raise ValueError(f"expected {SNAPSHOT_PACKET_KIND}, got {packet.kind}")
        return WorldSnapshot.from_payload(packet.payload)

    @staticmethod
    def decode_delta(packet: NetworkPacket) -> SnapshotDelta:
        if packet.kind != DELTA_PACKET_KIND:
            raise ValueError(f"expected {DELTA_PACKET_KIND}, got {packet.kind}")
        return SnapshotDelta.from_payload(packet.payload)


__all__ = [
    "BandwidthReport",
    "ClientPredictor",
    "DELTA_PACKET_KIND",
    "LagCompensationHistory",
    "MultiplayerBandwidthDiagnostics",
    "MultiplayerPacketCodec",
    "PredictionCommand",
    "ReconciliationResult",
    "ReplicatedEntity",
    "ReplicationComponent",
    "ReplicationField",
    "ReplicationRegistry",
    "SNAPSHOT_PACKET_KIND",
    "SnapshotBuffer",
    "SnapshotDelta",
    "SnapshotSample",
    "WorldSnapshot",
]
