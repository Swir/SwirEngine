from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass, field
from typing import Any

from .multiplayer14 import ReplicatedEntity, SnapshotDelta, WorldSnapshot
from .networking import NetworkPacket

REPLICATION_UPDATE_PACKET_KIND = "swir.multiplayer16.update"


def _client_id(value: str) -> str:
    client_id = value.strip()
    if not client_id:
        raise ValueError("client_id must not be empty")
    return client_id


def _channel(value: str) -> str:
    channel = value.strip()
    if not channel:
        raise ValueError("replication channel must not be empty")
    return channel


def _position(value: tuple[float, float, float]) -> tuple[float, float, float]:
    if len(value) != 3:
        raise ValueError("replication positions must contain exactly three coordinates")
    result = tuple(float(item) for item in value)
    if not all(math.isfinite(item) for item in result):
        raise ValueError("replication positions must be finite")
    return result  # type: ignore[return-value]


def _distance_sq(
    left: tuple[float, float, float], right: tuple[float, float, float]
) -> float:
    return sum((a - b) ** 2 for a, b in zip(left, right, strict=True))


@dataclass(slots=True, frozen=True)
class InterestView:
    """Per-client spatial and channel interest used by the 1.6 replication stream."""

    position: tuple[float, float, float] = (0.0, 0.0, 0.0)
    radius: float = 64.0
    channels: frozenset[str] = field(default_factory=lambda: frozenset({"default"}))

    def __post_init__(self) -> None:
        object.__setattr__(self, "position", _position(self.position))
        radius = float(self.radius)
        if not math.isfinite(radius) or radius < 0.0:
            raise ValueError("interest radius must be finite and non-negative")
        object.__setattr__(self, "radius", radius)
        channels = frozenset(_channel(item) for item in self.channels)
        if not channels:
            raise ValueError("an interest view requires at least one channel")
        object.__setattr__(self, "channels", channels)


@dataclass(slots=True, frozen=True)
class EntityInterest:
    """Replication metadata kept separate from creator-owned component state."""

    net_id: int
    position: tuple[float, float, float] = (0.0, 0.0, 0.0)
    channel: str = "default"
    priority: int = 0
    always_relevant: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.net_id, int) or isinstance(self.net_id, bool) or self.net_id < 1:
            raise ValueError("net_id must be a positive integer")
        object.__setattr__(self, "position", _position(self.position))
        object.__setattr__(self, "channel", _channel(self.channel))
        if not isinstance(self.priority, int) or isinstance(self.priority, bool):
            raise TypeError("replication priority must be an integer")


class InterestManager:
    """Deterministic interest query for scalable per-client replication.

    The manager intentionally owns only replication metadata. Gameplay state remains in the stable
    :mod:`swirengine.multiplayer14` snapshot model, keeping the 1.6 layer additive.
    """

    def __init__(self) -> None:
        self._entities: dict[int, EntityInterest] = {}

    def __len__(self) -> int:
        return len(self._entities)

    def __contains__(self, net_id: object) -> bool:
        return net_id in self._entities

    def upsert(self, entity: EntityInterest) -> EntityInterest:
        self._entities[entity.net_id] = entity
        return entity

    def remove(self, net_id: int) -> bool:
        return self._entities.pop(net_id, None) is not None

    def get(self, net_id: int) -> EntityInterest | None:
        return self._entities.get(net_id)

    def query(self, view: InterestView, *, limit: int | None = None) -> tuple[int, ...]:
        if limit is not None and limit < 1:
            raise ValueError("interest query limit must be positive")
        radius_sq = view.radius * view.radius
        matches: list[tuple[tuple[int, float, int, int], int]] = []
        for net_id, entity in self._entities.items():
            if entity.channel not in view.channels:
                continue
            distance_sq = _distance_sq(entity.position, view.position)
            if not entity.always_relevant and distance_sq > radius_sq:
                continue
            key = (
                0 if entity.always_relevant else 1,
                distance_sq,
                -entity.priority,
                net_id,
            )
            matches.append((key, net_id))
        matches.sort(key=lambda item: item[0])
        ids = tuple(item[1] for item in matches)
        return ids if limit is None else ids[:limit]


