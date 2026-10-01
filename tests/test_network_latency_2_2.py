from __future__ import annotations

import socket
import time
import traceback
from dataclasses import fields

import pytest

from swirengine.network_latency22 import (
    MAX_NETWORK_ROUND_TRIP_PENDING_22,
    MAX_NETWORK_ROUND_TRIP_SAMPLES_22,
    MAX_NETWORK_ROUND_TRIP_TIMEOUT_SECONDS_22,
    NETWORK_ROUND_TRIP_PING_KIND_22,
    NETWORK_ROUND_TRIP_PONG_KIND_22,
    NetworkRoundTripError22,
    NetworkRoundTripProbe22,
    NetworkRoundTripSample22,
)
from swirengine.networking import NetworkPacket, TCPPeer


class _Clock:
    def __init__(self, value: float = 0.0) -> None:
        self.value = value

    def __call__(self) -> float:
        return self.value


class _Nonces:
    def __init__(self) -> None:
        self.index = 0

    def __call__(self) -> str:
        self.index += 1
        return f"nonce-{self.index:010d}"


def _probe(
    clock: _Clock,
    *,
    max_pending: int = 64,
    max_samples: int = 128,
    timeout_seconds: float = 10.0,
) -> NetworkRoundTripProbe22:
    return NetworkRoundTripProbe22(
        clock=clock,
        nonce_factory=_Nonces(),
        max_pending=max_pending,
        max_samples=max_samples,
        timeout_seconds=timeout_seconds,
    )


def test_injected_monotonic_clock_measures_true_ping_pong_elapsed_time() -> None:
    clock = _Clock(100.0)
    probe = _probe(clock)

    ping = probe.create_ping()
    assert ping.kind == NETWORK_ROUND_TRIP_PING_KIND_22
    assert set(ping.payload) == {"version", "sequence", "nonce"}
    assert "timestamp" not in ping.payload

    pong = NetworkRoundTripProbe22.reply_to_ping(ping)
    clock.value = 100.0375
    sample = probe.accept_pong(pong)

    assert pong.kind == NETWORK_ROUND_TRIP_PONG_KIND_22
    assert sample.round_trip_ms == pytest.approx(37.5)
    assert probe.samples == (sample,)
    assert probe.pending_count == 0


def test_pending_and_sample_histories_are_hard_bounded() -> None:
    clock = _Clock()
    probe = _probe(clock, max_pending=2, max_samples=2)
    probe.create_ping()
    probe.create_ping()

    with pytest.raises(NetworkRoundTripError22) as capacity:
        probe.create_ping()
    assert capacity.value.code == "pending_limit"

    clock.value = 1.0
    first = _probe(clock, max_samples=2)
    for milliseconds in (10.0, 20.0, 30.0):
        ping = first.create_ping()
        clock.value += milliseconds / 1_000.0
        first.accept_pong(first.reply_to_ping(ping))

    assert [sample.round_trip_ms for sample in first.samples] == pytest.approx([20.0, 30.0])
    assert first.diagnostics()["samples_evicted"] == 1
    assert probe.diagnostics()["capacity_rejections"] == 1


def test_timeout_expiry_is_bounded_and_late_pong_is_rejected() -> None:
    clock = _Clock(5.0)
    probe = _probe(clock, timeout_seconds=0.5)
    ping = probe.create_ping()
    pong = probe.reply_to_ping(ping)

    clock.value = 5.5
    assert probe.expire() == 1
    assert probe.pending_count == 0
    with pytest.raises(NetworkRoundTripError22) as late:
        probe.accept_pong(pong)

    assert late.value.code == "unknown_probe"
    diagnostics = probe.diagnostics()
    assert diagnostics["probes_timed_out"] == 1
    assert diagnostics["packets_rejected"] == 1


def test_pong_nonce_must_match_and_replay_is_rejected_without_losing_probe() -> None:
    clock = _Clock()
    probe = _probe(clock)
    ping = probe.create_ping()
    mismatch = NetworkPacket(
        NETWORK_ROUND_TRIP_PONG_KIND_22,
        {**ping.payload, "nonce": "different-nonce-0001"},
    )

    with pytest.raises(NetworkRoundTripError22) as rejected:
        probe.accept_pong(mismatch)
    assert rejected.value.code == "probe_mismatch"
    assert probe.pending_count == 1

    pong = probe.reply_to_ping(ping)
    probe.accept_pong(pong)
    with pytest.raises(NetworkRoundTripError22) as replay:
        probe.accept_pong(pong)
    assert replay.value.code == "unknown_probe"


