from __future__ import annotations

import pytest

from swirengine.multiplayer_showcase16 import (
    DeterministicPacketLink,
    MultiplayerSoakConfig,
    NetworkImpairmentProfile,
    run_multiplayer_soak,
)
from swirengine.networking import NetworkPacket


def _packet(index: int) -> NetworkPacket:
    return NetworkPacket("showcase.test", {"index": index, "payload": [index, index + 1]})


def test_impairment_profile_validates_rates_bounds_and_capacity():
    with pytest.raises(ValueError, match="0..1000"):
        NetworkImpairmentProfile(loss_per_mille=1001)
    with pytest.raises(ValueError, match="positive"):
        NetworkImpairmentProfile(max_inflight_packets=0)
    with pytest.raises(TypeError, match="seed"):
        NetworkImpairmentProfile(seed=True)


def test_packet_link_is_deterministic_for_identical_seed_and_input():
    profile = NetworkImpairmentProfile(
        seed=777,
        loss_per_mille=120,
        duplicate_per_mille=180,
        reorder_per_mille=500,
        base_latency_ticks=1,
        jitter_ticks=4,
        reorder_extra_ticks=3,
        max_inflight_packets=512,
    )
    first = DeterministicPacketLink(profile)
    second = DeterministicPacketLink(profile)
    for tick in range(80):
        first.send(_packet(tick), tick=tick)
        second.send(_packet(tick), tick=tick)

    first_packets = first.receive(tick=200)
    second_packets = second.receive(tick=200)
    assert [packet.to_bytes() for packet in first_packets] == [
        packet.to_bytes() for packet in second_packets
    ]
    assert first.diagnostics() == second.diagnostics()
    assert first.diagnostics().lost_packets > 0
    assert first.diagnostics().reorder_injections > 0


def test_packet_link_snapshots_payload_and_never_exceeds_inflight_bound():
    profile = NetworkImpairmentProfile(
        seed=3,
        loss_per_mille=0,
        duplicate_per_mille=0,
        reorder_per_mille=0,
        base_latency_ticks=20,
        jitter_ticks=0,
        reorder_extra_ticks=0,
        max_inflight_packets=1,
    )
    link = DeterministicPacketLink(profile)
    mutable = {"value": 1}
    packet = NetworkPacket("snapshot", mutable)
    assert link.send(packet, tick=0) == 1
    mutable["value"] = 999
    assert link.send(NetworkPacket("snapshot", {"value": 2}), tick=0) == 0

    diagnostics = link.diagnostics()
    assert diagnostics.inflight_packets == 1
    assert diagnostics.peak_inflight_packets == 1
    assert diagnostics.capacity_drops == 1
    delivered = link.receive(tick=20)
    assert delivered[0].payload == {"value": 1}


def test_duplicate_and_reorder_impairment_exercise_transport_without_unbounded_queue():
    profile = NetworkImpairmentProfile(
        seed=9,
        loss_per_mille=0,
        duplicate_per_mille=1000,
        reorder_per_mille=1000,
        base_latency_ticks=1,
        jitter_ticks=2,
        reorder_extra_ticks=2,
        max_inflight_packets=64,
    )
    link = DeterministicPacketLink(profile)
    for tick in range(10):
        link.send(_packet(tick), tick=tick)
    assert link.diagnostics().inflight_packets <= 64
    link.receive(tick=100)
    diagnostics = link.diagnostics()
    assert diagnostics.duplicated_packets == 10
    assert diagnostics.reorder_injections == 20
    assert diagnostics.inflight_packets == 0


def test_multiplayer_soak_integrates_server_replication_prediction_qos_session_and_profiler():
    config = MultiplayerSoakConfig(
        clients=3,
        entities=18,
        ticks=48,
        entity_budget=9,
        tick_rate_hz=30,
        profiler_history=24,
        impairment=NetworkImpairmentProfile(
            seed=1234,
            loss_per_mille=0,
            duplicate_per_mille=1000,
            reorder_per_mille=1000,
            base_latency_ticks=1,
            jitter_ticks=2,
            reorder_extra_ticks=2,
            max_inflight_packets=128,
        ),
    )
    report = run_multiplayer_soak(config)

    assert report.ticks == 48
    assert report.clients == 3
    assert report.applied_updates > 0
    assert report.prediction_corrections == 3 * (48 // 4)
    assert report.profiler_diagnostics["samples_total"] == 3 * 48
    assert report.profiler_diagnostics["samples_retained"] == 3 * 24
    assert report.server_diagnostics["ticks_executed"] == 48
    assert report.server_diagnostics["state"] == "stopped"
    assert all(tick == 48 for tick in report.final_client_ticks.values())
    assert all(
        diagnostics["duplicated_packets"] > 0
        and diagnostics["reorder_injections"] > 0
        and diagnostics["inflight_packets"] == 0
        for diagnostics in report.link_diagnostics.values()
    )
    assert len(report.profiler_fingerprint) == 64
    assert len(report.fingerprint()) == 64


def test_multiplayer_soak_report_is_bitwise_deterministic_for_same_config():
    config = MultiplayerSoakConfig(
        clients=4,
        entities=24,
        ticks=60,
        entity_budget=12,
        profiler_history=16,
        impairment=NetworkImpairmentProfile(
            seed=0xBEEF,
            loss_per_mille=45,
            duplicate_per_mille=25,
            reorder_per_mille=150,
            base_latency_ticks=1,
            jitter_ticks=3,
            reorder_extra_ticks=2,
            max_inflight_packets=128,
        ),
    )
    first = run_multiplayer_soak(config)
    second = run_multiplayer_soak(config)

    assert first.portable() == second.portable()
    assert first.fingerprint() == second.fingerprint()


def test_multiplayer_soak_keeps_histories_and_virtual_links_bounded_under_pressure():
    config = MultiplayerSoakConfig(
        clients=2,
        entities=16,
        ticks=80,
        entity_budget=8,
        profiler_history=8,
        impairment=NetworkImpairmentProfile(
            seed=17,
            loss_per_mille=350,
            duplicate_per_mille=300,
            reorder_per_mille=700,
            base_latency_ticks=3,
            jitter_ticks=5,
            reorder_extra_ticks=4,
            max_inflight_packets=6,
        ),
    )
    report = run_multiplayer_soak(config)

    assert report.profiler_diagnostics["samples_retained"] == 16
    assert report.profiler_diagnostics["sample_evictions"] == 2 * (80 - 8)
    assert all(
        diagnostics["peak_inflight_packets"] <= 6
        for diagnostics in report.link_diagnostics.values()
    )
    assert all(
        diagnostics["inflight_packets"] == 0
        for diagnostics in report.link_diagnostics.values()
    )
    assert sum(
        diagnostics["lost_packets"] + diagnostics["capacity_drops"]
        for diagnostics in report.link_diagnostics.values()
    ) > 0