@dataclass(slots=True, frozen=True)
class ReplicationUpdate:
    """One full snapshot or ACK-based delta produced for a single client."""

    snapshot: WorldSnapshot | None = None
    delta: SnapshotDelta | None = None

    def __post_init__(self) -> None:
        if (self.snapshot is None) == (self.delta is None):
            raise ValueError("replication update requires exactly one snapshot or delta")

    @property
    def mode(self) -> str:
        return "snapshot" if self.snapshot is not None else "delta"

    @property
    def tick(self) -> int:
        if self.snapshot is not None:
            return self.snapshot.tick
        assert self.delta is not None
        return self.delta.tick

    @property
    def baseline_tick(self) -> int | None:
        return None if self.delta is None else self.delta.baseline_tick

    @property
    def entity_count(self) -> int:
        if self.snapshot is not None:
            return len(self.snapshot.entities)
        assert self.delta is not None
        return len(self.delta.upserts) + len(self.delta.removed)

    def to_packet(self) -> NetworkPacket:
        if self.snapshot is not None:
            payload: dict[str, Any] = {"mode": "snapshot", "snapshot": self.snapshot.to_payload()}
        else:
            assert self.delta is not None
            payload = {"mode": "delta", "delta": self.delta.to_payload()}
        return NetworkPacket(REPLICATION_UPDATE_PACKET_KIND, payload)

    @classmethod
    def from_packet(cls, packet: NetworkPacket) -> ReplicationUpdate:
        if packet.kind != REPLICATION_UPDATE_PACKET_KIND:
            raise ValueError(
                f"expected {REPLICATION_UPDATE_PACKET_KIND}, got {packet.kind}"
            )
        mode = packet.payload.get("mode")
        if mode == "snapshot":
            payload = packet.payload.get("snapshot")
            if not isinstance(payload, dict):
                raise TypeError("snapshot replication update requires object payload")
            return cls(snapshot=WorldSnapshot.from_payload(payload))
        if mode == "delta":
            payload = packet.payload.get("delta")
            if not isinstance(payload, dict):
                raise TypeError("delta replication update requires object payload")
            return cls(delta=SnapshotDelta.from_payload(payload))
        raise ValueError(f"unknown replication update mode: {mode!r}")


@dataclass(slots=True)
class ReplicationStreamDiagnostics:
    full_updates: int = 0
    delta_updates: int = 0
    upserted_entities: int = 0
    removed_entities: int = 0
    full_entities: int = 0
    acknowledgements: int = 0
    snapshot_fallbacks: int = 0

    def snapshot(self) -> dict[str, int]:
        return {
            "full_updates": self.full_updates,
            "delta_updates": self.delta_updates,
            "upserted_entities": self.upserted_entities,
            "removed_entities": self.removed_entities,
            "full_entities": self.full_entities,
            "acknowledgements": self.acknowledgements,
            "snapshot_fallbacks": self.snapshot_fallbacks,
        }


@dataclass(slots=True)
class _ServerClientState:
    view: InterestView
    acknowledged_tick: int = -1
    last_built_tick: int = -1
    sent: dict[int, WorldSnapshot] = field(default_factory=dict)
    diagnostics: ReplicationStreamDiagnostics = field(default_factory=ReplicationStreamDiagnostics)