@pytest.mark.parametrize(
    "packet",
    [
        NetworkPacket(NETWORK_ROUND_TRIP_PING_KIND_22, {}),
        NetworkPacket(
            NETWORK_ROUND_TRIP_PING_KIND_22,
            {"version": 1, "sequence": 1, "nonce": "nonce-0000000001", "extra": 0},
        ),
        NetworkPacket(
            NETWORK_ROUND_TRIP_PING_KIND_22,
            {"version": True, "sequence": 1, "nonce": "nonce-0000000001"},
        ),
        NetworkPacket(
            NETWORK_ROUND_TRIP_PING_KIND_22,
            {"version": 2, "sequence": 1, "nonce": "nonce-0000000001"},
        ),
        NetworkPacket(
            NETWORK_ROUND_TRIP_PING_KIND_22,
            {"version": 1, "sequence": True, "nonce": "nonce-0000000001"},
        ),
        NetworkPacket(
            NETWORK_ROUND_TRIP_PING_KIND_22,
            {"version": 1, "sequence": 0, "nonce": "nonce-0000000001"},
        ),
        NetworkPacket(
            NETWORK_ROUND_TRIP_PING_KIND_22,
            {"version": 1, "sequence": 1, "nonce": "too-short"},
        ),
        NetworkPacket(
            NETWORK_ROUND_TRIP_PING_KIND_22,
            {"version": 1, "sequence": 1, "nonce": "nonce-00000000!"},
        ),
    ],
)
def test_ping_validation_rejects_unknown_missing_or_invalid_fields(packet: NetworkPacket) -> None:
    with pytest.raises(NetworkRoundTripError22):
        NetworkRoundTripProbe22.reply_to_ping(packet)


def test_pong_validation_rejects_wrong_kind_without_mutating_pending_state() -> None:
    clock = _Clock()
    probe = _probe(clock)
    ping = probe.create_ping()

    with pytest.raises(NetworkRoundTripError22) as rejected:
        probe.accept_pong(ping)

    assert rejected.value.code == "invalid_packet"
    assert probe.pending_count == 1
    assert probe.diagnostics()["packets_rejected"] == 1


def test_diagnostics_and_samples_do_not_expose_correlation_or_clock_data() -> None:
    clock = _Clock(12_345.0)
    probe = _probe(clock)
    ping = probe.create_ping()
    nonce = str(ping.payload["nonce"])
    clock.value += 0.025
    probe.accept_pong(probe.reply_to_ping(ping))

    diagnostics = probe.diagnostics()
    encoded = repr(diagnostics)
    forbidden = {"nonce", "sequence", "timestamp", "started_at", "peer_id", "client_id"}
    assert forbidden.isdisjoint(key.lower() for key in diagnostics)
    assert all(not key.lower().endswith("_id") for key in diagnostics)
    assert nonce not in encoded
    assert "12345" not in encoded
    assert tuple(field.name for field in fields(NetworkRoundTripSample22)) == ("round_trip_ms",)
    assert diagnostics["minimum_ms"] == pytest.approx(25.0)
    assert diagnostics["maximum_ms"] == pytest.approx(25.0)
    assert diagnostics["average_ms"] == pytest.approx(25.0)
    assert diagnostics["latest_ms"] == pytest.approx(25.0)


@pytest.mark.parametrize(
    ("keyword", "value"),
    [
        ("max_pending", 0),
        ("max_pending", MAX_NETWORK_ROUND_TRIP_PENDING_22 + 1),
        ("max_samples", 0),
        ("max_samples", MAX_NETWORK_ROUND_TRIP_SAMPLES_22 + 1),
        ("timeout_seconds", 0.0),
        ("timeout_seconds", MAX_NETWORK_ROUND_TRIP_TIMEOUT_SECONDS_22 + 1.0),
        ("timeout_seconds", float("inf")),
        pytest.param("timeout_seconds", 10**10_000, id="timeout-overflow"),
    ],
)
def test_configuration_limits_are_strict(keyword: str, value: object) -> None:
    with pytest.raises(NetworkRoundTripError22) as invalid:
        NetworkRoundTripProbe22(**{keyword: value})
    assert invalid.value.code == "invalid_configuration"


