from __future__ import annotations

import json
import traceback
from itertools import count
from types import SimpleNamespace

import pytest

from swirengine.multiplayer14 import WorldSnapshot
from swirengine.multiplayer20 import MultiplayerCompatibility, ProductionMultiplayerSession
from swirengine.multiplayer_debugger22 import (
    MAX_MULTIPLAYER_DEBUG_CAPTURE_BYTES_22,
    MULTIPLAYER_DEBUG_CAPTURE_FORMAT_22,
    MultiplayerDebugger22,
    MultiplayerDebuggerError22,
    MultiplayerDebuggerLimits22,
)
from swirengine.network_latency22 import NetworkRoundTripProbe22
from swirengine.network_profiler16 import MultiplayerNetworkProfiler
from swirengine.networking import NetworkPacket
from swirengine.transport16 import ChannelPolicy, TransportQoSReceiver, TransportQoSScheduler


def _compatibility() -> MultiplayerCompatibility:
    return MultiplayerCompatibility(
        project_id="private-project-id",
        protocol_version="2.2",
        build_id="private-build-id",
        replication_schema="private-replication-schema",
        content_fingerprint="private-content-fingerprint",
    )


def _session(*, clients: int = 1) -> ProductionMultiplayerSession:
    token_number = count()
    session = ProductionMultiplayerSession(
        "private-session-id",
        "raw-host-client-id",
        _compatibility(),
        max_members=clients,
        token_factory=lambda: f"private-resume-token-{next(token_number):04d}",
    )
    for index in range(1, clients):
        session.join(f"raw-client-id-{index}", _compatibility())
    return session


class _RoundTripProbe:
    def __init__(self, *, fail: bool = False) -> None:
        self.samples = (SimpleNamespace(round_trip_ms=7.25),)
        self.fail = fail

    def diagnostics(self):
        if self.fail:
            raise RuntimeError("private-provider-error-text")
        return {
            "pending": 1,
            "pending_limit": 8,
            "samples_retained": 2,
            "sample_limit": 16,
            "probes_started": 3,
            "probes_completed": 2,
            "probes_timed_out": 0,
            "samples_evicted": 0,
            "packets_rejected": 0,
            "capacity_rejections": 0,
            "minimum_ms": 5.5,
            "maximum_ms": 8.0,
            "average_ms": 6.75,
            "latest_ms": 7.25,
            "private-address": "203.0.113.10",
        }


def _qos(channel: str):
    policy = ChannelPolicy(channel)
    outbound = TransportQoSScheduler((policy,))
    inbound = TransportQoSReceiver((policy,))
    outbound.enqueue(
        channel,
        NetworkPacket("private-packet-kind", {"payload": "private-packet-payload"}),
    )
    (wire_packet,) = outbound.drain(max_packets=1, max_bytes=64 * 1024)
    assert inbound.accept(wire_packet) is not None
    return outbound, inbound