class ReplicationStreamServer:
    """ACK-based, interest-aware replication producer for SwirEngine 1.6.

    A full world snapshot is published once per authoritative simulation tick. Each registered client
    then receives a filtered snapshot or a delta from the newest snapshot that client explicitly
    acknowledged. Lost/unacknowledged packets therefore never become implicit baselines.
    """

    def __init__(
        self,
        interest: InterestManager | None = None,
        *,
        max_world_history: int = 64,
        max_client_history: int = 32,
        max_entities_per_client: int | None = None,
        strict_metadata: bool = True,
    ) -> None:
        if max_world_history < 2:
            raise ValueError("max_world_history must be at least 2")
        if max_client_history < 2:
            raise ValueError("max_client_history must be at least 2")
        if max_entities_per_client is not None and max_entities_per_client < 1:
            raise ValueError("max_entities_per_client must be positive")
        self.interest = interest or InterestManager()
        self.max_world_history = int(max_world_history)
        self.max_client_history = int(max_client_history)
        self.max_entities_per_client = max_entities_per_client
        self.strict_metadata = bool(strict_metadata)
        self._world: deque[WorldSnapshot] = deque(maxlen=self.max_world_history)
        self._clients: dict[str, _ServerClientState] = {}

    @property
    def latest_tick(self) -> int | None:
        return self._world[-1].tick if self._world else None

    @property
    def client_ids(self) -> tuple[str, ...]:
        return tuple(sorted(self._clients))

    def register_client(self, client_id: str, view: InterestView | None = None) -> None:
        key = _client_id(client_id)
        if key in self._clients:
            raise ValueError(f"replication client already registered: {key}")
        self._clients[key] = _ServerClientState(view=view or InterestView())

    def unregister_client(self, client_id: str) -> bool:
        return self._clients.pop(_client_id(client_id), None) is not None

    def update_view(self, client_id: str, view: InterestView) -> None:
        self._state(client_id).view = view

    def publish(self, snapshot: WorldSnapshot) -> None:
        if self._world and snapshot.tick <= self._world[-1].tick:
            raise ValueError("published snapshot tick must increase")
        if self._world and snapshot.server_time < self._world[-1].server_time:
            raise ValueError("published snapshot server_time must not move backwards")
        self._world.append(snapshot)

    def build_update(self, client_id: str) -> ReplicationUpdate:
        state = self._state(client_id)
        if not self._world:
            raise LookupError("no authoritative snapshot has been published")
        current = self._world[-1]
        if current.tick <= state.last_built_tick:
            raise RuntimeError("no newer authoritative snapshot is available for this client")
        filtered = self._filter(current, state.view)
        baseline = state.sent.get(state.acknowledged_tick)
        if baseline is not None and baseline.tick < filtered.tick:
            delta = SnapshotDelta.between(baseline, filtered)
            update = ReplicationUpdate(delta=delta)
            state.diagnostics.delta_updates += 1
            state.diagnostics.upserted_entities += len(delta.upserts)
            state.diagnostics.removed_entities += len(delta.removed)
        else:
            update = ReplicationUpdate(snapshot=filtered)
            state.diagnostics.full_updates += 1
            state.diagnostics.full_entities += len(filtered.entities)
            if state.acknowledged_tick >= 0:
                state.diagnostics.snapshot_fallbacks += 1
        state.last_built_tick = filtered.tick
        state.sent[filtered.tick] = filtered
        self._prune_sent(state)
        return update

    def acknowledge(self, client_id: str, tick: int) -> bool:
        state = self._state(client_id)
        if not isinstance(tick, int) or isinstance(tick, bool) or tick < 0:
            raise ValueError("acknowledged tick must be a non-negative integer")
        if tick <= state.acknowledged_tick:
            return False
        if tick not in state.sent:
            raise ValueError(f"cannot acknowledge unsent replication tick {tick}")
        state.acknowledged_tick = tick
        state.diagnostics.acknowledgements += 1
        for candidate in tuple(state.sent):
            if candidate < tick:
                del state.sent[candidate]
        return True

    def diagnostics(self, client_id: str) -> dict[str, int]:
        return self._state(client_id).diagnostics.snapshot()

    def _state(self, client_id: str) -> _ServerClientState:
        key = _client_id(client_id)
        try:
            return self._clients[key]
        except KeyError as exc:
            raise KeyError(f"unknown replication client: {key}") from exc

    def _filter(self, snapshot: WorldSnapshot, view: InterestView) -> WorldSnapshot:
        if self.strict_metadata:
            missing = [entity.net_id for entity in snapshot.entities if entity.net_id not in self.interest]
            if missing:
                preview = ", ".join(str(item) for item in missing[:8])
                raise KeyError(f"missing interest metadata for replicated entities: {preview}")
        relevant = set(
            self.interest.query(view, limit=self.max_entities_per_client)
        )
        entities = tuple(entity for entity in snapshot.entities if entity.net_id in relevant)
        return WorldSnapshot(snapshot.tick, snapshot.server_time, entities)

    def _prune_sent(self, state: _ServerClientState) -> None:
        keep = set(sorted(state.sent)[-self.max_client_history :])
        if state.acknowledged_tick >= 0:
            keep.add(state.acknowledged_tick)
        for tick in tuple(state.sent):
            if tick not in keep:
                del state.sent[tick]


class ReplicationStreamClient:
    """Apply full/delta replication updates while retaining a bounded baseline history."""

    def __init__(self, *, max_history: int = 32) -> None:
        if max_history < 2:
            raise ValueError("max_history must be at least 2")
        self.max_history = int(max_history)
        self._history: dict[int, WorldSnapshot] = {}
        self.current: WorldSnapshot | None = None

    @property
    def tick(self) -> int | None:
        return None if self.current is None else self.current.tick

    @property
    def history_ticks(self) -> tuple[int, ...]:
        return tuple(sorted(self._history))

    def apply(self, update: ReplicationUpdate) -> WorldSnapshot:
        if self.current is not None and update.tick <= self.current.tick:
            raise ValueError("replication update tick must increase")
        if update.snapshot is not None:
            result = update.snapshot
        else:
            assert update.delta is not None
            baseline = self._history.get(update.delta.baseline_tick)
            if baseline is None:
                raise LookupError(
                    f"replication baseline {update.delta.baseline_tick} is not available"
                )
            result = update.delta.apply(baseline)
        self._history[result.tick] = result
        self.current = result
        self._prune()
        return result

    def apply_packet(self, packet: NetworkPacket) -> WorldSnapshot:
        return self.apply(ReplicationUpdate.from_packet(packet))

    def _prune(self) -> None:
        keep = set(sorted(self._history)[-self.max_history :])
        for tick in tuple(self._history):
            if tick not in keep:
                del self._history[tick]


__all__ = [
    "REPLICATION_UPDATE_PACKET_KIND",
    "EntityInterest",
    "InterestManager",
    "InterestView",
    "ReplicationStreamClient",
    "ReplicationStreamDiagnostics",
    "ReplicationStreamServer",
    "ReplicationUpdate",
]
