from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from itertools import count
from types import MappingProxyType
from typing import Generic, TypeVar

from .render_graph18 import RenderGraphPlan

ResourceT = TypeVar("ResourceT")
_POOL_IDS = count(1)


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


def _token(value: str, *, label: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{label} must be a string")
    result = value.strip()
    if not result:
        raise ValueError(f"{label} must not be empty")
    if len(result) > 128:
        raise ValueError(f"{label} must contain at most 128 characters")
    return result


class RenderResourcePoolError(RuntimeError):
    """Stable creator-facing transient resource-pool failure."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


@dataclass(frozen=True, slots=True)
class RenderResourceDescriptor:
    """Backend-neutral compatibility key for a reusable GPU-like resource."""

    kind: str
    format: str
    width: int
    height: int
    layers: int = 1
    samples: int = 1
    usage: str = "render-target"
    size_bytes: int = 0

    def __post_init__(self) -> None:
        object.__setattr__(self, "kind", _token(self.kind, label="kind"))
        object.__setattr__(self, "format", _token(self.format, label="format"))
        object.__setattr__(self, "usage", _token(self.usage, label="usage"))
        object.__setattr__(self, "width", _positive_int(self.width, label="width"))
        object.__setattr__(self, "height", _positive_int(self.height, label="height"))
        object.__setattr__(self, "layers", _positive_int(self.layers, label="layers"))
        object.__setattr__(self, "samples", _positive_int(self.samples, label="samples"))
        object.__setattr__(
            self,
            "size_bytes",
            _nonnegative_int(self.size_bytes, label="size_bytes"),
        )

    def portable(self) -> Mapping[str, object]:
        return MappingProxyType(
            {
                "kind": self.kind,
                "format": self.format,
                "width": self.width,
                "height": self.height,
                "layers": self.layers,
                "samples": self.samples,
                "usage": self.usage,
                "size_bytes": self.size_bytes,
            }
        )


@dataclass(frozen=True, slots=True)
class RenderResourceHandle:
    """Generation-safe lease handle scoped to one pool instance."""

    slot: int
    generation: int
    pool_id: int = 0

    def __post_init__(self) -> None:
        object.__setattr__(self, "slot", _nonnegative_int(self.slot, label="slot"))
        object.__setattr__(
            self,
            "generation",
            _positive_int(self.generation, label="generation"),
        )
        object.__setattr__(self, "pool_id", _nonnegative_int(self.pool_id, label="pool_id"))


@dataclass(frozen=True, slots=True)
class ResourceLease(Generic[ResourceT]):
    handle: RenderResourceHandle
    descriptor: RenderResourceDescriptor
    resource: ResourceT
    reused: bool


@dataclass(frozen=True, slots=True)
class RenderResourcePoolDiagnostics:
    resident_resources: int
    resident_bytes: int
    leased_resources: int
    free_resources: int
    peak_resident_resources: int
    peak_resident_bytes: int
    creates: int
    reuses: int
    releases: int
    evictions: int
    trims: int
    create_failures: int
    destroy_failures: int
    capacity_failures: int
    stale_handle_failures: int

    def portable(self) -> Mapping[str, int]:
        return MappingProxyType(
            {
                "resident_resources": self.resident_resources,
                "resident_bytes": self.resident_bytes,
                "leased_resources": self.leased_resources,
                "free_resources": self.free_resources,
                "peak_resident_resources": self.peak_resident_resources,
                "peak_resident_bytes": self.peak_resident_bytes,
                "creates": self.creates,
                "reuses": self.reuses,
                "releases": self.releases,
                "evictions": self.evictions,
                "trims": self.trims,
                "create_failures": self.create_failures,
                "destroy_failures": self.destroy_failures,
                "capacity_failures": self.capacity_failures,
                "stale_handle_failures": self.stale_handle_failures,
            }
        )


@dataclass(slots=True)
class _Entry(Generic[ResourceT]):
    descriptor: RenderResourceDescriptor
    resource: ResourceT
    generation: int
    leased: bool
    last_release_sequence: int


class TransientRenderResourcePool(Generic[ResourceT]):
    """Bounded deterministic reuse pool for renderer/backend resources.

    The pool owns resources produced by ``create`` until they are evicted or ``close()`` is called.
    Reuse requires an exact descriptor match. Handles carry both generation and pool identity, so a
    stale or cross-pool lease cannot mutate another live allocation.
    """

    def __init__(
        self,
        *,
        create: Callable[[RenderResourceDescriptor], ResourceT],
        destroy: Callable[[ResourceT], None],
        max_resources: int = 256,
        max_bytes: int = 512 * 1024 * 1024,
    ) -> None:
        if not callable(create):
            raise TypeError("create must be callable")
        if not callable(destroy):
            raise TypeError("destroy must be callable")
        self._create = create
        self._destroy = destroy
        self.max_resources = _positive_int(max_resources, label="max_resources")
        self.max_bytes = _positive_int(max_bytes, label="max_bytes")
        self._pool_id = next(_POOL_IDS)
        self._entries: dict[int, _Entry[ResourceT]] = {}
        self._free_by_descriptor: dict[RenderResourceDescriptor, set[int]] = {}
        self._next_slot = 0
        self._release_sequence = 0
        self._closed = False
        self._resident_bytes = 0
        self._peak_resident_resources = 0
        self._peak_resident_bytes = 0
        self._creates = 0
        self._reuses = 0
        self._releases = 0
        self._evictions = 0
        self._trims = 0
        self._create_failures = 0
        self._destroy_failures = 0
        self._capacity_failures = 0
        self._stale_handle_failures = 0

    @property
    def closed(self) -> bool:
        return self._closed

    def diagnostics(self) -> RenderResourcePoolDiagnostics:
        leased = sum(1 for entry in self._entries.values() if entry.leased)
        resident = len(self._entries)
        return RenderResourcePoolDiagnostics(
            resident_resources=resident,
            resident_bytes=self._resident_bytes,
            leased_resources=leased,
            free_resources=resident - leased,
            peak_resident_resources=self._peak_resident_resources,
            peak_resident_bytes=self._peak_resident_bytes,
            creates=self._creates,
            reuses=self._reuses,
            releases=self._releases,
            evictions=self._evictions,
            trims=self._trims,
            create_failures=self._create_failures,
            destroy_failures=self._destroy_failures,
            capacity_failures=self._capacity_failures,
            stale_handle_failures=self._stale_handle_failures,
        )

    def acquire(self, descriptor: RenderResourceDescriptor) -> ResourceLease[ResourceT]:
        self._require_open()
        if not isinstance(descriptor, RenderResourceDescriptor):
            raise TypeError("descriptor must be a RenderResourceDescriptor")
        if descriptor.size_bytes > self.max_bytes:
            self._capacity_failures += 1
            raise RenderResourcePoolError(
                "resource-too-large",
                f"resource requires {descriptor.size_bytes} bytes but pool limit is {self.max_bytes}",
            )

        reusable = self._oldest_free_slot(descriptor)
        if reusable is not None:
            entry = self._entries[reusable]
            self._remove_free(reusable, entry.descriptor)
            entry.generation += 1
            entry.leased = True
            self._reuses += 1
            return self._lease(reusable, entry, reused=True)

        self._make_capacity(descriptor.size_bytes)
        try:
            resource = self._create(descriptor)
        except Exception as exc:
            self._create_failures += 1
            raise RenderResourcePoolError(
                "create-failed",
                f"backend resource creation failed for {descriptor.kind}/{descriptor.format}",
            ) from exc
        if resource is None:
            self._create_failures += 1
            raise RenderResourcePoolError(
                "create-failed",
                "backend resource creation returned None",
            )

        slot = self._next_slot
        self._next_slot += 1
        entry = _Entry(
            descriptor=descriptor,
            resource=resource,
            generation=1,
            leased=True,
            last_release_sequence=-1,
        )
        self._entries[slot] = entry
        self._resident_bytes += descriptor.size_bytes
        self._creates += 1
        self._peak_resident_resources = max(self._peak_resident_resources, len(self._entries))
        self._peak_resident_bytes = max(self._peak_resident_bytes, self._resident_bytes)
        return self._lease(slot, entry, reused=False)

    def release(self, handle: RenderResourceHandle) -> None:
        self._require_open()
        entry = self._validate_leased_handle(handle)
        entry.leased = False
        entry.last_release_sequence = self._release_sequence
        self._release_sequence += 1
        self._free_by_descriptor.setdefault(entry.descriptor, set()).add(handle.slot)
        self._releases += 1

    def get(self, handle: RenderResourceHandle) -> ResourceT:
        self._require_open()
        return self._validate_leased_handle(handle).resource

    def trim(self, *, target_resources: int = 0, target_bytes: int = 0) -> int:
        """Destroy idle resources until both requested residency targets are satisfied."""
        self._require_open()
        target_resources = _nonnegative_int(target_resources, label="target_resources")
        target_bytes = _nonnegative_int(target_bytes, label="target_bytes")
        removed = 0
        while len(self._entries) > target_resources or self._resident_bytes > target_bytes:
            slot = self._oldest_free_slot_any()
            if slot is None:
                break
            self._evict(slot)
            removed += 1
        self._trims += 1
        return removed

    def close(self) -> None:
        if self._closed and not self._entries:
            return
        self._closed = True
        failures: list[BaseException] = []
        destroyed_slots: list[int] = []
        for slot in sorted(self._entries):
            entry = self._entries[slot]
            try:
                self._destroy(entry.resource)
            except Exception as exc:  # noqa: BLE001 - shutdown attempts every backend object.
                failures.append(exc)
                self._destroy_failures += 1
            else:
                destroyed_slots.append(slot)

        for slot in destroyed_slots:
            entry = self._entries.pop(slot)
            if not entry.leased:
                self._remove_free(slot, entry.descriptor)
            self._resident_bytes -= entry.descriptor.size_bytes

        if failures:
            raise RenderResourcePoolError(
                "destroy-failed",
                f"backend resource destruction failed for {len(failures)} resource(s)",
            ) from failures[0]

        self._free_by_descriptor.clear()
        self._resident_bytes = 0

    def _lease(
        self,
        slot: int,
        entry: _Entry[ResourceT],
        *,
        reused: bool,
    ) -> ResourceLease[ResourceT]:
        return ResourceLease(
            handle=RenderResourceHandle(slot, entry.generation, self._pool_id),
            descriptor=entry.descriptor,
            resource=entry.resource,
            reused=reused,
        )

    def _require_open(self) -> None:
        if self._closed:
            raise RenderResourcePoolError("pool-closed", "resource pool is closed")

    def _validate_leased_handle(self, handle: RenderResourceHandle) -> _Entry[ResourceT]:
        if not isinstance(handle, RenderResourceHandle):
            raise TypeError("handle must be a RenderResourceHandle")
        entry = self._entries.get(handle.slot)
        if (
            handle.pool_id != self._pool_id
            or entry is None
            or not entry.leased
            or entry.generation != handle.generation
        ):
            self._stale_handle_failures += 1
            raise RenderResourcePoolError("stale-handle", "resource handle is stale or not leased")
        return entry

    def _make_capacity(self, size_bytes: int) -> None:
        while (
            len(self._entries) >= self.max_resources
            or self._resident_bytes + size_bytes > self.max_bytes
        ):
            slot = self._oldest_free_slot_any()
            if slot is None:
                self._capacity_failures += 1
                raise RenderResourcePoolError(
                    "capacity-exhausted",
                    "resource pool capacity is fully leased and cannot satisfy the request",
                )
            self._evict(slot)

    def _oldest_free_slot(self, descriptor: RenderResourceDescriptor) -> int | None:
        slots = self._free_by_descriptor.get(descriptor)
        if not slots:
            return None
        return min(
            slots,
            key=lambda slot: (self._entries[slot].last_release_sequence, slot),
        )

    def _oldest_free_slot_any(self) -> int | None:
        candidates = (slot for slots in self._free_by_descriptor.values() for slot in slots)
        return min(
            candidates,
            key=lambda slot: (self._entries[slot].last_release_sequence, slot),
            default=None,
        )

    def _remove_free(self, slot: int, descriptor: RenderResourceDescriptor) -> None:
        slots = self._free_by_descriptor[descriptor]
        slots.remove(slot)
        if not slots:
            del self._free_by_descriptor[descriptor]

    def _evict(self, slot: int) -> None:
        entry = self._entries[slot]
        if entry.leased:
            raise RuntimeError("internal error: attempted to evict a leased resource")
        try:
            self._destroy(entry.resource)
        except Exception as exc:
            self._destroy_failures += 1
            raise RenderResourcePoolError(
                "destroy-failed",
                f"backend resource destruction failed for slot {slot}",
            ) from exc
        self._remove_free(slot, entry.descriptor)
        del self._entries[slot]
        self._resident_bytes -= entry.descriptor.size_bytes
        self._evictions += 1


@dataclass(frozen=True, slots=True)
class RenderPlanResourceEvent:
    pass_index: int
    phase: str
    resource_name: str
    descriptor: RenderResourceDescriptor


@dataclass(frozen=True, slots=True)
class RenderPlanResourceSchedule:
    """Deterministic acquire/release events derived from a verified render graph plan."""

    pass_count: int
    acquire_events: Mapping[int, tuple[RenderPlanResourceEvent, ...]]
    release_events: Mapping[int, tuple[RenderPlanResourceEvent, ...]]

    @classmethod
    def from_plan(
        cls,
        plan: RenderGraphPlan,
        descriptors: Mapping[str, RenderResourceDescriptor],
    ) -> RenderPlanResourceSchedule:
        if not isinstance(plan, RenderGraphPlan):
            raise TypeError("plan must be a RenderGraphPlan")
        if not isinstance(descriptors, Mapping):
            raise TypeError("descriptors must be a mapping")
        acquire: dict[int, list[RenderPlanResourceEvent]] = {}
        release: dict[int, list[RenderPlanResourceEvent]] = {}
        for name, lifetime in sorted(plan.lifetimes.items()):
            if not lifetime.transient:
                continue
            descriptor = descriptors.get(name)
            if descriptor is None:
                raise RenderResourcePoolError(
                    "missing-descriptor",
                    f"missing transient descriptor for graph resource: {name}",
                )
            if not isinstance(descriptor, RenderResourceDescriptor):
                raise TypeError(f"descriptor for {name} must be a RenderResourceDescriptor")
            if descriptor.size_bytes > lifetime.size_bytes and lifetime.size_bytes > 0:
                raise RenderResourcePoolError(
                    "descriptor-too-large",
                    f"descriptor for {name} exceeds graph-planned size",
                )
            acquire.setdefault(lifetime.first_pass, []).append(
                RenderPlanResourceEvent(lifetime.first_pass, "acquire", name, descriptor)
            )
            release.setdefault(lifetime.last_pass, []).append(
                RenderPlanResourceEvent(lifetime.last_pass, "release", name, descriptor)
            )
        acquire_view = MappingProxyType(
            {
                index: tuple(sorted(events, key=lambda event: event.resource_name))
                for index, events in sorted(acquire.items())
            }
        )
        release_view = MappingProxyType(
            {
                index: tuple(sorted(events, key=lambda event: event.resource_name))
                for index, events in sorted(release.items())
            }
        )
        return cls(len(plan.passes), acquire_view, release_view)


class RenderPlanPoolSession(Generic[ResourceT]):
    """Apply graph lifetime events to a transient pool one pass at a time."""

    def __init__(
        self,
        pool: TransientRenderResourcePool[ResourceT],
        schedule: RenderPlanResourceSchedule,
    ) -> None:
        if not isinstance(pool, TransientRenderResourcePool):
            raise TypeError("pool must be a TransientRenderResourcePool")
        if not isinstance(schedule, RenderPlanResourceSchedule):
            raise TypeError("schedule must be a RenderPlanResourceSchedule")
        self.pool = pool
        self.schedule = schedule
        self._leases: dict[str, ResourceLease[ResourceT]] = {}
        self._next_pass = 0
        self._active_pass: int | None = None

    @property
    def next_pass(self) -> int:
        return self._next_pass

    @property
    def active_resources(self) -> Mapping[str, ResourceT]:
        return MappingProxyType({name: lease.resource for name, lease in self._leases.items()})

    def begin_pass(self, pass_index: int) -> Mapping[str, ResourceT]:
        pass_index = _nonnegative_int(pass_index, label="pass_index")
        if self._active_pass is not None:
            raise RenderResourcePoolError("pass-active", "end the active pass before beginning another")
        if pass_index != self._next_pass or pass_index >= self.schedule.pass_count:
            raise RenderResourcePoolError(
                "pass-order",
                f"expected pass {self._next_pass}, got {pass_index}",
            )
        acquired: list[str] = []
        try:
            for event in self.schedule.acquire_events.get(pass_index, ()):
                lease = self.pool.acquire(event.descriptor)
                self._leases[event.resource_name] = lease
                acquired.append(event.resource_name)
        except Exception:
            for name in reversed(acquired):
                lease = self._leases.pop(name)
                self.pool.release(lease.handle)
            raise
        self._active_pass = pass_index
        return self.active_resources

    def end_pass(self, pass_index: int) -> None:
        pass_index = _nonnegative_int(pass_index, label="pass_index")
        if self._active_pass != pass_index:
            raise RenderResourcePoolError("pass-order", "pass is not currently active")
        for event in self.schedule.release_events.get(pass_index, ()):
            lease = self._leases.pop(event.resource_name)
            self.pool.release(lease.handle)
        self._active_pass = None
        self._next_pass += 1

    def abort(self) -> None:
        for name in sorted(self._leases):
            lease = self._leases.pop(name)
            try:
                self.pool.release(lease.handle)
            except RenderResourcePoolError:
                pass
        self._active_pass = None


__all__ = [
    "RenderPlanPoolSession",
    "RenderPlanResourceEvent",
    "RenderPlanResourceSchedule",
    "RenderResourceDescriptor",
    "RenderResourceHandle",
    "RenderResourcePoolDiagnostics",
    "RenderResourcePoolError",
    "ResourceLease",
    "TransientRenderResourcePool",
]