def test_injected_clock_must_remain_finite_and_monotonic() -> None:
    clock = _Clock(2.0)
    probe = _probe(clock)
    probe.create_ping()
    clock.value = 1.0

    with pytest.raises(NetworkRoundTripError22) as backwards:
        probe.expire()
    assert backwards.value.code == "invalid_clock"

    invalid = _probe(_Clock(float("nan")))
    with pytest.raises(NetworkRoundTripError22) as non_finite:
        invalid.create_ping()
    assert non_finite.value.code == "invalid_clock"

    overflow = _probe(_Clock(10**10_000))
    with pytest.raises(NetworkRoundTripError22) as too_large:
        overflow.create_ping()
    assert too_large.value.code == "invalid_clock"


def test_nonce_provider_is_strict_and_duplicate_pending_nonce_is_rejected() -> None:
    clock = _Clock()
    invalid = NetworkRoundTripProbe22(clock=clock, nonce_factory=lambda: "short")
    with pytest.raises(NetworkRoundTripError22) as bad_nonce:
        invalid.create_ping()
    assert bad_nonce.value.code == "invalid_nonce"

    duplicate = NetworkRoundTripProbe22(
        clock=clock,
        nonce_factory=lambda: "same-nonce-000000",
    )
    duplicate.create_ping()
    with pytest.raises(NetworkRoundTripError22) as collision:
        duplicate.create_ping()
    assert collision.value.code == "invalid_nonce"


def test_clock_and_nonce_provider_failures_hide_raw_error_chains() -> None:
    def fail_clock() -> float:
        raise RuntimeError("private-clock-provider-secret")

    def fail_nonce() -> str:
        raise RuntimeError("private-nonce-provider-secret")

    with pytest.raises(NetworkRoundTripError22) as clock_failure:
        NetworkRoundTripProbe22(clock=fail_clock).create_ping()
    with pytest.raises(NetworkRoundTripError22) as nonce_failure:
        NetworkRoundTripProbe22(nonce_factory=fail_nonce).create_ping()

    assert clock_failure.value.code == "invalid_clock"
    assert nonce_failure.value.code == "invalid_nonce"
    assert clock_failure.value.__cause__ is None
    assert nonce_failure.value.__cause__ is None
    assert clock_failure.value.__context__ is None
    assert nonce_failure.value.__context__ is None
    clock_traceback = "".join(
        traceback.format_exception(
            type(clock_failure.value),
            clock_failure.value,
            clock_failure.value.__traceback__,
        )
    )
    nonce_traceback = "".join(
        traceback.format_exception(
            type(nonce_failure.value),
            nonce_failure.value,
            nonce_failure.value.__traceback__,
        )
    )
    assert "private-clock-provider-secret" not in clock_traceback
    assert "private-nonce-provider-secret" not in nonce_traceback


def test_real_localhost_tcp_peer_round_trip_records_a_real_rtt() -> None:
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.settimeout(2.0)
    listener.bind(("127.0.0.1", 0))
    listener.listen(1)
    client_socket = socket.create_connection(listener.getsockname(), timeout=2.0)
    server_socket, _remote = listener.accept()
    listener.close()
    client = TCPPeer(client_socket)
    server = TCPPeer(server_socket)
    probe = NetworkRoundTripProbe22(timeout_seconds=2.0)

    try:
        client.queue(probe.create_ping())
        deadline = time.monotonic() + 2.0
        pong_queued = False
        sample = None
        while time.monotonic() < deadline and sample is None:
            client.flush()
            for packet in server.poll():
                server.queue(NetworkRoundTripProbe22.reply_to_ping(packet))
                pong_queued = True
            if pong_queued:
                server.flush()
            for packet in client.poll():
                sample = probe.accept_pong(packet)
            if sample is None:
                time.sleep(0.001)

        assert sample is not None
        assert sample.round_trip_ms >= 0.0
        assert probe.diagnostics()["probes_completed"] == 1
    finally:
        client.close()
        server.close()
