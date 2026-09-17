from __future__ import annotations

import hashlib
import json
from collections import deque
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from types import MappingProxyType

from .render_resources18 import RenderResourceDescriptor


class TextureUploadError(RuntimeError):
    """Stable creator-facing error raised by the 1.8 upload pipeline."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def _positive_int(name: str, value: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{name} must be an integer")
    if value <= 0:
        raise ValueError(f"{name} must be greater than zero")
    return value


def _nonnegative_int(name: str, value: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{name} must be an integer")
    if value < 0:
        raise ValueError(f"{name} must be non-negative")
    return value


def _token(name: str, value: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{name} must be a string")
    value = value.strip()
    if not value:
        raise ValueError(f"{name} must not be empty")
    if len(value) > 128:
        raise ValueError(f"{name} must contain at most 128 characters")
    return value


def _priority(value: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError("priority must be an integer")
    return value


@dataclass(frozen=True, slots=True)
class TextureUploadRegion:
    """A rectangular layer subresource used by atlas and sprite updates."""

    x: int
    y: int
    width: int
    height: int
    layer: int = 0

    def __post_init__(self) -> None:
        object.__setattr__(self, "x", _nonnegative_int("x", self.x))
        object.__setattr__(self, "y", _nonnegative_int("y", self.y))
        object.__setattr__(self, "width", _positive_int("width", self.width))
        object.__setattr__(self, "height", _positive_int("height", self.height))
        object.__setattr__(self, "layer", _nonnegative_int("layer", self.layer))

    def validate_for(self, descriptor: RenderResourceDescriptor) -> None:
        if self.layer >= descriptor.layers:
            raise TextureUploadError("region-out-of-bounds", "upload layer exceeds texture layers")
        if self.x + self.width > descriptor.width:
            raise TextureUploadError("region-out-of-bounds", "upload region exceeds texture width")
        if self.y + self.height > descriptor.height:
            raise TextureUploadError("region-out-of-bounds", "upload region exceeds texture height")

    def portable(self) -> Mapping[str, int]:
        return MappingProxyType(
            {
                "x": self.x,
                "y": self.y,
                "width": self.width,
                "height": self.height,
                "layer": self.layer,
            }
        )


@dataclass(frozen=True, slots=True)
class TextureUpload:
    """Immutable upload work item. Payload bytes are snapshotted at enqueue time."""

    sequence: int
    texture_id: str
    descriptor: RenderResourceDescriptor
    payload: bytes
    digest: str
    region: TextureUploadRegion | None
    priority: int
    resident_bytes: int
    pinned: bool

    @property
    def byte_count(self) -> int:
        return len(self.payload)

    @property
    def partial(self) -> bool:
        return self.region is not None


@dataclass(frozen=True, slots=True)
class TextureResidency:
    texture_id: str
    bytes: int
    priority: int
    last_touch: int
    pinned: bool

    def portable(self) -> Mapping[str, int | str | bool]:
        return MappingProxyType(
            {
                "texture_id": self.texture_id,
                "bytes": self.bytes,
                "priority": self.priority,
                "last_touch": self.last_touch,
                "pinned": self.pinned,
            }
        )


@dataclass(frozen=True, slots=True)
class TextureUploadDiagnostics:
    queued_uploads: int
    queued_bytes: int
    resident_textures: int
    resident_bytes: int
    submitted_uploads: int
    submitted_bytes: int
    full_uploads: int
    partial_uploads: int
    duplicate_skips: int
    duplicate_skip_bytes: int
    evictions: int
    evicted_bytes: int
    flushes: int
    deferred_uploads: int
    backpressure_rejections: int
    submit_failures: int
    eviction_failures: int
    queue_high_water_uploads: int
    queue_high_water_bytes: int

    def portable(self) -> Mapping[str, int]:
        return MappingProxyType(
            {
                field: getattr(self, field)
                for field in self.__dataclass_fields__
            }
        )


@dataclass(slots=True)
class _Counters:
    submitted_uploads: int = 0
    submitted_bytes: int = 0
    full_uploads: int = 0
    partial_uploads: int = 0
    duplicate_skips: int = 0
    duplicate_skip_bytes: int = 0
    evictions: int = 0
    evicted_bytes: int = 0
    flushes: int = 0
    deferred_uploads: int = 0
    backpressure_rejections: int = 0
    submit_failures: int = 0
    eviction_failures: int = 0
    queue_high_water_uploads: int = 0
    queue_high_water_bytes: int = 0


class TextureUploadQueue:
    """Deterministic bounded staging queue with logical texture residency tracking.

    The queue is renderer-independent. ``submit`` performs the backend upload, while
    the optional ``evict`` callback releases a backend texture when logical residency
    pressure selects it for eviction. Neither callback is invoked while enqueueing.
    """

    def __init__(
        self,
        *,
        submit: Callable[[TextureUpload], None],
        evict: Callable[[str], None] | None = None,
        max_pending_uploads: int = 256,
        max_pending_bytes: int = 64 * 1024 * 1024,
        max_uploads_per_flush: int = 64,
        max_bytes_per_flush: int = 16 * 1024 * 1024,
        max_resident_textures: int = 1024,
        max_resident_bytes: int = 512 * 1024 * 1024,
    ) -> None:
        if not callable(submit):
            raise TypeError("submit must be callable")
        if evict is not None and not callable(evict):
            raise TypeError("evict must be callable")
        self._submit = submit
        self._evict = evict
        self.max_pending_uploads = _positive_int("max_pending_uploads", max_pending_uploads)
        self.max_pending_bytes = _positive_int("max_pending_bytes", max_pending_bytes)
        self.max_uploads_per_flush = _positive_int(
            "max_uploads_per_flush", max_uploads_per_flush
        )
        self.max_bytes_per_flush = _positive_int("max_bytes_per_flush", max_bytes_per_flush)
        self.max_resident_textures = _positive_int(
            "max_resident_textures", max_resident_textures
        )
        self.max_resident_bytes = _positive_int("max_resident_bytes", max_resident_bytes)
        self._queue: deque[TextureUpload] = deque()
        self._queued_bytes = 0
        self._sequence = 0
        self._touch_sequence = 0
        self._residency: dict[str, TextureResidency] = {}
        self._digests: dict[tuple[object, ...], str] = {}
        self._counters = _Counters()

    @property
    def queued_uploads(self) -> int:
        return len(self._queue)

    @property
    def queued_bytes(self) -> int:
        return self._queued_bytes

    def enqueue(
        self,
        texture_id: str,
        descriptor: RenderResourceDescriptor,
        payload: bytes | bytearray | memoryview,
        *,
        region: TextureUploadRegion | None = None,
        priority: int = 0,
        resident_bytes: int | None = None,
        pinned: bool = False,
    ) -> TextureUpload:
        texture_id = _token("texture_id", texture_id)
        if not isinstance(descriptor, RenderResourceDescriptor):
            raise TypeError("descriptor must be a RenderResourceDescriptor")
        if descriptor.kind != "texture":
            raise TextureUploadError("not-a-texture", "texture uploads require a texture descriptor")
        if region is not None:
            if not isinstance(region, TextureUploadRegion):
                raise TypeError("region must be a TextureUploadRegion or None")
            region.validate_for(descriptor)
        if not isinstance(payload, (bytes, bytearray, memoryview)):
            raise TypeError("payload must be bytes-like")

        payload_bytes = payload.nbytes if isinstance(payload, memoryview) else len(payload)
        if payload_bytes <= 0:
            raise TextureUploadError("empty-upload", "texture upload payload must not be empty")
        if payload_bytes > self.max_bytes_per_flush:
            raise TextureUploadError(
                "upload-too-large",
                "single upload exceeds the configured per-flush byte budget",
            )
        if len(self._queue) >= self.max_pending_uploads:
            self._counters.backpressure_rejections += 1
            raise TextureUploadError("queue-full", "texture upload queue is full")
        if self._queued_bytes + payload_bytes > self.max_pending_bytes:
            self._counters.backpressure_rejections += 1
            raise TextureUploadError("queue-bytes-full", "texture upload byte queue is full")

        if resident_bytes is None:
            resident_bytes = descriptor.size_bytes or payload_bytes
        resident_bytes = _positive_int("resident_bytes", resident_bytes)
        if resident_bytes > self.max_resident_bytes:
            raise TextureUploadError(
                "texture-too-large",
                "texture residency exceeds the configured resident byte budget",
            )
        priority = _priority(priority)
        if not isinstance(pinned, bool):
            raise TypeError("pinned must be a boolean")

        snapshot = bytes(payload)
        if len(snapshot) != payload_bytes:
            raise TextureUploadError(
                "payload-size-mismatch",
                "bytes-like payload changed size while it was being snapshotted",
            )

        self._sequence += 1
        upload = TextureUpload(
            sequence=self._sequence,
            texture_id=texture_id,
            descriptor=descriptor,
            payload=snapshot,
            digest=hashlib.sha256(snapshot).hexdigest(),
            region=region,
            priority=priority,
            resident_bytes=resident_bytes,
            pinned=pinned,
        )
        self._queue.append(upload)
        self._queued_bytes += upload.byte_count
        self._counters.queue_high_water_uploads = max(
            self._counters.queue_high_water_uploads, len(self._queue)
        )
        self._counters.queue_high_water_bytes = max(
            self._counters.queue_high_water_bytes, self._queued_bytes
        )
        return upload

    def flush(self) -> int:
        """Submit a bounded FIFO batch and return the number of backend submissions."""

        self._counters.flushes += 1
        submitted = 0
        consumed_bytes = 0
        processed = 0
        while self._queue and processed < self.max_uploads_per_flush:
            upload = self._queue[0]
            if consumed_bytes + upload.byte_count > self.max_bytes_per_flush:
                break
            cache_key = self._digest_key(upload)
            resident = self._residency.get(upload.texture_id)
            if resident is not None and self._digests.get(cache_key) == upload.digest:
                self._pop_head(upload)
                self._touch_resident(upload)
                self._counters.duplicate_skips += 1
                self._counters.duplicate_skip_bytes += upload.byte_count
                consumed_bytes += upload.byte_count
                processed += 1
                continue

            self._ensure_residency_capacity(upload)
            try:
                self._submit(upload)
            except Exception as exc:
                self._counters.submit_failures += 1
                raise TextureUploadError("submit-failed", f"texture upload failed: {exc}") from exc

            self._pop_head(upload)
            self._commit_residency(upload)
            self._commit_digest(upload)
            self._counters.submitted_uploads += 1
            self._counters.submitted_bytes += upload.byte_count
            if upload.partial:
                self._counters.partial_uploads += 1
            else:
                self._counters.full_uploads += 1
            submitted += 1
            consumed_bytes += upload.byte_count
            processed += 1

        if self._queue:
            self._counters.deferred_uploads += len(self._queue)
        return submitted

    def set_residency_priority(self, texture_id: str, priority: int) -> None:
        texture_id = _token("texture_id", texture_id)
        entry = self._require_resident(texture_id)
        self._residency[texture_id] = TextureResidency(
            texture_id=entry.texture_id,
            bytes=entry.bytes,
            priority=_priority(priority),
            last_touch=entry.last_touch,
            pinned=entry.pinned,
        )

    def pin(self, texture_id: str, pinned: bool = True) -> None:
        texture_id = _token("texture_id", texture_id)
        if not isinstance(pinned, bool):
            raise TypeError("pinned must be a boolean")
        entry = self._require_resident(texture_id)
        self._residency[texture_id] = TextureResidency(
            texture_id=entry.texture_id,
            bytes=entry.bytes,
            priority=entry.priority,
            last_touch=entry.last_touch,
            pinned=pinned,
        )

    def mark_used(self, texture_id: str) -> None:
        texture_id = _token("texture_id", texture_id)
        entry = self._require_resident(texture_id)
        self._touch_sequence += 1
        self._residency[texture_id] = TextureResidency(
            texture_id=entry.texture_id,
            bytes=entry.bytes,
            priority=entry.priority,
            last_touch=self._touch_sequence,
            pinned=entry.pinned,
        )

    def evict_texture(self, texture_id: str) -> None:
        texture_id = _token("texture_id", texture_id)
        entry = self._require_resident(texture_id)
        if entry.pinned:
            raise TextureUploadError("texture-pinned", "pinned texture cannot be evicted")
        self._evict_entry(entry)

    def residency(self) -> tuple[TextureResidency, ...]:
        return tuple(self._residency[key] for key in sorted(self._residency))

    def diagnostics(self) -> TextureUploadDiagnostics:
        resident_bytes = sum(entry.bytes for entry in self._residency.values())
        return TextureUploadDiagnostics(
            queued_uploads=len(self._queue),
            queued_bytes=self._queued_bytes,
            resident_textures=len(self._residency),
            resident_bytes=resident_bytes,
            submitted_uploads=self._counters.submitted_uploads,
            submitted_bytes=self._counters.submitted_bytes,
            full_uploads=self._counters.full_uploads,
            partial_uploads=self._counters.partial_uploads,
            duplicate_skips=self._counters.duplicate_skips,
            duplicate_skip_bytes=self._counters.duplicate_skip_bytes,
            evictions=self._counters.evictions,
            evicted_bytes=self._counters.evicted_bytes,
            flushes=self._counters.flushes,
            deferred_uploads=self._counters.deferred_uploads,
            backpressure_rejections=self._counters.backpressure_rejections,
            submit_failures=self._counters.submit_failures,
            eviction_failures=self._counters.eviction_failures,
            queue_high_water_uploads=self._counters.queue_high_water_uploads,
            queue_high_water_bytes=self._counters.queue_high_water_bytes,
        )

    def state_fingerprint(self) -> str:
        state = {
            "queue": [
                {
                    "sequence": upload.sequence,
                    "texture_id": upload.texture_id,
                    "descriptor": dict(upload.descriptor.portable()),
                    "digest": upload.digest,
                    "bytes": upload.byte_count,
                    "region": dict(upload.region.portable()) if upload.region else None,
                    "priority": upload.priority,
                    "resident_bytes": upload.resident_bytes,
                    "pinned": upload.pinned,
                }
                for upload in self._queue
            ],
            "residency": [dict(entry.portable()) for entry in self.residency()],
            "digests": [
                {"key": list(key), "digest": digest}
                for key, digest in sorted(self._digests.items(), key=lambda item: repr(item[0]))
            ],
            "diagnostics": dict(self.diagnostics().portable()),
        }
        encoded = json.dumps(state, sort_keys=True, separators=(",", ":")).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    def _require_resident(self, texture_id: str) -> TextureResidency:
        try:
            return self._residency[texture_id]
        except KeyError as exc:
            raise TextureUploadError("not-resident", f"texture is not resident: {texture_id}") from exc

    def _pop_head(self, upload: TextureUpload) -> None:
        current = self._queue.popleft()
        if current is not upload:
            raise RuntimeError("texture upload queue order was corrupted")
        self._queued_bytes -= upload.byte_count

    def _touch_resident(self, upload: TextureUpload) -> None:
        current = self._residency[upload.texture_id]
        self._touch_sequence += 1
        self._residency[upload.texture_id] = TextureResidency(
            texture_id=current.texture_id,
            bytes=current.bytes,
            priority=max(current.priority, upload.priority),
            last_touch=self._touch_sequence,
            pinned=current.pinned or upload.pinned,
        )

    def _commit_residency(self, upload: TextureUpload) -> None:
        self._touch_sequence += 1
        current = self._residency.get(upload.texture_id)
        priority = upload.priority if current is None else max(current.priority, upload.priority)
        pinned = upload.pinned if current is None else current.pinned or upload.pinned
        self._residency[upload.texture_id] = TextureResidency(
            texture_id=upload.texture_id,
            bytes=upload.resident_bytes,
            priority=priority,
            last_touch=self._touch_sequence,
            pinned=pinned,
        )

    def _ensure_residency_capacity(self, upload: TextureUpload) -> None:
        current = self._residency.get(upload.texture_id)
        current_bytes = 0 if current is None else current.bytes
        added_texture = 1 if current is None else 0
        required_bytes = upload.resident_bytes - current_bytes
        while (
            len(self._residency) + added_texture > self.max_resident_textures
            or self._resident_bytes() + required_bytes > self.max_resident_bytes
        ):
            candidates = [
                entry
                for entry in self._residency.values()
                if not entry.pinned and entry.texture_id != upload.texture_id
            ]
            if not candidates:
                raise TextureUploadError(
                    "residency-exhausted",
                    "texture residency budget is exhausted by retained or pinned textures",
                )
            victim = min(
                candidates,
                key=lambda entry: (entry.priority, entry.last_touch, entry.texture_id),
            )
            self._evict_entry(victim)

    def _resident_bytes(self) -> int:
        return sum(entry.bytes for entry in self._residency.values())

    def _evict_entry(self, entry: TextureResidency) -> None:
        try:
            if self._evict is not None:
                self._evict(entry.texture_id)
        except Exception as exc:
            self._counters.eviction_failures += 1
            raise TextureUploadError("evict-failed", f"texture eviction failed: {exc}") from exc
        del self._residency[entry.texture_id]
        self._clear_texture_digests(entry.texture_id)
        self._counters.evictions += 1
        self._counters.evicted_bytes += entry.bytes

    @staticmethod
    def _descriptor_key(
        descriptor: RenderResourceDescriptor, resident_bytes: int
    ) -> tuple[object, ...]:
        return (
            descriptor.kind,
            descriptor.format,
            descriptor.width,
            descriptor.height,
            descriptor.layers,
            descriptor.samples,
            descriptor.usage,
            descriptor.size_bytes,
            resident_bytes,
        )

    @classmethod
    def _digest_key(cls, upload: TextureUpload) -> tuple[object, ...]:
        descriptor_key = cls._descriptor_key(upload.descriptor, upload.resident_bytes)
        if upload.region is None:
            return (upload.texture_id, "full", *descriptor_key)
        return (
            upload.texture_id,
            "region",
            upload.region.layer,
            upload.region.x,
            upload.region.y,
            upload.region.width,
            upload.region.height,
            *descriptor_key,
        )

    def _commit_digest(self, upload: TextureUpload) -> None:
        if upload.region is None:
            self._clear_texture_digests(upload.texture_id)
        else:
            self._clear_texture_full_digests(upload.texture_id)
            self._invalidate_overlapping_regions(upload.texture_id, upload.region)
        self._digests[self._digest_key(upload)] = upload.digest

    def _clear_texture_digests(self, texture_id: str) -> None:
        for key in [key for key in self._digests if key[0] == texture_id]:
            del self._digests[key]

    def _clear_texture_full_digests(self, texture_id: str) -> None:
        for key in [
            key
            for key in self._digests
            if key[0] == texture_id and len(key) >= 2 and key[1] == "full"
        ]:
            del self._digests[key]

    def _invalidate_overlapping_regions(
        self, texture_id: str, region: TextureUploadRegion
    ) -> None:
        for key in list(self._digests):
            if len(key) < 7 or key[0] != texture_id or key[1] != "region":
                continue
            _, _, layer, x, y, width, height, *_ = key
            if layer != region.layer:
                continue
            if (
                x < region.x + region.width
                and region.x < x + width
                and y < region.y + region.height
                and region.y < y + height
            ):
                del self._digests[key]
