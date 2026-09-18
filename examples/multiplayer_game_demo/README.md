# SwirEngine Multiplayer Game Demo

This directory is the source-only multiplayer integration fixture used by the SwirEngine real-game
production gate. It is not a separately released product.

The fixture drives the established replication, prediction/reconciliation, session, transport/QoS
and network-profiler path through a deterministic hostile-network simulation. The workload uses four
clients and 32 replicated entities while injecting seeded packet loss, duplication, reordering,
latency and jitter. Because the impairment is deterministic, CI can compare behavior without opening
public sockets or depending on an external service.

The SwirEngine 2.0 production probe additionally exercises the high-level compatibility/session
contract: a matching client joins, authoritative gameplay state remains separate from client-local
settings/save data, the match starts, the client disconnects and resumes with a rotated token, and the
server forces a full replication resynchronization from the current authoritative snapshot.

Run it from the repository after a development install:

```bash
python examples/multiplayer_game_demo/run_game.py
```

A successful run prints a deterministic report containing the simulation fingerprint, applied and
stale update counts, resynchronizations, prediction corrections, final client ticks, profiler data,
per-link diagnostics and the 2.0 production-contract probe. The source-only production gates also copy
this fixture into isolated temporary projects, validate scene/content declarations, stage it with
`ProjectExporter`, and run the staged entrypoint to catch packaging/runtime drift.
