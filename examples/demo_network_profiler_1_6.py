from __future__ import annotations

from swirengine.network_profiler16 import MultiplayerNetworkProfiler
from swirengine.session16 import SessionLifecycle
from swirengine.transport16 import ChannelPolicy, TransportQoSReceiver, TransportQoSScheduler

profiler = MultiplayerNetworkProfiler(max_samples_per_client=8, max_events=16)
session = SessionLifecycle("demo-session", "host", token_factory=lambda: "demo-token-0001")
outbound = TransportQoSScheduler([ChannelPolicy("game", priority=10)])
inbound = TransportQoSReceiver([ChannelPolicy("game", priority=10)])

for tick in range(1, 6):
    profiler.sample_runtime(
        "host",
        tick,
        transport_outbound=outbound,
        transport_inbound=inbound,
        session=session,
        sent_bytes=700 + tick * 10,
        received_bytes=220 + tick * 5,
        replicated_entities=12 + tick,
        entity_budget=32,
    )

profiler.record_event("host", 5, "session", "demo-complete", {"ticks": 5})
print(profiler.bandwidth_hotspots(limit=1)[0])
print(profiler.diagnostics())
print(profiler.fingerprint())
