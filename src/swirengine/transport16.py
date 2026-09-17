from __future__ import annotations

from collections import deque
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from enum import Enum
from typing import Any

from .networking import NetworkPacket

TRANSPORT_QOS_PACKET_KIND = "swir.transport16.qos"


def _bounded_text(value: object, label: str, *, maximum: int) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{label} must be a string")
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{label} must not be empty")
    if len(normalized) > maximum:
        raise ValueError(f"{label} must not exceed {maximum} characters")
    return normalized


def _positive_int(value: object, label: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise TypeError(f"{label} must be an integer")
    if value < 1:
        raise ValueError(f"{label} must be positive")
    return value


def _priority(value: object) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise TypeError("priority must be an integer")
    if not -1000 <= value <= 1000:
        raise ValueError("priority must be between -1000 and 1000")
    return value


def _wire_snapshot(packet: NetworkPacket) -> NetworkPacket:
    """Detach a packet through the stable wire codec so queued bounds cannot drift."""

    if not isinstance(packet, NetworkPacket):
        raise TypeError("packet must be a NetworkPacket")
    framed = packet.to_bytes()
    return NetworkPacket.from_body(framed[4:])


class DeliveryPolicy(str, Enum):
    RELIABLE = "reliable"
    UNRELIABLE = "unreliable"


class TransportQoError(RuntimeError):
    """Stable creator-facing QoS failure with a machine-readable code."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(slots=True, frozen=True)
class ChannelPolicy:
    """Bounded scheduling and delivery contract for one logical channel."""

    name: str
    delivery: DeliveryPolicy = DeliveryPolicy.RELIABLE
    priority: int = 0
    max_packet_bytes: int = 64 * 1024
    max_queue_packets: int = 256
    max_queue_bytes: int = 1024 * 1024

    def __post_init__(self) -> None:
        object.__setattr__(self, "name", _bounded_text(self.name, "channel name", maximum=96))
        object.__setattr__(self, "delivery", DeliveryPolicy(self.delivery))
        object.__setattr__(self, "priority", _priority(self.priority))
        object.__setattr__(
            self,
            "max_packet_bytes",
            _positive_int(self.max_packet_bytes, "max_packet_bytes"),
        )
        object.__setattr__(
            self,
            "max_queue_packets",
            _positive_int(self.max_queue_packets, "max_queue_packets"),
        )
        object.__setattr__(
            self,
            "max_queue_bytes",
            _positive_int(self.max_queue_bytes, "max_queue_bytes"),
        )


@dataclass(slots=True, frozen=True)
class QoSEnvelope:
    """Transport-independent envelope carried by the stable NetworkPacket framing."""

    channel: str
    sequence: int
    delivery: DeliveryPolicy
    packet: NetworkPacket

    def __post_init__(self) -> None:
        object.__setattr__(self, "channel", _bounded_text(self.channel, "channel", maximum=96))
        object.__setattr__(self, "sequence", _positive_int(self.sequence, "sequence"))
        object.__setattr__(self, "delivery", DeliveryPolicy(self.delivery))
        if not isinstance(self.packet, NetworkPacket):
            raise TypeError("packet must be a NetworkPacket")

    def to_packet(self) -> NetworkPacket:
        inner = _wire_snapshot(self.packet)
        return NetworkPacket(
            TRANSPORT_QOS_PACKET_KIND,
            {
                "channel": self.channel,
                "sequence": self.sequence,
                "delivery": self.delivery.value,
                "packet": {
                    "kind": inner.kind,
                    "payload": inner.payload,
                },
            },
        )

    @classmethod
    def from_packet(cls, packet: NetworkPacket) -> QoSEnvelope:
        if packet.kind != TRANSPORT_QOS_PACKET_KIND:
            raise ValueError(f"expected {TRANSPORT_QOS_PACKET_KIND}, got {packet.kind}")
        payload = packet.payload
        nested = payload.get("packet")
        if not isinstance(nested, Mapping):
            raise TypeError("QoS packet payload must contain a packet object")
        kind = nested.get("kind")
        nested_payload = nested.get("payload")
        if not isinstance(kind, str) or not isinstance(nested_payload, dict):
            raise TypeError("QoS nested packet requires string kind and object payload")
        return cls(
            channel=payload.get("channel"),
            sequence=payload.get("sequence"),
            delivery=payload.get("delivery"),
            packet=_wire_snapshot(NetworkPacket(kind, nested_payload)),
        )


@dataclass(slots=True)
class _QueuedPacket:
    envelope: QoSEnvelope
    encoded_bytes: int
    enqueue_order: int


@dataclass(slots=True)
class _OutboundCounters:
    enqueued_packets: int = 0
    enqueued_bytes: int = 0
    emitted_packets: int = 0
    emitted_bytes: int = 0
    dropped_packets: int = 0
    dropped_bytes: int = 0
    backpressure_rejections: int = 0
    oversized_rejections: int = 0


@dataclass(slots=True)
class _InboundCounters:
    accepted_packets: int = 0
    duplicate_packets: int = 0
    stale_packets: int = 0
    gap_events: int = 0
    skipped_sequences: int = 0
    policy_mismatches: int = 0
    oversized_rejections: int = 0


def _policy_table(policies: Iterable[ChannelPolicy]) -> dict[str, ChannelPolicy]:
    table: dict[str, ChannelPolicy] = {}
    for policy in policies:
        if not isinstance(policy, ChannelPolicy):
            raise TypeError("policies must contain ChannelPolicy values")
        if policy.name in table:
            raise ValueError(f"duplicate channel policy: {policy.name}")
        table[policy.name] = policy
    if not table:
        raise ValueError("at least one channel policy is required")
    return table


class TransportQoSScheduler:
    """Deterministic bounded outbound scheduler independent of socket implementation.

    Reliable channels apply back-pressure when their configured queue bound would be
    exceeded. Unreliable channels instead evict their oldest queued packet(s) until the
    newest update fits, preserving fresh state under pressure.
    """

    def __init__(self, policies: Iterable[ChannelPolicy]) -> None:
        self._policies = _policy_table(policies)
        self._queues = {name: deque() for name in self._policies}
        self._queue_bytes = {name: 0 for name in self._policies}
        self._next_sequence = {name: 1 for name in self._policies}
        self._counters = {name: _OutboundCounters() for name in self._policies}
        self._enqueue_order = 0

    @property
    def queued_packets(self) -> int:
        return sum(len(queue) for queue in self._queues.values())

    @property
    def queued_bytes(self) -> int:
        return sum(self._queue_bytes.values())

    def enqueue(self, channel: str, packet: NetworkPacket) -> QoSEnvelope:
        policy = self._policy(channel)
        if not isinstance(packet, NetworkPacket):
            raise TypeError("packet must be a NetworkPacket")

        sequence = self._next_sequence[policy.name]
        envelope = QoSEnvelope(
            policy.name,
            sequence,
            policy.delivery,
            _wire_snapshot(packet),
        )
        wire_packet = envelope.to_packet()
        encoded_bytes = len(wire_packet.to_bytes())
        counters = self._counters[policy.name]
        if encoded_bytes > policy.max_packet_bytes or encoded_bytes > policy.max_queue_bytes:
            counters.oversized_rejections += 1
            raise TransportQoError(
                "packet_too_large",
                f"encoded QoS packet requires {encoded_bytes} bytes but channel limits reject it",
            )

        queue = self._queues[policy.name]
        queue_bytes = self._queue_bytes[policy.name]
        would_exceed = (
            len(queue) + 1 > policy.max_queue_packets
            or queue_bytes + encoded_bytes > policy.max_queue_bytes
        )
        if would_exceed and policy.delivery is DeliveryPolicy.RELIABLE:
            counters.backpressure_rejections += 1
            raise TransportQoError(
                "backpressure",
                f"reliable channel {policy.name!r} queue is at its configured bound",
            )

        if policy.delivery is DeliveryPolicy.UNRELIABLE:
            while queue and (
                len(queue) + 1 > policy.max_queue_packets
                or queue_bytes + encoded_bytes > policy.max_queue_bytes
            ):
                dropped = queue.popleft()
                queue_bytes -= dropped.encoded_bytes
                counters.dropped_packets += 1
                counters.dropped_bytes += dropped.encoded_bytes

        self._enqueue_order += 1
        stored_envelope = QoSEnvelope.from_packet(wire_packet)
        queue.append(_QueuedPacket(stored_envelope, encoded_bytes, self._enqueue_order))
        self._queue_bytes[policy.name] = queue_bytes + encoded_bytes
        self._next_sequence[policy.name] = sequence + 1
        counters.enqueued_packets += 1
        counters.enqueued_bytes += encoded_bytes
        return envelope

    def drain(self, *, max_packets: int, max_bytes: int) -> tuple[NetworkPacket, ...]:
        packet_budget = _positive_int(max_packets, "max_packets")
        byte_budget = _positive_int(max_bytes, "max_bytes")
        emitted: list[NetworkPacket] = []
        emitted_bytes = 0

        while len(emitted) < packet_budget:
            candidates: list[tuple[int, int, str, _QueuedPacket]] = []
            remaining_bytes = byte_budget - emitted_bytes
            for name, queue in self._queues.items():
                if not queue:
                    continue
                head = queue[0]
                if head.encoded_bytes <= remaining_bytes:
                    policy = self._policies[name]
                    candidates.append((-policy.priority, head.enqueue_order, name, head))
            if not candidates:
                break

            _, _, name, selected = min(candidates)
            self._queues[name].popleft()
            self._queue_bytes[name] -= selected.encoded_bytes
            counters = self._counters[name]
            counters.emitted_packets += 1
            counters.emitted_bytes += selected.encoded_bytes
            emitted_bytes += selected.encoded_bytes
            emitted.append(selected.envelope.to_packet())

        return tuple(emitted)

    def diagnostics(self) -> dict[str, Any]:
        channels: dict[str, Any] = {}
        for name in sorted(self._policies):
            policy = self._policies[name]
            counters = self._counters[name]
            channels[name] = {
                "delivery": policy.delivery.value,
                "priority": policy.priority,
                "queued_packets": len(self._queues[name]),
                "queued_bytes": self._queue_bytes[name],
                "enqueued_packets": counters.enqueued_packets,
                "enqueued_bytes": counters.enqueued_bytes,
                "emitted_packets": counters.emitted_packets,
                "emitted_bytes": counters.emitted_bytes,
                "dropped_packets": counters.dropped_packets,
                "dropped_bytes": counters.dropped_bytes,
                "backpressure_rejections": counters.backpressure_rejections,
                "oversized_rejections": counters.oversized_rejections,
                "next_sequence": self._next_sequence[name],
            }
        return {
            "queued_packets": self.queued_packets,
            "queued_bytes": self.queued_bytes,
            "channels": channels,
        }

    def _policy(self, channel: str) -> ChannelPolicy:
        channel = _bounded_text(channel, "channel", maximum=96)
        policy = self._policies.get(channel)
        if policy is None:
            raise TransportQoError("unknown_channel", f"unknown transport channel: {channel}")
        return policy


class TransportQoSReceiver:
    """Sequence/duplicate policy layer for packets from any transport implementation."""

    def __init__(self, policies: Iterable[ChannelPolicy]) -> None:
        self._policies = _policy_table(policies)
        self._last_sequence = {name: 0 for name in self._policies}
        self._counters = {name: _InboundCounters() for name in self._policies}

    def accept(self, packet: NetworkPacket) -> NetworkPacket | None:
        if not isinstance(packet, NetworkPacket):
            raise TypeError("packet must be a NetworkPacket")
        envelope = QoSEnvelope.from_packet(packet)
        policy = self._policies.get(envelope.channel)
        if policy is None:
            raise TransportQoError(
                "unknown_channel",
                f"unknown transport channel: {envelope.channel}",
            )
        counters = self._counters[policy.name]
        if envelope.delivery is not policy.delivery:
            counters.policy_mismatches += 1
            raise TransportQoError(
                "policy_mismatch",
                f"packet delivery policy does not match channel {policy.name!r}",
            )

        encoded_bytes = len(packet.to_bytes())
        if encoded_bytes > policy.max_packet_bytes:
            counters.oversized_rejections += 1
            raise TransportQoError(
                "packet_too_large",
                f"encoded QoS packet requires {encoded_bytes} bytes but channel limit rejects it",
            )

        last = self._last_sequence[policy.name]
        expected = last + 1
        if envelope.sequence <= last:
            if envelope.sequence == last:
                counters.duplicate_packets += 1
            else:
                counters.stale_packets += 1
            return None

        if envelope.sequence > expected:
            skipped = envelope.sequence - expected
            counters.gap_events += 1
            counters.skipped_sequences += skipped
            if policy.delivery is DeliveryPolicy.RELIABLE:
                raise TransportQoError(
                    "reliable_gap",
                    f"reliable channel {policy.name!r} expected sequence {expected} "
                    f"but received {envelope.sequence}",
                )

        self._last_sequence[policy.name] = envelope.sequence
        counters.accepted_packets += 1
        return envelope.packet

    def diagnostics(self) -> dict[str, Any]:
        channels: dict[str, Any] = {}
        for name in sorted(self._policies):
            counters = self._counters[name]
            channels[name] = {
                "delivery": self._policies[name].delivery.value,
                "last_sequence": self._last_sequence[name],
                "accepted_packets": counters.accepted_packets,
                "duplicate_packets": counters.duplicate_packets,
                "stale_packets": counters.stale_packets,
                "gap_events": counters.gap_events,
                "skipped_sequences": counters.skipped_sequences,
                "policy_mismatches": counters.policy_mismatches,
                "oversized_rejections": counters.oversized_rejections,
            }
        return {"channels": channels}


__all__ = [
    "TRANSPORT_QOS_PACKET_KIND",
    "ChannelPolicy",
    "DeliveryPolicy",
    "QoSEnvelope",
    "TransportQoError",
    "TransportQoSReceiver",
    "TransportQoSScheduler",
]
