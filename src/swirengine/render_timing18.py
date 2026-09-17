from __future__ import annotations

import hashlib
import json
import math
import os
from collections import deque
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from types import MappingProxyType
from typing import Protocol, runtime_checkable

from .render_graph18 import RenderGraphPlan

_MAX_NAME = 128


def _name(value: str, *, label: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{label} must be a string")
    result = value.strip()
    if not result:
        raise ValueError(f"{label} must not be empty")
    if len(result) > _MAX_NAME:
        raise ValueError(f"{label} must contain at most {_MAX_NAME} characters")
    return result


def _positive_int(value: int, *, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{label} must be an integer")
    if value < 1:
        raise ValueError(f"{label} must be >= 1")
    return value


def _nonnegative_int(value: int, *, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{label} must be an integer")
    if value < 0:
        raise ValueError(f"{label} must be >= 0")
    return value


def _metadata_value(value: object) -> str:
    result = str(value)
    if len(result) > 1024:
        raise ValueError("metadata value must contain at most 1024 characters")
    return result


def _milliseconds(value: float, *, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{label} must be a number")
    result = float(value)
    if not math.isfinite(result) or result < 0.0:
        raise ValueError(f"{label} must be finite and >= 0")
    return result


class GpuTimingError(RuntimeError):
    """Stable creator-facing GPU timing/capture failure."""

    def __init__(self, code: str, message: str) -> None:
        self.code = _name(code, label="error code")
        super().__init__(message)


@runtime_checkable
class GpuTimingProvider(Protocol):
    """Backend contract for non-blocking timestamp queries.

    ``poll`` must return ``None`` while a query is not ready. Providers must not wait,
    flush, finish, or otherwise force GPU synchronization from ``poll``.
    """

    def begin(self, frame_index: int, pass_name: str) -> object | None:
        """Start a timestamp query and return an opaque token, or ``None`` if unavailable."""

    def end(self, token: object) -> None:
        """Close the timestamp query represented by ``token``."""

    def poll(self, token: object) -> float | None:
        """Return elapsed seconds when ready, otherwise ``None`` without blocking."""


@dataclass(frozen=True, slots=True)
class GpuPassTiming:
    pass_name: str
    status: str
    milliseconds: float | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "pass_name", _name(self.pass_name, label="pass_name"))
        status = _name(self.status, label="timing status")
        if status not in {"ready", "unavailable", "failed"}:
            raise ValueError(f"unsupported timing status: {status}")
        object.__setattr__(self, "status", status)
        if status == "ready":
            if self.milliseconds is None:
                raise ValueError("ready GPU timing requires milliseconds")
            object.__setattr__(
                self,
                "milliseconds",
                _milliseconds(self.milliseconds, label="GPU timing milliseconds"),
            )
        elif self.milliseconds is not None:
            raise ValueError(f"{status} GPU timing must not carry milliseconds")

    def portable(self) -> Mapping[str, object]:
        return MappingProxyType(
            {
                "pass_name": self.pass_name,
                "status": self.status,
                "milliseconds": self.milliseconds,
            }
        )


@dataclass(frozen=True, slots=True)
class GpuFrameTiming:
    frame_index: int
    plan_fingerprint: str | None
    samples: tuple[GpuPassTiming, ...]
    provider_failures: int
    unavailable_queries: int
    fingerprint: str = field(init=False)

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "frame_index",
            _nonnegative_int(self.frame_index, label="frame_index"),
        )
        if self.plan_fingerprint is not None:
            object.__setattr__(
                self,
                "plan_fingerprint",
                _name(self.plan_fingerprint, label="plan_fingerprint"),
            )
        samples = tuple(self.samples)
        if not all(isinstance(sample, GpuPassTiming) for sample in samples):
            raise TypeError("samples must contain GpuPassTiming values")
        names = [sample.pass_name for sample in samples]
        if len(set(names)) != len(names):
            raise ValueError("GPU frame samples must contain unique pass names")
        object.__setattr__(self, "samples", samples)
        object.__setattr__(
            self,
            "provider_failures",
            _nonnegative_int(self.provider_failures, label="provider_failures"),
        )
        object.__setattr__(
            self,
            "unavailable_queries",
            _nonnegative_int(self.unavailable_queries, label="unavailable_queries"),
        )
        payload = self._portable_payload()
        object.__setattr__(
            self,
            "fingerprint",
            hashlib.sha256(
                json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
            ).hexdigest(),
        )

    @property
    def ready_samples(self) -> tuple[GpuPassTiming, ...]:
        return tuple(sample for sample in self.samples if sample.status == "ready")

    @property
    def gpu_ms(self) -> float:
        return sum(sample.milliseconds or 0.0 for sample in self.ready_samples)

    def _portable_payload(self) -> dict[str, object]:
        return {
            "frame_index": self.frame_index,
            "plan_fingerprint": self.plan_fingerprint,
            "samples": [dict(sample.portable()) for sample in self.samples],
            "provider_failures": self.provider_failures,
            "unavailable_queries": self.unavailable_queries,
        }

    def portable(self) -> Mapping[str, object]:
        payload = self._portable_payload()
        payload["gpu_ms"] = self.gpu_ms
        payload["fingerprint"] = self.fingerprint
        return MappingProxyType(payload)


@dataclass(frozen=True, slots=True)
class GpuTimingDiagnostics:
    history_frames: int
    pending_frames: int
    pending_queries: int
    submitted_queries: int
    resolved_queries: int
    unavailable_queries: int
    provider_failures: int
    dropped_frames: int

    def portable(self) -> Mapping[str, int]:
        return MappingProxyType(
            {name: getattr(self, name) for name in self.__dataclass_fields__}
        )


@dataclass(frozen=True, slots=True)
class GpuTimingHotspot:
    pass_name: str
    samples: int
    total_ms: float
    average_ms: float
    maximum_ms: float

    def portable(self) -> Mapping[str, object]:
        return MappingProxyType(
            {
                "pass_name": self.pass_name,
                "samples": self.samples,
                "total_ms": self.total_ms,
                "average_ms": self.average_ms,
                "maximum_ms": self.maximum_ms,
            }
        )


@dataclass(frozen=True, slots=True)
class GpuTimingCapture:
    frames: tuple[GpuFrameTiming, ...]
    metadata: tuple[tuple[str, str], ...] = ()
    format_version: int = 1

    def __post_init__(self) -> None:
        if self.format_version != 1:
            raise ValueError("unsupported GPU timing capture format version")
        frames = tuple(self.frames)
        if not all(isinstance(frame, GpuFrameTiming) for frame in frames):
            raise TypeError("frames must contain GpuFrameTiming values")
        object.__setattr__(self, "frames", frames)
        if len(self.metadata) > 64:
            raise ValueError("GPU timing capture supports at most 64 metadata entries")
        normalized: list[tuple[str, str]] = []
        for key, value in self.metadata:
            normalized.append(
                (_name(str(key), label="metadata key"), _metadata_value(value))
            )
        normalized.sort()
        if len({key for key, _value in normalized}) != len(normalized):
            raise ValueError("GPU timing capture metadata keys must be unique")
        object.__setattr__(self, "metadata", tuple(normalized))

    def hotspots(self, *, limit: int = 10) -> tuple[GpuTimingHotspot, ...]:
        limit = _positive_int(limit, label="hotspot limit")
        aggregate: dict[str, list[float]] = {}
        for frame in self.frames:
            for sample in frame.ready_samples:
                assert sample.milliseconds is not None
                aggregate.setdefault(sample.pass_name, []).append(sample.milliseconds)
        hotspots = [
            GpuTimingHotspot(
                pass_name=name,
                samples=len(values),
                total_ms=sum(values),
                average_ms=sum(values) / len(values),
                maximum_ms=max(values),
            )
            for name, values in aggregate.items()
        ]
        hotspots.sort(key=lambda item: (-item.total_ms, -item.maximum_ms, item.pass_name))
        return tuple(hotspots[:limit])

    def portable(self) -> Mapping[str, object]:
        return MappingProxyType(
            {
                "format": "swirengine.gpu-timing.capture",
                "format_version": self.format_version,
                "metadata": dict(self.metadata),
                "frames": [dict(frame.portable()) for frame in self.frames],
                "hotspots": [dict(item.portable()) for item in self.hotspots()],
            }
        )

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


@dataclass(slots=True)
class _PendingQuery:
    pass_name: str
    token: object | None
    status: str = "pending"
    milliseconds: float | None = None


@dataclass(slots=True)
class _PendingFrame:
    frame_index: int
    plan_fingerprint: str | None
    queries: list[_PendingQuery]


class GpuTimingRecorder:
    """Bounded non-blocking GPU pass timing and portable frame capture.

    The recorder never waits for a query. ``poll_ready`` asks the backend only for
    already-available results and leaves unresolved queries pending for a later call.
    """

    def __init__(
        self,
        provider: GpuTimingProvider | None = None,
        *,
        history: int = 240,
        max_pending_frames: int = 8,
        max_passes_per_frame: int = 512,
        max_pending_queries: int = 4096,
        strict_provider: bool = False,
    ) -> None:
        if provider is not None and not isinstance(provider, GpuTimingProvider):
            raise TypeError("provider must satisfy GpuTimingProvider")
        self.provider = provider
        self.history = _positive_int(history, label="history")
        self.max_pending_frames = _positive_int(
            max_pending_frames, label="max_pending_frames"
        )
        self.max_passes_per_frame = _positive_int(
            max_passes_per_frame, label="max_passes_per_frame"
        )
        self.max_pending_queries = _positive_int(
            max_pending_queries, label="max_pending_queries"
        )
        self.strict_provider = bool(strict_provider)
        self._frames: deque[GpuFrameTiming] = deque(maxlen=self.history)
        self._pending: deque[_PendingFrame] = deque()
        self._active_frame_index: int | None = None
        self._active_plan: RenderGraphPlan | None = None
        self._active_queries: list[_PendingQuery] = []
        self._active_names: set[str] = set()
        self._active_open: _PendingQuery | None = None
        self._plan_cursor = -1
        self._next_frame_index = 0
        self._submitted_queries = 0
        self._resolved_queries = 0
        self._unavailable_queries = 0
        self._provider_failures = 0
        self._dropped_frames = 0

    @property
    def active(self) -> bool:
        return self._active_frame_index is not None

    @property
    def frames(self) -> tuple[GpuFrameTiming, ...]:
        return tuple(self._frames)

    @property
    def latest(self) -> GpuFrameTiming | None:
        return self._frames[-1] if self._frames else None

    @property
    def pending_queries(self) -> int:
        return sum(
            1
            for frame in self._pending
            for query in frame.queries
            if query.status == "pending"
        )

    def diagnostics(self) -> GpuTimingDiagnostics:
        return GpuTimingDiagnostics(
            history_frames=len(self._frames),
            pending_frames=len(self._pending),
            pending_queries=self.pending_queries,
            submitted_queries=self._submitted_queries,
            resolved_queries=self._resolved_queries,
            unavailable_queries=self._unavailable_queries,
            provider_failures=self._provider_failures,
            dropped_frames=self._dropped_frames,
        )

    def begin_frame(
        self,
        plan: RenderGraphPlan | None = None,
        *,
        frame_index: int | None = None,
    ) -> int:
        if self.active:
            raise GpuTimingError("frame-active", "GPU timing frame is already active")
        if len(self._pending) >= self.max_pending_frames:
            raise GpuTimingError(
                "pending-frame-limit",
                "GPU timing pending frame limit reached; poll ready queries first",
            )
        if self.pending_queries >= self.max_pending_queries:
            raise GpuTimingError(
                "pending-query-limit",
                "GPU timing pending query limit reached; poll ready queries first",
            )
        if plan is not None and not isinstance(plan, RenderGraphPlan):
            raise TypeError("plan must be a RenderGraphPlan or None")
        if frame_index is None:
            frame_index = self._next_frame_index
        else:
            frame_index = _nonnegative_int(frame_index, label="frame_index")
        self._next_frame_index = max(self._next_frame_index, frame_index + 1)
        self._active_frame_index = frame_index
        self._active_plan = plan
        self._active_queries = []
        self._active_names = set()
        self._active_open = None
        self._plan_cursor = -1
        return frame_index

    def begin_pass(self, pass_name: str) -> None:
        if not self.active:
            raise GpuTimingError("frame-inactive", "begin_frame() must be called first")
        if self._active_open is not None:
            raise GpuTimingError("pass-active", "a GPU timing pass is already active")
        pass_name = _name(pass_name, label="pass_name")
        if pass_name in self._active_names:
            raise GpuTimingError(
                "duplicate-pass",
                f"GPU timing pass already recorded in this frame: {pass_name}",
            )
        if len(self._active_queries) >= self.max_passes_per_frame:
            raise GpuTimingError("pass-limit", "GPU timing pass-per-frame limit reached")
        if self.pending_queries + len(self._active_queries) >= self.max_pending_queries:
            raise GpuTimingError("pending-query-limit", "GPU timing pending query limit reached")
        self._validate_plan_order(pass_name)

        query = _PendingQuery(pass_name=pass_name, token=None)
        provider = self.provider
        if provider is None:
            query.status = "unavailable"
            self._unavailable_queries += 1
        else:
            try:
                token = provider.begin(self._active_frame_index or 0, pass_name)
            except Exception as exc:
                query.status = "failed"
                self._provider_failure(
                    "provider-begin-failed",
                    f"GPU timing provider begin failed for {pass_name}: {exc}",
                )
            else:
                if token is None:
                    query.status = "unavailable"
                    self._unavailable_queries += 1
                else:
                    query.token = token
                    self._submitted_queries += 1
        self._active_names.add(pass_name)
        self._active_open = query

    def end_pass(self) -> None:
        if not self.active or self._active_open is None:
            raise GpuTimingError("pass-inactive", "begin_pass() must be called first")
        query = self._active_open
        if query.status == "pending":
            assert query.token is not None
            assert self.provider is not None
            try:
                self.provider.end(query.token)
            except Exception as exc:
                query.status = "failed"
                query.token = None
                self._provider_failure(
                    "provider-end-failed",
                    f"GPU timing provider end failed for {query.pass_name}: {exc}",
                )
        self._active_queries.append(query)
        self._active_open = None

    def end_frame(self) -> None:
        if not self.active:
            raise GpuTimingError("frame-inactive", "no GPU timing frame is active")
        if self._active_open is not None:
            raise GpuTimingError("pass-active", "end the active GPU timing pass first")
        assert self._active_frame_index is not None
        plan_fingerprint = (
            None if self._active_plan is None else self._active_plan.fingerprint
        )
        pending = _PendingFrame(
            frame_index=self._active_frame_index,
            plan_fingerprint=plan_fingerprint,
            queries=list(self._active_queries),
        )
        self._pending.append(pending)
        self._active_frame_index = None
        self._active_plan = None
        self._active_queries = []
        self._active_names = set()
        self._plan_cursor = -1
        self._commit_terminal_frames()

    def poll_ready(self, *, max_queries: int = 1024) -> tuple[GpuFrameTiming, ...]:
        max_queries = _positive_int(max_queries, label="max_queries")
        provider = self.provider
        if provider is None:
            return self._commit_terminal_frames()
        polled = 0
        for frame in self._pending:
            for query in frame.queries:
                if query.status != "pending":
                    continue
                if polled >= max_queries:
                    return self._commit_terminal_frames()
                polled += 1
                assert query.token is not None
                try:
                    seconds = provider.poll(query.token)
                except Exception as exc:
                    query.status = "failed"
                    query.token = None
                    self._provider_failure(
                        "provider-poll-failed",
                        f"GPU timing provider poll failed for {query.pass_name}: {exc}",
                    )
                    continue
                if seconds is None:
                    continue
                if isinstance(seconds, bool) or not isinstance(seconds, (int, float)):
                    query.status = "failed"
                    query.token = None
                    self._provider_failure(
                        "provider-result",
                        f"GPU timing provider returned non-numeric result for {query.pass_name}",
                    )
                    continue
                seconds = float(seconds)
                if not math.isfinite(seconds) or seconds < 0.0:
                    query.status = "failed"
                    query.token = None
                    self._provider_failure(
                        "provider-result",
                        f"GPU timing provider returned invalid result for {query.pass_name}",
                    )
                    continue
                query.status = "ready"
                query.milliseconds = seconds * 1000.0
                query.token = None
                self._resolved_queries += 1
        return self._commit_terminal_frames()

    def record_into(self, performance: object, frame: GpuFrameTiming | None = None) -> int:
        if frame is None:
            frame = self.latest
        if frame is None:
            return 0
        record_timing = getattr(performance, "record_timing", None)
        set_counter = getattr(performance, "set_counter", None)
        if not callable(record_timing) or not callable(set_counter):
            raise TypeError(
                "performance must expose record_timing(domain, name, seconds) "
                "and set_counter(domain, name, value)"
            )
        count = 0
        for sample in frame.ready_samples:
            assert sample.milliseconds is not None
            record_timing("gpu", sample.pass_name, sample.milliseconds / 1000.0)
            count += 1
        set_counter("gpu", "ready_passes", count)
        set_counter("gpu", "provider_failures", frame.provider_failures)
        set_counter("gpu", "unavailable_queries", frame.unavailable_queries)
        set_counter("gpu", "frame_ms", frame.gpu_ms)
        return count

    def capture(self, metadata: Mapping[str, object] | None = None) -> GpuTimingCapture:
        items = () if metadata is None else tuple((str(k), str(v)) for k, v in metadata.items())
        return GpuTimingCapture(frames=self.frames, metadata=items)

    def clear(self) -> None:
        if self.active:
            raise GpuTimingError("frame-active", "cannot clear during an active GPU timing frame")
        if self._pending:
            raise GpuTimingError(
                "pending-queries",
                "cannot clear while GPU timing frames are pending",
            )
        self._frames.clear()
        self._submitted_queries = 0
        self._resolved_queries = 0
        self._unavailable_queries = 0
        self._provider_failures = 0
        self._dropped_frames = 0

    def _validate_plan_order(self, pass_name: str) -> None:
        plan = self._active_plan
        if plan is None:
            return
        try:
            position = plan.passes.index(pass_name)
        except ValueError as exc:
            raise GpuTimingError(
                "unknown-plan-pass",
                f"GPU timing pass is not active in the render plan: {pass_name}",
            ) from exc
        if position <= self._plan_cursor:
            raise GpuTimingError(
                "plan-order",
                "GPU timing passes must follow render-plan execution order",
            )
        self._plan_cursor = position

    def _provider_failure(self, code: str, message: str) -> None:
        self._provider_failures += 1
        if self.strict_provider:
            raise GpuTimingError(code, message)

    def _commit_terminal_frames(self) -> tuple[GpuFrameTiming, ...]:
        committed: list[GpuFrameTiming] = []
        while self._pending:
            pending = self._pending[0]
            if any(query.status == "pending" for query in pending.queries):
                break
            self._pending.popleft()
            samples = tuple(
                GpuPassTiming(
                    pass_name=query.pass_name,
                    status=query.status,
                    milliseconds=query.milliseconds,
                )
                for query in pending.queries
            )
            failures = sum(1 for query in pending.queries if query.status == "failed")
            unavailable = sum(
                1 for query in pending.queries if query.status == "unavailable"
            )
            frame = GpuFrameTiming(
                frame_index=pending.frame_index,
                plan_fingerprint=pending.plan_fingerprint,
                samples=samples,
                provider_failures=failures,
                unavailable_queries=unavailable,
            )
            if len(self._frames) == self.history:
                self._dropped_frames += 1
            self._frames.append(frame)
            committed.append(frame)
        return tuple(committed)
