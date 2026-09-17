from __future__ import annotations

import hashlib
import json
import math
import os
import tracemalloc
from collections import deque
from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass, fields, is_dataclass
from pathlib import Path
from time import perf_counter

MetricNumber = int | float
Clock = Callable[[], float]
DiagnosticsProvider = Callable[[], object]


def _metric_name(value: str, *, label: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{label} must be a string")
    result = value.strip()
    if not result:
        raise ValueError(f"{label} must not be empty")
    return result


def _metric_number(value: MetricNumber, *, label: str) -> MetricNumber:
    if isinstance(value, bool):
        return int(value)
    if not isinstance(value, (int, float)):
        raise TypeError(f"{label} must be an int or float")
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError(f"{label} must be finite")
    return value


def _milliseconds(value: float, *, label: str) -> float:
    result = float(value)
    if not math.isfinite(result) or result < 0.0:
        raise ValueError(f"{label} must be finite and >= 0")
    return result


def _nonnegative_int(value: int, *, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{label} must be an integer")
    if value < 0:
        raise ValueError(f"{label} must be >= 0")
    return value


def _diagnostics_mapping(value: object) -> Mapping[str, object]:
    if isinstance(value, Mapping):
        return value
    portable = getattr(value, "portable", None)
    if callable(portable):
        result = portable()
        if not isinstance(result, Mapping):
            raise TypeError("diagnostics portable() must return a mapping")
        return result
    if is_dataclass(value) and not isinstance(value, type):
        return {field.name: getattr(value, field.name) for field in fields(value)}
    raise TypeError("diagnostics must be a mapping, dataclass, or expose portable()")


def _numeric_items(
    mapping: Mapping[str, object],
    *,
    prefix: str = "",
) -> Iterator[tuple[str, MetricNumber]]:
    for raw_name, value in sorted(mapping.items(), key=lambda item: str(item[0])):
        name = str(raw_name).strip()
        if not name:
            continue
        path = f"{prefix}.{name}" if prefix else name
        if isinstance(value, Mapping):
            yield from _numeric_items(value, prefix=path)
            continue
        if isinstance(value, bool):
            yield path, int(value)
        elif isinstance(value, int) or isinstance(value, float) and math.isfinite(value):
            yield path, value


@dataclass(frozen=True, slots=True)
class PerformanceMetric:
    domain: str
    name: str
    value: MetricNumber

    def __post_init__(self) -> None:
        object.__setattr__(self, "domain", _metric_name(self.domain, label="metric domain"))
        object.__setattr__(self, "name", _metric_name(self.name, label="metric name"))
        object.__setattr__(
            self,
            "value",
            _metric_number(self.value, label=f"metric {self.domain}.{self.name}"),
        )

    def portable(self) -> dict[str, object]:
        return {"domain": self.domain, "name": self.name, "value": self.value}


@dataclass(frozen=True, slots=True)
class PerformanceResource:
    name: str
    count: int
    bytes_used: int = 0

    def __post_init__(self) -> None:
        object.__setattr__(self, "name", _metric_name(self.name, label="resource name"))
        object.__setattr__(self, "count", _nonnegative_int(self.count, label="resource count"))
        object.__setattr__(
            self,
            "bytes_used",
            _nonnegative_int(self.bytes_used, label="resource bytes_used"),
        )

    def portable(self) -> dict[str, object]:
        return {"name": self.name, "count": self.count, "bytes_used": self.bytes_used}


@dataclass(frozen=True, slots=True)
class PerformanceMemory:
    current_bytes: int
    peak_bytes: int

    def __post_init__(self) -> None:
        current = _nonnegative_int(self.current_bytes, label="current memory bytes")
        peak = _nonnegative_int(self.peak_bytes, label="peak memory bytes")
        if peak < current:
            raise ValueError("peak memory bytes must be >= current memory bytes")
        object.__setattr__(self, "current_bytes", current)
        object.__setattr__(self, "peak_bytes", peak)

    def portable(self) -> dict[str, int]:
        return {"current_bytes": self.current_bytes, "peak_bytes": self.peak_bytes}


@dataclass(frozen=True, slots=True)
class PerformanceFrame:
    index: int
    frame_ms: float
    update_ms: float
    physics_ms: float
    render_ms: float
    timings: tuple[PerformanceMetric, ...] = ()
    counters: tuple[PerformanceMetric, ...] = ()
    resources: tuple[PerformanceResource, ...] = ()
    memory: PerformanceMemory | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "index", _nonnegative_int(self.index, label="frame index"))
        for field_name in ("frame_ms", "update_ms", "physics_ms", "render_ms"):
            object.__setattr__(
                self,
                field_name,
                _milliseconds(getattr(self, field_name), label=field_name),
            )
        object.__setattr__(self, "timings", tuple(self.timings))
        object.__setattr__(self, "counters", tuple(self.counters))
        object.__setattr__(self, "resources", tuple(self.resources))
        if not all(isinstance(item, PerformanceMetric) for item in self.timings):
            raise TypeError("frame timings must contain PerformanceMetric values")
        if not all(isinstance(item, PerformanceMetric) for item in self.counters):
            raise TypeError("frame counters must contain PerformanceMetric values")
        if not all(isinstance(item, PerformanceResource) for item in self.resources):
            raise TypeError("frame resources must contain PerformanceResource values")
        if self.memory is not None and not isinstance(self.memory, PerformanceMemory):
            raise TypeError("frame memory must be PerformanceMemory or None")

    @property
    def fps(self) -> float:
        return 1000.0 / self.frame_ms if self.frame_ms > 0.0 else 0.0

    def portable(self) -> dict[str, object]:
        result: dict[str, object] = {
            "index": self.index,
            "frame_ms": self.frame_ms,
            "fps": self.fps,
            "update_ms": self.update_ms,
            "physics_ms": self.physics_ms,
            "render_ms": self.render_ms,
            "timings": [metric.portable() for metric in self.timings],
            "counters": [metric.portable() for metric in self.counters],
            "resources": [resource.portable() for resource in self.resources],
        }
        if self.memory is not None:
            result["memory"] = self.memory.portable()
        return result


@dataclass(frozen=True, slots=True)
class PerformanceCapture:
    """Portable, deterministic performance capture suitable for CI comparisons."""

    frames: tuple[PerformanceFrame, ...]
    metadata: tuple[tuple[str, str], ...] = ()
    format_version: int = 1

    def __post_init__(self) -> None:
        if self.format_version != 1:
            raise ValueError("unsupported performance capture format version")
        frames = tuple(self.frames)
        if not all(isinstance(frame, PerformanceFrame) for frame in frames):
            raise TypeError("performance capture frames must contain PerformanceFrame values")
        normalized = tuple(
            sorted(
                (
                    _metric_name(str(key), label="capture metadata key"),
                    str(value),
                )
                for key, value in self.metadata
            )
        )
        if len({key for key, _value in normalized}) != len(normalized):
            raise ValueError("capture metadata keys must be unique")
        object.__setattr__(self, "frames", frames)
        object.__setattr__(self, "metadata", normalized)

    def portable(self) -> dict[str, object]:
        return {
            "format": "swirengine.performance.capture",
            "format_version": self.format_version,
            "metadata": dict(self.metadata),
            "frames": [frame.portable() for frame in self.frames],
        }

    def canonical_json(self) -> str:
        return json.dumps(
            self.portable(),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )

    @property
    def fingerprint(self) -> str:
        return hashlib.sha256(self.canonical_json().encode("utf-8")).hexdigest()

    def to_json(self, *, indent: int | None = 2) -> str:
        return json.dumps(
            self.portable(),
            ensure_ascii=False,
            sort_keys=True,
            indent=indent,
        )

    def export_json(self, path: str | Path, *, indent: int | None = 2) -> Path:
        destination = Path(path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = destination.with_name(f".{destination.name}.tmp")
        try:
            temporary.write_text(self.to_json(indent=indent) + "\n", encoding="utf-8")
            os.replace(temporary, destination)
        finally:
            try:
                temporary.unlink()
            except FileNotFoundError:
                pass
        return destination


class PerformanceDiagnostics2:
    """Additive SwirEngine 1.5 profiling, counters, resources and capture API.

    The recorder is opt-in and independent from the stable :class:`swirengine.Profiler` API.
    A bounded frame history keeps long sessions from accumulating unbounded diagnostics memory.
    Diagnostic providers are sampled at ``end_frame`` and can expose a mapping, dataclass, or a
    ``portable()`` mapping. Non-numeric fields are intentionally ignored.
    """

    _FRAME_SECTIONS = frozenset({"update", "physics", "render"})

    def __init__(
        self,
        *,
        history: int = 300,
        enabled: bool = True,
        clock: Clock = perf_counter,
        strict_providers: bool = False,
    ) -> None:
        if isinstance(history, bool) or not isinstance(history, int):
            raise TypeError("performance history must be an integer")
        if history < 1:
            raise ValueError("performance history must be at least 1")
        if not callable(clock):
            raise TypeError("performance clock must be callable")
        self.enabled = bool(enabled)
        self.strict_providers = bool(strict_providers)
        self._clock = clock
        self._frames: deque[PerformanceFrame] = deque(maxlen=history)
        self._providers: dict[str, DiagnosticsProvider] = {}
        self._frame_started: float | None = None
        self._next_index = 0
        self._timings: dict[tuple[str, str], float] = {}
        self._counters: dict[tuple[str, str], MetricNumber] = {}
        self._resources: dict[str, PerformanceResource] = {}
        self._provider_errors = 0
        self._capture_memory = False
        self._owns_tracemalloc = False

    @property
    def active(self) -> bool:
        return self._frame_started is not None

    @property
    def frames(self) -> tuple[PerformanceFrame, ...]:
        return tuple(self._frames)

    @property
    def latest(self) -> PerformanceFrame | None:
        return self._frames[-1] if self._frames else None

    @property
    def provider_errors(self) -> int:
        return self._provider_errors

    def clear(self) -> None:
        if self.active:
            raise RuntimeError("cannot clear performance diagnostics during an active frame")
        self._frames.clear()
        self._next_index = 0
        self._provider_errors = 0

    def begin_frame(self) -> None:
        if not self.enabled:
            return
        if self.active:
            raise RuntimeError("performance frame is already active")
        self._timings.clear()
        self._counters.clear()
        self._resources.clear()
        self._frame_started = float(self._clock())

    def _require_active(self) -> None:
        if self.enabled and not self.active:
            raise RuntimeError("begin_frame() must be called before recording performance data")

    def record_timing(self, domain: str, name: str, seconds: float) -> None:
        if not self.enabled:
            return
        self._require_active()
        domain = _metric_name(domain, label="timing domain")
        name = _metric_name(name, label="timing name")
        seconds = float(seconds)
        if not math.isfinite(seconds) or seconds < 0.0:
            raise ValueError("timing seconds must be finite and >= 0")
        key = (domain, name)
        self._timings[key] = self._timings.get(key, 0.0) + seconds

    @contextmanager
    def measure_timing(self, domain: str, name: str) -> Iterator[None]:
        if not self.enabled:
            yield
            return
        self._require_active()
        started = float(self._clock())
        try:
            yield
        finally:
            self.record_timing(domain, name, max(0.0, float(self._clock()) - started))

    @contextmanager
    def measure(self, section: str) -> Iterator[None]:
        if not self.enabled:
            yield
            return
        section = _metric_name(section, label="performance frame section")
        if section not in self._FRAME_SECTIONS:
            raise ValueError(f"unknown performance frame section: {section}")
        with self.measure_timing("frame", section):
            yield

    @contextmanager
    def measure_asset(self, asset: str) -> Iterator[None]:
        with self.measure_timing("asset", asset):
            yield

    def set_counter(self, domain: str, name: str, value: MetricNumber) -> None:
        if not self.enabled:
            return
        self._require_active()
        domain = _metric_name(domain, label="counter domain")
        name = _metric_name(name, label="counter name")
        self._counters[(domain, name)] = _metric_number(
            value,
            label=f"counter {domain}.{name}",
        )

    def add_counter(self, domain: str, name: str, amount: MetricNumber = 1) -> None:
        if not self.enabled:
            return
        self._require_active()
        domain = _metric_name(domain, label="counter domain")
        name = _metric_name(name, label="counter name")
        amount = _metric_number(amount, label=f"counter increment {domain}.{name}")
        key = (domain, name)
        current = self._counters.get(key, 0)
        result = current + amount
        self._counters[key] = _metric_number(result, label=f"counter {domain}.{name}")

    def record_resource(self, name: str, *, count: int, bytes_used: int = 0) -> None:
        if not self.enabled:
            return
        self._require_active()
        resource = PerformanceResource(name=name, count=count, bytes_used=bytes_used)
        self._resources[resource.name] = resource

    def sample_diagnostics(self, domain: str, diagnostics: object) -> int:
        if not self.enabled:
            return 0
        self._require_active()
        domain = _metric_name(domain, label="diagnostics domain")
        mapping = _diagnostics_mapping(diagnostics)
        sampled = 0
        for name, value in _numeric_items(mapping):
            self.set_counter(domain, name, value)
            sampled += 1
        return sampled

    def bind_provider(self, domain: str, provider: DiagnosticsProvider) -> None:
        domain = _metric_name(domain, label="diagnostics provider domain")
        if not callable(provider):
            raise TypeError("diagnostics provider must be callable")
        self._providers[domain] = provider

    def unbind_provider(self, domain: str) -> bool:
        domain = _metric_name(domain, label="diagnostics provider domain")
        return self._providers.pop(domain, None) is not None

    def enable_memory_tracking(self, *, reset_peak: bool = True) -> None:
        if not tracemalloc.is_tracing():
            tracemalloc.start()
            self._owns_tracemalloc = True
            if reset_peak:
                tracemalloc.reset_peak()
        elif self._owns_tracemalloc and reset_peak:
            tracemalloc.reset_peak()
        self._capture_memory = True

    def disable_memory_tracking(self, *, stop_tracing: bool = False) -> None:
        self._capture_memory = False
        if stop_tracing and self._owns_tracemalloc and tracemalloc.is_tracing():
            tracemalloc.stop()
        if not tracemalloc.is_tracing():
            self._owns_tracemalloc = False

    def _memory_snapshot(self) -> PerformanceMemory | None:
        if not self._capture_memory or not tracemalloc.is_tracing():
            return None
        current, peak = tracemalloc.get_traced_memory()
        return PerformanceMemory(current_bytes=current, peak_bytes=peak)

    def _sample_bound_providers(self) -> None:
        for domain, provider in sorted(self._providers.items()):
            try:
                self.sample_diagnostics(domain, provider())
            # Runtime diagnostics are observational and must not destabilize game code.
            except Exception:
                self._provider_errors += 1
                if self.strict_providers:
                    raise
        if self._provider_errors:
            self.set_counter("diagnostics", "provider_errors", self._provider_errors)

    def end_frame(self, frame_seconds: float | None = None) -> PerformanceFrame:
        if not self.enabled:
            return PerformanceFrame(self._next_index, 0.0, 0.0, 0.0, 0.0)
        self._require_active()
        assert self._frame_started is not None
        ended = float(self._clock())
        if frame_seconds is None:
            frame_seconds = max(0.0, ended - self._frame_started)
        else:
            frame_seconds = float(frame_seconds)
            if not math.isfinite(frame_seconds) or frame_seconds < 0.0:
                raise ValueError("frame seconds must be finite and >= 0")

        try:
            self._sample_bound_providers()
            update_ms = self._timings.get(("frame", "update"), 0.0) * 1000.0
            physics_ms = self._timings.get(("frame", "physics"), 0.0) * 1000.0
            render_ms = self._timings.get(("frame", "render"), 0.0) * 1000.0
            frame_keys = {("frame", name) for name in self._FRAME_SECTIONS}
            timings = tuple(
                PerformanceMetric(domain, name, seconds * 1000.0)
                for (domain, name), seconds in sorted(self._timings.items())
                if (domain, name) not in frame_keys
            )
            counters = tuple(
                PerformanceMetric(domain, name, value)
                for (domain, name), value in sorted(self._counters.items())
            )
            resources = tuple(self._resources[name] for name in sorted(self._resources))
            frame = PerformanceFrame(
                index=self._next_index,
                frame_ms=frame_seconds * 1000.0,
                update_ms=update_ms,
                physics_ms=physics_ms,
                render_ms=render_ms,
                timings=timings,
                counters=counters,
                resources=resources,
                memory=self._memory_snapshot(),
            )
            self._frames.append(frame)
            self._next_index += 1
            return frame
        finally:
            self._frame_started = None

    def capture(self, metadata: Mapping[str, object] | None = None) -> PerformanceCapture:
        metadata_items = () if metadata is None else tuple((str(k), str(v)) for k, v in metadata.items())
        return PerformanceCapture(frames=self.frames, metadata=metadata_items)
