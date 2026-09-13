from __future__ import annotations

import socket
import struct

import pytest

from swirengine.networking import NetworkAddress, NetworkPacket, PacketStreamDecoder, TCPPeer


def test_packet_round_trip_is_deterministic() -> None:
    packet = NetworkPacket("state", {"x": 4, "name": "player"})
    encoded = packet.to_bytes()
    (size,) = struct.unpack("!I", encoded[:4])

    assert size == len(encoded) - 4
    assert NetworkPacket.from_body(encoded[4:]) == packet
    assert encoded == packet.to_bytes()


def test_stream_decoder_handles_partial_and_multiple_packets() -> None:
    decoder = PacketStreamDecoder()
    first = NetworkPacket("one", {"value": 1}).to_bytes()
    second = NetworkPacket("two", {"value": 2}).to_bytes()

    assert decoder.feed(first[:5]) == ()
    assert decoder.buffered_bytes == 5
    assert decoder.feed(first[5:] + second) == (
        NetworkPacket("one", {"value": 1}),
        NetworkPacket("two", {"value": 2}),
    )
    assert decoder.buffered_bytes == 0


def test_stream_decoder_rejects_oversized_packet() -> None:
    decoder = PacketStreamDecoder(max_packet_size=4)

    with pytest.raises(ValueError, match="exceeds limit"):
        decoder.feed(struct.pack("!I", 5) + b"12345")

    assert decoder.buffered_bytes == 0


def test_peer_transfers_packets_without_background_thread() -> None:
    left_socket, right_socket = socket.socketpair()
    left = TCPPeer(left_socket)
    right = TCPPeer(right_socket)
    try:
        left.queue(NetworkPacket("move", {"x": 1, "y": -2}))
        while left.pending_send_bytes:
            left.flush()

        assert right.poll() == (NetworkPacket("move", {"x": 1, "y": -2}),)
    finally:
        left.close()
        right.close()


def test_network_address_validates_input() -> None:
    assert NetworkAddress("localhost", 7777).tuple == ("localhost", 7777)
    with pytest.raises(ValueError):
        NetworkAddress("", 7777)
    with pytest.raises(ValueError):
        NetworkAddress("localhost", 0)
