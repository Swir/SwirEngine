from __future__ import annotations

import socket

import pytest

from swirengine.network_gameplay import (
    ConnectionState,
    GameplayMessage,
    GameplaySession,
    MessageKind,
    MessageRouter,
    RPCRegistry,
)
from swirengine.networking import NetworkPacket, TCPPeer


def _session_pair() -> tuple[GameplaySession, GameplaySession]:
    left_socket, right_socket = socket.socketpair()
    return GameplaySession(TCPPeer(left_socket)), GameplaySession(TCPPeer(right_socket))


def _pump(left: GameplaySession, right: GameplaySession, *, turns: int = 4) -> None:
    for _ in range(turns):
        left.update()
        right.update()


def test_gameplay_message_round_trip() -> None:
    message = GameplayMessage("player.move", {"x": 3, "y": -1})

    packet = message.to_packet()

    assert packet.kind == MessageKind.EVENT
    assert GameplayMessage.from_packet(packet) == message


def test_message_router_dispatches_in_registration_order() -> None:
    router = MessageRouter()
    seen: list[str] = []
    router.on("hit", lambda message: seen.append(f"first:{message.payload['damage']}"))
    router.on("hit", lambda message: seen.append(f"second:{message.payload['damage']}"))

    handled = router.dispatch(GameplayMessage("hit", {"damage": 7}))

    assert handled == 2
    assert seen == ["first:7", "second:7"]


def test_sessions_deliver_messages_and_diagnostics() -> None:
    left, right = _session_pair()
    received: list[GameplayMessage] = []
    right.router.on("player.spawn", received.append)
    try:
        left.send("player.spawn", {"id": 4, "x": 12})
        _pump(left, right)

        assert received == [GameplayMessage("player.spawn", {"id": 4, "x": 12})]
        assert left.diagnostics.sent_messages == 1
        assert left.diagnostics.sent_packets == 1
        assert right.diagnostics.received_messages == 1
        assert right.diagnostics.received_packets == 1
        assert right.diagnostics.unknown_messages == 0
    finally:
        left.close()
        right.close()


def test_rpc_round_trip_returns_value_without_background_threads() -> None:
    client, server = _session_pair()
    server.rpc.register("combat.damage", lambda payload: payload["base"] * payload["multiplier"])
    try:
        request_id = client.call_rpc("combat.damage", {"base": 6, "multiplier": 3})
        _pump(client, server, turns=6)

        result = client.pop_rpc_result()
        assert result is not None
        assert result.request_id == request_id
        assert result.method == "combat.damage"
        assert result.ok is True
        assert result.value == 18
        assert client.pending_rpc_count == 0
        assert client.diagnostics.rpc_requests_sent == 1
        assert client.diagnostics.rpc_responses_received == 1
        assert server.diagnostics.rpc_requests_received == 1
        assert server.diagnostics.rpc_responses_sent == 1
    finally:
        client.close()
        server.close()


def test_unknown_rpc_returns_deterministic_error() -> None:
    client, server = _session_pair()
    try:
        request_id = client.call_rpc("missing.method")
        _pump(client, server, turns=6)

        result = client.pop_rpc_result()
        assert result is not None
        assert result.request_id == request_id
        assert result.ok is False
        assert result.error == "unknown RPC method: missing.method"
        assert server.diagnostics.unknown_rpc_methods == 1
        assert server.diagnostics.rpc_errors == 1
        assert client.diagnostics.rpc_errors == 1
    finally:
        client.close()
        server.close()


def test_rpc_registry_rejects_duplicate_and_arbitrary_lookup() -> None:
    registry = RPCRegistry()
    registry.register("score.add", lambda payload: payload["points"])

    with pytest.raises(ValueError, match="already registered"):
        registry.register("score.add", lambda payload: payload)
    with pytest.raises(KeyError, match="unknown RPC method"):
        registry.call("__class__", {})


def test_unhandled_messages_are_counted_without_failing_session() -> None:
    session = GameplaySession()

    session.handle_packet(NetworkPacket(MessageKind.EVENT, {"name": "unhandled", "payload": {}}))

    assert session.diagnostics.received_packets == 1
    assert session.diagnostics.received_messages == 1
    assert session.diagnostics.unknown_messages == 1


def test_session_state_is_explicit_and_close_is_idempotent() -> None:
    session = GameplaySession()
    assert session.state == ConnectionState.DISCONNECTED

    left_socket, right_socket = socket.socketpair()
    try:
        session.attach(TCPPeer(left_socket))
        assert session.connected is True
        assert session.state == ConnectionState.CONNECTED

        session.close()
        session.close()

        assert session.connected is False
        assert session.state == ConnectionState.CLOSED
        assert session.diagnostics.state_transitions == 3
    finally:
        right_socket.close()
