# Transport QoS & Channel Policies — SwirEngine 1.6

SwirEngine 1.6 adds an **opt-in, transport-independent QoS layer** in `swirengine.transport16`. It sits above the stable 1.x `NetworkPacket` framing instead of replacing or changing `TCPPeer`, `TCPClient`, or `TCPServer`.

The goal is to make multiplayer traffic policy explicit and deterministic: creators can separate reliable control/event traffic from freshness-oriented state traffic, bound every outbound queue, schedule channels by priority, reject or evict packets predictably under pressure, and inspect per-channel counters.

## Compatibility model

`transport16` is additive. Existing code that uses `swirengine.networking` continues to work unchanged. A QoS scheduler emits ordinary `NetworkPacket` instances, so the result can be passed directly to `TCPPeer.queue()` or another creator-owned transport bridge.

The QoS layer does **not** pretend that every underlying transport has wire-level reliability. `DeliveryPolicy.RELIABLE` means SwirEngine preserves queued packets under pressure, enforces contiguous receive sequencing, and refuses silent gaps. Retransmission/acknowledgement at the wire layer remains the responsibility of the selected transport. With the existing TCP transport, TCP supplies ordered reliable delivery beneath this policy layer.

## Defining channels

```python
from swirengine.transport16 import ChannelPolicy, DeliveryPolicy

policies = (
    ChannelPolicy("control", DeliveryPolicy.RELIABLE, priority=100),
    ChannelPolicy("state", DeliveryPolicy.UNRELIABLE, priority=10),
    ChannelPolicy("chat", DeliveryPolicy.RELIABLE, priority=1),
)
```

Each `ChannelPolicy` defines:

- `name`: normalized non-empty channel identifier;
- `delivery`: `reliable` or `unreliable`;
- `priority`: deterministic scheduler priority from `-1000` through `1000`;
- `max_packet_bytes`: hard limit for the **complete encoded QoS `NetworkPacket` frame**, including the stable length prefix;
- `max_queue_packets`: hard count bound for the channel;
- `max_queue_bytes`: hard byte bound for the channel.

Duplicate normalized channel names and invalid bounds are rejected during construction.

## Outbound scheduling

```python
from swirengine.networking import NetworkPacket
from swirengine.transport16 import TransportQoSScheduler

scheduler = TransportQoSScheduler(policies)
scheduler.enqueue("control", NetworkPacket("match.start", {"tick": 42}))
scheduler.enqueue("state", NetworkPacket("player.state", {"tick": 42, "x": 12}))

wire_packets = scheduler.drain(max_packets=32, max_bytes=64 * 1024)
for packet in wire_packets:
    peer.queue(packet)
```

Sequences are monotonic **per channel** and are consumed only when an enqueue is accepted. Drain order is deterministic:

1. the highest configured channel priority wins;
2. packets within a channel remain FIFO;
3. equal-priority heads are ordered by global enqueue order;
4. a head that cannot fit the remaining byte budget is left queued, allowing another channel head that does fit to make progress.

Both `max_packets` and `max_bytes` are hard per-drain budgets. `drain()` never silently discards a packet just because the current drain budget is too small.

## Back-pressure semantics

### Reliable channels

A reliable channel never evicts an accepted queued packet to make room for a newer one. If the next enqueue would exceed `max_queue_packets` or `max_queue_bytes`, `enqueue()` raises:

```text
TransportQoError(code="backpressure")
```

The rejection is atomic with respect to queue contents and sequence allocation. Creators can slow producers, drain the transport, disconnect an unhealthy peer, or apply their own higher-level policy.

### Unreliable channels

An unreliable channel favors **freshness**. When the next valid packet would exceed a queue bound, the oldest queued packet(s) are deterministically removed until the newest packet fits. Those removals are exposed in `dropped_packets` and `dropped_bytes` diagnostics.

A single encoded packet that cannot satisfy `max_packet_bytes` or `max_queue_bytes` is rejected with `TransportQoError(code="packet_too_large")`; queue pressure never bypasses a hard size bound.

