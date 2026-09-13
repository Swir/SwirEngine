from __future__ import annotations

import json
import socket
import struct
from dataclasses import dataclass
from typing import Any

_HEADER = struct.Struct("!I")
_DEFAULT_MAX_PACKET = 1024 * 1024


@dataclass(slots=True, frozen=True)
class NetworkPacket:
    """Small JSON-compatible message used by the built-in TCP transport."""

    kind: str
    payload: dict[str, Any]

    def __post_init__(self) -> None:
        if not self.kind.strip():
            raise ValueError("packet kind must not be empty")
        if not isinstance(self.payload, dict):
            raise TypeError("packet payload must be a dictionary")

    def to_bytes(self) -> bytes:
        body = json.dumps(
            {"kind": self.kind, "payload": self.payload},
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
        return _HEADER.pack(len(body)) + body

    @classmethod
    def from_body(cls, body: bytes) -> NetworkPacket:
        decoded = json.loads(body.decode("utf-8"))
        if not isinstance(decoded, dict):
            raise TypeError("network packet must decode to an object")
        kind = decoded.get("kind")
        payload = decoded.get("payload")
        if not isinstance(kind, str) or not isinstance(payload, dict):
            raise TypeError("network packet requires string kind and object payload")
        return cls(kind=kind, payload=payload)


class PacketStreamDecoder:
    """Incrementally decode length-prefixed packets from arbitrary TCP chunks."""

    def __init__(self, *, max_packet_size: int = _DEFAULT_MAX_PACKET) -> None:
        self.max_packet_size = max(1, int(max_packet_size))
        self._buffer = bytearray()

    @property
    def buffered_bytes(self) -> int:
        return len(self._buffer)

    def reset(self) -> None:
        self._buffer.clear()

    def feed(self, data: bytes | bytearray | memoryview) -> tuple[NetworkPacket, ...]:
        self._buffer.extend(data)
        packets: list[NetworkPacket] = []
        while len(self._buffer) >= _HEADER.size:
            (size,) = _HEADER.unpack_from(self._buffer)
            if size > self.max_packet_size:
                self.reset()
                raise ValueError(
                    f"network packet size {size} exceeds limit {self.max_packet_size}"
                )
            total = _HEADER.size + size
            if len(self._buffer) < total:
                break
            body = bytes(self._buffer[_HEADER.size:total])
            del self._buffer[:total]
            packets.append(NetworkPacket.from_body(body))
        return tuple(packets)


@dataclass(slots=True, frozen=True)
class NetworkAddress:
    host: str = "127.0.0.1"
    port: int = 7777

    def __post_init__(self) -> None:
        if not self.host.strip():
            raise ValueError("host must not be empty")
        if not 1 <= int(self.port) <= 65535:
            raise ValueError("port must be between 1 and 65535")

    @property
    def tuple(self) -> tuple[str, int]:
        return self.host, int(self.port)


class TCPPeer:
    """Non-blocking TCP peer with framed JSON packet send/receive helpers.

    The peer intentionally exposes polling rather than creating background threads. This keeps
    networking deterministic and easy to integrate into SwirEngine's normal update loop.
    """

    def __init__(
        self,
        sock: socket.socket,
        *,
        max_packet_size: int = _DEFAULT_MAX_PACKET,
    ) -> None:
        self.socket = sock
        self.socket.setblocking(False)
        self.decoder = PacketStreamDecoder(max_packet_size=max_packet_size)
        self._send_buffer = bytearray()
        self.closed = False

    @property
    def pending_send_bytes(self) -> int:
        return len(self._send_buffer)

    def queue(self, packet: NetworkPacket) -> None:
        if self.closed:
            raise RuntimeError("peer is closed")
        encoded = packet.to_bytes()
        if len(encoded) - _HEADER.size > self.decoder.max_packet_size:
            raise ValueError("packet exceeds configured maximum size")
        self._send_buffer.extend(encoded)

    def flush(self) -> int:
        if self.closed or not self._send_buffer:
            return 0
        try:
            sent = self.socket.send(self._send_buffer)
        except (BlockingIOError, InterruptedError):
            return 0
        if sent == 0:
            self.close()
            return 0
        del self._send_buffer[:sent]
        return sent

    def poll(self, *, chunk_size: int = 65536) -> tuple[NetworkPacket, ...]:
        if self.closed:
            return ()
        packets: list[NetworkPacket] = []
        while True:
            try:
                chunk = self.socket.recv(max(1, int(chunk_size)))
            except (BlockingIOError, InterruptedError):
                break
            if not chunk:
                self.close()
                break
            packets.extend(self.decoder.feed(chunk))
            if len(chunk) < chunk_size:
                break
        return tuple(packets)

    def close(self) -> None:
        if self.closed:
            return
        self.closed = True
        try:
            self.socket.close()
        finally:
            self.decoder.reset()
            self._send_buffer.clear()


class TCPClient:
    """Creator-facing TCP client that returns a :class:`TCPPeer`."""

    @staticmethod
    def connect(
        address: NetworkAddress,
        *,
        timeout: float = 5.0,
        max_packet_size: int = _DEFAULT_MAX_PACKET,
    ) -> TCPPeer:
        sock = socket.create_connection(address.tuple, timeout=max(0.01, float(timeout)))
        return TCPPeer(sock, max_packet_size=max_packet_size)


class TCPServer:
    """Small non-blocking TCP listener suitable for polling from a game loop."""

    def __init__(
        self,
        address: NetworkAddress | None = None,
        *,
        backlog: int = 16,
        max_packet_size: int = _DEFAULT_MAX_PACKET,
    ) -> None:
        self.address = address or NetworkAddress()
        self.backlog = max(1, int(backlog))
        self.max_packet_size = max(1, int(max_packet_size))
        self.socket: socket.socket | None = None

    @property
    def running(self) -> bool:
        return self.socket is not None

    def start(self) -> NetworkAddress:
        if self.socket is not None:
            raise RuntimeError("server is already running")
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind(self.address.tuple)
        sock.listen(self.backlog)
        sock.setblocking(False)
        self.socket = sock
        host, port = sock.getsockname()[:2]
        return NetworkAddress(str(host), int(port))

    def accept(self) -> tuple[TCPPeer, NetworkAddress] | None:
        if self.socket is None:
            raise RuntimeError("server is not running")
        try:
            client, remote = self.socket.accept()
        except (BlockingIOError, InterruptedError):
            return None
        return (
            TCPPeer(client, max_packet_size=self.max_packet_size),
            NetworkAddress(str(remote[0]), int(remote[1])),
        )

    def close(self) -> None:
        if self.socket is None:
            return
        self.socket.close()
        self.socket = None
