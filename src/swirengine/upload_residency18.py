from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType


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


def _integer(value: int, *, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{label} must be an integer")
    return value


def _token(value: str, *, label: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{label} must be a string")
    result = value.strip()
    if not result:
        raise ValueError(f"{label} must not be empty")
    if len(result) > 256:
        raise ValueError(f"{label} must contain at most 256 characters")
    return result


class UploadResidencyError(RuntimeError):
    """Stable creator-facing upload/residency planning failure."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


@dataclass(frozen=True, slots=True)
class UploadRequest:
    """Portable metadata for one logical texture/buffer upload."""

    asset_id: str
    revision: int
    size_bytes: int
    priority: int = 0
    kind: str = "texture"

    def __post_init__(self) -> None:
        object.__setattr__(self, "asset_id", _token(self.asset_id, label="asset_id"))
        object.__setattr__(self, "revision", _nonnegative_int(self.revision, label="revision"))
        object.__setattr__(self, "size_bytes", _positive_int(self.size_bytes, label="size_bytes"))
        object.__setattr__(self, "priority", _integer(self.priority, label="priority"))
        object.__setattr__(self, "kind", _token(self.kind, label="kind"))

    def portable(self) -> Mapping[str, object]:
        return MappingProxyType(
            {
                "asset_id": self.asset_id,
                "revision": self.revision,
                "size_bytes": self.size_bytes,
                "priority": self.priority,
                "kind": self.kind,
            }
        )


@dataclass(frozen=True, slots=True)
class UploadBatch:
    batch_id: int
    requests: tuple[UploadRequest, ...]
    total_bytes: int

    def portable(self) -> Mapping[str, object]:
        return MappingProxyType(
            {
                "batch_id": self.batch_id,
                "requests": tuple(dict(request.portable()) for request in self.requests),
                "total_bytes": self.total_bytes,
            }
        )


@dataclass(frozen=True, slots=True)
class UploadQueueDiagnostics:
    pending_requests: int
    pending_bytes: int
    staged_batches: int
    staged_requests: int
    staged_bytes: int
    outstanding_requests: int
    outstanding_bytes: int
    peak_outstanding_requests: int
    peak_outstanding_bytes: int
    enqueued: int
    duplicate_suppressed: int
    superseded: int
    staged: int
    completed: int
    aborted: int
    backpressure_failures: int
    stale_batch_failures: int

    def portable(self) -> Mapping[str, int]:
        return MappingProxyType(
            {
                "pending_requests": self.pending_requests,
                "pending_bytes": self.pending_bytes,
                "staged_batches": self.staged_batches,
                "staged_requests": self.staged_requests,
                "staged_bytes": self.staged_bytes,
                "outstanding_requests": self.outstanding_requests,
                "outstanding_bytes": self.outstanding_bytes,
                "peak_outstanding_requests": self.peak_outstanding_requests,
                "peak_outstanding_bytes": self.peak_outstanding_bytes,
                "enqueued": self.enqueued,
                "duplicate_suppressed": self.duplicate_suppressed,
                "superseded": self.superseded,
                "staged": self.staged,
                "completed": self.completed,
                "aborted": self.aborted,
                "backpressure_failures": self.backpressure_failures,
                "stale_batch_failures": self.stale_batch_failures,
            }
        )


@dataclass(slots=True)
class _PendingUpload:
    request: UploadRequest
    sequence: int


@dataclass(slots=True)
class _StagedUploadBatch:
    public: UploadBatch
    items: tuple[_PendingUpload, ...]


class BoundedUploadQueue:
    """Deterministic bounded upload queue with explicit staging back-pressure.

    The queue stores metadata only. Creator/backend code owns upload payloads and GPU commands. A
    logical asset can have one pending revision while older revisions are staged; equal/older
    duplicates are suppressed, and a newer pending revision supersedes an older pending revision.
    """

    def __init__(
        self,
        *,
        max_outstanding_requests: int = 2048,
        max_outstanding_bytes: int = 512 * 1024 * 1024,
        max_staging_bytes: int = 64 * 1024 * 1024,
        max_batch_bytes: int = 16 * 1024 * 1024,
        max_batch_requests: int = 128,
    ) -> None:
        self.max_outstanding_requests = _positive_int(
            max_outstanding_requests, label="max_outstanding_requests"
        )
        self.max_outstanding_bytes = _positive_int(
            max_outstanding_bytes, label="max_outstanding_bytes"
        )
        self.max_staging_bytes = _positive_int(max_staging_bytes, label="max_staging_bytes")
        self.max_batch_bytes = _positive_int(max_batch_bytes, label="max_batch_bytes")
        self.max_batch_requests = _positive_int(max_batch_requests, label="max_batch_requests")
        if self.max_batch_bytes > self.max_staging_bytes:
            raise ValueError("max_batch_bytes must be <= max_staging_bytes")

        self._pending: dict[str, _PendingUpload] = {}
        self._staged: dict[int, _StagedUploadBatch] = {}
        self._next_sequence = 0
        self._next_batch_id = 1
        self._outstanding_requests = 0
        self._outstanding_bytes = 0
        self._staged_bytes = 0
        self._peak_outstanding_requests = 0
        self._peak_outstanding_bytes = 0
        self._enqueued = 0
        self._duplicate_suppressed = 0
        self._superseded = 0
        self._staged_count = 0
        self._completed = 0
        self._aborted = 0
        self._backpressure_failures = 0
        self._stale_batch_failures = 0

    def diagnostics(self) -> UploadQueueDiagnostics:
        pending_bytes = sum(item.request.size_bytes for item in self._pending.values())
        staged_requests = sum(len(batch.items) for batch in self._staged.values())
        return UploadQueueDiagnostics(
            pending_requests=len(self._pending),
            pending_bytes=pending_bytes,
            staged_batches=len(self._staged),
            staged_requests=staged_requests,
            staged_bytes=self._staged_bytes,
            outstanding_requests=self._outstanding_requests,
            outstanding_bytes=self._outstanding_bytes,
            peak_outstanding_requests=self._peak_outstanding_requests,
            peak_outstanding_bytes=self._peak_outstanding_bytes,
            enqueued=self._enqueued,
            duplicate_suppressed=self._duplicate_suppressed,
            superseded=self._superseded,
            staged=self._staged_count,
            completed=self._completed,
            aborted=self._aborted,
            backpressure_failures=self._backpressure_failures,
            stale_batch_failures=self._stale_batch_failures,
        )

    def pending_snapshot(self) -> tuple[UploadRequest, ...]:
        return tuple(
            item.request
            for item in sorted(
                self._pending.values(),
                key=lambda item: (-item.request.priority, item.sequence, item.request.asset_id),
            )
        )

    def enqueue(self, request: UploadRequest) -> bool:
        if not isinstance(request, UploadRequest):
            raise TypeError("request must be an UploadRequest")
        if request.size_bytes > self.max_outstanding_bytes:
            self._backpressure_failures += 1
            raise UploadResidencyError(
                "request-too-large",
                "upload request exceeds the total outstanding byte budget",
            )

        latest_revision = self._latest_revision(request.asset_id)
        current = self._pending.get(request.asset_id)
        if latest_revision is not None and request.revision <= latest_revision:
            self._duplicate_suppressed += 1
            return False

        if current is not None:
            next_bytes = self._outstanding_bytes - current.request.size_bytes + request.size_bytes
            if next_bytes > self.max_outstanding_bytes:
                self._backpressure_failures += 1
                raise UploadResidencyError(
                    "outstanding-bytes",
                    "superseding upload would exceed the outstanding byte budget",
                )
            self._pending[request.asset_id] = _PendingUpload(request, current.sequence)
            self._outstanding_bytes = next_bytes
            self._enqueued += 1
            self._superseded += 1
            self._record_peak()
            return True

        if self._outstanding_requests + 1 > self.max_outstanding_requests:
            self._backpressure_failures += 1
            raise UploadResidencyError(
                "outstanding-requests",
                "upload request count budget is exhausted",
            )
        if self._outstanding_bytes + request.size_bytes > self.max_outstanding_bytes:
            self._backpressure_failures += 1
            raise UploadResidencyError(
                "outstanding-bytes",
                "upload byte budget is exhausted",
            )

        self._pending[request.asset_id] = _PendingUpload(request, self._next_sequence)
        self._next_sequence += 1
        self._outstanding_requests += 1
        self._outstanding_bytes += request.size_bytes
        self._enqueued += 1
        self._record_peak()
        return True

    def stage_batch(
        self,
        *,
        max_bytes: int | None = None,
        max_requests: int | None = None,
    ) -> UploadBatch | None:
        if not self._pending:
            return None
        byte_limit = self.max_batch_bytes if max_bytes is None else _positive_int(max_bytes, label="max_bytes")
        request_limit = (
            self.max_batch_requests
            if max_requests is None
            else _positive_int(max_requests, label="max_requests")
        )
        byte_limit = min(byte_limit, self.max_batch_bytes)
        request_limit = min(request_limit, self.max_batch_requests)
        available_staging = self.max_staging_bytes - self._staged_bytes
        byte_limit = min(byte_limit, available_staging)
        if byte_limit < 1:
            self._backpressure_failures += 1
            raise UploadResidencyError("staging-backpressure", "staging byte budget is exhausted")

        ordered = sorted(
            self._pending.values(),
            key=lambda item: (-item.request.priority, item.sequence, item.request.asset_id),
        )
        selected: list[_PendingUpload] = []
        selected_bytes = 0
        for item in ordered:
            if len(selected) >= request_limit:
                break
            if selected_bytes + item.request.size_bytes > byte_limit:
                continue
            selected.append(item)
            selected_bytes += item.request.size_bytes

        if not selected:
            self._backpressure_failures += 1
            raise UploadResidencyError(
                "staging-backpressure",
                "no pending upload fits the current staging/batch budget",
            )

        for item in selected:
            del self._pending[item.request.asset_id]
        batch_id = self._next_batch_id
        self._next_batch_id += 1
        public = UploadBatch(
            batch_id=batch_id,
            requests=tuple(item.request for item in selected),
            total_bytes=selected_bytes,
        )
        self._staged[batch_id] = _StagedUploadBatch(public, tuple(selected))
        self._staged_bytes += selected_bytes
        self._staged_count += len(selected)
        return public

    def complete_batch(self, batch_id: int) -> UploadBatch:
        staged = self._pop_batch(batch_id)
        self._outstanding_requests -= len(staged.items)
        self._outstanding_bytes -= staged.public.total_bytes
        self._completed += 1
        return staged.public

    def abort_batch(self, batch_id: int) -> UploadBatch:
        staged = self._pop_batch(batch_id)
        for item in staged.items:
            current = self._pending.get(item.request.asset_id)
            if current is None:
                self._pending[item.request.asset_id] = item
                continue
            if current.request.revision > item.request.revision:
                self._outstanding_requests -= 1
                self._outstanding_bytes -= item.request.size_bytes
                self._superseded += 1
                continue
            # This should be unreachable because enqueue only accepts strictly newer revisions.
            raise RuntimeError("internal error: staged upload revision ordering was violated")
        self._aborted += 1
        return staged.public

    def _latest_revision(self, asset_id: str) -> int | None:
        revisions: list[int] = []
        pending = self._pending.get(asset_id)
        if pending is not None:
            revisions.append(pending.request.revision)
        for batch in self._staged.values():
            for item in batch.items:
                if item.request.asset_id == asset_id:
                    revisions.append(item.request.revision)
        return max(revisions, default=None)

    def _pop_batch(self, batch_id: int) -> _StagedUploadBatch:
        batch_id = _positive_int(batch_id, label="batch_id")
        staged = self._staged.pop(batch_id, None)
        if staged is None:
            self._stale_batch_failures += 1
            raise UploadResidencyError("stale-batch", "upload batch is unknown or already completed")
        self._staged_bytes -= staged.public.total_bytes
        return staged

    def _record_peak(self) -> None:
        self._peak_outstanding_requests = max(
            self._peak_outstanding_requests, self._outstanding_requests
        )
        self._peak_outstanding_bytes = max(self._peak_outstanding_bytes, self._outstanding_bytes)


@dataclass(frozen=True, slots=True)
class ResidencyEntry:
    asset_id: str
    revision: int
    size_bytes: int
    priority: int
    pinned: bool
    last_used_sequence: int

    def portable(self) -> Mapping[str, object]:
        return MappingProxyType(
            {
                "asset_id": self.asset_id,
                "revision": self.revision,
                "size_bytes": self.size_bytes,
                "priority": self.priority,
                "pinned": self.pinned,
                "last_used_sequence": self.last_used_sequence,
            }
        )


@dataclass(frozen=True, slots=True)
class ResidencyAdmission:
    admitted: bool
    replaced: bool
    evicted: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ResidencyDiagnostics:
    resident_resources: int
    resident_bytes: int
    pinned_resources: int
    peak_resident_resources: int
    peak_resident_bytes: int
    admissions: int
    duplicate_suppressed: int
    replacements: int
    evictions: int
    touches: int
    pressure_failures: int

    def portable(self) -> Mapping[str, int]:
        return MappingProxyType(
            {
                "resident_resources": self.resident_resources,
                "resident_bytes": self.resident_bytes,
                "pinned_resources": self.pinned_resources,
                "peak_resident_resources": self.peak_resident_resources,
                "peak_resident_bytes": self.peak_resident_bytes,
                "admissions": self.admissions,
                "duplicate_suppressed": self.duplicate_suppressed,
                "replacements": self.replacements,
                "evictions": self.evictions,
                "touches": self.touches,
                "pressure_failures": self.pressure_failures,
            }
        )


class TextureResidencyManager:
    """Deterministic metadata-only residency planner for uploaded resources.

    Eviction prefers the lowest creator priority, then the least-recently-used entry, then asset id.
    Pinned entries are never selected. A lower-priority incoming request cannot evict a higher-priority
    resident entry; if no eligible set can satisfy both budgets, admission fails atomically.
    """

    def __init__(
        self,
        *,
        max_resources: int = 4096,
        max_bytes: int = 1024 * 1024 * 1024,
    ) -> None:
        self.max_resources = _positive_int(max_resources, label="max_resources")
        self.max_bytes = _positive_int(max_bytes, label="max_bytes")
        self._entries: dict[str, ResidencyEntry] = {}
        self._use_sequence = 0
        self._resident_bytes = 0
        self._peak_resident_resources = 0
        self._peak_resident_bytes = 0
        self._admissions = 0
        self._duplicate_suppressed = 0
        self._replacements = 0
        self._evictions = 0
        self._touches = 0
        self._pressure_failures = 0

    def diagnostics(self) -> ResidencyDiagnostics:
        return ResidencyDiagnostics(
            resident_resources=len(self._entries),
            resident_bytes=self._resident_bytes,
            pinned_resources=sum(1 for entry in self._entries.values() if entry.pinned),
            peak_resident_resources=self._peak_resident_resources,
            peak_resident_bytes=self._peak_resident_bytes,
            admissions=self._admissions,
            duplicate_suppressed=self._duplicate_suppressed,
            replacements=self._replacements,
            evictions=self._evictions,
            touches=self._touches,
            pressure_failures=self._pressure_failures,
        )

    def snapshot(self) -> tuple[ResidencyEntry, ...]:
        return tuple(self._entries[name] for name in sorted(self._entries))

    def resident_revision(self, asset_id: str) -> int | None:
        asset_id = _token(asset_id, label="asset_id")
        entry = self._entries.get(asset_id)
        return None if entry is None else entry.revision

    def admit(self, request: UploadRequest, *, pinned: bool = False) -> ResidencyAdmission:
        if not isinstance(request, UploadRequest):
            raise TypeError("request must be an UploadRequest")
        if not isinstance(pinned, bool):
            raise TypeError("pinned must be a bool")
        if request.size_bytes > self.max_bytes:
            self._pressure_failures += 1
            raise UploadResidencyError(
                "residency-resource-too-large",
                "resource exceeds the residency byte budget",
            )

        current = self._entries.get(request.asset_id)
        if current is not None and request.revision <= current.revision:
            self._duplicate_suppressed += 1
            return ResidencyAdmission(False, False, ())

        base_count = len(self._entries) - (1 if current is not None else 0)
        base_bytes = self._resident_bytes - (current.size_bytes if current is not None else 0)
        needed_count = base_count + 1
        needed_bytes = base_bytes + request.size_bytes
        candidates = sorted(
            (
                entry
                for entry in self._entries.values()
                if entry.asset_id != request.asset_id
                and not entry.pinned
                and entry.priority <= request.priority
            ),
            key=lambda entry: (entry.priority, entry.last_used_sequence, entry.asset_id),
        )
        selected: list[ResidencyEntry] = []
        for entry in candidates:
            if needed_count <= self.max_resources and needed_bytes <= self.max_bytes:
                break
            selected.append(entry)
            needed_count -= 1
            needed_bytes -= entry.size_bytes

        if needed_count > self.max_resources or needed_bytes > self.max_bytes:
            self._pressure_failures += 1
            raise UploadResidencyError(
                "residency-pressure",
                "resident budgets cannot admit the resource without protected/higher-priority eviction",
            )

        for entry in selected:
            del self._entries[entry.asset_id]
            self._resident_bytes -= entry.size_bytes
        self._evictions += len(selected)

        replaced = current is not None
        if current is not None:
            self._resident_bytes -= current.size_bytes
            self._replacements += 1
        next_entry = ResidencyEntry(
            asset_id=request.asset_id,
            revision=request.revision,
            size_bytes=request.size_bytes,
            priority=request.priority,
            pinned=pinned,
            last_used_sequence=self._use_sequence,
        )
        self._use_sequence += 1
        self._entries[request.asset_id] = next_entry
        self._resident_bytes += request.size_bytes
        self._admissions += 1
        self._peak_resident_resources = max(self._peak_resident_resources, len(self._entries))
        self._peak_resident_bytes = max(self._peak_resident_bytes, self._resident_bytes)
        return ResidencyAdmission(True, replaced, tuple(entry.asset_id for entry in selected))

    def touch(self, asset_id: str) -> bool:
        asset_id = _token(asset_id, label="asset_id")
        entry = self._entries.get(asset_id)
        if entry is None:
            return False
        self._entries[asset_id] = ResidencyEntry(
            asset_id=entry.asset_id,
            revision=entry.revision,
            size_bytes=entry.size_bytes,
            priority=entry.priority,
            pinned=entry.pinned,
            last_used_sequence=self._use_sequence,
        )
        self._use_sequence += 1
        self._touches += 1
        return True

    def set_pinned(self, asset_id: str, pinned: bool) -> bool:
        asset_id = _token(asset_id, label="asset_id")
        if not isinstance(pinned, bool):
            raise TypeError("pinned must be a bool")
        entry = self._entries.get(asset_id)
        if entry is None:
            return False
        self._entries[asset_id] = ResidencyEntry(
            asset_id=entry.asset_id,
            revision=entry.revision,
            size_bytes=entry.size_bytes,
            priority=entry.priority,
            pinned=pinned,
            last_used_sequence=entry.last_used_sequence,
        )
        return True

    def evict(self, asset_id: str, *, force: bool = False) -> bool:
        asset_id = _token(asset_id, label="asset_id")
        if not isinstance(force, bool):
            raise TypeError("force must be a bool")
        entry = self._entries.get(asset_id)
        if entry is None:
            return False
        if entry.pinned and not force:
            raise UploadResidencyError("resident-pinned", "pinned resident resource cannot be evicted")
        del self._entries[asset_id]
        self._resident_bytes -= entry.size_bytes
        self._evictions += 1
        return True


__all__ = [
    "BoundedUploadQueue",
    "ResidencyAdmission",
    "ResidencyDiagnostics",
    "ResidencyEntry",
    "TextureResidencyManager",
    "UploadBatch",
    "UploadQueueDiagnostics",
    "UploadRequest",
    "UploadResidencyError",
]
