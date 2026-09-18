# SwirEngine Multiplayer Game Demo

This directory is the source-only multiplayer integration fixture used by the SwirEngine real-game
production gate. It is not a separately released product.

The fixture drives the established replication, prediction/reconciliation, session, transport/QoS
and network-profiler path through a deterministic hostile-network simulation. The workload uses four
clients and 32 replicated entities while injecting seeded packet loss, duplication, reordering,
latency and jitter. Because the impairment is deterministic, CI can compare behavior without opening
public sockets or depending on an external service.

Run it from the repository after a development install:

```bash
python examples/multiplayer_game_demo/run_game.py
```

A successful run prints a deterministic report containing the simulation fingerprint, applied and
stale update counts, resynchronizations, prediction corrections, final client ticks, profiler data
and per-link diagnostics. The SwirEngine 1.9 production gate also copies this exact source into a
temporary project, validates scene/content declarations, stages it with `ProjectExporter`, and runs
the staged entrypoint to catch packaging/runtime drift.
