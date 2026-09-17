from __future__ import annotations

from swirengine.networking import NetworkPacket
from swirengine.transport16 import (
    ChannelPolicy,
    DeliveryPolicy,
    QoSEnvelope,
    TransportQoSReceiver,
    TransportQoSScheduler,
)


def main() -> None:
    policies = (
        ChannelPolicy("control", DeliveryPolicy.RELIABLE, priority=100),
        ChannelPolicy(
            "state",
            DeliveryPolicy.UNRELIABLE,
            priority=10,
            max_queue_packets=2,
        ),
        ChannelPolicy("chat", DeliveryPolicy.RELIABLE, priority=1),
    )
    scheduler = TransportQoSScheduler(policies)
    receiver = TransportQoSReceiver(policies)

    scheduler.enqueue("chat", NetworkPacket("chat", {"text": "ready"}))
    scheduler.enqueue("state", NetworkPacket("player.state", {"tick": 1, "x": 10}))
    scheduler.enqueue("state", NetworkPacket("player.state", {"tick": 2, "x": 11}))
    scheduler.enqueue("state", NetworkPacket("player.state", {"tick": 3, "x": 12}))
    scheduler.enqueue("control", NetworkPacket("match.start", {"tick": 3}))

    print("Outbound order:")
    for packet in scheduler.drain(max_packets=8, max_bytes=64 * 1024):
        envelope = QoSEnvelope.from_packet(packet)
        accepted = receiver.accept(packet)
        print(
            f"  channel={envelope.channel:<7} sequence={envelope.sequence:<2} "
            f"delivery={envelope.delivery.value:<10} kind={accepted.kind if accepted else 'dropped'}"
        )

    print("Outbound diagnostics:", scheduler.diagnostics())
    print("Inbound diagnostics:", receiver.diagnostics())


if __name__ == "__main__":
    main()