This makes a small unreliable `state` channel useful for transient snapshots where an old unsent position update has less value than a current one.

## Receive sequencing and duplicate suppression

```python
from swirengine.transport16 import TransportQoSReceiver

receiver = TransportQoSReceiver(policies)

for qos_packet in peer.poll():
    inner = receiver.accept(qos_packet)
    if inner is not None:
        handle(inner)
```

The receiver validates the QoS envelope and configured channel policy before exposing the nested creator packet.

For **reliable** channels:

- the next sequence must be exactly `last_sequence + 1`;
- the current sequence repeated again is suppressed as a duplicate;
- older sequences are suppressed as stale;
- a forward gap raises `TransportQoError(code="reliable_gap")` without advancing the accepted sequence baseline.

For **unreliable** channels:

- any sequence newer than the accepted baseline is accepted;
- skipped sequence numbers are counted as observed loss/eviction;
- duplicate/stale packets are suppressed;
- the newest accepted sequence becomes the new baseline.

An envelope whose declared delivery policy disagrees with the locally configured channel is rejected with `TransportQoError(code="policy_mismatch")`. Unknown channels are rejected with `TransportQoError(code="unknown_channel")`.

## Stable framing

A `QoSEnvelope` is encoded as a normal stable 1.x packet with kind:

```text
swir.transport16.qos
```

Its payload contains the channel, per-channel sequence, delivery policy, and nested `NetworkPacket` kind/payload. This gives the QoS layer a transport-independent representation while retaining deterministic JSON framing and the existing TCP path.

```python
from swirengine.transport16 import QoSEnvelope

envelope = QoSEnvelope.from_packet(qos_packet)
round_tripped = envelope.to_packet()
```

## Telemetry

Both scheduler and receiver expose deterministic `diagnostics()` dictionaries sorted by channel name.

Outbound counters include:

- queued packet/byte totals;
- enqueued/emitted packet and byte totals;
- unreliable pressure drops;
- reliable back-pressure rejections;
- oversized-packet rejections;
- next per-channel sequence.

Inbound counters include:

- accepted packets;
- duplicate and stale suppressions;
- gap events and skipped sequences;
- policy mismatches;
- last accepted sequence.

The diagnostics contain no packet payload data and no session resume secrets.

## Failure handling recommendations

`packet_too_large` usually indicates a creator payload or channel bound that should be adjusted deliberately. Do not automatically increase limits based on untrusted input.

`backpressure` on reliable traffic means the consumer is not keeping up with the producer. Drain more frequently, reduce production, or treat sustained pressure as a peer-health failure rather than allowing unbounded memory growth.

`reliable_gap` means the selected transport/path did not provide the sequence the policy expected. Keep the baseline unchanged. A transport adapter may recover/retransmit, or the application may reconnect/resynchronize instead of accepting an incomplete reliable stream.

`policy_mismatch` and `unknown_channel` should normally be treated as protocol/configuration errors.

## Verification workload

The dedicated 1.6 QoS gate validates Python 3.10, 3.13, and 3.14 and covers:

- deterministic envelope round trips through stable `NetworkPacket` framing;
- strict channel policy validation;
- per-channel monotonic sequencing;
- reliable atomic back-pressure;
- unreliable oldest-first pressure eviction;
- strict priority scheduling and packet/byte drain budgets;
- reliable gap rejection and duplicate/stale suppression;
- unreliable gap accounting;
- policy mismatch/unknown-channel rejection;
- actual `TCPPeer` socket-pair transport compatibility;
- locked 1.4 multiplayer/networking and verified 1.6 replication, prediction, and session regressions;
- deterministic workload benchmark and creator demo.

Run the focused checks locally with:

```bash
pytest tests/test_transport_qos_1_6.py tests/test_networking.py tests/test_multiplayer_2_1_4.py
python tools/benchmark_transport_qos_1_6.py
python examples/demo_transport_qos_1_6.py
```
