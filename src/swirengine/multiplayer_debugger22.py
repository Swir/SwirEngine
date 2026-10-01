from __future__ import annotations

import hashlib
import json
import math
from collections import deque
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Protocol

from .multiplayer20 import ProductionMultiplayerSession
from .network_profiler16 import (
    MultiplayerNetworkProfiler,
    NetworkProfileEvent,
    NetworkProfileSample,
)
from .transport16 import (
    ChannelPolicy,
    DeliveryPolicy,
    TransportQoSReceiver,
    TransportQoSScheduler,
    _InboundCounters,
    _OutboundCounters,
)

MULTIPLAYER_DEBUG_CAPTURE_FORMAT_22 = "swir.multiplayer-debugger"
MULTIPLAYER_DEBUG_CAPTURE_VERSION_22 = 1
MAX_MULTIPLAYER_DEBUG_CAPTURE_BYTES_22 = 2 * 1024 * 1024

_MAX_CLIENTS_22 = 64
_MAX_CHANNELS_22 = 64
_MAX_COUNTERS_PER_SAMPLE_22 = 128
_MAX_SAMPLES_PER_CLIENT_22 = 256
_MAX_EVENTS_22 = 1024
_MIN_CAPTURE_BYTES_22 = 4096
_MAX_NUMBER_22 = 1_000_000_000_000_000
_MAX_SOURCE_COUNTERS_PER_SAMPLE_22 = 2_048
_MAX_SOURCE_COUNTERS_TOTAL_22 = 262_144
_CAPTURE_TRIM_HEADROOM_BYTES_22 = 128

_REPLICATION_COUNTERS_22 = frozenset(
    {
        "replication.acknowledgements",
        "replication.delta_updates",
        "replication.full_entities",
        "replication.full_updates",
        "replication.removed_entities",
        "replication.snapshot_fallbacks",
        "replication.upserted_entities",
    }
)
_SESSION_COUNTERS_22 = frozenset(
    {
        "session.active_resume_tokens",
        "session.connected_members",
        "session.event_evictions",
        "session.events_emitted",
        "session.failures_total",
        "session.members",
        "session.ready_members",
        "session.retained_events",
        "session.revision",
        "session.successful_mutations",
        "session.token_evictions",
    }
)
_TRAFFIC_COUNTERS_22 = frozenset(
    {
        "traffic.entity_budget",
        "traffic.entity_budget_ratio",
        "traffic.received_bytes",
        "traffic.replicated_entities",
        "traffic.sent_bytes",
    }
)
_TRANSPORT_TOTAL_COUNTERS_22 = frozenset(
    {
        "transport_outbound.queued_bytes",
        "transport_outbound.queued_packets",
    }
)
_OUTBOUND_CHANNEL_COUNTERS_22 = frozenset(
    {
        "backpressure_rejections",
        "dropped_bytes",
        "dropped_packets",
        "emitted_bytes",
        "emitted_packets",
        "enqueued_bytes",
        "enqueued_packets",
        "next_sequence",
        "oversized_rejections",
        "queued_bytes",
        "queued_packets",
    }
)
_INBOUND_CHANNEL_COUNTERS_22 = frozenset(
    {
        "accepted_packets",
        "duplicate_packets",
        "gap_events",
        "last_sequence",
        "oversized_rejections",
        "policy_mismatches",
        "skipped_sequences",
        "stale_packets",
    }
)
_SAFE_DIRECT_COUNTERS_22 = (
    _REPLICATION_COUNTERS_22
    | _SESSION_COUNTERS_22
    | _TRAFFIC_COUNTERS_22
    | _TRANSPORT_TOTAL_COUNTERS_22
)
_ROUND_TRIP_INTEGER_FIELDS_22 = (
    "pending",
    "pending_limit",
    "samples_retained",
    "sample_limit",
    "probes_started",
    "probes_completed",
    "probes_timed_out",
    "samples_evicted",
    "packets_rejected",
    "capacity_rejections",
)
_ROUND_TRIP_FLOAT_FIELDS_22 = (
    "minimum_ms",
    "maximum_ms",
    "average_ms",
    "latest_ms",
)


class RoundTripProbeSource22(Protocol):
    @property
    def samples(self) -> tuple[object, ...]: ...

    def diagnostics(self) -> Mapping[str, object]: ...


@dataclass(slots=True, frozen=True)
class _TransportDiagnosticsSnapshot22:
    """Small trusted adapter for the older profiler diagnostics protocol."""

    payload: dict[str, Any]

    def diagnostics(self) -> Mapping[str, Any]:
        return self.payload


