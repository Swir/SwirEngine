# SwirEngine 1.2 gameplay networking

SwirEngine 1.2 layers a small gameplay protocol on top of the existing framed TCP transport. The original `NetworkPacket`, `TCPPeer`, `TCPClient` and `TCPServer` APIs remain available and unchanged.

## Goals

- keep networking deterministic and compatible with the normal game update loop;
- provide named gameplay events without making creators manually encode packet shapes;
- provide explicit RPC helpers without exposing arbitrary Python functions to network input;
- expose connection/session state and deterministic counters for debugging and regression tests;
- keep the protocol transport-friendly so a future transport can feed already-decoded `NetworkPacket` objects into the same session layer.

## Gameplay messages

```python
from swirengine import GameplaySession

session = GameplaySession(peer)
session.router.on("player.spawn", lambda message: print(message.payload))
session.send("player.spawn", {"player_id": 7, "x": 14, "y": 3})

# Call once per game tick.
session.update()
```

Handlers run in registration order on the thread that calls `update()`. SwirEngine does not create a hidden networking thread.

## Explicit RPC registry

```python
session.rpc.register(
    "inventory.add",
    lambda payload: {"accepted": payload["count"] > 0},
)

request_id = session.call_rpc("inventory.add", {"item": "key", "count": 1})
session.update()
result = session.pop_rpc_result()
```

RPC lookup only uses methods explicitly registered in `RPCRegistry`. It never performs dynamic global lookup, `getattr()` traversal or import resolution based on remote data.

Unknown methods return a deterministic `RPCResult` error. Handler exceptions are converted to RPC errors on the responding side and are counted in diagnostics.

## Connection state

`GameplaySession.state` uses `ConnectionState` values:

- `DISCONNECTED`
- `CONNECTING`
- `CONNECTED`
- `CLOSING`
- `CLOSED`
- `ERROR`

Attaching an existing `TCPPeer` transitions the session to connected. `close()` is idempotent and closes the owned peer.

## Diagnostics

Each session owns `NetworkDiagnostics` with deterministic counters for:

- packets sent/received;
- gameplay messages sent/received;
- RPC requests/responses;
- RPC errors;
- unknown messages/methods;
- handler errors;
- state transitions.

`diagnostics.snapshot()` returns a plain dictionary suitable for debug overlays, test assertions and telemetry adapters.

## Frame-time behavior

The gameplay layer performs no background polling and allocates no per-frame task/thread objects. If a frame has no packets, `GameplaySession.update()` performs only the existing peer flush/poll path. Message and RPC dispatch occur only for packets that actually arrived.

This milestone does not claim an end-to-end FPS improvement. Its performance goal is predictable simulation integration and removal of creator-side ad-hoc dispatch/parsing work.