def test_real_runtime_capture_is_deterministic_ascii_and_privacy_safe() -> None:
    session = _session(clients=2)
    session.set_authoritative_player_state(
        "raw-host-client-id",
        {"display_name": "private-player-state", "score": 42},
    )
    session.set_ready("raw-host-client-id")
    session.set_ready("raw-client-id-1")
    session.start_match("raw-host-client-id")
    session.publish_authoritative(WorldSnapshot(1, 1 / 60, ()))
    client_update = session.build_update("raw-client-id-1")
    assert session.acknowledge("raw-client-id-1", client_update.tick) is True

    profiler = MultiplayerNetworkProfiler(max_samples_per_client=8, max_events=8)
    debugger = MultiplayerDebugger22(session, profiler)
    channel = "private-channel-203.0.113.10"
    outbound, inbound = _qos(channel)
    debugger.sample_peer(
        "raw-host-client-id",
        1,
        transport_outbound=outbound,
        transport_inbound=inbound,
        sent_bytes=400,
        received_bytes=300,
        replicated_entities=4,
        entity_budget=8,
        round_trip_probe=_RoundTripProbe(),
    )
    debugger.sample(
        "raw-client-id-1",
        1,
        sent_bytes=200,
        received_bytes=500,
        replicated_entities=2,
    )
    profiler.record_event(
        "raw-host-client-id",
        1,
        "private-event-category",
        "private-event-name",
        {
            "traffic.sent_bytes": 12,
            "private-counter-key": 99,
            "private-token": "private-resume-token-0000",
        },
    )

    first = debugger.portable_capture()
    second = debugger.portable_capture()
    encoded = debugger.capture_json()

    assert first == second
    assert first["format"] == MULTIPLAYER_DEBUG_CAPTURE_FORMAT_22
    assert first["session"] == {
        "phase": "match",
        "revision": 5,
        "members": 2,
        "connected_members": 2,
        "ready_members": 2,
        "failures_total": 0,
    }
    assert [peer["alias"] for peer in first["peers"]] == ["peer-000", "peer-001"]
    assert first["peers"][0]["round_trip"]["latest_ms"] == pytest.approx(7.25)
    assert first["peers"][1]["replication"]["acknowledgements"] == 1
    assert first["events"] == [
        {
            "sequence": 1,
            "tick": 1,
            "peer": "peer-000",
            "kind": "network-profile",
            "counters": {"traffic.sent_bytes": 12},
        }
    ]
    host_counters = first["peers"][0]["samples"][0]["counters"]
    assert host_counters["transport_outbound.channels.channel-000.emitted_packets"] == 1
    assert host_counters["transport_inbound.channels.channel-000.accepted_packets"] == 1
    encoded.encode("ascii")
    assert len(encoded.encode("ascii")) <= MAX_MULTIPLAYER_DEBUG_CAPTURE_BYTES_22
    assert debugger.fingerprint() == debugger.fingerprint()

    forbidden = (
        "raw-host-client-id",
        "raw-client-id-1",
        "private-session-id",
        "private-project-id",
        "private-resume-token",
        "private-player-state",
        "private-channel",
        "203.0.113.10",
        "private-packet-kind",
        "private-packet-payload",
        "private-event-category",
        "private-event-name",
        "private-counter-key",
        "private-address",
    )
    assert all(secret not in encoded for secret in forbidden)


def test_history_events_channels_counters_and_encoded_size_are_hard_bounded() -> None:
    session = _session(clients=2)
    profiler = MultiplayerNetworkProfiler(max_samples_per_client=32, max_events=32)
    limits = MultiplayerDebuggerLimits22(
        max_clients=2,
        max_channels=1,
        max_counters_per_sample=3,
        max_samples_per_client=2,
        max_events=2,
        max_capture_bytes=4096,
    )
    debugger = MultiplayerDebugger22(session, profiler, limits=limits)
    first_outbound, _ = _qos("raw-channel-z")
    second_outbound, _ = _qos("raw-channel-a")

    for tick in range(1, 9):
        debugger.sample_peer(
            "raw-host-client-id",
            tick,
            transport_outbound=first_outbound if tick % 2 else second_outbound,
            sent_bytes=tick * 100,
            received_bytes=tick * 10,
            replicated_entities=tick,
            entity_budget=100,
        )
        profiler.record_event(
            "raw-host-client-id",
            tick,
            "raw-category",
            "raw-name",
            {"traffic.sent_bytes": tick},
        )

    capture = debugger.portable_capture()
    assert len(debugger.capture_bytes()) <= limits.max_capture_bytes
    assert len(capture["events"]) <= limits.max_events
    assert all(len(peer["samples"]) <= limits.max_samples_per_client for peer in capture["peers"])
    assert all(
        len(sample["counters"]) <= limits.max_counters_per_sample
        for peer in capture["peers"]
        for sample in peer["samples"]
    )
    assert capture["diagnostics"]["channels_observed"] == 2
    assert capture["diagnostics"]["channels_omitted"] == 1
    assert capture["diagnostics"]["counters_omitted"] > 0
    assert "raw-channel" not in debugger.capture_json()


def test_client_limit_fails_closed_without_leaking_the_rejected_identifier() -> None:
    session = _session(clients=2)
    debugger = MultiplayerDebugger22(
        session,
        limits=MultiplayerDebuggerLimits22(max_clients=1),
    )

    with pytest.raises(MultiplayerDebuggerError22) as raised:
        debugger.sample_peer("raw-client-id-1", 1)

    assert raised.value.code == "client_limit_reached"
    assert "raw-client-id-1" not in str(raised.value)
    capture = debugger.portable_capture()
    assert capture["diagnostics"]["clients_omitted"] == 1
    assert [peer["alias"] for peer in capture["peers"]] == ["peer-000"]


