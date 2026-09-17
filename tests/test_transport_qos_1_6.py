from __future__ import annotations

import socket

import pytest

from swirengine.networking import NetworkPacket, TCPPeer
from swirengine.transport16 import (
    TRANSPORT_QOS_PACKET_KIND,
    ChannelPolicy,
    DeliveryPolicy,
    QoSEnvelope,
    TransportQoError,
    TransportQoSReceiver,
    TransportQoSScheduler,
)


def _policies() -> tuple[ChannelPolicy, ...]:
    return (
        ChannelPolicy("control", DeliveryPolicy.RELIABLE, priority=100),
        ChannelPolicy("state", DeliveryPolicy.UNRELIABLE, priority=10),
        ChannelPolicy("chat", DeliveryPolicy.RELIABLE, priority=1),
    )


def _decode(packet: NetworkPacket) -> QoSEnvelope:
    return QoSEnvelope.from_packet(packet)


def test_channel_policy_validates_strict_bounds_and_normalizes_name() -> None:
    policy = ChannelPolicy(" control ", priority=-10)
    assert policy.name == "control"
    assert policy.delivery is DeliveryPolicy.RELIABLE

    with pytest.raises(TypeError, match="integer"):
        ChannelPolicy("x", priority=True)
    with pytest.raises(ValueError, match="between"):
        ChannelPolicy("x", priority=1001)
    with pytest.raises(ValueError, match="positive"):
        ChannelPolicy("x", max_queue_packets=0)


def test_policy_table_rejects_duplicate_normalized_channels() -> None:
    with pytest.raises(ValueError, match="duplicate"):
        TransportQoSScheduler((ChannelPolicy("state"), ChannelPolicy(" state ")))
    with pytest.raises(ValueError, match="at least one"):
        TransportQoSScheduler(())


def test_qos_envelope_round_trips_through_stable_network_packet_framing() -> None:
    envelope = QoSEnvelope(
        "control",
        7,
        DeliveryPolicy.RELIABLE,
        NetworkPacket("move", {"x": 4, "y": -2}),
    )

    framed = envelope.to_packet().to_bytes()
    decoded_packet = NetworkPacket.from_body(framed[4:])
    decoded = QoSEnvelope.from_packet(decoded_packet)

    assert decoded == envelope
    assert decoded_packet.kind == TRANSPORT_QOS_PACKET_KIND
    assert framed == envelope.to_packet().to_bytes()


def test_qos_envelope_rejects_wrong_kind_and_malformed_nested_packet() -> None:
    with pytest.raises(ValueError, match="expected"):
        QoSEnvelope.from_packet(NetworkPacket("wrong", {}))
    with pytest.raises(TypeError, match="packet object"):
        QoSEnvelope.from_packet(
            NetworkPacket(
                TRANSPORT_QOS_PACKET_KIND,
                {"channel": "x", "sequence": 1, "delivery": "reliable"},
            )
        )


def test_scheduler_assigns_per_channel_monotonic_sequences_only_after_acceptance() -> None:
    scheduler = TransportQoSScheduler(
        (
            ChannelPolicy(
                "reliable",
                max_queue_packets=1,
                max_queue_bytes=4096,
                max_packet_bytes=4096,
            ),
            ChannelPolicy("other"),
        )
    )

    first = scheduler.enqueue("reliable", NetworkPacket("a", {}))
    other = scheduler.enqueue("other", NetworkPacket("b", {}))
    with pytest.raises(TransportQoError) as blocked:
        scheduler.enqueue("reliable", NetworkPacket("c", {}))
    assert blocked.value.code == "backpressure"

    drained = scheduler.drain(max_packets=1, max_bytes=4096)
    second = scheduler.enqueue("reliable", NetworkPacket("d", {}))

    assert first.sequence == 1
    assert other.sequence == 1
    assert _decode(drained[0]).channel == "reliable"
    assert second.sequence == 2


def test_reliable_channel_applies_atomic_backpressure_without_eviction() -> None:
    scheduler = TransportQoSScheduler(
        (
            ChannelPolicy(
                "events",
                DeliveryPolicy.RELIABLE,
                max_queue_packets=1,
                max_queue_bytes=4096,
                max_packet_bytes=4096,
            ),
        )
    )
    first = scheduler.enqueue("events", NetworkPacket("first", {"value": 1}))

    with pytest.raises(TransportQoError) as blocked:
        scheduler.enqueue("events", NetworkPacket("second", {"value": 2}))

    assert blocked.value.code == "backpressure"
    assert scheduler.queued_packets == 1
    drained = scheduler.drain(max_packets=1, max_bytes=4096)
    assert _decode(drained[0]) == first
    diagnostics = scheduler.diagnostics()["channels"]["events"]
    assert diagnostics["dropped_packets"] == 0
    assert diagnostics["backpressure_rejections"] == 1


