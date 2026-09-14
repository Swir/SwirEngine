from __future__ import annotations

import socket

from swirengine import GameplaySession, TCPPeer


def pump(left: GameplaySession, right: GameplaySession, turns: int = 6) -> None:
    for _ in range(turns):
        left.update()
        right.update()


def main() -> None:
    left_socket, right_socket = socket.socketpair()
    client = GameplaySession(TCPPeer(left_socket))
    server = GameplaySession(TCPPeer(right_socket))

    server.router.on("player.spawn", lambda message: print("event:", message.payload))
    server.rpc.register("score.add", lambda payload: payload["current"] + payload["points"])

    try:
        client.send("player.spawn", {"player_id": 7, "x": 12, "y": 4})
        request_id = client.call_rpc("score.add", {"current": 100, "points": 25})
        pump(client, server)

        result = client.pop_rpc_result()
        print("rpc request:", request_id)
        print("rpc result:", result)
        print("client diagnostics:", client.diagnostics.snapshot())
        print("server diagnostics:", server.diagnostics.snapshot())
    finally:
        client.close()
        server.close()


if __name__ == "__main__":
    main()
