# Multiplayer Diagnostics & Network Profiler — SwirEngine 1.6

`swirengine.network_profiler16` is an additive, headless-safe aggregation layer for the diagnostics already exposed by the verified SwirEngine 1.6 replication, prediction, transport and session systems.

It does not own sockets, simulation truth, session state or gameplay payloads. The stable 1.x API remains unchanged.

## Runtime sampling

```python
from swirengine.network_profiler16 import MultiplayerNetworkProfiler

profiler = MultiplayerNetworkProfiler(max_samples_per_client=240, max_events=1024)

sample = profiler.sample_runtime(
    "player-7",
    tick=120,
    replication=replication_server,
    prediction=prediction_timeline,
    transport_outbound=qos_scheduler,
    transport_inbound=qos_receiver,
    session=session,
    sent_bytes=1840,
    received_bytes=620,
    replicated_entities=28,
    entity_budget=32,
)
```

The profiler calls the existing `diagnostics(...)` surfaces and flattens only finite numeric counters. Text values, booleans, payload bytes, session tokens, identity values and provider exception text are not copied into the capture.

Replication diagnostics are sampled per client; prediction, transport and session diagnostics use their existing aggregate diagnostics calls. Samples must advance monotonically per client, but different clients may be sampled independently.

## Bounded timeline

Per-client sample histories and creator-recorded events have hard retention bounds. Evictions are counted explicitly rather than growing memory silently.

```python
profiler.record_event(
    "player-7",
    tick=120,
    category="transport",
    name="snapshot-burst",
    counters={"packets": 4, "bytes": 1840},
)
```

Event metadata is intentionally small and counters-only. Do not place gameplay payloads or secrets in event category/name fields.

## Hotspot reporting

`bandwidth_hotspots()` ranks retained clients deterministically using sent + received bytes, then peak entity-budget pressure and client id. Each row reports retained-window sent/received bytes, replicated entity count and the peak `replicated_entities / entity_budget` ratio.

This is a workload/debugging surface, not an FPS or real-world network-performance claim. The caller supplies byte/entity measurements from the transport/replication integration it is profiling.

## Deterministic capture and export

`portable_capture()` returns a versioned, deterministic JSON-safe structure containing bounded samples, counters, hotspot rows and events. `fingerprint()` hashes canonical JSON with SHA-256. `export_json(path)` uses a same-directory temporary file followed by replacement so creator tooling does not leave a partially written capture at the requested path.

The capture is safe for headless servers and regression fixtures because it retains numeric diagnostics rather than arbitrary gameplay state.

## Integration guidance

- Keep profiling opt-in; do not make captures part of deterministic simulation truth.
- Sample at a fixed diagnostic cadence appropriate for the project rather than every network packet.
- Supply explicit `sent_bytes`, `received_bytes`, `replicated_entities` and `entity_budget` values when hotspot reporting is required.
- Use the existing subsystem diagnostics surfaces instead of introspecting private queues or tokens.
- Treat retained-window hotspot rankings as diagnostic evidence, not as a universal network quality score.
- Export captures only to creator-controlled local paths.

SwirEngine 1.6 remains a source-development checkpoint. No 1.6 tag, GitHub Release or PyPI publication is created by this milestone; the next public Release/PyPI publication after 1.5.0 remains reserved for SwirEngine 2.0.
