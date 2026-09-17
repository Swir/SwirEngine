# Interest-aware Replication Streaming 2.0 (SwirEngine 1.6)

SwirEngine 1.6 starts with an additive replication-streaming layer in `swirengine.multiplayer16`. It builds on the stable 1.4 snapshot/delta model instead of replacing it, so existing 1.x multiplayer code can continue using `swirengine.multiplayer14` unchanged.

## Why this layer exists

A single authoritative world snapshot is useful, but sending every replicated entity to every player does not scale. Replication Streaming 2.0 adds a deterministic per-client selection layer and explicit ACK-based baselines:

- creators publish one authoritative `WorldSnapshot` per server tick;
- each replicated entity has separate `EntityInterest` metadata (position, channel, priority, always-relevant flag);
- every client has an `InterestView` (position, radius, subscribed channels);
- the server filters the current snapshot for that client and enforces an optional entity budget;
- the first update is a full filtered snapshot;
- later updates become deltas only from a snapshot that the client explicitly acknowledged;
- if a packet is lost, that lost tick is never silently selected as a baseline;
- moving out of relevance becomes a normal `SnapshotDelta.removed` entry;
- clients retain bounded baseline history so a newer delta can still reference the last ACKed snapshot.

## Minimal server/client flow

```python
from swirengine.multiplayer14 import ReplicatedEntity, WorldSnapshot
from swirengine.multiplayer16 import (
    EntityInterest,
    InterestManager,
    InterestView,
    ReplicationStreamClient,
    ReplicationStreamServer,
)

interest = InterestManager()
interest.upsert(EntityInterest(1, (0.0, 0.0, 0.0), priority=10))
interest.upsert(EntityInterest(2, (200.0, 0.0, 0.0)))

server = ReplicationStreamServer(interest)
server.register_client("player-1", InterestView((0.0, 0.0, 0.0), radius=64.0))
client = ReplicationStreamClient()

snapshot = WorldSnapshot(
    tick=1,
    server_time=0.05,
    entities=(
        ReplicatedEntity(1, {"transform": {"x": 0.0}}),
        ReplicatedEntity(2, {"transform": {"x": 200.0}}),
    ),
)
server.publish(snapshot)

update = server.build_update("player-1")
client.apply(update)
server.acknowledge("player-1", update.tick)
```

The client sees entity `1`; entity `2` is outside its current interest radius.

## Interest ordering

Queries are stable and deterministic. Matching entities are ordered by:

1. `always_relevant=True` before normal entities;
2. squared distance from the client's interest position;
3. higher integer `priority` when distances are equal;
4. lower `net_id` as the final deterministic tie-breaker.

The optional `max_entities_per_client` budget cuts this ordered result. Snapshot entities themselves remain ordered by the stable `WorldSnapshot` contract.

`always_relevant` bypasses the radius check, not the channel check. This allows globally relevant gameplay objects to stay scoped to a creator-defined replication channel.

## Explicit ACK baseline rule

`ReplicationStreamServer` stores the filtered snapshots it actually sent to each client. Calling:

```python
server.acknowledge("player-1", tick)
```

moves that client's baseline only when `tick` was genuinely sent. ACKs are monotonic. Unknown/unsent future ticks are rejected.

This matters under loss:

- tick 10 is sent and ACKed;
- tick 11 is sent but lost, therefore never ACKed;
- tick 12 is built from tick 10, not tick 11.

The receiver can therefore reconstruct tick 12 from a baseline it proved it had.

## Relevance transitions

Interest state is applied before delta generation. If entity `7` existed in the ACKed filtered snapshot but is no longer relevant, the next delta contains `removed=(7,)`. If it later re-enters interest, its current complete replicated entity state appears as an upsert.

This keeps relevance changes inside the same deterministic delta semantics as gameplay state changes.

## Strict metadata safety

By default, every entity in an authoritative `WorldSnapshot` must have matching `EntityInterest` metadata. Missing metadata raises `KeyError` during `build_update()` instead of silently omitting a replicated object.

Advanced/custom interest providers may opt out deliberately:

```python
server = ReplicationStreamServer(interest, strict_metadata=False)
```

This is intentionally explicit because silent omissions are difficult to diagnose in multiplayer games.

## Packet transport

`ReplicationUpdate.to_packet()` serializes either a full snapshot or delta into the existing stable `NetworkPacket` type using packet kind:

```text
swir.multiplayer16.update
```

`ReplicationUpdate.from_packet()` reverses the operation. The 1.6 system does not modify TCP framing or existing `GameplaySession` behavior, so creators may use the built-in transport or carry these packets through a custom transport.

## Client history and resynchronization

`ReplicationStreamClient` stores a bounded tick-indexed snapshot history. A delta can reference any retained baseline, not only the receiver's latest speculative/unacknowledged state. If the requested baseline was pruned or never received, application raises `LookupError` rather than applying the delta to the wrong state.

A server can recover by sending a full snapshot. Full delivery is also used automatically when the server cannot use an acknowledged retained baseline.

## Diagnostics

Per-client server counters are available through:

```python
server.diagnostics("player-1")
```

The report includes full/delta update counts, full entities, upserts, removals, ACKs, and full-snapshot fallbacks. Counters use deterministic integer accounting and are suitable for tests and creator diagnostics.

## Compatibility boundary

Replication Streaming 2.0 is intentionally opt-in:

- it lives in `swirengine.multiplayer16`;
- it imports and reuses the stable `ReplicatedEntity`, `WorldSnapshot`, and `SnapshotDelta` contracts;
- it does not change root-package imports;
- it does not alter `swirengine.networking`, `swirengine.network_gameplay`, or `swirengine.multiplayer14` behavior.

The dedicated validation gate also reruns `tests/test_multiplayer_2_1_4.py` so the older multiplayer contract remains locked while 1.6 evolves.
