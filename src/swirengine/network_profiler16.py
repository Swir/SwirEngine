from __future__ import annotations

import hashlib
import json
import math
from collections import deque
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any


def _bounded_text(value: object, label: str, *, maximum: int = 128) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{label} must be a string")
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{label} must not be empty")
    if len(normalized) > maximum:
        raise ValueError(f"{label} must not exceed {maximum} characters")
    return normalized


def _non_negative_int(value: object, label: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise TypeError(f"{label} must be an integer")
    if value < 0:
        raise ValueError(f"{label} must be non-negative")
    return value


def _positive_int(value: object, label: str) -> int:
    result = _non_negative_int(value, label)
    if result < 1:
        raise ValueError(f"{label} must be positive")
    return result


def _finite_number(value: object, label: str) -> int | float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{label} must be numeric")
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError(f"{label} must be finite")
    return value


def _flatten_numeric(
    value: Mapping[str, Any],
    *,
    prefix: str = "",
    maximum_depth: int = 8,
) -> dict[str, int | float]:
    result: dict[str, int | float] = {}

    def visit(mapping: Mapping[str, Any], path: str, depth: int) -> None:
        if depth > maximum_depth:
            raise ValueError("diagnostic nesting exceeds maximum_depth")
        for raw_key in sorted(mapping):
            if not isinstance(raw_key, str):
                raise TypeError("diagnostic mapping keys must be strings")
            key = _bounded_text(raw_key, "diagnostic key", maximum=128)
            full_key = f"{path}.{key}" if path else key
            item = mapping[raw_key]
            if isinstance(item, bool) or item is None or isinstance(item, str):
                continue
            if isinstance(item, Mapping):
                visit(item, full_key, depth + 1)
                continue
            if isinstance(item, (int, float)):
                result[full_key] = _finite_number(item, full_key)

    visit(value, prefix, 0)
    return result


def _diagnostics(source: object, *args: object) -> Mapping[str, Any]:
    method = getattr(source, "diagnostics", None)
    if not callable(method):
        raise TypeError("diagnostic source must provide diagnostics(...)")
    value = method(*args)
    if not isinstance(value, Mapping):
        raise TypeError("diagnostics(...) must return a mapping")
    return value


@dataclass(slots=True, frozen=True)
class NetworkProfileSample:
    client_id: str
    tick: int
    counters: dict[str, int | float]

    def __post_init__(self) -> None:
        object.__setattr__(self, "client_id", _bounded_text(self.client_id, "client_id"))
        object.__setattr__(self, "tick", _non_negative_int(self.tick, "tick"))
        normalized: dict[str, int | float] = {}
        for key in sorted(self.counters):
            normalized[_bounded_text(key, "counter key", maximum=256)] = _finite_number(
                self.counters[key], key
            )
        object.__setattr__(self, "counters", normalized)

    def portable(self) -> dict[str, Any]:
        return {
            "client_id": self.client_id,
            "tick": self.tick,
            "counters": dict(self.counters),
        }


@dataclass(slots=True, frozen=True)
class NetworkProfileEvent:
    sequence: int
    tick: int
    client_id: str
    category: str
    name: str
    counters: dict[str, int | float]

    def __post_init__(self) -> None:
        object.__setattr__(self, "sequence", _positive_int(self.sequence, "sequence"))
        object.__setattr__(self, "tick", _non_negative_int(self.tick, "tick"))
        object.__setattr__(self, "client_id", _bounded_text(self.client_id, "client_id"))
        object.__setattr__(self, "category", _bounded_text(self.category, "category", maximum=96))
        object.__setattr__(self, "name", _bounded_text(self.name, "name", maximum=128))
        object.__setattr__(self, "counters", _flatten_numeric(self.counters))

    def portable(self) -> dict[str, Any]:
        return {
            "sequence": self.sequence,
            "tick": self.tick,
            "client_id": self.client_id,
            "category": self.category,
            "name": self.name,
            "counters": dict(self.counters),
        }


class MultiplayerNetworkProfiler:
    """Bounded, deterministic multiplayer diagnostics aggregation for SwirEngine 1.6.

    The profiler consumes the existing 1.6 diagnostics surfaces without owning networking,
    simulation, sessions, or transport state. Only numeric diagnostics are retained so creator
    captures remain useful in headless runtimes without copying gameplay payloads, tokens, or
    provider exception text.
    """

    CAPTURE_VERSION = 1

    def __init__(self, *, max_samples_per_client: int = 256, max_events: int = 2048) -> None:
        self.max_samples_per_client = _positive_int(
            max_samples_per_client, "max_samples_per_client"
        )
        self.max_events = _positive_int(max_events, "max_events")
        self._samples: dict[str, deque[NetworkProfileSample]] = {}
        self._last_tick: dict[str, int] = {}
        self._events: deque[NetworkProfileEvent] = deque(maxlen=self.max_events)
        self._event_sequence = 0
        self._samples_total = 0
        self._sample_evictions = 0
        self._event_evictions = 0

    @property
    def client_ids(self) -> tuple[str, ...]:
        return tuple(sorted(self._samples))

    def sample_runtime(
        self,
        client_id: str,
        tick: int,
        *,
        replication: object | None = None,
        prediction: object | None = None,
        transport_outbound: object | None = None,
        transport_inbound: object | None = None,
        session: object | None = None,
        sent_bytes: int = 0,
        received_bytes: int = 0,
        replicated_entities: int = 0,
        entity_budget: int | None = None,
    ) -> NetworkProfileSample:
        client_id = _bounded_text(client_id, "client_id")
        tick = _non_negative_int(tick, "tick")
        last_tick = self._last_tick.get(client_id)
        if last_tick is not None and tick <= last_tick:
            raise ValueError("sample tick must increase for each client")

        counters: dict[str, int | float] = {}
        if replication is not None:
            counters.update(
                _flatten_numeric(_diagnostics(replication, client_id), prefix="replication")
            )
        if prediction is not None:
            counters.update(_flatten_numeric(_diagnostics(prediction), prefix="prediction"))
        if transport_outbound is not None:
            counters.update(
                _flatten_numeric(_diagnostics(transport_outbound), prefix="transport_outbound")
            )
        if transport_inbound is not None:
            counters.update(
                _flatten_numeric(_diagnostics(transport_inbound), prefix="transport_inbound")
            )
        if session is not None:
            counters.update(_flatten_numeric(_diagnostics(session), prefix="session"))

        sent_bytes = _non_negative_int(sent_bytes, "sent_bytes")
        received_bytes = _non_negative_int(received_bytes, "received_bytes")
        replicated_entities = _non_negative_int(replicated_entities, "replicated_entities")
        counters["traffic.sent_bytes"] = sent_bytes
        counters["traffic.received_bytes"] = received_bytes
        counters["traffic.replicated_entities"] = replicated_entities
        if entity_budget is not None:
            entity_budget = _positive_int(entity_budget, "entity_budget")
            counters["traffic.entity_budget"] = entity_budget
            counters["traffic.entity_budget_ratio"] = replicated_entities / entity_budget

        sample = NetworkProfileSample(client_id, tick, counters)
        history = self._samples.setdefault(
            client_id, deque(maxlen=self.max_samples_per_client)
        )
        if len(history) == self.max_samples_per_client:
            self._sample_evictions += 1
        history.append(sample)
        self._last_tick[client_id] = tick
        self._samples_total += 1
        return sample

    def record_event(
        self,
        client_id: str,
        tick: int,
        category: str,
        name: str,
        counters: Mapping[str, Any] | None = None,
    ) -> NetworkProfileEvent:
        self._event_sequence += 1
        event = NetworkProfileEvent(
            self._event_sequence,
            tick,
            client_id,
            category,
            name,
            dict(counters or {}),
        )
        if len(self._events) == self.max_events:
            self._event_evictions += 1
        self._events.append(event)
        return event

    def latest(self, client_id: str) -> NetworkProfileSample | None:
        history = self._samples.get(_bounded_text(client_id, "client_id"))
        return None if not history else history[-1]

    def history(self, client_id: str) -> tuple[NetworkProfileSample, ...]:
        history = self._samples.get(_bounded_text(client_id, "client_id"))
        return () if history is None else tuple(history)

    def events(
        self,
        *,
        client_id: str | None = None,
        since_sequence: int = 0,
    ) -> tuple[NetworkProfileEvent, ...]:
        since_sequence = _non_negative_int(since_sequence, "since_sequence")
        normalized_client = None
        if client_id is not None:
            normalized_client = _bounded_text(client_id, "client_id")
        return tuple(
            event
            for event in self._events
            if event.sequence > since_sequence
            and (normalized_client is None or event.client_id == normalized_client)
        )

    def bandwidth_hotspots(self, *, limit: int = 8) -> tuple[dict[str, int | float | str], ...]:
        limit = _positive_int(limit, "limit")
        rows: list[dict[str, int | float | str]] = []
        for client_id in self.client_ids:
            history = self._samples[client_id]
            sent = sum(int(sample.counters.get("traffic.sent_bytes", 0)) for sample in history)
            received = sum(
                int(sample.counters.get("traffic.received_bytes", 0)) for sample in history
            )
            entities = sum(
                int(sample.counters.get("traffic.replicated_entities", 0))
                for sample in history
            )
            peak_ratio = max(
                (
                    float(sample.counters.get("traffic.entity_budget_ratio", 0.0))
                    for sample in history
                ),
                default=0.0,
            )
            rows.append(
                {
                    "client_id": client_id,
                    "sent_bytes": sent,
                    "received_bytes": received,
                    "replicated_entities": entities,
                    "peak_entity_budget_ratio": peak_ratio,
                }
            )
        rows.sort(
            key=lambda row: (
                -int(row["sent_bytes"]) - int(row["received_bytes"]),
                -float(row["peak_entity_budget_ratio"]),
                str(row["client_id"]),
            )
        )
        return tuple(rows[:limit])

    def diagnostics(self) -> dict[str, int]:
        return {
            "clients": len(self._samples),
            "samples_total": self._samples_total,
            "samples_retained": sum(len(history) for history in self._samples.values()),
            "sample_evictions": self._sample_evictions,
            "events_total": self._event_sequence,
            "events_retained": len(self._events),
            "event_evictions": self._event_evictions,
        }

    def portable_capture(self) -> dict[str, Any]:
        clients: dict[str, Any] = {}
        for client_id in self.client_ids:
            history = self._samples[client_id]
            clients[client_id] = {
                "samples": [sample.portable() for sample in history],
                "latest_tick": history[-1].tick if history else None,
            }
        return {
            "version": self.CAPTURE_VERSION,
            "limits": {
                "max_samples_per_client": self.max_samples_per_client,
                "max_events": self.max_events,
            },
            "diagnostics": self.diagnostics(),
            "clients": clients,
            "hotspots": list(self.bandwidth_hotspots(limit=max(1, len(clients)))) if clients else [],
            "events": [event.portable() for event in self._events],
        }

    def fingerprint(self) -> str:
        payload = json.dumps(
            self.portable_capture(),
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def export_json(self, path: str | Path) -> Path:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_name(f".{target.name}.tmp")
        payload = json.dumps(
            self.portable_capture(),
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
        temporary.write_text(payload + "\n", encoding="utf-8")
        temporary.replace(target)
        return target


__all__ = [
    "MultiplayerNetworkProfiler",
    "NetworkProfileEvent",
    "NetworkProfileSample",
]