class MultiplayerDebuggerError22(RuntimeError):
    """Stable debugger failure that never embeds source identifiers or provider errors."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


_PUBLIC_ERROR_CODES_22 = frozenset(
    {
        "capture_failed",
        "capture_limit_too_small",
        "client_limit_reached",
        "client_unavailable",
        "diagnostic_source_limit",
        "diagnostic_source_unavailable",
        "sample_failed",
        "snapshot_failed",
    }
)


def _sanitized_failure(
    exc: Exception,
    *,
    fallback_code: str,
    message: str,
) -> MultiplayerDebuggerError22:
    code = fallback_code
    if (
        type(exc) is MultiplayerDebuggerError22
        and type(exc.code) is str
        and exc.code in _PUBLIC_ERROR_CODES_22
    ):
        code = exc.code
    return MultiplayerDebuggerError22(code, message)


def _transport_source_unavailable() -> MultiplayerDebuggerError22:
    return MultiplayerDebuggerError22(
        "diagnostic_source_unavailable",
        "transport diagnostic source is unavailable",
    )


def _transport_source_limit() -> MultiplayerDebuggerError22:
    return MultiplayerDebuggerError22(
        "diagnostic_source_limit",
        "transport diagnostics exceed the debugger safety limit",
    )


def _transport_state_mapping(source: object, name: str) -> dict[str, Any]:
    value: object | None = None
    failure: MultiplayerDebuggerError22 | None = None
    try:
        value = object.__getattribute__(source, name)
    except Exception:  # noqa: BLE001 - provider state errors are private
        failure = _transport_source_unavailable()
    if failure is not None:
        raise failure
    if type(value) is not dict:
        raise _transport_source_unavailable()
    if len(value) > _MAX_CHANNELS_22:
        raise _transport_source_limit()
    for channel in value:
        if type(channel) is not str or not channel or len(channel) > 96:
            raise _transport_source_unavailable()
    return value


def _matching_channel_state(
    policies: dict[str, Any],
    *states: dict[str, Any],
) -> tuple[str, ...]:
    channels = tuple(sorted(policies))
    for state in states:
        if tuple(sorted(state)) != channels:
            raise _transport_source_unavailable()
    return channels


def _transport_counter(value: object, *, minimum: int = 0) -> int:
    if type(value) is not int:
        raise _transport_source_unavailable()
    if value < minimum or value > _MAX_NUMBER_22:
        raise _transport_source_limit()
    return value


def _transport_policy(value: object, channel: str) -> ChannelPolicy:
    if type(value) is not ChannelPolicy:
        raise _transport_source_unavailable()
    if value.name != channel or type(value.delivery) is not DeliveryPolicy:
        raise _transport_source_unavailable()
    if type(value.priority) is not int or not -1000 <= value.priority <= 1000:
        raise _transport_source_unavailable()
    return value


def _outbound_transport_snapshot(
    source: TransportQoSScheduler,
) -> _TransportDiagnosticsSnapshot22:
    policies = _transport_state_mapping(source, "_policies")
    queues = _transport_state_mapping(source, "_queues")
    queue_bytes = _transport_state_mapping(source, "_queue_bytes")
    next_sequence = _transport_state_mapping(source, "_next_sequence")
    counters = _transport_state_mapping(source, "_counters")
    channels = _matching_channel_state(
        policies,
        queues,
        queue_bytes,
        next_sequence,
        counters,
    )

    payload_channels: dict[str, Any] = {}
    queued_packets_total = 0
    queued_bytes_total = 0
    for channel in channels:
        policy = _transport_policy(policies[channel], channel)
        queue = queues[channel]
        counter = counters[channel]
        if type(queue) is not deque or type(counter) is not _OutboundCounters:
            raise _transport_source_unavailable()
        queued_packets = _transport_counter(len(queue))
        channel_queued_bytes = _transport_counter(queue_bytes[channel])
        queued_packets_total += queued_packets
        queued_bytes_total += channel_queued_bytes
        if (
            queued_packets_total > _MAX_NUMBER_22
            or queued_bytes_total > _MAX_NUMBER_22
        ):
            raise _transport_source_limit()
        payload_channels[channel] = {
            "delivery": policy.delivery.value,
            "priority": policy.priority,
            "queued_packets": queued_packets,
            "queued_bytes": channel_queued_bytes,
            "enqueued_packets": _transport_counter(counter.enqueued_packets),
            "enqueued_bytes": _transport_counter(counter.enqueued_bytes),
            "emitted_packets": _transport_counter(counter.emitted_packets),
            "emitted_bytes": _transport_counter(counter.emitted_bytes),
            "dropped_packets": _transport_counter(counter.dropped_packets),
            "dropped_bytes": _transport_counter(counter.dropped_bytes),
            "backpressure_rejections": _transport_counter(
                counter.backpressure_rejections
            ),
            "oversized_rejections": _transport_counter(counter.oversized_rejections),
            "next_sequence": _transport_counter(next_sequence[channel], minimum=1),
        }
    return _TransportDiagnosticsSnapshot22(
        {
            "queued_packets": queued_packets_total,
            "queued_bytes": queued_bytes_total,
            "channels": payload_channels,
        }
    )


def _inbound_transport_snapshot(
    source: TransportQoSReceiver,
) -> _TransportDiagnosticsSnapshot22:
    policies = _transport_state_mapping(source, "_policies")
    last_sequence = _transport_state_mapping(source, "_last_sequence")
    counters = _transport_state_mapping(source, "_counters")
    channels = _matching_channel_state(policies, last_sequence, counters)

    payload_channels: dict[str, Any] = {}
    for channel in channels:
        policy = _transport_policy(policies[channel], channel)
        counter = counters[channel]
        if type(counter) is not _InboundCounters:
            raise _transport_source_unavailable()
        payload_channels[channel] = {
            "delivery": policy.delivery.value,
            "last_sequence": _transport_counter(last_sequence[channel]),
            "accepted_packets": _transport_counter(counter.accepted_packets),
            "duplicate_packets": _transport_counter(counter.duplicate_packets),
            "stale_packets": _transport_counter(counter.stale_packets),
            "gap_events": _transport_counter(counter.gap_events),
            "skipped_sequences": _transport_counter(counter.skipped_sequences),
            "policy_mismatches": _transport_counter(counter.policy_mismatches),
            "oversized_rejections": _transport_counter(counter.oversized_rejections),
        }
    return _TransportDiagnosticsSnapshot22({"channels": payload_channels})


def _bounded_int(value: object, label: str, *, minimum: int, maximum: int) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise TypeError(f"{label} must be an integer")
    if not minimum <= value <= maximum:
        raise ValueError(f"{label} must be between {minimum} and {maximum}")
    return value


def _client_id(value: object) -> str:
    if not isinstance(value, str):
        raise TypeError("client_id must be a string")
    normalized = value.strip()
    if not normalized:
        raise ValueError("client_id must not be empty")
    if len(normalized) > 128:
        raise ValueError("client_id must not exceed 128 characters")
    return normalized


def _safe_number(value: object) -> int | float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if value > _MAX_NUMBER_22:
        return _MAX_NUMBER_22
    if value < -_MAX_NUMBER_22:
        return -_MAX_NUMBER_22
    return value


@dataclass(slots=True, frozen=True)
class MultiplayerDebuggerLimits22:
    max_clients: int = 32
    max_channels: int = 16
    max_counters_per_sample: int = 64
    max_samples_per_client: int = 64
    max_events: int = 256
    max_capture_bytes: int = MAX_MULTIPLAYER_DEBUG_CAPTURE_BYTES_22

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "max_clients",
            _bounded_int(self.max_clients, "max_clients", minimum=1, maximum=_MAX_CLIENTS_22),
        )
        object.__setattr__(
            self,
            "max_channels",
            _bounded_int(self.max_channels, "max_channels", minimum=1, maximum=_MAX_CHANNELS_22),
        )
        object.__setattr__(
            self,
            "max_counters_per_sample",
            _bounded_int(
                self.max_counters_per_sample,
                "max_counters_per_sample",
                minimum=1,
                maximum=_MAX_COUNTERS_PER_SAMPLE_22,
            ),
        )
        object.__setattr__(
            self,
            "max_samples_per_client",
            _bounded_int(
                self.max_samples_per_client,
                "max_samples_per_client",
                minimum=1,
                maximum=_MAX_SAMPLES_PER_CLIENT_22,
            ),
        )
        object.__setattr__(
            self,
            "max_events",
            _bounded_int(self.max_events, "max_events", minimum=1, maximum=_MAX_EVENTS_22),
        )
        object.__setattr__(
            self,
            "max_capture_bytes",
            _bounded_int(
                self.max_capture_bytes,
                "max_capture_bytes",
                minimum=_MIN_CAPTURE_BYTES_22,
                maximum=MAX_MULTIPLAYER_DEBUG_CAPTURE_BYTES_22,
            ),
        )

    def portable(self) -> dict[str, int]:
        return {
            "max_clients": self.max_clients,
            "max_channels": self.max_channels,
            "max_counters_per_sample": self.max_counters_per_sample,
            "max_samples_per_client": self.max_samples_per_client,
            "max_events": self.max_events,
            "max_capture_bytes": self.max_capture_bytes,
        }


def _channel_counter(key: str) -> tuple[str, str, str] | None:
    for direction, allowed in (
        ("outbound", _OUTBOUND_CHANNEL_COUNTERS_22),
        ("inbound", _INBOUND_CHANNEL_COUNTERS_22),
    ):
        prefix = f"transport_{direction}.channels."
        if not key.startswith(prefix):
            continue
        remainder = key[len(prefix) :]
        if "." not in remainder:
            return None
        channel, metric = remainder.rsplit(".", 1)
        if channel and metric in allowed:
            return direction, channel, metric
        return None
    return None


def _canonical_bytes(payload: Mapping[str, Any]) -> bytes:
    return json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("ascii")


class MultiplayerDebugger22:
    """Privacy-safe diagnostics facade over the production multiplayer runtime.

    Raw client identifiers are used only to query the existing production session and profiler.
    Returned snapshots contain stable peer/channel aliases, bounded numeric aggregates and no
    gameplay state, payloads, tokens, addresses, paths, event text or exception text.
    """

    def __init__(
        self,
        session: ProductionMultiplayerSession,
        profiler: MultiplayerNetworkProfiler | None = None,
        *,
        limits: MultiplayerDebuggerLimits22 | None = None,
    ) -> None:
        if not isinstance(session, ProductionMultiplayerSession):
            raise TypeError("session must be a ProductionMultiplayerSession")
        if profiler is not None and not isinstance(profiler, MultiplayerNetworkProfiler):
            raise TypeError("profiler must be a MultiplayerNetworkProfiler")
        if limits is not None and not isinstance(limits, MultiplayerDebuggerLimits22):
            raise TypeError("limits must be MultiplayerDebuggerLimits22")
        self._session = session
        self.limits = limits or MultiplayerDebuggerLimits22()
        self._profiler = profiler or MultiplayerNetworkProfiler(
            max_samples_per_client=self.limits.max_samples_per_client,
            max_events=self.limits.max_events,
        )
        self._client_aliases: dict[str, str] = {}
        self._round_trip_probes: dict[str, RoundTripProbeSource22] = {}
        failure: MultiplayerDebuggerError22 | None = None
        try:
            self._validate_source_bounds()
            self._refresh_client_aliases()
        except MultiplayerDebuggerError22 as exc:
            failure = _sanitized_failure(
                exc,
                fallback_code="diagnostic_source_unavailable",
                message="multiplayer diagnostic source was rejected",
            )
        except Exception:  # noqa: BLE001 - provider error text is private
            failure = MultiplayerDebuggerError22(
                "diagnostic_source_unavailable",
                "multiplayer diagnostic source is unavailable",
            )
        if failure is not None:
            raise failure

    @staticmethod
    def _source_limit(message: str) -> MultiplayerDebuggerError22:
        return MultiplayerDebuggerError22("diagnostic_source_limit", message)

    def _validate_source_bounds(self) -> None:
        """Reject source state that could bypass the debugger's hard work limits.

        ``MultiplayerNetworkProfiler`` predates this privacy facade and intentionally lets callers
        choose its retention limits. Inspecting its bounded containers here avoids asking its public
        tuple-returning helpers to materialize an unbounded history before this facade can apply its
        own limits.
        """

        max_members = getattr(self._session.lifecycle, "max_members", None)
        if (
            not isinstance(max_members, int)
            or isinstance(max_members, bool)
            or not 1 <= max_members <= _MAX_CLIENTS_22
        ):
            raise self._source_limit(
                "multiplayer session member capacity exceeds the debugger safety limit"
            )

        max_samples = getattr(self._profiler, "max_samples_per_client", None)
        max_events = getattr(self._profiler, "max_events", None)
        if (
            not isinstance(max_samples, int)
            or isinstance(max_samples, bool)
            or not 1 <= max_samples <= _MAX_SAMPLES_PER_CLIENT_22
        ):
            raise self._source_limit(
                "network profiler sample retention exceeds the debugger safety limit"
            )
        if (
            not isinstance(max_events, int)
            or isinstance(max_events, bool)
            or not 1 <= max_events <= _MAX_EVENTS_22
        ):
            raise self._source_limit(
                "network profiler event retention exceeds the debugger safety limit"
            )

        sample_store = getattr(self._profiler, "_samples", None)
        event_store = getattr(self._profiler, "_events", None)
        if not isinstance(sample_store, Mapping) or event_store is None:
            raise MultiplayerDebuggerError22(
                "diagnostic_source_unavailable",
                "network profiler bounded state is unavailable",
            )
        if len(sample_store) > _MAX_CLIENTS_22:
            raise self._source_limit(
                "network profiler client history exceeds the debugger safety limit"
            )
        failure: MultiplayerDebuggerError22 | None = None
        retained_events = 0
        try:
            retained_events = len(event_store)
        except Exception:  # noqa: BLE001 - provider container is an external boundary
            failure = MultiplayerDebuggerError22(
                "diagnostic_source_unavailable",
                "network profiler bounded state is unavailable",
            )
        if failure is not None:
            raise failure
        if retained_events > _MAX_EVENTS_22:
            raise self._source_limit(
                "network profiler event history exceeds the debugger safety limit"
            )

        total_counters = 0
        for history in sample_store.values():
            failure = None
            retained_samples = 0
            try:
                retained_samples = len(history)
            except Exception:  # noqa: BLE001 - provider container is an external boundary
                failure = MultiplayerDebuggerError22(
                    "diagnostic_source_unavailable",
                    "network profiler bounded state is unavailable",
                )
            if failure is not None:
                raise failure
            if retained_samples > _MAX_SAMPLES_PER_CLIENT_22:
                raise self._source_limit(
                    "network profiler sample history exceeds the debugger safety limit"
                )
            for sample in history:
                if not isinstance(sample, NetworkProfileSample):
                    raise MultiplayerDebuggerError22(
                        "diagnostic_source_unavailable",
                        "network profiler retained an invalid sample",
                    )
                counter_count = len(sample.counters)
                if counter_count > _MAX_SOURCE_COUNTERS_PER_SAMPLE_22:
                    raise self._source_limit(
                        "network profiler sample counters exceed the debugger safety limit"
                    )
                total_counters += counter_count
                if total_counters > _MAX_SOURCE_COUNTERS_TOTAL_22:
                    raise self._source_limit(
                        "network profiler retained counters exceed the debugger work budget"
                    )
        for event in event_store:
            if not isinstance(event, NetworkProfileEvent):
                raise MultiplayerDebuggerError22(
                    "diagnostic_source_unavailable",
                    "network profiler retained an invalid event",
                )
            counter_count = len(event.counters)
            if counter_count > _MAX_SOURCE_COUNTERS_PER_SAMPLE_22:
                raise self._source_limit(
                    "network profiler event counters exceed the debugger safety limit"
                )
            total_counters += counter_count
            if total_counters > _MAX_SOURCE_COUNTERS_TOTAL_22:
                raise self._source_limit(
                    "network profiler retained counters exceed the debugger work budget"
                )

    def _refresh_client_aliases(self) -> None:
        members = sorted(
            self._session.lifecycle.members,
            key=lambda member: (member.join_order, member.client_id),
        )
        for member in members:
            if member.client_id in self._client_aliases:
                continue
            if len(self._client_aliases) >= self.limits.max_clients:
                break
            self._client_aliases[member.client_id] = f"peer-{len(self._client_aliases):03d}"

    def _require_active_client(self, client_id: object) -> str:
        normalized = _client_id(client_id)
        failure: MultiplayerDebuggerError22 | None = None
        try:
            self._validate_source_bounds()
            active = {member.client_id for member in self._session.lifecycle.members}
            self._refresh_client_aliases()
        except MultiplayerDebuggerError22 as exc:
            failure = _sanitized_failure(
                exc,
                fallback_code="diagnostic_source_unavailable",
                message="multiplayer diagnostic source was rejected",
            )
        except Exception:  # noqa: BLE001 - provider error text is private
            failure = MultiplayerDebuggerError22(
                "diagnostic_source_unavailable",
                "multiplayer diagnostic source is unavailable",
            )
        if failure is not None:
            raise failure
        if normalized not in active:
            raise MultiplayerDebuggerError22("client_unavailable", "client is not active")
        if normalized not in self._client_aliases:
            raise MultiplayerDebuggerError22(
                "client_limit_reached",
                "multiplayer debugger client limit is reached",
            )
        return normalized

    def attach_round_trip_probe(
        self,
        client_id: str,
        probe: RoundTripProbeSource22,
    ) -> None:
        normalized = self._require_active_client(client_id)
        failure: TypeError | None = None
        diagnostics: object | None = None
        samples: object | None = None
        try:
            diagnostics = getattr(probe, "diagnostics", None)
            samples = probe.samples
        except Exception:  # noqa: BLE001 - hide provider error text
            failure = TypeError("probe must provide samples and diagnostics()")
        if failure is not None:
            raise failure
        if not callable(diagnostics) or not isinstance(samples, tuple):
            raise TypeError("probe must provide samples and diagnostics()")
        self._round_trip_probes[normalized] = probe

    def detach_round_trip_probe(self, client_id: str) -> bool:
        normalized = _client_id(client_id)
        return self._round_trip_probes.pop(normalized, None) is not None

    def sample_peer(
        self,
        client_id: str,
        tick: int,
        *,
        transport_outbound: TransportQoSScheduler | None = None,
        transport_inbound: TransportQoSReceiver | None = None,
        sent_bytes: int = 0,
        received_bytes: int = 0,
        replicated_entities: int = 0,
        entity_budget: int | None = None,
        round_trip_probe: RoundTripProbeSource22 | None = None,
    ) -> None:
        normalized = self._require_active_client(client_id)
        if transport_outbound is not None and not isinstance(
            transport_outbound, TransportQoSScheduler
        ):
            raise TypeError("transport_outbound must be a TransportQoSScheduler")
        if transport_inbound is not None and not isinstance(
            transport_inbound, TransportQoSReceiver
        ):
            raise TypeError("transport_inbound must be a TransportQoSReceiver")
        failure: MultiplayerDebuggerError22 | None = None
        try:
            outbound_snapshot = (
                None
                if transport_outbound is None
                else _outbound_transport_snapshot(transport_outbound)
            )
            inbound_snapshot = (
                None
                if transport_inbound is None
                else _inbound_transport_snapshot(transport_inbound)
            )
            self._validate_source_bounds()
            if round_trip_probe is not None:
                self.attach_round_trip_probe(normalized, round_trip_probe)
            sample = self._profiler.sample_runtime(
                normalized,
                tick,
                replication=self._session.replication,
                transport_outbound=outbound_snapshot,
                transport_inbound=inbound_snapshot,
                session=self._session.lifecycle,
                sent_bytes=sent_bytes,
                received_bytes=received_bytes,
                replicated_entities=replicated_entities,
                entity_budget=entity_budget,
            )
            if len(sample.counters) > _MAX_SOURCE_COUNTERS_PER_SAMPLE_22:
                raise self._source_limit(
                    "network profiler sample counters exceed the debugger safety limit"
                )
            self._validate_source_bounds()
        except MultiplayerDebuggerError22 as exc:
            failure = _sanitized_failure(
                exc,
                fallback_code="sample_failed",
                message="multiplayer debugger sample was rejected",
            )
        except Exception:  # noqa: BLE001 - provider error text is private
            failure = MultiplayerDebuggerError22(
                "sample_failed", "multiplayer debugger sample failed"
            )
        if failure is not None:
            raise failure

    def sample(self, client_id: str, tick: int, **kwargs: Any) -> None:
        self.sample_peer(client_id, tick, **kwargs)

    def snapshot(self) -> dict[str, Any]:
        failure: MultiplayerDebuggerError22 | None = None
        result: dict[str, Any] | None = None
        try:
            result = self._build_capture(history=False)
        except MultiplayerDebuggerError22 as exc:
            failure = _sanitized_failure(
                exc,
                fallback_code="snapshot_failed",
                message="multiplayer debugger snapshot was rejected",
            )
        except Exception:  # noqa: BLE001 - provider error text is private
            failure = MultiplayerDebuggerError22(
                "snapshot_failed", "multiplayer debugger snapshot failed"
            )
        if failure is not None:
            raise failure
        if result is None:
            raise MultiplayerDebuggerError22(
                "snapshot_failed", "multiplayer debugger snapshot failed"
            )
        return result

    def portable_capture(self) -> dict[str, Any]:
        failure: MultiplayerDebuggerError22 | None = None
        result: dict[str, Any] | None = None
        try:
            result = self._build_capture(history=True)
        except MultiplayerDebuggerError22 as exc:
            failure = _sanitized_failure(
                exc,
                fallback_code="capture_failed",
                message="multiplayer debugger capture was rejected",
            )
        except Exception:  # noqa: BLE001 - provider error text is private
            failure = MultiplayerDebuggerError22(
                "capture_failed", "multiplayer debugger capture failed"
            )
        if failure is not None:
            raise failure
        if result is None:
            raise MultiplayerDebuggerError22(
                "capture_failed", "multiplayer debugger capture failed"
            )
        return result

    def capture_bytes(self) -> bytes:
        failure: MultiplayerDebuggerError22 | None = None
        result: bytes | None = None
        try:
            result = _canonical_bytes(self.portable_capture())
        except MultiplayerDebuggerError22 as exc:
            failure = _sanitized_failure(
                exc,
                fallback_code="capture_failed",
                message="multiplayer debugger capture was rejected",
            )
        except Exception:  # noqa: BLE001 - provider error text is private
            failure = MultiplayerDebuggerError22(
                "capture_failed", "multiplayer debugger capture failed"
            )
        if failure is not None:
            raise failure
        if result is None:
            raise MultiplayerDebuggerError22(
                "capture_failed", "multiplayer debugger capture failed"
            )
        return result

    def capture_json(self) -> str:
        return self.capture_bytes().decode("ascii")

    def fingerprint(self) -> str:
        return hashlib.sha256(self.capture_bytes()).hexdigest()

    def _build_capture(self, *, history: bool) -> dict[str, Any]:
        self._validate_source_bounds()
        self._refresh_client_aliases()
        lifecycle_snapshot = self._session.lifecycle.snapshot()
        current_members = {member.client_id: member for member in lifecycle_snapshot.members}
        ordered_ids = tuple(
            client_id
            for client_id, _alias in sorted(self._client_aliases.items(), key=lambda item: item[1])
        )
        histories: dict[str, tuple[NetworkProfileSample, ...]] = {}
        for client_id in ordered_ids:
            source_history = self._profiler.history(client_id)
            if not isinstance(source_history, tuple):
                raise MultiplayerDebuggerError22(
                    "diagnostic_source_unavailable",
                    "network profiler returned an invalid history",
                )
            if len(source_history) > _MAX_SAMPLES_PER_CLIENT_22:
                raise self._source_limit(
                    "network profiler sample history exceeds the debugger safety limit"
                )
            if not history and source_history:
                source_history = source_history[-1:]
            histories[client_id] = source_history[-self.limits.max_samples_per_client :]
        selected_ids = tuple(
            client_id
            for client_id in ordered_ids
            if client_id in current_members
            or histories[client_id]
            or client_id in self._round_trip_probes
        )
        selected_histories = {client_id: histories[client_id] for client_id in selected_ids}
        channel_aliases, channel_count, channels_omitted = self._channel_aliases(
            selected_histories
        )

        all_events = self._profiler.events()
        if not isinstance(all_events, tuple):
            raise MultiplayerDebuggerError22(
                "diagnostic_source_unavailable",
                "network profiler returned invalid events",
            )
        if len(all_events) > _MAX_EVENTS_22:
            raise self._source_limit(
                "network profiler event history exceeds the debugger safety limit"
            )
        source_events = all_events[-self.limits.max_events :]

        counters_omitted = 0
        unavailable_round_trip_sources = 0
        peers: list[dict[str, Any]] = []
        replication_clients = set(self._session.replication.client_ids)
        for client_id in selected_ids:
            member = current_members.get(client_id)
            replication: dict[str, int | float] = {}
            if client_id in replication_clients:
                source = self._session.replication.diagnostics(client_id)
                for key in sorted(source):
                    if f"replication.{key}" not in _REPLICATION_COUNTERS_22:
                        continue
                    value = _safe_number(source[key])
                    if value is not None:
                        replication[key] = value

            peer: dict[str, Any] = {
                "alias": self._client_aliases[client_id],
                "present": member is not None,
                "connected": False if member is None else member.connected,
                "ready": False if member is None else member.ready,
                "host": client_id == lifecycle_snapshot.host_client_id,
                "role_count": 0 if member is None else len(member.roles),
                "replication": replication,
                "samples": [],
            }
            probe = self._round_trip_probes.get(client_id)
            if probe is not None:
                round_trip = self._round_trip_diagnostics(probe)
                if round_trip is None:
                    unavailable_round_trip_sources += 1
                else:
                    peer["round_trip"] = round_trip
            peers.append(peer)

        diagnostics = self._profiler.diagnostics()
        profiler_diagnostics = {
            key: value
            for key in (
                "clients",
                "samples_total",
                "samples_retained",
                "sample_evictions",
                "events_total",
                "events_retained",
                "event_evictions",
            )
            if (value := _safe_number(diagnostics.get(key))) is not None
        }
        lifecycle_diagnostics = self._session.lifecycle.diagnostics()
        payload: dict[str, Any] = {
            "format": MULTIPLAYER_DEBUG_CAPTURE_FORMAT_22,
            "version": MULTIPLAYER_DEBUG_CAPTURE_VERSION_22,
            "kind": "capture" if history else "snapshot",
            "limits": self.limits.portable(),
            "session": {
                "phase": lifecycle_snapshot.phase.value,
                "revision": lifecycle_snapshot.revision,
                "members": len(lifecycle_snapshot.members),
                "connected_members": sum(member.connected for member in lifecycle_snapshot.members),
                "ready_members": sum(member.ready for member in lifecycle_snapshot.members),
                "failures_total": _safe_number(lifecycle_diagnostics.get("failures_total", 0)),
            },
            "peers": peers,
            "events": [],
            "diagnostics": {
                "profiler": profiler_diagnostics,
                "clients_omitted": sum(
                    member.client_id not in self._client_aliases
                    for member in lifecycle_snapshot.members
                ),
                "channels_observed": channel_count,
                "channels_omitted": channels_omitted,
                "counters_omitted": counters_omitted,
                "round_trip_sources_unavailable": unavailable_round_trip_sources,
                "capture_entries_trimmed": 0,
                "peers_trimmed_for_bytes": 0,
            },
        }
        payload = self._fit_capture(payload)

        diagnostics_payload = payload["diagnostics"]
        base_trimmed = int(diagnostics_payload["capture_entries_trimmed"])
        candidate_trimmed = 0
        included_peers = {peer["alias"]: peer for peer in payload["peers"]}
        eligible_events = tuple(
            event for event in source_events if event.client_id in self._client_aliases
        )
        if base_trimmed:
            candidate_trimmed += sum(len(items) for items in selected_histories.values())
            candidate_trimmed += len(eligible_events)
        else:
            remaining = max(
                0,
                self.limits.max_capture_bytes
                - len(_canonical_bytes(payload))
                - _CAPTURE_TRIM_HEADROOM_BYTES_22,
            )
            blocked_peers: set[str] = set()
            max_history = max((len(items) for items in selected_histories.values()), default=0)
            for depth in range(1, max_history + 1):
                for client_id in selected_ids:
                    source_history = selected_histories[client_id]
                    if depth > len(source_history):
                        continue
                    alias = self._client_aliases[client_id]
                    peer = included_peers.get(alias)
                    if peer is None or alias in blocked_peers:
                        continue
                    portable, omitted = self._portable_sample(
                        source_history[-depth], channel_aliases
                    )
                    encoded_size = len(_canonical_bytes(portable))
                    delta = encoded_size + (1 if peer["samples"] else 0)
                    if delta > remaining:
                        candidate_trimmed += len(source_history) - depth + 1
                        blocked_peers.add(alias)
                        continue
                    peer["samples"].append(portable)
                    counters_omitted += omitted
                    remaining -= delta
            for peer in payload["peers"]:
                peer["samples"].reverse()

            if blocked_peers:
                candidate_trimmed += len(eligible_events)
            else:
                retained_events: list[dict[str, Any]] = []
                for index, event in enumerate(reversed(eligible_events)):
                    alias = self._client_aliases[event.client_id]
                    counters, omitted = self._safe_counters(event.counters, channel_aliases)
                    portable_event = {
                        "sequence": event.sequence,
                        "tick": event.tick,
                        "peer": alias,
                        "kind": "network-profile",
                        "counters": counters,
                    }
                    encoded_size = len(_canonical_bytes(portable_event))
                    delta = encoded_size + (1 if retained_events else 0)
                    if delta > remaining:
                        candidate_trimmed += len(eligible_events) - index
                        break
                    retained_events.append(portable_event)
                    counters_omitted += omitted
                    remaining -= delta
                payload["events"] = list(reversed(retained_events))

        diagnostics_payload["counters_omitted"] = counters_omitted
        diagnostics_payload["capture_entries_trimmed"] = base_trimmed + candidate_trimmed
        return self._fit_capture(payload)

    def _channel_aliases(
        self,
        histories: Mapping[str, tuple[NetworkProfileSample, ...]],
    ) -> tuple[dict[str, str], int, int]:
        names: set[str] = set()
        for source_history in histories.values():
            for sample in source_history:
                for key in sample.counters:
                    parsed = _channel_counter(key)
                    if parsed is not None:
                        names.add(parsed[1])
        selected = sorted(names)[: self.limits.max_channels]
        return (
            {name: f"channel-{index:03d}" for index, name in enumerate(selected)},
            len(names),
            max(0, len(names) - len(selected)),
        )

    def _portable_sample(
        self,
        sample: NetworkProfileSample,
        channel_aliases: Mapping[str, str],
    ) -> tuple[dict[str, Any], int]:
        counters, omitted = self._safe_counters(sample.counters, channel_aliases)
        return {"tick": sample.tick, "counters": counters}, omitted

    def _safe_counters(
        self,
        source: Mapping[str, object],
        channel_aliases: Mapping[str, str],
    ) -> tuple[dict[str, int | float], int]:
        if len(source) > _MAX_SOURCE_COUNTERS_PER_SAMPLE_22:
            raise self._source_limit(
                "network profiler counters exceed the debugger safety limit"
            )
        candidates: dict[str, int | float] = {}
        omitted = sum(not isinstance(item, str) for item in source)
        for key in sorted(item for item in source if isinstance(item, str)):
            value = _safe_number(source[key])
            if value is None:
                omitted += 1
                continue
            safe_key: str | None = key if key in _SAFE_DIRECT_COUNTERS_22 else None
            if safe_key is None:
                parsed = _channel_counter(key)
                if parsed is not None:
                    direction, channel, metric = parsed
                    alias = channel_aliases.get(channel)
                    if alias is not None:
                        safe_key = f"transport_{direction}.channels.{alias}.{metric}"
            if safe_key is None:
                omitted += 1
                continue
            candidates[safe_key] = value

        selected = sorted(candidates)[: self.limits.max_counters_per_sample]
        omitted += len(candidates) - len(selected)
        return {key: candidates[key] for key in selected}, omitted

    @staticmethod
    def _round_trip_diagnostics(
        probe: RoundTripProbeSource22,
    ) -> dict[str, int | float | None] | None:
        try:
            source = probe.diagnostics()
            if not isinstance(source, Mapping):
                return None
            result: dict[str, int | float | None] = {}
            for key in _ROUND_TRIP_INTEGER_FIELDS_22:
                value = _safe_number(source.get(key))
                if not isinstance(value, int) or value < 0:
                    return None
                result[key] = value
            for key in _ROUND_TRIP_FLOAT_FIELDS_22:
                raw = source.get(key)
                if raw is None:
                    result[key] = None
                    continue
                value = _safe_number(raw)
                if value is None or value < 0:
                    return None
                result[key] = value
            if result["pending_limit"] < 1 or result["sample_limit"] < 1:
                return None
            if result["pending"] > result["pending_limit"]:
                return None
            if result["samples_retained"] > result["sample_limit"]:
                return None
            if result["samples_retained"] > result["probes_completed"]:
                return None
            if (
                result["probes_completed"]
                + result["probes_timed_out"]
                + result["pending"]
                > result["probes_started"]
            ):
                return None
            timing_values = tuple(result[key] for key in _ROUND_TRIP_FLOAT_FIELDS_22)
            if result["samples_retained"] == 0:
                if any(value is not None for value in timing_values):
                    return None
            elif any(value is None for value in timing_values):
                return None
            else:
                minimum = result["minimum_ms"]
                maximum = result["maximum_ms"]
                average = result["average_ms"]
                latest = result["latest_ms"]
                if not (
                    isinstance(minimum, (int, float))
                    and isinstance(maximum, (int, float))
                    and isinstance(average, (int, float))
                    and isinstance(latest, (int, float))
                    and minimum <= average <= maximum
                    and minimum <= latest <= maximum
                ):
                    return None
            return result
        except Exception:  # noqa: BLE001 - provider error text must never reach captures
            return None

    @staticmethod
    def _trim_capture_once(
        payload: dict[str, Any],
        required_reduction: int,
    ) -> tuple[int, int]:
        reduced = 0
        trimmed = 0
        peers_trimmed = 0

        events = payload["events"]
        event_removals = 0
        while event_removals < len(events) and reduced < required_reduction:
            remaining_count = len(events) - event_removals
            reduced += len(_canonical_bytes(events[event_removals]))
            if remaining_count > 1:
                reduced += 1
            event_removals += 1
            trimmed += 1
        if event_removals:
            del events[:event_removals]

        peers = payload["peers"]
        for peer in sorted(peers, key=lambda item: item["alias"]):
            if reduced >= required_reduction:
                break
            samples = peer["samples"]
            sample_removals = 0
            while sample_removals < len(samples) and reduced < required_reduction:
                remaining_count = len(samples) - sample_removals
                reduced += len(_canonical_bytes(samples[sample_removals]))
                if remaining_count > 1:
                    reduced += 1
                sample_removals += 1
                trimmed += 1
            if sample_removals:
                del samples[:sample_removals]

        for peer in reversed(peers):
            if reduced >= required_reduction:
                break
            if "round_trip" in peer:
                before = len(_canonical_bytes(peer))
                peer.pop("round_trip")
                reduced += before - len(_canonical_bytes(peer))
                trimmed += 1

        for peer in reversed(peers):
            if reduced >= required_reduction:
                break
            if peer["replication"]:
                before = len(_canonical_bytes(peer))
                peer["replication"] = {}
                reduced += before - len(_canonical_bytes(peer))
                trimmed += 1

        peer_removals = 0
        while peer_removals < len(peers) and reduced < required_reduction:
            remaining_count = len(peers) - peer_removals
            peer = peers[-1 - peer_removals]
            reduced += len(_canonical_bytes(peer))
            if remaining_count > 1:
                reduced += 1
            peer_removals += 1
            peers_trimmed += 1
            trimmed += 1
        if peer_removals:
            del peers[len(peers) - peer_removals :]

        return trimmed, peers_trimmed

    def _fit_capture(self, payload: dict[str, Any]) -> dict[str, Any]:
        for _attempt in range(3):
            encoded_size = len(_canonical_bytes(payload))
            if encoded_size <= self.limits.max_capture_bytes:
                return payload
            required_reduction = (
                encoded_size
                - self.limits.max_capture_bytes
                + _CAPTURE_TRIM_HEADROOM_BYTES_22
            )
            trimmed, peers_trimmed = self._trim_capture_once(payload, required_reduction)
            if trimmed == 0:
                raise MultiplayerDebuggerError22(
                    "capture_limit_too_small",
                    "capture metadata exceeds the configured byte limit",
                )
            diagnostics = payload["diagnostics"]
            diagnostics["capture_entries_trimmed"] = (
                int(diagnostics.get("capture_entries_trimmed", 0)) + trimmed
            )
            diagnostics["peers_trimmed_for_bytes"] = (
                int(diagnostics.get("peers_trimmed_for_bytes", 0)) + peers_trimmed
            )

        if len(_canonical_bytes(payload)) > self.limits.max_capture_bytes:
            raise MultiplayerDebuggerError22(
                "capture_limit_too_small",
                "capture metadata exceeds the configured byte limit",
            )
        return payload


__all__ = [
    "MAX_MULTIPLAYER_DEBUG_CAPTURE_BYTES_22",
    "MULTIPLAYER_DEBUG_CAPTURE_FORMAT_22",
    "MULTIPLAYER_DEBUG_CAPTURE_VERSION_22",
    "MultiplayerDebugger22",
    "MultiplayerDebuggerError22",
    "MultiplayerDebuggerLimits22",
    "RoundTripProbeSource22",
]
