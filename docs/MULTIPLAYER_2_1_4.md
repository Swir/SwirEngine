# SwirEngine 1.4 Multiplayer 2.0

SwirEngine 1.4 adds an opt-in deterministic multiplayer simulation layer in
`swirengine.multiplayer14`. It builds on the stable 1.x `NetworkPacket` transport instead of
replacing it, so existing networking, gameplay messaging, RPC code, and root imports remain
compatible.

The milestone focuses on the game-simulation problems that sit above transport I/O:

- explicit replicated component schemas,
- canonical world snapshots and sparse entity deltas,
- jitter-tolerant snapshot interpolation,
- local client prediction and authoritative reconciliation,
- bounded server rewind history for lag-compensation foundations,
- deterministic packet/byte diagnostics,
- an additive bridge to the stable `NetworkPacket` wire format.

No background threads or wall-clock reads are hidden in these primitives. Ticks, server time, input
sequence numbers, and diagnostic elapsed time are supplied by the caller so tests and replays remain
deterministic.

## Replication schemas

Replication is opt-in. A component must declare exactly which fields cross the network.

```python
from swirengine.multiplayer14 import ReplicationField, ReplicationRegistry

registry = ReplicationRegistry()
registry.define(
    "transform",
    (
        ReplicationField("x"),
        ReplicationField("y"),
        ReplicationField("animation", interpolate=False),
    ),
)
registry.define("health", ("hp",))
```

`ReplicationRegistry.capture(...)` copies only declared fields and validates values into a portable
JSON-compatible representation. Unknown components, missing declared fields, non-string mapping
keys, unsupported object values, and non-finite floats are rejected before a snapshot is built.

The `interpolate=False` flag is useful for discrete creator state such as animation names, weapon
slots, stance modes, or state-machine labels. Numeric transform data can interpolate while discrete
fields remain on the older authoritative value until the newer snapshot is reached.

## Snapshots and deltas

`WorldSnapshot` sorts entities by positive network id and emits canonical JSON bytes with stable key
ordering. That gives creator tooling and regression tests a deterministic payload independent of
dictionary insertion order.

```python
snapshot = WorldSnapshot(tick=120, server_time=6.0, entities=(player, enemy))
wire_bytes = snapshot.to_bytes()
restored = WorldSnapshot.from_bytes(wire_bytes)
```

`SnapshotDelta.between(baseline, current)` sends only changed/new entities plus removed network ids.
A delta records its baseline tick and refuses to apply to the wrong baseline, preventing silent world
corruption when a packet is lost or an old baseline is selected.

```python
delta = SnapshotDelta.between(previous, current)
current_again = delta.apply(previous)
```

The delta layer is intentionally entity-granular in the first 2.0 contract. Component/field-level
compression can be layered on later without changing authoritative snapshot semantics.

## Snapshot interpolation

`SnapshotBuffer` accepts snapshots that arrive out of order, replaces duplicate ticks, keeps a
bounded history, and samples by server time.

```python
buffer = SnapshotBuffer(registry=registry, max_snapshots=32)
buffer.push(snapshot_a)
buffer.push(snapshot_b)
render_state = buffer.sample(render_server_time)
```

Numeric replicated values interpolate recursively. Discrete schema fields do not. Samples before or
after the buffered time range clamp to the nearest authoritative state and expose `clamped=True`.

Entity lifetime is conservative: an entity present in the older snapshot remains visible until the
newer boundary, while a newly spawned entity appears at the newer boundary. This avoids inventing
partially authoritative entity state between snapshots.

## Client prediction and reconciliation

`ClientPredictor` keeps a bounded ordered history of unacknowledged commands. The game supplies a
pure simulation callback and uses the same callback both for immediate local prediction and replay
after an authoritative correction.

```python
def simulate(state, command):
    return {"x": state["x"] + command.payload["dx"]}

predictor = ClientPredictor({"x": 0.0}, simulate)
predictor.predict(PredictionCommand(1, tick=50, payload={"dx": 1.0}))
result = predictor.reconcile(acknowledged_sequence=1, authoritative_state={"x": 0.9})
```

Reconciliation discards acknowledged inputs, resets to the authoritative state, and replays only the
remaining commands in sequence order. Duplicate or decreasing command sequence numbers are rejected,
and bounded pending history fails explicitly rather than silently dropping unacknowledged input.

## Lag-compensation foundation

`LagCompensationHistory` stores bounded authoritative snapshots for server-side rewind. It is not a
hit-validation policy by itself; game code decides what client timestamp is trusted and what gameplay
query to evaluate against the rewind sample.

```python
history = LagCompensationHistory(registry=registry, max_seconds=1.0, max_frames=128)
history.record(authoritative_snapshot)
rewound = history.rewind(client_server_time)
```

Snapshots must be recorded in non-decreasing server-time order. Old frames are pruned by both time
window and frame count. Rewind uses the same deterministic interpolation semantics as render
interpolation.

## Bandwidth diagnostics

`MultiplayerBandwidthDiagnostics` records packet and byte totals globally and per creator-selected
channel. It does not read a system clock. The caller supplies elapsed seconds when requesting a
report, which makes bandwidth-rate tests deterministic.

```python
diagnostics.record_sent(packet.to_bytes(), channel="snapshot")
diagnostics.record_received(input_bytes, channel="input")
report = diagnostics.report(elapsed_seconds=1.0)
```

The report exposes sent/received packet counts, byte counts, bytes-per-second rates, and channel
breakdowns.

## Stable transport bridge

`MultiplayerPacketCodec` wraps snapshots and deltas in the existing stable `NetworkPacket` type:

```python
packet = MultiplayerPacketCodec.snapshot_packet(snapshot)
snapshot_again = MultiplayerPacketCodec.decode_snapshot(packet)
```

Packet kinds are namespaced as `swir.multiplayer.snapshot` and `swir.multiplayer.delta`. Existing
`TCPPeer`, framing, message routing, and custom transports do not need to change.

## Compatibility and verified validation

`swirengine.multiplayer14` is additive and opt-in. It does not modify `swirengine.__init__`, the
stable 1.2 networking APIs, `GameplaySession`, packet framing, or package version 1.3.0.

The completed `Multiplayer 2.0 1.4 Validation` gate is green on Python 3.10, 3.13 and 3.14. It verifies
29 focused Multiplayer 2.0 plus stable networking regressions, strict Ruff, compileall and the
runnable integration demo. The Python 3.13 workload validates 500 replicated entities, 120
interpolation samples, 256 predicted commands with reconciliation and 100 rewind queries in
**0.493160s**. In the sparse-update case, the delta is **2,493 bytes** versus **50,114 bytes** for the
full snapshot (about 4.97%). The repository-level CI, Desktop Export, Demo Game 3D and Neon Snake 3D
compatibility gates are also green on the implementation head.

With those implementation, regression, documentation, demo, performance and repository gates green,
Multiplayer 2.0 is the verified ninth roadmap deliverable and 1.4 progress is **9/10 = 90.0%**.
SwirEngine 1.4 still must not be tagged or published until the final Showcase + Hardening + Release
Gate reaches 10/10 and its release checks are green.