def test_unreliable_channel_drops_oldest_under_pressure_to_keep_fresh_state() -> None:
    scheduler = TransportQoSScheduler(
        (
            ChannelPolicy(
                "state",
                DeliveryPolicy.UNRELIABLE,
                max_queue_packets=2,
                max_queue_bytes=8192,
                max_packet_bytes=4096,
            ),
        )
    )
    scheduler.enqueue("state", NetworkPacket("state", {"tick": 1}))
    scheduler.enqueue("state", NetworkPacket("state", {"tick": 2}))
    newest = scheduler.enqueue("state", NetworkPacket("state", {"tick": 3}))

    drained = scheduler.drain(max_packets=2, max_bytes=8192)

    assert [_decode(packet).sequence for packet in drained] == [2, 3]
    assert _decode(drained[-1]) == newest
    diagnostics = scheduler.diagnostics()["channels"]["state"]
    assert diagnostics["dropped_packets"] == 1
    assert diagnostics["backpressure_rejections"] == 0


def test_scheduler_rejects_encoded_packet_over_channel_bound_without_sequence_consumption() -> None:
    scheduler = TransportQoSScheduler(
        (ChannelPolicy("tiny", max_packet_bytes=180, max_queue_bytes=1024),)
    )

    with pytest.raises(TransportQoError) as oversized:
        scheduler.enqueue("tiny", NetworkPacket("blob", {"data": "x" * 500}))
    assert oversized.value.code == "packet_too_large"

    accepted = scheduler.enqueue("tiny", NetworkPacket("ok", {}))
    assert accepted.sequence == 1
    assert scheduler.diagnostics()["channels"]["tiny"]["oversized_rejections"] == 1


def test_receiver_rejects_oversized_packet_without_advancing_sequence_baseline() -> None:
    policy = ChannelPolicy("control", max_packet_bytes=256)
    receiver = TransportQoSReceiver((policy,))
    oversized = QoSEnvelope(
        "control",
        1,
        DeliveryPolicy.RELIABLE,
        NetworkPacket("blob", {"data": "x" * 500}),
    ).to_packet()

    assert len(oversized.to_bytes()) > policy.max_packet_bytes
    with pytest.raises(TransportQoError) as rejected:
        receiver.accept(oversized)
    assert rejected.value.code == "packet_too_large"

    diagnostics = receiver.diagnostics()["channels"]["control"]
    assert diagnostics["last_sequence"] == 0
    assert diagnostics["accepted_packets"] == 0
    assert diagnostics["oversized_rejections"] == 1

    valid = QoSEnvelope(
        "control",
        1,
        DeliveryPolicy.RELIABLE,
        NetworkPacket("ok", {}),
    ).to_packet()
    assert len(valid.to_bytes()) <= policy.max_packet_bytes
    assert receiver.accept(valid) == NetworkPacket("ok", {})


def test_scheduler_uses_strict_priority_then_enqueue_order_deterministically() -> None:
    scheduler = TransportQoSScheduler(_policies())
    scheduler.enqueue("chat", NetworkPacket("chat", {"n": 1}))
    scheduler.enqueue("state", NetworkPacket("state", {"n": 1}))
    scheduler.enqueue("control", NetworkPacket("control", {"n": 1}))
    scheduler.enqueue("control", NetworkPacket("control", {"n": 2}))

    drained = scheduler.drain(max_packets=4, max_bytes=64 * 1024)

    assert [(_decode(item).channel, _decode(item).packet.payload["n"]) for item in drained] == [
        ("control", 1),
        ("control", 2),
        ("state", 1),
        ("chat", 1),
    ]


def test_drain_respects_packet_and_byte_budgets_without_discarding_blocked_heads() -> None:
    scheduler = TransportQoSScheduler(_policies())
    first = scheduler.enqueue("control", NetworkPacket("control", {"data": "a" * 80}))
    second = scheduler.enqueue("chat", NetworkPacket("chat", {"data": "b"}))
    first_size = len(first.to_packet().to_bytes())
    second_size = len(second.to_packet().to_bytes())

    drained = scheduler.drain(max_packets=1, max_bytes=first_size - 1)
    assert len(drained) == 1
    assert _decode(drained[0]).channel == "chat"
    assert scheduler.queued_packets == 1

    assert scheduler.drain(max_packets=1, max_bytes=second_size) == ()
    assert scheduler.queued_packets == 1

    final = scheduler.drain(max_packets=1, max_bytes=first_size)
    assert len(final) == 1
    assert _decode(final[0]).channel == "control"
    assert scheduler.queued_packets == 0


def test_scheduler_rejects_unknown_channel_with_stable_code() -> None:
    scheduler = TransportQoSScheduler(_policies())
    with pytest.raises(TransportQoError) as unknown:
        scheduler.enqueue("missing", NetworkPacket("x", {}))
    assert unknown.value.code == "unknown_channel"


