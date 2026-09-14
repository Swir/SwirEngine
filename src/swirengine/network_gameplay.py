from __future__ import annotations

from collections import deque
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from .networking import NetworkPacket, TCPPeer

Payload = dict[str, Any]
MessageHandler = Callable[["GameplayMessage"], None]
RPCHandler = Callable[[Payload], Any]


class RPCError(Exception):
    """Expected gameplay RPC failure that is safe to return to the remote caller."""


class ConnectionState(str, Enum):
    """High-level lifecycle state for a gameplay network session."""

    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    CLOSING = "closing"
    CLOSED = "closed"
    ERROR = "error"


class MessageKind(str, Enum):
    """Built-in packet kinds used by :class:`GameplaySession`."""

    EVENT = "swir.event"
    RPC_REQUEST = "swir.rpc.request"
    RPC_RESPONSE = "swir.rpc.response"
    RPC_ERROR = "swir.rpc.error"


@dataclass(slots=True, frozen=True)
class GameplayMessage:
    """Creator-facing gameplay message independent from the TCP framing layer."""

    name: str
    payload: Payload = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("message name must not be empty")
        if not isinstance(self.payload, dict):
            raise TypeError("message payload must be a dictionary")

    def to_packet(self) -> NetworkPacket:
        return NetworkPacket(
            MessageKind.EVENT,
            {"name": self.name, "payload": self.payload},
        )

    @classmethod
    def from_packet(cls, packet: NetworkPacket) -> GameplayMessage:
        if packet.kind != MessageKind.EVENT:
            raise ValueError(f"packet kind {packet.kind!r} is not a gameplay event")
        name = packet.payload.get("name")
        payload = packet.payload.get("payload", {})
        if not isinstance(name, str) or not isinstance(payload, dict):
            raise TypeError("gameplay event requires string name and object payload")
        return cls(name=name, payload=payload)


@dataclass(slots=True, frozen=True)
class RPCResult:
    request_id: int
    method: str
    value: Any = None
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.error is None


@dataclass(slots=True)
class NetworkDiagnostics:
    """Deterministic counters for creator tooling and regression tests."""

    sent_packets: int = 0
    received_packets: int = 0
    sent_messages: int = 0
    received_messages: int = 0
    rpc_requests_sent: int = 0
    rpc_requests_received: int = 0
    rpc_responses_sent: int = 0
    rpc_responses_received: int = 0
    rpc_errors: int = 0
    unknown_messages: int = 0
    unknown_rpc_methods: int = 0
    handler_errors: int = 0
    state_transitions: int = 0

    def snapshot(self) -> dict[str, int]:
        return {
            "sent_packets": self.sent_packets,
            "received_packets": self.received_packets,
            "sent_messages": self.sent_messages,
            "received_messages": self.received_messages,
            "rpc_requests_sent": self.rpc_requests_sent,
            "rpc_requests_received": self.rpc_requests_received,
            "rpc_responses_sent": self.rpc_responses_sent,
            "rpc_responses_received": self.rpc_responses_received,
            "rpc_errors": self.rpc_errors,
            "unknown_messages": self.unknown_messages,
            "unknown_rpc_methods": self.unknown_rpc_methods,
            "handler_errors": self.handler_errors,
            "state_transitions": self.state_transitions,
        }


class MessageRouter:
    """Name-based event router with stable insertion-order dispatch."""

    def __init__(self) -> None:
        self._handlers: dict[str, list[MessageHandler]] = {}

    def on(self, name: str, handler: MessageHandler) -> MessageHandler:
        key = name.strip()
        if not key:
            raise ValueError("message name must not be empty")
        self._handlers.setdefault(key, []).append(handler)
        return handler

    def off(self, name: str, handler: MessageHandler) -> bool:
        handlers = self._handlers.get(name)
        if not handlers:
            return False
        try:
            handlers.remove(handler)
        except ValueError:
            return False
        if not handlers:
            del self._handlers[name]
        return True

    def dispatch(self, message: GameplayMessage) -> int:
        handlers = tuple(self._handlers.get(message.name, ()))
        for handler in handlers:
            handler(message)
        return len(handlers)


