# SwirEngine 1.6 Multiplayer Showcase & Soak Gate

SwirEngine 1.6 adds a source-only multiplayer integration showcase for validating the multiplayer stack under deterministic packet impairment. It is a regression and creator example, not a network-speed or Internet-latency benchmark, and it does not create a separate demo release.

## What the showcase integrates

`swirengine.multiplayer_showcase16` composes the already verified 1.6 systems instead of introducing a competing networking stack:

- `ReplicationStreamServer` / `ReplicationStreamClient` for interest-aware ACK-baselined replication;
- `PredictionTimeline` and `PredictionCorrection` for bounded client prediction/reconciliation;
- `SessionLifecycle` for deterministic lobby/ready/match state;
- `TransportQoSScheduler` / `TransportQoSReceiver` for logical unreliable state-channel sequencing and duplicate/stale suppression;
- `DedicatedServerRuntime` for the headless fixed-tick authoritative loop;
- `MultiplayerNetworkProfiler` for bounded per-client numeric diagnostics and deterministic captures.

The showcase stays additive. Stable 1.x root imports and the published 1.5 runtime surface are unchanged.

## Deterministic virtual packet link

`DeterministicPacketLink` is an in-process impairment simulator intended for reproducible tests. `NetworkImpairmentProfile` controls:

- per-mille packet loss;
- duplicate injection;
- deterministic reorder delay;
- base latency and bounded jitter in authoritative ticks;
- a hard maximum number of in-flight packets.

The simulator snapshots every accepted packet through the stable `NetworkPacket` codec before queueing it. Caller-side payload mutation therefore cannot change queued wire state. A small platform-independent 64-bit generator is used instead of Python's randomized hashing or global `random` state, so identical seed + input produces identical impairment decisions across supported Python versions.

Queue growth is hard-bounded. When the virtual link reaches `max_inflight_packets`, new simulated copies are accounted as capacity drops rather than allowing an unbounded soak-test queue.

## Headless multi-client soak

`run_multiplayer_soak(...)` creates a deterministic match, client interest views, prediction timelines, QoS channels, packet links and profiler histories, then drives them from `DedicatedServerRuntime.run_ticks(...)`.

Each authoritative tick:

1. updates deterministic replicated entity state and interest metadata;
2. publishes one authoritative `WorldSnapshot`;
3. advances one prediction command per client and periodically applies an authoritative correction packet;
4. builds each client's replication update from its last explicit ACK baseline;
5. sends the update through the existing QoS envelope and deterministic impairment link;
6. accepts delivered QoS packets, suppresses duplicates/stale sequences, applies valid replication updates and ACKs only successfully applied ticks;
7. captures bounded replication/prediction/transport/session/traffic diagnostics.

After the authoritative loop, the runner flushes only the bounded virtual-link delay window. It does not generate hidden extra simulation ticks.

## Determinism and reports

`MultiplayerSoakReport` contains deterministic counters, final client replication ticks, per-link impairment diagnostics, a network-profiler fingerprint, stable dedicated-server counters and a SHA-256 report fingerprint. Wall-clock server tick durations are intentionally excluded from the report fingerprint because they are machine-performance measurements rather than simulation truth.

The same configuration and seed must produce the same portable report and fingerprint. The dedicated workload gate separately measures host execution time with a generous ceiling; that ceiling is a regression budget, not an FPS claim.

## Run the source showcase

```bash
python examples/demo_multiplayer_showcase_1_6.py
```

Run the focused tests:

```bash
pytest tests/test_multiplayer_showcase_soak_1_6.py
```

Run the deterministic workload gate:

```bash
python tools/benchmark_multiplayer_showcase_1_6.py
```

The dedicated GitHub Actions workflow validates the source showcase on Python 3.10, 3.13 and 3.14 and re-runs the locked 1.6 multiplayer contracts. The normal repository CI remains authoritative for broader Windows/Linux compatibility and packaging regressions.

## Release policy

This is a source-development milestone only. SwirEngine 1.6 must not create a GitHub Release, tag or PyPI publication. The next public GitHub Release and PyPI publication after 1.5.0 are reserved for SwirEngine 2.0 after its dedicated 10/10 release gate is verified.
