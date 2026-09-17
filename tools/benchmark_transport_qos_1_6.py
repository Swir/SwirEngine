from __future__ import annotations

import time

from swirengine.networking import NetworkPacket
from swirengine.transport16 import (
    ChannelPolicy,
    DeliveryPolicy,
    TransportQoSReceiver,
    TransportQoSScheduler,
)

ITERATIONS = 20_000
BUDGET_SECONDS = 5.0


def main() -> None:
    policies = (
        ChannelPolicy(
            "control",
            DeliveryPolicy.RELIABLE,
            priority=100,
            max_queue_packets=512,
            max_queue_bytes=2 * 1024 * 1024,
        ),
        ChannelPolicy(
            "state",
            DeliveryPolicy.UNRELIABLE,
            priority=10,
            max_queue_packets=128,
            max_queue_bytes=512 * 1024,
        ),
    )
    scheduler = TransportQoSScheduler(policies)
    receiver = TransportQoSReceiver(policies)
    emitted = 0
    accepted = 0

    started = time.perf_counter()
    for tick in range(1, ITERATIONS + 1):
        scheduler.enqueue("control", NetworkPacket("input.ack", {"tick": tick}))
        scheduler.enqueue("state", NetworkPacket("state", {"tick": tick, "x": tick % 257}))
        if tick % 128 == 0:
            packets = scheduler.drain(max_packets=256, max_bytes=2 * 1024 * 1024)
            emitted += len(packets)
            for packet in packets:
                if receiver.accept(packet) is not None:
                    accepted += 1

    while scheduler.queued_packets:
        packets = scheduler.drain(max_packets=256, max_bytes=2 * 1024 * 1024)
        if not packets:
            raise RuntimeError("QoS benchmark queue could not make progress")
        emitted += len(packets)
        for packet in packets:
            if receiver.accept(packet) is not None:
                accepted += 1

    elapsed = time.perf_counter() - started
    outbound = scheduler.diagnostics()
    inbound = receiver.diagnostics()
    print(
        "transport-qos benchmark:",
        f"iterations={ITERATIONS}",
        f"emitted={emitted}",
        f"accepted={accepted}",
        f"queued={outbound['queued_packets']}",
        f"state_skipped={inbound['channels']['state']['skipped_sequences']}",
        f"elapsed={elapsed:.4f}s",
        f"budget={BUDGET_SECONDS:.1f}s",
    )
    if elapsed > BUDGET_SECONDS:
        raise SystemExit(
            f"transport QoS benchmark exceeded budget: {elapsed:.4f}s > {BUDGET_SECONDS:.1f}s"
        )


if __name__ == "__main__":
    main()