def test_round_trip_source_is_optional_measured_data_and_provider_errors_are_inert() -> None:
    session = _session()
    debugger = MultiplayerDebugger22(session)
    debugger.attach_round_trip_probe("raw-host-client-id", _RoundTripProbe(fail=True))

    snapshot = debugger.snapshot()
    assert "round_trip" not in snapshot["peers"][0]
    assert snapshot["diagnostics"]["round_trip_sources_unavailable"] == 1
    assert "provider-error" not in json.dumps(snapshot)
    assert "latency" not in json.dumps(snapshot).casefold()

    debugger.detach_round_trip_probe("raw-host-client-id")
    debugger.attach_round_trip_probe("raw-host-client-id", _RoundTripProbe())
    measured = debugger.snapshot()["peers"][0]["round_trip"]
    assert measured["probes_completed"] == 2
    assert measured["average_ms"] == pytest.approx(6.75)


def test_invalid_round_trip_statistics_are_not_presented_as_measurements() -> None:
    probe = _RoundTripProbe()
    original_diagnostics = probe.diagnostics

    def invalid_diagnostics():
        values = original_diagnostics()
        values["minimum_ms"] = -1.0
        return values

    probe.diagnostics = invalid_diagnostics  # type: ignore[method-assign]
    debugger = MultiplayerDebugger22(_session())
    debugger.attach_round_trip_probe("raw-host-client-id", probe)

    snapshot = debugger.snapshot()

    assert "round_trip" not in snapshot["peers"][0]
    assert snapshot["diagnostics"]["round_trip_sources_unavailable"] == 1


def test_real_round_trip_probe_plugs_into_debugger_without_correlation_data() -> None:
    clock = [20.0]
    probe = NetworkRoundTripProbe22(
        clock=lambda: clock[0],
        nonce_factory=lambda: "private-nonce-00000001",
    )
    ping = probe.create_ping()
    clock[0] += 0.0125
    probe.accept_pong(probe.reply_to_ping(ping))
    debugger = MultiplayerDebugger22(_session())

    debugger.sample_peer("raw-host-client-id", 1, round_trip_probe=probe)
    encoded = debugger.capture_json()
    round_trip = debugger.portable_capture()["peers"][0]["round_trip"]

    assert round_trip["latest_ms"] == pytest.approx(12.5)
    assert "private-nonce" not in encoded
    assert "sequence" not in encoded


def test_capture_results_are_defensive_and_departed_peer_alias_stays_private() -> None:
    session = _session(clients=2)
    debugger = MultiplayerDebugger22(session)
    debugger.sample_peer("raw-client-id-1", 1, sent_bytes=10)

    first = debugger.portable_capture()
    first["peers"][1]["alias"] = "tampered"
    first["peers"][1]["samples"][0]["counters"]["traffic.sent_bytes"] = -1
    session.leave("raw-client-id-1")
    second = debugger.portable_capture()

    departed = next(peer for peer in second["peers"] if peer["alias"] == "peer-001")
    assert departed["present"] is False
    assert departed["samples"][0]["counters"]["traffic.sent_bytes"] == 10
    assert "raw-client-id-1" not in json.dumps(second)


def test_limits_and_source_contracts_reject_unbounded_or_nonproduction_inputs() -> None:
    session = _session()
    with pytest.raises(ValueError, match="max_capture_bytes"):
        MultiplayerDebuggerLimits22(max_capture_bytes=MAX_MULTIPLAYER_DEBUG_CAPTURE_BYTES_22 + 1)
    with pytest.raises(ValueError, match="max_clients"):
        MultiplayerDebuggerLimits22(max_clients=65)
    with pytest.raises(TypeError, match="ProductionMultiplayerSession"):
        MultiplayerDebugger22(object())  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="MultiplayerNetworkProfiler"):
        MultiplayerDebugger22(session, object())  # type: ignore[arg-type]

    debugger = MultiplayerDebugger22(session)
    with pytest.raises(TypeError, match="TransportQoSScheduler"):
        debugger.sample_peer(
            "raw-host-client-id",
            1,
            transport_outbound=object(),  # type: ignore[arg-type]
        )
    with pytest.raises(TypeError, match="samples and diagnostics"):
        debugger.attach_round_trip_probe("raw-host-client-id", object())  # type: ignore[arg-type]

    class FailingProbe:
        @property
        def samples(self):
            raise RuntimeError("private probe property detail")

        @staticmethod
        def diagnostics():
            return {}

    with pytest.raises(TypeError, match="samples and diagnostics") as probe_failure:
        debugger.attach_round_trip_probe("raw-host-client-id", FailingProbe())
    assert probe_failure.value.__cause__ is None
    assert probe_failure.value.__context__ is None