def test_receiver_accepts_in_order_reliable_packets_and_suppresses_duplicate() -> None:
    scheduler = TransportQoSScheduler((ChannelPolicy("control"),))
    receiver = TransportQoSReceiver((ChannelPolicy("control"),))
    scheduler.enqueue("control", NetworkPacket("one", {"v": 1}))
    scheduler.enqueue("control", NetworkPacket("two", {"v": 2}))
    first, second = scheduler.drain(max_packets=2, max_bytes=8192)

    assert receiver.accept(first) == NetworkPacket("one", {"v": 1})
    assert receiver.accept(first) is None
    assert receiver.accept(second) == NetworkPacket("two", {"v": 2})

    diagnostics = receiver.diagnostics()["channels"]["control"]
    assert diagnostics["accepted_packets"] == 2
    assert diagnostics["duplicate_packets"] == 1
    assert diagnostics["last_sequence"] == 2


def test_reliable_receiver_rejects_gap_without_advancing_baseline() -> None:
    policy = ChannelPolicy("control", DeliveryPolicy.RELIABLE)
    receiver = TransportQoSReceiver((policy,))
    first = QoSEnvelope("control", 1, policy.delivery, NetworkPacket("one", {})).to_packet()
    third = QoSEnvelope("control", 3, policy.delivery, NetworkPacket("three", {})).to_packet()
    second = QoSEnvelope("control", 2, policy.delivery, NetworkPacket("two", {})).to_packet()

    assert receiver.accept(first) == NetworkPacket("one", {})
    with pytest.raises(TransportQoError) as gap:
        receiver.accept(third)
    assert gap.value.code == "reliable_gap"
    assert receiver.diagnostics()["channels"]["control"]["last_sequence"] == 1

    assert receiver.accept(second) == NetworkPacket("two", {})
    assert receiver.accept(third) == NetworkPacket("three", {})


def test_unreliable_receiver_accepts_newest_packet_and_accounts_for_skipped_sequences() -> None:
    policy = ChannelPolicy("state", DeliveryPolicy.UNRELIABLE)
    receiver = TransportQoSReceiver((policy,))
    first = QoSEnvelope("state", 1, policy.delivery, NetworkPacket("state", {"t": 1})).to_packet()
    fourth = QoSEnvelope("state", 4, policy.delivery, NetworkPacket("state", {"t": 4})).to_packet()
    stale = QoSEnvelope("state", 2, policy.delivery, NetworkPacket("state", {"t": 2})).to_packet()

    assert receiver.accept(first) == NetworkPacket("state", {"t": 1})
    assert receiver.accept(fourth) == NetworkPacket("state", {"t": 4})
    assert receiver.accept(stale) is None

    diagnostics = receiver.diagnostics()["channels"]["state"]
    assert diagnostics["gap_events"] == 1
    assert diagnostics["skipped_sequences"] == 2
    assert diagnostics["stale_packets"] == 1
    assert diagnostics["last_sequence"] == 4


def test_receiver_rejects_delivery_policy_mismatch_without_advancing_sequence() -> None:
    receiver = TransportQoSReceiver((ChannelPolicy("state", DeliveryPolicy.UNRELIABLE),))
    packet = QoSEnvelope(
        "state",
        1,
        DeliveryPolicy.RELIABLE,
        NetworkPacket("state", {}),
    ).to_packet()

    with pytest.raises(TransportQoError) as mismatch:
        receiver.accept(packet)

    assert mismatch.value.code == "policy_mismatch"
    diagnostics = receiver.diagnostics()["channels"]["state"]
    assert diagnostics["last_sequence"] == 0
    assert diagnostics["policy_mismatches"] == 1


def test_qos_packets_flow_through_existing_tcp_peer_without_transport_changes() -> None:
    scheduler = TransportQoSScheduler((ChannelPolicy("control"),))
    receiver = TransportQoSReceiver((ChannelPolicy("control"),))
    scheduler.enqueue("control", NetworkPacket("command", {"jump": True}))
    (qos_packet,) = scheduler.drain(max_packets=1, max_bytes=8192)

    left_socket, right_socket = socket.socketpair()
    left = TCPPeer(left_socket)
    right = TCPPeer(right_socket)
    try:
        left.queue(qos_packet)
        while left.pending_send_bytes:
            left.flush()
        received = right.poll()
        assert len(received) == 1
        assert receiver.accept(received[0]) == NetworkPacket("command", {"jump": True})
    finally:
        left.close()
        right.close()


def test_diagnostics_are_deterministically_sorted_by_channel_name() -> None:
    policies = (ChannelPolicy("z"), ChannelPolicy("a"), ChannelPolicy("m"))
    scheduler = TransportQoSScheduler(policies)
    receiver = TransportQoSReceiver(policies)

    assert list(scheduler.diagnostics()["channels"]) == ["a", "m", "z"]
    assert list(receiver.diagnostics()["channels"]) == ["a", "m", "z"]