class RPCRegistry:
    """Explicit registry for gameplay RPC methods.

    RPC names are never resolved through globals or attribute lookup. This keeps the public surface
    auditable and prevents network input from selecting arbitrary Python callables.
    """

    def __init__(self) -> None:
        self._methods: dict[str, RPCHandler] = {}

    def register(self, name: str, handler: RPCHandler) -> RPCHandler:
        key = name.strip()
        if not key:
            raise ValueError("RPC method name must not be empty")
        if key in self._methods:
            raise ValueError(f"RPC method already registered: {key}")
        self._methods[key] = handler
        return handler

    def unregister(self, name: str) -> bool:
        return self._methods.pop(name, None) is not None

    def call(self, name: str, payload: Payload) -> Any:
        try:
            handler = self._methods[name]
        except KeyError as exc:
            raise KeyError(f"unknown RPC method: {name}") from exc
        return handler(payload)

    def __contains__(self, name: object) -> bool:
        return name in self._methods


class GameplaySession:
    """Polling gameplay protocol layered over the existing 1.x :class:`TCPPeer`.

    The class is intentionally thread-free. ``update()`` can be called once per game tick, keeping
    dispatch order deterministic and avoiding callback races with the main simulation loop.
    """

    def __init__(
        self,
        peer: TCPPeer | None = None,
        *,
        router: MessageRouter | None = None,
        rpc: RPCRegistry | None = None,
        completed_rpc_limit: int = 256,
    ) -> None:
        self.peer = peer
        self.router = router or MessageRouter()
        self.rpc = rpc or RPCRegistry()
        self.diagnostics = NetworkDiagnostics()
        self.state = ConnectionState.CONNECTED if peer is not None else ConnectionState.DISCONNECTED
        self.last_error: str | None = None
        self._next_request_id = 1
        self._pending_rpc: dict[int, str] = {}
        self._completed_rpc: deque[RPCResult] = deque(maxlen=max(1, int(completed_rpc_limit)))

    @property
    def connected(self) -> bool:
        return self.state == ConnectionState.CONNECTED and self.peer is not None and not self.peer.closed

    @property
    def pending_rpc_count(self) -> int:
        return len(self._pending_rpc)

    def attach(self, peer: TCPPeer) -> None:
        if self.connected:
            raise RuntimeError("session already has a connected peer")
        self.peer = peer
        self.last_error = None
        self._set_state(ConnectionState.CONNECTED)

    def close(self) -> None:
        if self.state in {ConnectionState.CLOSED, ConnectionState.DISCONNECTED}:
            self._set_state(ConnectionState.CLOSED)
            return
        self._set_state(ConnectionState.CLOSING)
        if self.peer is not None:
            self.peer.close()
        self.peer = None
        self._set_state(ConnectionState.CLOSED)

    def send(self, name: str, payload: Mapping[str, Any] | None = None) -> None:
        message = GameplayMessage(name, dict(payload or {}))
        self._queue_packet(message.to_packet())
        self.diagnostics.sent_messages += 1

    def call_rpc(self, method: str, payload: Mapping[str, Any] | None = None) -> int:
        if not method.strip():
            raise ValueError("RPC method name must not be empty")
        request_id = self._next_request_id
        self._next_request_id += 1
        self._pending_rpc[request_id] = method
        self._queue_packet(
            NetworkPacket(
                MessageKind.RPC_REQUEST,
                {"id": request_id, "method": method, "payload": dict(payload or {})},
            )
        )
        self.diagnostics.rpc_requests_sent += 1
        return request_id

    def pop_rpc_result(self) -> RPCResult | None:
        if not self._completed_rpc:
            return None
        return self._completed_rpc.popleft()

    def update(self) -> int:
        if self.peer is None:
            return 0
        if self.peer.closed:
            self.peer = None
            self._set_state(ConnectionState.CLOSED)
            return 0
        try:
            self.peer.flush()
            packets = self.peer.poll()
            for packet in packets:
                self._handle_packet(packet)
            if self.peer.closed:
                self.peer = None
                self._set_state(ConnectionState.CLOSED)
            return len(packets)
        except Exception as exc:
            self.last_error = f"{type(exc).__name__}: {exc}"
            self._set_state(ConnectionState.ERROR)
            raise

    def handle_packet(self, packet: NetworkPacket) -> None:
        """Handle one already-decoded packet, useful for custom transports and tests."""

        self._handle_packet(packet)

    def _queue_packet(self, packet: NetworkPacket) -> None:
        if not self.connected or self.peer is None:
            raise RuntimeError("session is not connected")
        self.peer.queue(packet)
        self.diagnostics.sent_packets += 1

    def _handle_packet(self, packet: NetworkPacket) -> None:
        self.diagnostics.received_packets += 1
        if packet.kind == MessageKind.EVENT:
            self._handle_event(packet)
        elif packet.kind == MessageKind.RPC_REQUEST:
            self._handle_rpc_request(packet)
        elif packet.kind in {MessageKind.RPC_RESPONSE, MessageKind.RPC_ERROR}:
            self._handle_rpc_result(packet)

    def _handle_event(self, packet: NetworkPacket) -> None:
        message = GameplayMessage.from_packet(packet)
        self.diagnostics.received_messages += 1
        try:
            handled = self.router.dispatch(message)
        except Exception:
            self.diagnostics.handler_errors += 1
            raise
        if handled == 0:
            self.diagnostics.unknown_messages += 1

    def _handle_rpc_request(self, packet: NetworkPacket) -> None:
        request_id = packet.payload.get("id")
        method = packet.payload.get("method")
        payload = packet.payload.get("payload", {})
        if not isinstance(request_id, int) or request_id < 1:
            raise TypeError("RPC request requires a positive integer id")
        if not isinstance(method, str) or not isinstance(payload, dict):
            raise TypeError("RPC request requires string method and object payload")
        self.diagnostics.rpc_requests_received += 1
        if method not in self.rpc:
            self.diagnostics.unknown_rpc_methods += 1
            self._send_rpc_error(request_id, method, f"unknown RPC method: {method}")
            return
        try:
            value = self.rpc.call(method, payload)
        except RPCError as exc:
            self.diagnostics.handler_errors += 1
            self._send_rpc_error(request_id, method, str(exc))
            return
        self._queue_packet(
            NetworkPacket(
                MessageKind.RPC_RESPONSE,
                {"id": request_id, "method": method, "value": value},
            )
        )
        self.diagnostics.rpc_responses_sent += 1

    def _send_rpc_error(self, request_id: int, method: str, error: str) -> None:
        self._queue_packet(
            NetworkPacket(
                MessageKind.RPC_ERROR,
                {"id": request_id, "method": method, "error": error},
            )
        )
        self.diagnostics.rpc_errors += 1

    def _handle_rpc_result(self, packet: NetworkPacket) -> None:
        request_id = packet.payload.get("id")
        method = packet.payload.get("method")
        if not isinstance(request_id, int) or not isinstance(method, str):
            raise TypeError("RPC result requires integer id and string method")
        expected_method = self._pending_rpc.pop(request_id, None)
        if expected_method is None:
            return
        if expected_method != method:
            self.diagnostics.rpc_errors += 1
            self._completed_rpc.append(
                RPCResult(request_id, expected_method, error="RPC response method mismatch")
            )
            return
        if packet.kind == MessageKind.RPC_ERROR:
            error = packet.payload.get("error")
            if not isinstance(error, str):
                raise TypeError("RPC error response requires string error")
            self.diagnostics.rpc_errors += 1
            self._completed_rpc.append(RPCResult(request_id, method, error=error))
        else:
            self.diagnostics.rpc_responses_received += 1
            self._completed_rpc.append(RPCResult(request_id, method, value=packet.payload.get("value")))

    def _set_state(self, state: ConnectionState) -> None:
        if state != self.state:
            self.state = state
            self.diagnostics.state_transitions += 1