def test_provider_failures_are_sanitized_at_the_core_boundary() -> None:
    class _FailingProfiler(MultiplayerNetworkProfiler):
        def sample_runtime(self, *args, **kwargs):
            raise RuntimeError("private-provider-error-and-client-id")

    debugger = MultiplayerDebugger22(
        _session(),
        _FailingProfiler(max_samples_per_client=1, max_events=1),
    )

    with pytest.raises(MultiplayerDebuggerError22) as failed:
        debugger.sample_peer("raw-host-client-id", 1)

    assert failed.value.code == "sample_failed"
    assert failed.value.__cause__ is None
    assert failed.value.__context__ is None
    rendered = "".join(
        traceback.format_exception(
            type(failed.value), failed.value, failed.value.__traceback__
        )
    )
    assert "private-provider-error" not in rendered
    assert "raw-host-client-id" not in str(failed.value)

    class _SpoofingProfiler(MultiplayerNetworkProfiler):
        def sample_runtime(self, *args, **kwargs):
            raise MultiplayerDebuggerError22(
                "private-provider-code",
                "private-provider-error-from-engine-error-type",
            )

    spoofing = MultiplayerDebugger22(
        _session(),
        _SpoofingProfiler(max_samples_per_client=1, max_events=1),
    )
    with pytest.raises(MultiplayerDebuggerError22) as spoofed:
        spoofing.sample_peer("raw-host-client-id", 1)
    assert spoofed.value.code == "sample_failed"
    assert spoofed.value.__cause__ is None
    assert spoofed.value.__context__ is None
    assert "private-provider" not in repr(spoofed.value)


def test_transport_diagnostics_overrides_are_not_called_before_bounded_sampling() -> None:
    class _ExplosiveScheduler(TransportQoSScheduler):
        diagnostics_calls = 0

        def diagnostics(self):
            self.diagnostics_calls += 1
            raise AssertionError("unbounded outbound diagnostics override was invoked")

    class _ExplosiveReceiver(TransportQoSReceiver):
        diagnostics_calls = 0

        def diagnostics(self):
            self.diagnostics_calls += 1
            raise AssertionError("unbounded inbound diagnostics override was invoked")

    policy = ChannelPolicy("game")
    outbound = _ExplosiveScheduler((policy,))
    inbound = _ExplosiveReceiver((policy,))
    outbound.enqueue(
        "game",
        NetworkPacket("private-packet-kind", {"payload": "private-packet-payload"}),
    )
    (wire_packet,) = outbound.drain(max_packets=1, max_bytes=64 * 1024)
    assert inbound.accept(wire_packet) is not None

    debugger = MultiplayerDebugger22(_session())
    debugger.sample_peer(
        "raw-host-client-id",
        1,
        transport_outbound=outbound,
        transport_inbound=inbound,
    )

    assert outbound.diagnostics_calls == 0
    assert inbound.diagnostics_calls == 0
    sample = debugger._profiler.latest("raw-host-client-id")
    assert sample is not None
    assert sample.counters["transport_outbound.channels.game.emitted_packets"] == 1
    assert sample.counters["transport_inbound.channels.game.accepted_packets"] == 1


@pytest.mark.parametrize(
    "profiler",
    [
        MultiplayerNetworkProfiler(max_samples_per_client=257, max_events=1),
        MultiplayerNetworkProfiler(max_samples_per_client=1, max_events=1025),
    ],
)
def test_external_profiler_retention_cannot_bypass_hard_work_limits(
    profiler: MultiplayerNetworkProfiler,
) -> None:
    with pytest.raises(MultiplayerDebuggerError22) as rejected:
        MultiplayerDebugger22(_session(), profiler)

    assert rejected.value.code == "diagnostic_source_limit"


def test_external_profiler_counter_volume_cannot_bypass_hard_work_limits() -> None:
    profiler = MultiplayerNetworkProfiler(max_samples_per_client=1, max_events=1)
    profiler.record_event(
        "raw-host-client-id",
        1,
        "category",
        "event",
        {f"private-counter-{index:04d}": index for index in range(2_049)},
    )

    with pytest.raises(MultiplayerDebuggerError22) as rejected:
        MultiplayerDebugger22(_session(), profiler)

    assert rejected.value.code == "diagnostic_source_limit"
