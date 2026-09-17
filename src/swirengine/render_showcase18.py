from __future__ import annotations

import hashlib
import json
from collections import deque
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any

from .render_resources18 import (
    RenderResourceDescriptor,
    RenderResourceHandle,
    RenderResourcePoolError,
    TransientRenderResourcePool,
)
from .render_uploads18 import TextureUploadError, TextureUploadQueue
from .renderer2_bridge18 import Renderer2CompatibilityBridge


class RenderShowcaseError(RuntimeError):
    """Stable failure raised when the 1.8 render soak exceeds its failure budget."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


def _positive_int(value: int, *, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{label} must be an integer")
    if value < 1:
        raise ValueError(f"{label} must be >= 1")
    return value


@dataclass(frozen=True, slots=True)
class RenderShowcaseSettings:
    """Bounded settings for deterministic source-only rendering soak tests."""

    frames: int = 240
    max_consecutive_failures: int = 3
    retained_failure_events: int = 32

    def __post_init__(self) -> None:
        object.__setattr__(self, "frames", _positive_int(self.frames, label="frames"))
        object.__setattr__(
            self,
            "max_consecutive_failures",
            _positive_int(self.max_consecutive_failures, label="max_consecutive_failures"),
        )
        object.__setattr__(
            self,
            "retained_failure_events",
            _positive_int(self.retained_failure_events, label="retained_failure_events"),
        )


@dataclass(frozen=True, slots=True)
class RenderShowcaseUpload:
    """Immutable logical upload repeated by the soak workload."""

    texture_id: str
    descriptor: RenderResourceDescriptor
    payload: bytes
    priority: int = 0
    resident_bytes: int | None = None
    pinned: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.texture_id, str):
            raise TypeError("texture_id must be a string")
        texture_id = self.texture_id.strip()
        if not texture_id:
            raise ValueError("texture_id must not be empty")
        if len(texture_id) > 128:
            raise ValueError("texture_id must contain at most 128 characters")
        object.__setattr__(self, "texture_id", texture_id)
        if not isinstance(self.descriptor, RenderResourceDescriptor):
            raise TypeError("descriptor must be a RenderResourceDescriptor")
        if self.descriptor.kind != "texture":
            raise ValueError("showcase uploads require texture descriptors")
        if not isinstance(self.payload, bytes):
            raise TypeError("payload must be bytes")
        if not self.payload:
            raise ValueError("payload must not be empty")
        if isinstance(self.priority, bool) or not isinstance(self.priority, int):
            raise TypeError("priority must be an integer")
        if self.resident_bytes is not None:
            object.__setattr__(
                self,
                "resident_bytes",
                _positive_int(self.resident_bytes, label="resident_bytes"),
            )
        if not isinstance(self.pinned, bool):
            raise TypeError("pinned must be a boolean")


@dataclass(frozen=True, slots=True)
class RenderShowcaseFailure:
    frame: int
    stage: str
    code: str

    def portable(self) -> Mapping[str, int | str]:
        return MappingProxyType(
            {"frame": self.frame, "stage": self.stage, "code": self.code}
        )


@dataclass(frozen=True, slots=True)
class RenderShowcaseReport:
    frames_attempted: int
    clean_frames: int
    rendered_frames: int
    graph_backend_frames: int
    graph_compat_frames: int
    fallback_frames: int
    allocation_failures: int
    upload_failures: int
    render_failures: int
    recoveries: int
    max_consecutive_failures: int
    resource_acquires: int
    resource_reuses: int
    upload_submissions: int
    duplicate_upload_skips: int
    retained_failures: tuple[RenderShowcaseFailure, ...]
    bridge_diagnostics: Mapping[str, object]
    resource_diagnostics: Mapping[str, int] | None
    upload_diagnostics: Mapping[str, int] | None
    workload_fingerprint: str

    def portable(self) -> Mapping[str, object]:
        return MappingProxyType(
            {
                "frames_attempted": self.frames_attempted,
                "clean_frames": self.clean_frames,
                "rendered_frames": self.rendered_frames,
                "graph_backend_frames": self.graph_backend_frames,
                "graph_compat_frames": self.graph_compat_frames,
                "fallback_frames": self.fallback_frames,
                "allocation_failures": self.allocation_failures,
                "upload_failures": self.upload_failures,
                "render_failures": self.render_failures,
                "recoveries": self.recoveries,
                "max_consecutive_failures": self.max_consecutive_failures,
                "resource_acquires": self.resource_acquires,
                "resource_reuses": self.resource_reuses,
                "upload_submissions": self.upload_submissions,
                "duplicate_upload_skips": self.duplicate_upload_skips,
                "retained_failures": [dict(item.portable()) for item in self.retained_failures],
                "bridge_diagnostics": dict(self.bridge_diagnostics),
                "resource_diagnostics": None
                if self.resource_diagnostics is None
                else dict(self.resource_diagnostics),
                "upload_diagnostics": None
                if self.upload_diagnostics is None
                else dict(self.upload_diagnostics),
                "workload_fingerprint": self.workload_fingerprint,
            }
        )

    def fingerprint(self) -> str:
        payload = json.dumps(
            dict(self.portable()), sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
        return hashlib.sha256(payload).hexdigest()


SceneFactory = Callable[[int], object]
CameraFactory = Callable[[int], object | None]


def _failure_code(exc: BaseException) -> str:
    code = getattr(exc, "code", None)
    if isinstance(code, str) and code:
        return code
    return type(exc).__name__


def run_render_showcase(
    bridge: Renderer2CompatibilityBridge,
    scene_factory: SceneFactory,
    *,
    settings: RenderShowcaseSettings | None = None,
    camera_factory: CameraFactory | None = None,
    resource_pool: TransientRenderResourcePool[Any] | None = None,
    resource_descriptors: Iterable[RenderResourceDescriptor] = (),
    upload_queue: TextureUploadQueue | None = None,
    uploads: Iterable[RenderShowcaseUpload] = (),
) -> RenderShowcaseReport:
    """Run a bounded deterministic renderer/resource/upload soak.

    The harness intentionally contains backend/resource/upload failures at the frame boundary so a
    later frame can prove recovery. It never retries recursively and never suppresses the configured
    consecutive-failure ceiling.
    """

    if not isinstance(bridge, Renderer2CompatibilityBridge):
        raise TypeError("bridge must be a Renderer2CompatibilityBridge")
    if not callable(scene_factory):
        raise TypeError("scene_factory must be callable")
    if camera_factory is not None and not callable(camera_factory):
        raise TypeError("camera_factory must be callable or None")
    if settings is None:
        settings = RenderShowcaseSettings()
    if not isinstance(settings, RenderShowcaseSettings):
        raise TypeError("settings must be a RenderShowcaseSettings")
    if resource_pool is not None and not isinstance(
        resource_pool, TransientRenderResourcePool
    ):
        raise TypeError("resource_pool must be a TransientRenderResourcePool or None")
    if upload_queue is not None and not isinstance(upload_queue, TextureUploadQueue):
        raise TypeError("upload_queue must be a TextureUploadQueue or None")

    descriptors = tuple(resource_descriptors)
    for descriptor in descriptors:
        if not isinstance(descriptor, RenderResourceDescriptor):
            raise TypeError("resource_descriptors must contain RenderResourceDescriptor values")
    upload_specs = tuple(uploads)
    for upload in upload_specs:
        if not isinstance(upload, RenderShowcaseUpload):
            raise TypeError("uploads must contain RenderShowcaseUpload values")
    if descriptors and resource_pool is None:
        raise ValueError("resource_pool is required when resource_descriptors are supplied")
    if upload_specs and upload_queue is None:
        raise ValueError("upload_queue is required when uploads are supplied")

    failures: deque[RenderShowcaseFailure] = deque(
        maxlen=settings.retained_failure_events
    )
    digest = hashlib.sha256()
    clean_frames = 0
    rendered_frames = 0
    graph_backend_frames = 0
    graph_compat_frames = 0
    fallback_frames = 0
    allocation_failures = 0
    upload_failures = 0
    render_failures = 0
    recoveries = 0
    consecutive_failures = 0
    peak_consecutive_failures = 0
    previous_failed = False

    for frame_index in range(settings.frames):
        frame_failed = False
        leases: list[RenderResourceHandle] = []

        if resource_pool is not None:
            try:
                for descriptor in descriptors:
                    lease = resource_pool.acquire(descriptor)
                    leases.append(lease.handle)
            except RenderResourcePoolError as exc:
                frame_failed = True
                allocation_failures += 1
                failures.append(
                    RenderShowcaseFailure(frame_index, "allocation", _failure_code(exc))
                )
            finally:
                for handle in reversed(leases):
                    try:
                        resource_pool.release(handle)
                    except RenderResourcePoolError as exc:
                        frame_failed = True
                        allocation_failures += 1
                        failures.append(
                            RenderShowcaseFailure(frame_index, "release", _failure_code(exc))
                        )

        if upload_queue is not None:
            try:
                for upload in upload_specs:
                    upload_queue.enqueue(
                        upload.texture_id,
                        upload.descriptor,
                        upload.payload,
                        priority=upload.priority,
                        resident_bytes=upload.resident_bytes,
                        pinned=upload.pinned,
                    )
                upload_queue.flush()
            except TextureUploadError as exc:
                frame_failed = True
                upload_failures += 1
                failures.append(
                    RenderShowcaseFailure(frame_index, "upload", _failure_code(exc))
                )

        try:
            scene = scene_factory(frame_index)
            camera = None if camera_factory is None else camera_factory(frame_index)
            result = bridge.render(scene, camera=camera)
        except Exception as exc:  # noqa: BLE001 - this harness contains injected backend failures.
            frame_failed = True
            render_failures += 1
            failures.append(
                RenderShowcaseFailure(frame_index, "render", _failure_code(exc))
            )
            digest.update(f"{frame_index}:render-failure:{_failure_code(exc)}".encode())
        else:
            rendered_frames += 1
            if result.execution == "graph-backend":
                graph_backend_frames += 1
            elif result.execution == "graph-compat":
                graph_compat_frames += 1
            else:
                fallback_frames += 1
            frame_fingerprint = "none" if result.frame is None else result.frame.fingerprint
            digest.update(
                f"{frame_index}:{result.execution}:{frame_fingerprint}".encode()
            )

        if frame_failed:
            consecutive_failures += 1
            peak_consecutive_failures = max(
                peak_consecutive_failures, consecutive_failures
            )
            previous_failed = True
            if consecutive_failures > settings.max_consecutive_failures:
                raise RenderShowcaseError(
                    "failure-budget-exceeded",
                    "render showcase exceeded the configured consecutive failure budget",
                )
        else:
            clean_frames += 1
            if previous_failed:
                recoveries += 1
            consecutive_failures = 0
            previous_failed = False

    resource_diag = None
    resource_acquires = 0
    resource_reuses = 0
    if resource_pool is not None:
        diagnostics = resource_pool.diagnostics()
        resource_diag = dict(diagnostics.portable())
        resource_acquires = diagnostics.creates + diagnostics.reuses
        resource_reuses = diagnostics.reuses
        digest.update(
            json.dumps(resource_diag, sort_keys=True, separators=(",", ":")).encode()
        )

    upload_diag = None
    upload_submissions = 0
    duplicate_upload_skips = 0
    if upload_queue is not None:
        diagnostics = upload_queue.diagnostics()
        upload_diag = dict(diagnostics.portable())
        upload_submissions = diagnostics.submitted_uploads
        duplicate_upload_skips = diagnostics.duplicate_skips
        digest.update(
            json.dumps(upload_diag, sort_keys=True, separators=(",", ":")).encode()
        )

    bridge_diag = dict(bridge.diagnostics().portable())
    digest.update(json.dumps(bridge_diag, sort_keys=True, separators=(",", ":")).encode())
    digest.update(
        json.dumps(
            [dict(item.portable()) for item in failures],
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    )

    return RenderShowcaseReport(
        frames_attempted=settings.frames,
        clean_frames=clean_frames,
        rendered_frames=rendered_frames,
        graph_backend_frames=graph_backend_frames,
        graph_compat_frames=graph_compat_frames,
        fallback_frames=fallback_frames,
        allocation_failures=allocation_failures,
        upload_failures=upload_failures,
        render_failures=render_failures,
        recoveries=recoveries,
        max_consecutive_failures=peak_consecutive_failures,
        resource_acquires=resource_acquires,
        resource_reuses=resource_reuses,
        upload_submissions=upload_submissions,
        duplicate_upload_skips=duplicate_upload_skips,
        retained_failures=tuple(failures),
        bridge_diagnostics=MappingProxyType(bridge_diag),
        resource_diagnostics=None
        if resource_diag is None
        else MappingProxyType(resource_diag),
        upload_diagnostics=None if upload_diag is None else MappingProxyType(upload_diag),
        workload_fingerprint=digest.hexdigest(),
    )


__all__ = [
    "RenderShowcaseError",
    "RenderShowcaseFailure",
    "RenderShowcaseReport",
    "RenderShowcaseSettings",
    "RenderShowcaseUpload",
    "run_render_showcase",
]
