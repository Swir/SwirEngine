from __future__ import annotations

import json

import pytest

from swirengine.network_profiler16 import MultiplayerNetworkProfiler


class _Diagnostics:
    def __init__(self, payload):
        self.payload = payload

    def diagnostics(self, *args):
        return self.payload


def test_runtime_sample_flattens_numeric_diagnostics_and_ignores_sensitive_values():
    profiler = MultiplayerNetworkProfiler()
    sample = profiler.sample_runtime(
        "player-b",
        10,
        replication=_Diagnostics({"full_updates": 2, "secret": "payload"}),
        prediction=_Diagnostics({"replayed_commands": 4, "corrected": True}),
        transport_outbound=_Diagnostics(
            {"channels": {"game": {"emitted_bytes": 512, "delivery": "reliable"}}}
        ),
        session=_Diagnostics({"members": 3, "phase": "match"}),
        sent_bytes=900,
        received_bytes=400,
        replicated_entities=18,
        entity_budget=24,
    )

    assert sample.counters["replication.full_updates"] == 2
    assert sample.counters["prediction.replayed_commands"] == 4
    assert sample.counters["transport_outbound.channels.game.emitted_bytes"] == 512
    assert sample.counters["session.members"] == 3
    assert sample.counters["traffic.entity_budget_ratio"] == pytest.approx(0.75)
    assert all("secret" not in key for key in sample.counters)
    assert all("phase" not in key for key in sample.counters)


def test_sample_ticks_must_increase_per_client_but_clients_are_independent():
    profiler = MultiplayerNetworkProfiler()
    profiler.sample_runtime("a", 5)
    profiler.sample_runtime("b", 1)
    with pytest.raises(ValueError, match="tick must increase"):
        profiler.sample_runtime("a", 5)
    profiler.sample_runtime("b", 2)


def test_history_and_events_are_hard_bounded_with_eviction_diagnostics():
    profiler = MultiplayerNetworkProfiler(max_samples_per_client=2, max_events=2)
    for tick in range(1, 5):
        profiler.sample_runtime("a", tick, sent_bytes=tick)
    for tick in range(1, 5):
        profiler.record_event("a", tick, "transport", "sample", {"bytes": tick})

    assert [sample.tick for sample in profiler.history("a")] == [3, 4]
    assert [event.sequence for event in profiler.events()] == [3, 4]
    assert profiler.diagnostics() == {
        "clients": 1,
        "samples_total": 4,
        "samples_retained": 2,
        "sample_evictions": 2,
        "events_total": 4,
        "events_retained": 2,
        "event_evictions": 2,
    }


def test_event_filtering_uses_sequence_and_client_without_storing_text_payloads():
    profiler = MultiplayerNetworkProfiler()
    profiler.record_event("b", 1, "session", "join", {"members": 2, "token": "hidden"})
    second = profiler.record_event("a", 2, "replication", "burst", {"entities": 14})
    profiler.record_event("a", 3, "transport", "drop", {"dropped": 1})

    events = profiler.events(client_id="a", since_sequence=1)
    assert [event.sequence for event in events] == [second.sequence, 3]
    assert events[0].counters == {"entities": 14}
    capture = profiler.portable_capture()
    assert "hidden" not in json.dumps(capture)


def test_bandwidth_hotspots_are_deterministic_and_include_entity_pressure():
    profiler = MultiplayerNetworkProfiler()
    profiler.sample_runtime(
        "zeta", 1, sent_bytes=100, received_bytes=100, replicated_entities=9, entity_budget=10
    )
    profiler.sample_runtime(
        "alpha", 1, sent_bytes=150, received_bytes=100, replicated_entities=4, entity_budget=10
    )
    profiler.sample_runtime(
        "beta", 1, sent_bytes=125, received_bytes=125, replicated_entities=8, entity_budget=10
    )

    hotspots = profiler.bandwidth_hotspots(limit=3)
    assert [row["client_id"] for row in hotspots] == ["beta", "alpha", "zeta"]
    assert hotspots[0]["peak_entity_budget_ratio"] == pytest.approx(0.8)


def test_capture_and_fingerprint_are_deterministic_across_client_insertion_order():
    first = MultiplayerNetworkProfiler()
    second = MultiplayerNetworkProfiler()
    for profiler, order in ((first, ("b", "a")), (second, ("a", "b"))):
        for client_id in order:
            profiler.sample_runtime(client_id, 1, sent_bytes=10)

    assert first.portable_capture() == second.portable_capture()
    assert first.fingerprint() == second.fingerprint()


def test_atomic_json_export_round_trips_capture(tmp_path):
    profiler = MultiplayerNetworkProfiler()
    profiler.sample_runtime("player", 7, sent_bytes=123, entity_budget=32)
    target = profiler.export_json(tmp_path / "captures" / "network.json")

    assert target.exists()
    assert json.loads(target.read_text(encoding="utf-8")) == profiler.portable_capture()
    assert not target.with_name(".network.json.tmp").exists()


def test_non_finite_diagnostics_and_negative_traffic_are_rejected():
    profiler = MultiplayerNetworkProfiler()
    with pytest.raises(ValueError, match="finite"):
        profiler.sample_runtime("a", 1, prediction=_Diagnostics({"bad": float("inf")}))
    with pytest.raises(ValueError, match="non-negative"):
        profiler.sample_runtime("a", 1, sent_bytes=-1)


def test_diagnostic_source_contract_is_explicit():
    profiler = MultiplayerNetworkProfiler()
    with pytest.raises(TypeError, match="diagnostics"):
        profiler.sample_runtime("a", 1, prediction=object())
    with pytest.raises(TypeError, match="return a mapping"):
        profiler.sample_runtime("a", 1, prediction=_Diagnostics([]))


def test_real_existing_diagnostics_surfaces_can_be_composed():
    from swirengine.prediction16 import PredictionTimeline
    from swirengine.session16 import SessionLifecycle
    from swirengine.transport16 import ChannelPolicy, TransportQoSReceiver, TransportQoSScheduler

    timeline = PredictionTimeline({"x": 0.0}, lambda state, command: state)
    session = SessionLifecycle("session", "host", token_factory=lambda: "token-0001")
    outbound = TransportQoSScheduler([ChannelPolicy("game")])
    inbound = TransportQoSReceiver([ChannelPolicy("game")])

    profiler = MultiplayerNetworkProfiler()
    sample = profiler.sample_runtime(
        "host",
        1,
        prediction=timeline,
        transport_outbound=outbound,
        transport_inbound=inbound,
        session=session,
    )

    assert "prediction.predicted_commands" in sample.counters
    assert "transport_outbound.queued_packets" in sample.counters
    assert "transport_inbound.channels.game.accepted_packets" in sample.counters
    assert "session.members" in sample.counters
