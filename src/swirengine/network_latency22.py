from __future__ import annotations

import math
import secrets
import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass

from .networking import NetworkPacket

NETWORK_ROUND_TRIP_VERSION_22 = 1
NETWORK_ROUND_TRIP_PING_KIND_22 = "swir.network22.rtt.ping"
NETWORK_ROUND_TRIP_PONG_KIND_22 = "swir.network22.rtt.pong"

MAX_NETWORK_ROUND_TRIP_PENDING_22 = 4_096
MAX_NETWORK_ROUND_TRIP_SAMPLES_22 = 4_096
MAX_NETWORK_ROUND_TRIP_TIMEOUT_SECONDS_22 = 300.0

_MAX_SEQUENCE_22 = (1 << 63) - 1
_MIN_NONCE_LENGTH_22 = 16
_MAX_NONCE_LENGTH_22 = 64
_NONCE_CHARACTERS_22 = frozenset(
    "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_"
)
_PACKET_FIELDS_22 = frozenset({"version", "sequence", "nonce"})


class NetworkRoundTripError22(ValueError):
    """Stable failure raised for invalid or unsafe round-trip probe operations."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def _bounded_integer(value: object, label: str, *, maximum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise NetworkRoundTripError22("invalid_configuration", f"{label} must be an integer")
    if not 1 <= value <= maximum:
        raise NetworkRoundTripError22(
            "invalid_configuration",
            f"{label} must be in [1, {maximum}]",
        )
    return value


def _timeout(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise NetworkRoundTripError22(
            "invalid_configuration", "timeout_seconds must be a number"
        )
    overflow = False
    try:
        result = float(value)
    except Exception:  # noqa: BLE001 - numeric provider details stay private
        overflow = True
        result = 0.0
    if overflow:
        raise NetworkRoundTripError22(
            "invalid_configuration", "timeout_seconds is outside numeric range"
        )
    if not math.isfinite(result) or not 0.0 < result <= MAX_NETWORK_ROUND_TRIP_TIMEOUT_SECONDS_22:
        raise NetworkRoundTripError22(
            "invalid_configuration",
            "timeout_seconds must be finite and in (0, 300]",
        )
    return result


def _nonce(value: object) -> str:
    if not isinstance(value, str):
        raise NetworkRoundTripError22("invalid_packet", "round-trip nonce must be a string")
    if not _MIN_NONCE_LENGTH_22 <= len(value) <= _MAX_NONCE_LENGTH_22:
        raise NetworkRoundTripError22(
            "invalid_packet", "round-trip nonce has an invalid length"
        )
    if any(character not in _NONCE_CHARACTERS_22 for character in value):
        raise NetworkRoundTripError22(
            "invalid_packet", "round-trip nonce contains non-portable characters"
        )
    return value


def _packet_values(packet: object, *, expected_kind: str) -> tuple[int, str]:
    if not isinstance(packet, NetworkPacket):
        raise NetworkRoundTripError22(
            "invalid_packet", "round-trip message must be a NetworkPacket"
        )
    if packet.kind != expected_kind:
        raise NetworkRoundTripError22("invalid_packet", "unexpected round-trip packet kind")
    payload = packet.payload
    if set(payload) != _PACKET_FIELDS_22:
        raise NetworkRoundTripError22(
            "invalid_packet", "round-trip packet fields do not match the protocol"
        )
    version = payload["version"]
    if isinstance(version, bool) or not isinstance(version, int):
        raise NetworkRoundTripError22(
            "invalid_packet", "round-trip version must be an integer"
        )
    if version != NETWORK_ROUND_TRIP_VERSION_22:
        raise NetworkRoundTripError22(
            "unsupported_version", "round-trip packet version is not supported"
        )
    sequence = payload["sequence"]
    if (
        isinstance(sequence, bool)
        or not isinstance(sequence, int)
        or not 1 <= sequence <= _MAX_SEQUENCE_22
    ):
        raise NetworkRoundTripError22(
            "invalid_packet", "round-trip sequence is outside the supported range"
        )
    return sequence, _nonce(payload["nonce"])


def _packet(kind: str, sequence: int, nonce: str) -> NetworkPacket:
    return NetworkPacket(
        kind,
        {
            "version": NETWORK_ROUND_TRIP_VERSION_22,
            "sequence": sequence,
            "nonce": nonce,
        },
    )


@dataclass(frozen=True, slots=True)
class NetworkRoundTripSample22:
    """One privacy-safe RTT result without peer, packet or clock identifiers."""

    round_trip_ms: float

    def __post_init__(self) -> None:
        value = self.round_trip_ms
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise NetworkRoundTripError22("invalid_sample", "round_trip_ms must be a number")
        overflow = False
        try:
            normalized = float(value)
        except Exception:  # noqa: BLE001 - numeric provider details stay private
            overflow = True
            normalized = 0.0
        if overflow:
            raise NetworkRoundTripError22(
                "invalid_sample", "round_trip_ms is outside numeric range"
            )
        if not math.isfinite(normalized) or normalized < 0.0:
            raise NetworkRoundTripError22(
                "invalid_sample", "round_trip_ms must be finite and non-negative"
            )
        object.__setattr__(self, "round_trip_ms", normalized)


@dataclass(frozen=True, slots=True)
class _PendingRoundTrip22:
    nonce: str
    started_at: float


class NetworkRoundTripProbe22:
    """Bounded real RTT measurement over SwirEngine ``NetworkPacket`` messages.

    Monotonic start times stay private to this instance. The wire protocol carries only the
    minimum correlation fields needed to authenticate a pong against a pending ping, and public
    samples and diagnostics contain no nonce, sequence, peer identifier or clock timestamp.
    """

    def __init__(
        self,
        *,
        max_pending: int = 64,
        max_samples: int = 128,
        timeout_seconds: float = 10.0,
        clock: Callable[[], float] = time.monotonic,
        nonce_factory: Callable[[], str] = lambda: secrets.token_hex(16),
    ) -> None:
        self.max_pending = _bounded_integer(
            max_pending,
            "max_pending",
            maximum=MAX_NETWORK_ROUND_TRIP_PENDING_22,
        )
        self.max_samples = _bounded_integer(
            max_samples,
            "max_samples",
            maximum=MAX_NETWORK_ROUND_TRIP_SAMPLES_22,
        )
        self.timeout_seconds = _timeout(timeout_seconds)
        if not callable(clock):
            raise NetworkRoundTripError22("invalid_configuration", "clock must be callable")
        if not callable(nonce_factory):
            raise NetworkRoundTripError22(
                "invalid_configuration", "nonce_factory must be callable"
            )
        self._clock = clock
        self._nonce_factory = nonce_factory
        self._pending: dict[int, _PendingRoundTrip22] = {}
        self._samples: deque[NetworkRoundTripSample22] = deque(maxlen=self.max_samples)
        self._next_sequence = 1
        self._last_clock: float | None = None
        self._probes_started = 0
        self._probes_completed = 0
        self._probes_timed_out = 0
        self._samples_evicted = 0
        self._packets_rejected = 0
        self._capacity_rejections = 0

    @property
    def pending_count(self) -> int:
        return len(self._pending)

    @property
    def samples(self) -> tuple[NetworkRoundTripSample22, ...]:
        return tuple(self._samples)

    def _now(self) -> float:
        failure: NetworkRoundTripError22 | None = None
        raw: object | None = None
        try:
            raw = self._clock()
        except Exception:  # noqa: BLE001 - provider error text is private
            failure = NetworkRoundTripError22("invalid_clock", "monotonic clock failed")
        if failure is not None:
            raise failure
        if isinstance(raw, bool) or not isinstance(raw, (int, float)):
            raise NetworkRoundTripError22(
                "invalid_clock", "monotonic clock must return a number"
            )
        overflow = False
        try:
            current = float(raw)
        except Exception:  # noqa: BLE001 - numeric provider details stay private
            overflow = True
            current = 0.0
        if overflow:
            raise NetworkRoundTripError22(
                "invalid_clock", "monotonic clock returned a value outside numeric range"
            )
        if not math.isfinite(current) or current < 0.0:
            raise NetworkRoundTripError22(
                "invalid_clock", "monotonic clock must return a finite non-negative value"
            )
        if self._last_clock is not None and current < self._last_clock:
            raise NetworkRoundTripError22("invalid_clock", "monotonic clock moved backwards")
        self._last_clock = current
        return current

    def _expire_at(self, current: float) -> int:
        expired = tuple(
            sequence
            for sequence, pending in self._pending.items()
            if current - pending.started_at >= self.timeout_seconds
        )
        for sequence in expired:
            del self._pending[sequence]
        self._probes_timed_out += len(expired)
        return len(expired)

    def create_ping(self) -> NetworkPacket:
        """Start a measurement and return its bounded ping packet."""

        current = self._now()
        self._expire_at(current)
        if len(self._pending) >= self.max_pending:
            self._capacity_rejections += 1
            raise NetworkRoundTripError22(
                "pending_limit", "round-trip pending probe limit reached"
            )
        if self._next_sequence > _MAX_SEQUENCE_22:
            raise NetworkRoundTripError22(
                "sequence_exhausted", "round-trip sequence space is exhausted"
            )
        failure: NetworkRoundTripError22 | None = None
        raw_nonce: object | None = None
        try:
            raw_nonce = self._nonce_factory()
        except Exception:  # noqa: BLE001 - provider error text is private
            failure = NetworkRoundTripError22(
                "invalid_nonce", "round-trip nonce generation failed"
            )
        if failure is not None:
            raise failure
        invalid_nonce = False
        try:
            nonce = _nonce(raw_nonce)
        except Exception:  # noqa: BLE001 - nonce provider details stay private
            invalid_nonce = True
            nonce = ""
        if invalid_nonce:
            raise NetworkRoundTripError22(
                "invalid_nonce", "round-trip nonce generation returned invalid data"
            )
        if any(pending.nonce == nonce for pending in self._pending.values()):
            raise NetworkRoundTripError22(
                "invalid_nonce", "round-trip nonce generation returned a duplicate"
            )
        sequence = self._next_sequence
        self._next_sequence += 1
        self._pending[sequence] = _PendingRoundTrip22(nonce, current)
        self._probes_started += 1
        return _packet(NETWORK_ROUND_TRIP_PING_KIND_22, sequence, nonce)

    @staticmethod
    def reply_to_ping(packet: NetworkPacket) -> NetworkPacket:
        """Validate a ping and return the matching pong without adding private state."""

        sequence, nonce = _packet_values(
            packet,
            expected_kind=NETWORK_ROUND_TRIP_PING_KIND_22,
        )
        return _packet(NETWORK_ROUND_TRIP_PONG_KIND_22, sequence, nonce)

    def accept_pong(self, packet: NetworkPacket) -> NetworkRoundTripSample22:
        """Validate a pong, close its pending probe and record the measured RTT."""

        try:
            sequence, nonce = _packet_values(
                packet,
                expected_kind=NETWORK_ROUND_TRIP_PONG_KIND_22,
            )
        except NetworkRoundTripError22:
            self._packets_rejected += 1
            raise
        pending = self._pending.get(sequence)
        if pending is None:
            self._packets_rejected += 1
            raise NetworkRoundTripError22(
                "unknown_probe", "pong does not match a pending round-trip probe"
            )
        if not secrets.compare_digest(pending.nonce, nonce):
            self._packets_rejected += 1
            raise NetworkRoundTripError22(
                "probe_mismatch", "pong does not match a pending round-trip probe"
            )
        current = self._now()
        elapsed = current - pending.started_at
        if elapsed >= self.timeout_seconds:
            del self._pending[sequence]
            self._probes_timed_out += 1
            self._packets_rejected += 1
            raise NetworkRoundTripError22("probe_timeout", "round-trip probe timed out")
        del self._pending[sequence]
        sample = NetworkRoundTripSample22(elapsed * 1_000.0)
        if len(self._samples) == self.max_samples:
            self._samples_evicted += 1
        self._samples.append(sample)
        self._probes_completed += 1
        return sample

    def expire(self) -> int:
        """Expire overdue probes and return the number removed."""

        return self._expire_at(self._now())

    def diagnostics(self) -> dict[str, int | float | None]:
        """Return bounded aggregate data without correlation or clock identifiers."""

        values = tuple(sample.round_trip_ms for sample in self._samples)
        return {
            "pending": len(self._pending),
            "pending_limit": self.max_pending,
            "samples_retained": len(values),
            "sample_limit": self.max_samples,
            "probes_started": self._probes_started,
            "probes_completed": self._probes_completed,
            "probes_timed_out": self._probes_timed_out,
            "samples_evicted": self._samples_evicted,
            "packets_rejected": self._packets_rejected,
            "capacity_rejections": self._capacity_rejections,
            "minimum_ms": min(values) if values else None,
            "maximum_ms": max(values) if values else None,
            "average_ms": sum(values) / len(values) if values else None,
            "latest_ms": values[-1] if values else None,
        }


__all__ = [
    "MAX_NETWORK_ROUND_TRIP_PENDING_22",
    "MAX_NETWORK_ROUND_TRIP_SAMPLES_22",
    "MAX_NETWORK_ROUND_TRIP_TIMEOUT_SECONDS_22",
    "NETWORK_ROUND_TRIP_PING_KIND_22",
    "NETWORK_ROUND_TRIP_PONG_KIND_22",
    "NETWORK_ROUND_TRIP_VERSION_22",
    "NetworkRoundTripError22",
    "NetworkRoundTripProbe22",
    "NetworkRoundTripSample22",
]
