from __future__ import annotations

import threading
from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum


def _name(value: str, *, label: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{label} must be a string")
    result = value.strip()
    if not result:
        raise ValueError(f"{label} must not be empty")
    if len(result) > 128:
        raise ValueError(f"{label} must contain at most 128 characters")
    return result


def _nonnegative_int(value: int, *, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{label} must be an integer")
    if value < 0:
        raise ValueError(f"{label} must be >= 0")
    return value


def _priority(value: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError("priority must be an integer")
    return value


@dataclass(frozen=True, slots=True)
class BudgetVector:
    """Three-dimensional resource demand shared by 1.7 streaming systems."""

    memory_bytes: int = 0
    count: int = 0
    work_units: int = 0

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "memory_bytes",
            _nonnegative_int(self.memory_bytes, label="memory_bytes"),
        )
        object.__setattr__(self, "count", _nonnegative_int(self.count, label="count"))
        object.__setattr__(
            self,
            "work_units",
            _nonnegative_int(self.work_units, label="work_units"),
        )

    @property
    def empty(self) -> bool:
        return self.memory_bytes == 0 and self.count == 0 and self.work_units == 0

    def added(self, other: BudgetVector) -> BudgetVector:
        if not isinstance(other, BudgetVector):
            raise TypeError("other must be a BudgetVector")
        return BudgetVector(
            self.memory_bytes + other.memory_bytes,
            self.count + other.count,
            self.work_units + other.work_units,
        )

    def subtracted(self, other: BudgetVector) -> BudgetVector:
        if not isinstance(other, BudgetVector):
            raise TypeError("other must be a BudgetVector")
        values = (
            self.memory_bytes - other.memory_bytes,
            self.count - other.count,
            self.work_units - other.work_units,
        )
        if any(value < 0 for value in values):
            raise ValueError("budget subtraction would become negative")
        return BudgetVector(*values)

    def fits_within(self, limit: BudgetVector) -> bool:
        if not isinstance(limit, BudgetVector):
            raise TypeError("limit must be a BudgetVector")
        return (
            self.memory_bytes <= limit.memory_bytes
            and self.count <= limit.count
            and self.work_units <= limit.work_units
        )

    def component_min(self, other: BudgetVector) -> BudgetVector:
        if not isinstance(other, BudgetVector):
            raise TypeError("other must be a BudgetVector")
        return BudgetVector(
            min(self.memory_bytes, other.memory_bytes),
            min(self.count, other.count),
            min(self.work_units, other.work_units),
        )

    def helps_excess(self, used: BudgetVector, limit: BudgetVector) -> bool:
        return (
            used.memory_bytes > limit.memory_bytes and self.memory_bytes > 0
            or used.count > limit.count and self.count > 0
            or used.work_units > limit.work_units and self.work_units > 0
        )

    def portable(self) -> dict[str, int]:
        return {
            "memory_bytes": self.memory_bytes,
            "count": self.count,
            "work_units": self.work_units,
        }


ZERO_BUDGET = BudgetVector()


class AdmissionReason(str, Enum):
    ADMITTED = "admitted"
    DUPLICATE_RESOURCE = "duplicate_resource"
    REQUEST_EXCEEDS_CAPACITY = "request_exceeds_capacity"
    REQUEST_EXCEEDS_SUBSYSTEM_LIMIT = "request_exceeds_subsystem_limit"
    SUBSYSTEM_LIMIT = "subsystem_limit"
    RESERVATION_PROTECTED = "reservation_protected"
    PRIORITY_PROTECTED = "priority_protected"
    PROTECTED_ALLOCATION = "protected_allocation"
    CAPACITY = "capacity"


@dataclass(frozen=True, slots=True)
class ReservationClass:
    name: str
    reserved: BudgetVector = ZERO_BUDGET

    def __post_init__(self) -> None:
        object.__setattr__(self, "name", _name(self.name, label="reservation class name"))
        if not isinstance(self.reserved, BudgetVector):
            raise TypeError("reserved must be a BudgetVector")

    def portable(self) -> dict[str, object]:
        return {"name": self.name, "reserved": self.reserved.portable()}


@dataclass(frozen=True, slots=True)
class BudgetRequest:
    resource_id: str
    subsystem: str
    demand: BudgetVector
    reservation_class: str = "default"
    priority: int = 0
    evictable: bool = True

    def __post_init__(self) -> None:
        object.__setattr__(self, "resource_id", _name(self.resource_id, label="resource_id"))
        object.__setattr__(self, "subsystem", _name(self.subsystem, label="subsystem"))
        object.__setattr__(
            self,
            "reservation_class",
            _name(self.reservation_class, label="reservation_class"),
        )
        if not isinstance(self.demand, BudgetVector):
            raise TypeError("demand must be a BudgetVector")
        if self.demand.empty:
            raise ValueError("demand must reserve at least one resource dimension")
        object.__setattr__(self, "priority", _priority(self.priority))
        if not isinstance(self.evictable, bool):
            raise TypeError("evictable must be a bool")


@dataclass(frozen=True, slots=True)
class BudgetAllocation:
    resource_id: str
    subsystem: str
    demand: BudgetVector
    reservation_class: str
    priority: int
    evictable: bool
    sequence: int

    def portable(self) -> dict[str, object]:
        return {
            "resource_id": self.resource_id,
            "subsystem": self.subsystem,
            "reservation_class": self.reservation_class,
            "priority": self.priority,
            "evictable": self.evictable,
            "sequence": self.sequence,
            "demand": self.demand.portable(),
        }


@dataclass(frozen=True, slots=True)
class AdmissionPlan:
    revision: int
    request: BudgetRequest
    admitted: bool
    reason: AdmissionReason
    evicted: tuple[BudgetAllocation, ...] = ()

    def __post_init__(self) -> None:
        if self.admitted != (self.reason is AdmissionReason.ADMITTED):
            raise ValueError("admitted plans must use the ADMITTED reason only")


@dataclass(frozen=True, slots=True)
class AdmissionResult:
    admitted: bool
    reason: AdmissionReason
    revision: int
    allocation: BudgetAllocation | None = None
    evicted: tuple[BudgetAllocation, ...] = ()


class StaleBudgetPlanError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class SubsystemBudgetSnapshot:
    name: str
    used: BudgetVector
    limit: BudgetVector

    def portable(self) -> dict[str, object]:
        return {"used": self.used.portable(), "limit": self.limit.portable()}


@dataclass(frozen=True, slots=True)
class ReservationBudgetSnapshot:
    name: str
    used: BudgetVector
    reserved: BudgetVector
    protected: BudgetVector

    def portable(self) -> dict[str, object]:
        return {
            "used": self.used.portable(),
            "reserved": self.reserved.portable(),
            "protected": self.protected.portable(),
        }


@dataclass(frozen=True, slots=True)
class ResourceBudgetDiagnostics:
    revision: int
    capacity: BudgetVector
    used: BudgetVector
    available: BudgetVector
    allocations: int
    admitted_total: int
    rejected_total: int
    released_total: int
    evicted_total: int
    rejection_reasons: tuple[tuple[str, int], ...]
    subsystems: tuple[SubsystemBudgetSnapshot, ...]
    reservation_classes: tuple[ReservationBudgetSnapshot, ...]

    @staticmethod
    def _ratio(used: int, capacity: int) -> float:
        if capacity <= 0:
            return 0.0
        return used / capacity

    def portable(self) -> Mapping[str, object]:
        return {
            "revision": self.revision,
            "capacity": self.capacity.portable(),
            "used": self.used.portable(),
            "available": self.available.portable(),
            "allocations": self.allocations,
            "admitted_total": self.admitted_total,
            "rejected_total": self.rejected_total,
            "released_total": self.released_total,
            "evicted_total": self.evicted_total,
            "pressure": {
                "memory": self._ratio(self.used.memory_bytes, self.capacity.memory_bytes),
                "count": self._ratio(self.used.count, self.capacity.count),
                "work": self._ratio(self.used.work_units, self.capacity.work_units),
            },
            "rejection_reasons": dict(self.rejection_reasons),
            "subsystems": {
                item.name: item.portable() for item in self.subsystems
            },
            "reservation_classes": {
                item.name: item.portable() for item in self.reservation_classes
            },
        }


class ResourceBudgetBroker:
    """Atomic shared resource accounting for additive SwirEngine 1.7 systems.

    The broker owns accounting only. Evicted ``BudgetAllocation`` records tell the creator which
    concrete resources should be unloaded; the broker never calls renderer/audio/streaming code.
    Lower integer priority is evicted first. Equal or higher-priority allocations are never
    displaced by a new request. Within one priority, newer allocations are evicted first so
    long-resident resources remain stable.

    Reservation classes protect *resident* usage up to their configured floor. Unused reserved
    capacity may therefore be borrowed by other classes; the reservation does not imply surprise
    preemption of equal/higher-priority work.
    """

    def __init__(self, capacity: BudgetVector) -> None:
        if not isinstance(capacity, BudgetVector):
            raise TypeError("capacity must be a BudgetVector")
        if capacity.empty:
            raise ValueError("capacity must expose at least one positive resource dimension")
        self.capacity = capacity
        self._classes: dict[str, ReservationClass] = {
            "default": ReservationClass("default")
        }
        self._subsystem_limits: dict[str, BudgetVector] = {}
        self._allocations: dict[str, BudgetAllocation] = {}
        self._used = ZERO_BUDGET
        self._used_by_subsystem: dict[str, BudgetVector] = {}
        self._used_by_class: dict[str, BudgetVector] = {}
        self._revision = 0
        self._next_sequence = 1
        self._admitted_total = 0
        self._rejected_total = 0
        self._released_total = 0
        self._evicted_total = 0
        self._rejection_reasons: dict[AdmissionReason, int] = {}
        self._lock = threading.RLock()

    @property
    def revision(self) -> int:
        with self._lock:
            return self._revision

    def register_reservation_class(
        self,
        name: str,
        *,
        reserved: BudgetVector = ZERO_BUDGET,
    ) -> ReservationClass:
        entry = ReservationClass(name=name, reserved=reserved)
        with self._lock:
            if entry.name in self._classes:
                raise ValueError(f"reservation class {entry.name!r} is already registered")
            combined = entry.reserved
            for current in self._classes.values():
                combined = combined.added(current.reserved)
            if not combined.fits_within(self.capacity):
                raise ValueError("reservation class totals cannot exceed global capacity")
            self._classes[entry.name] = entry
            self._revision += 1
            return entry

    def set_reservation(self, name: str, reserved: BudgetVector) -> ReservationClass:
        class_name = _name(name, label="reservation class name")
        if not isinstance(reserved, BudgetVector):
            raise TypeError("reserved must be a BudgetVector")
        with self._lock:
            if class_name not in self._classes:
                raise KeyError(class_name)
            combined = reserved
            for key, current in self._classes.items():
                if key != class_name:
                    combined = combined.added(current.reserved)
            if not combined.fits_within(self.capacity):
                raise ValueError("reservation class totals cannot exceed global capacity")
            entry = ReservationClass(class_name, reserved)
            self._classes[class_name] = entry
            self._revision += 1
            return entry

    def set_subsystem_limit(self, subsystem: str, limit: BudgetVector) -> None:
        name = _name(subsystem, label="subsystem")
        if not isinstance(limit, BudgetVector):
            raise TypeError("limit must be a BudgetVector")
        if not limit.fits_within(self.capacity):
            raise ValueError("subsystem limit cannot exceed global capacity")
        with self._lock:
            used = self._used_by_subsystem.get(name, ZERO_BUDGET)
            if not used.fits_within(limit):
                raise ValueError("subsystem limit cannot be lower than current subsystem usage")
            self._subsystem_limits[name] = limit
            self._revision += 1

    def clear_subsystem_limit(self, subsystem: str) -> bool:
        name = _name(subsystem, label="subsystem")
        with self._lock:
            if name not in self._subsystem_limits:
                return False
            del self._subsystem_limits[name]
            self._revision += 1
            return True

    def plan_admission(
        self,
        resource_id: str,
        *,
        subsystem: str,
        demand: BudgetVector,
        reservation_class: str = "default",
        priority: int = 0,
        evictable: bool = True,
    ) -> AdmissionPlan:
        request = BudgetRequest(
            resource_id=resource_id,
            subsystem=subsystem,
            demand=demand,
            reservation_class=reservation_class,
            priority=priority,
            evictable=evictable,
        )
        with self._lock:
            return self._plan_locked(request)

    def _plan_locked(self, request: BudgetRequest) -> AdmissionPlan:
        if request.reservation_class not in self._classes:
            raise KeyError(request.reservation_class)
        if request.resource_id in self._allocations:
            return AdmissionPlan(
                revision=self._revision,
                request=request,
                admitted=False,
                reason=AdmissionReason.DUPLICATE_RESOURCE,
            )
        if not request.demand.fits_within(self.capacity):
            return AdmissionPlan(
                revision=self._revision,
                request=request,
                admitted=False,
                reason=AdmissionReason.REQUEST_EXCEEDS_CAPACITY,
            )

        subsystem_limit = self._subsystem_limits.get(request.subsystem, self.capacity)
        if not request.demand.fits_within(subsystem_limit):
            return AdmissionPlan(
                revision=self._revision,
                request=request,
                admitted=False,
                reason=AdmissionReason.REQUEST_EXCEEDS_SUBSYSTEM_LIMIT,
            )

        global_used = self._used.added(request.demand)
        subsystem_used = self._used_by_subsystem.get(
            request.subsystem, ZERO_BUDGET
        ).added(request.demand)
        class_usage = dict(self._used_by_class)
        class_usage[request.reservation_class] = class_usage.get(
            request.reservation_class, ZERO_BUDGET
        ).added(request.demand)

        if global_used.fits_within(self.capacity) and subsystem_used.fits_within(
            subsystem_limit
        ):
            return AdmissionPlan(
                revision=self._revision,
                request=request,
                admitted=True,
                reason=AdmissionReason.ADMITTED,
            )

        reservation_floors = {
            name: self._used_by_class.get(name, ZERO_BUDGET).component_min(entry.reserved)
            for name, entry in self._classes.items()
        }
        candidates = sorted(
            self._allocations.values(),
            key=lambda item: (item.priority, -item.sequence, item.resource_id),
        )
        evicted: list[BudgetAllocation] = []
        saw_priority_block = False
        saw_reservation_block = False
        saw_protected_block = False

        for candidate in candidates:
            helps_global = candidate.demand.helps_excess(global_used, self.capacity)
            helps_subsystem = (
                candidate.subsystem == request.subsystem
                and candidate.demand.helps_excess(subsystem_used, subsystem_limit)
            )
            if not helps_global and not helps_subsystem:
                continue
            if not candidate.evictable:
                saw_protected_block = True
                continue
            if candidate.priority >= request.priority:
                saw_priority_block = True
                continue

            current_class_usage = class_usage.get(candidate.reservation_class, ZERO_BUDGET)
            proposed_class_usage = current_class_usage.subtracted(candidate.demand)
            protected_floor = reservation_floors.get(candidate.reservation_class, ZERO_BUDGET)
            if not protected_floor.fits_within(proposed_class_usage):
                saw_reservation_block = True
                continue

            global_used = global_used.subtracted(candidate.demand)
            class_usage[candidate.reservation_class] = proposed_class_usage
            if candidate.subsystem == request.subsystem:
                subsystem_used = subsystem_used.subtracted(candidate.demand)
            evicted.append(candidate)

            if global_used.fits_within(self.capacity) and subsystem_used.fits_within(
                subsystem_limit
            ):
                return AdmissionPlan(
                    revision=self._revision,
                    request=request,
                    admitted=True,
                    reason=AdmissionReason.ADMITTED,
                    evicted=tuple(evicted),
                )

        subsystem_over = not subsystem_used.fits_within(subsystem_limit)
        if saw_reservation_block:
            reason = AdmissionReason.RESERVATION_PROTECTED
        elif saw_priority_block:
            reason = AdmissionReason.PRIORITY_PROTECTED
        elif saw_protected_block:
            reason = AdmissionReason.PROTECTED_ALLOCATION
        elif subsystem_over:
            reason = AdmissionReason.SUBSYSTEM_LIMIT
        else:
            reason = AdmissionReason.CAPACITY
        return AdmissionPlan(
            revision=self._revision,
            request=request,
            admitted=False,
            reason=reason,
        )

    def commit(self, plan: AdmissionPlan) -> AdmissionResult:
        if not isinstance(plan, AdmissionPlan):
            raise TypeError("plan must be an AdmissionPlan")
        if not plan.admitted:
            raise ValueError("cannot commit a rejected admission plan")
        with self._lock:
            if plan.revision != self._revision:
                raise StaleBudgetPlanError(
                    f"budget plan revision {plan.revision} is stale; current revision is {self._revision}"
                )
            fresh = self._plan_locked(plan.request)
            if not fresh.admitted or fresh.evicted != plan.evicted:
                raise StaleBudgetPlanError("budget plan no longer matches current admission state")
            return self._commit_locked(fresh)

    def admit(
        self,
        resource_id: str,
        *,
        subsystem: str,
        demand: BudgetVector,
        reservation_class: str = "default",
        priority: int = 0,
        evictable: bool = True,
    ) -> AdmissionResult:
        request = BudgetRequest(
            resource_id=resource_id,
            subsystem=subsystem,
            demand=demand,
            reservation_class=reservation_class,
            priority=priority,
            evictable=evictable,
        )
        with self._lock:
            plan = self._plan_locked(request)
            if not plan.admitted:
                self._rejected_total += 1
                self._rejection_reasons[plan.reason] = (
                    self._rejection_reasons.get(plan.reason, 0) + 1
                )
                return AdmissionResult(
                    admitted=False,
                    reason=plan.reason,
                    revision=self._revision,
                )
            return self._commit_locked(plan)

    def _commit_locked(self, plan: AdmissionPlan) -> AdmissionResult:
        request = plan.request
        evicted = plan.evicted
        for allocation in evicted:
            current = self._allocations.get(allocation.resource_id)
            if current != allocation:
                raise StaleBudgetPlanError(
                    f"eviction target {allocation.resource_id!r} changed before commit"
                )
            self._remove_allocation_locked(allocation)

        allocation = BudgetAllocation(
            resource_id=request.resource_id,
            subsystem=request.subsystem,
            demand=request.demand,
            reservation_class=request.reservation_class,
            priority=request.priority,
            evictable=request.evictable,
            sequence=self._next_sequence,
        )
        self._next_sequence += 1
        self._allocations[allocation.resource_id] = allocation
        self._used = self._used.added(allocation.demand)
        self._used_by_subsystem[allocation.subsystem] = self._used_by_subsystem.get(
            allocation.subsystem, ZERO_BUDGET
        ).added(allocation.demand)
        self._used_by_class[allocation.reservation_class] = self._used_by_class.get(
            allocation.reservation_class, ZERO_BUDGET
        ).added(allocation.demand)
        self._admitted_total += 1
        self._evicted_total += len(evicted)
        self._revision += 1
        return AdmissionResult(
            admitted=True,
            reason=AdmissionReason.ADMITTED,
            revision=self._revision,
            allocation=allocation,
            evicted=evicted,
        )

    def release(self, resource_id: str) -> BudgetAllocation | None:
        key = _name(resource_id, label="resource_id")
        with self._lock:
            allocation = self._allocations.get(key)
            if allocation is None:
                return None
            self._remove_allocation_locked(allocation)
            self._released_total += 1
            self._revision += 1
            return allocation

    def _remove_allocation_locked(self, allocation: BudgetAllocation) -> None:
        del self._allocations[allocation.resource_id]
        self._used = self._used.subtracted(allocation.demand)
        self._subtract_mapping_usage(
            self._used_by_subsystem,
            allocation.subsystem,
            allocation.demand,
        )
        self._subtract_mapping_usage(
            self._used_by_class,
            allocation.reservation_class,
            allocation.demand,
        )

    @staticmethod
    def _subtract_mapping_usage(
        mapping: dict[str, BudgetVector],
        key: str,
        demand: BudgetVector,
    ) -> None:
        remaining = mapping.get(key, ZERO_BUDGET).subtracted(demand)
        if remaining.empty:
            mapping.pop(key, None)
        else:
            mapping[key] = remaining

    def allocation(self, resource_id: str) -> BudgetAllocation:
        key = _name(resource_id, label="resource_id")
        with self._lock:
            try:
                return self._allocations[key]
            except KeyError:
                raise KeyError(key) from None

    def allocations(self) -> tuple[BudgetAllocation, ...]:
        with self._lock:
            return tuple(sorted(self._allocations.values(), key=lambda item: item.sequence))

    def usage(self) -> BudgetVector:
        with self._lock:
            return self._used

    def subsystem_usage(self, subsystem: str) -> BudgetVector:
        name = _name(subsystem, label="subsystem")
        with self._lock:
            return self._used_by_subsystem.get(name, ZERO_BUDGET)

    def reservation_usage(self, reservation_class: str) -> BudgetVector:
        name = _name(reservation_class, label="reservation_class")
        with self._lock:
            if name not in self._classes:
                raise KeyError(name)
            return self._used_by_class.get(name, ZERO_BUDGET)

    def diagnostics(self) -> ResourceBudgetDiagnostics:
        with self._lock:
            available = self.capacity.subtracted(self._used)
            subsystem_names = sorted(
                set(self._used_by_subsystem) | set(self._subsystem_limits)
            )
            subsystems = tuple(
                SubsystemBudgetSnapshot(
                    name=name,
                    used=self._used_by_subsystem.get(name, ZERO_BUDGET),
                    limit=self._subsystem_limits.get(name, self.capacity),
                )
                for name in subsystem_names
            )
            reservation_classes = tuple(
                ReservationBudgetSnapshot(
                    name=name,
                    used=self._used_by_class.get(name, ZERO_BUDGET),
                    reserved=entry.reserved,
                    protected=self._used_by_class.get(name, ZERO_BUDGET).component_min(
                        entry.reserved
                    ),
                )
                for name, entry in sorted(self._classes.items())
            )
            rejection_reasons = tuple(
                (reason.value, count)
                for reason, count in sorted(
                    self._rejection_reasons.items(), key=lambda item: item[0].value
                )
            )
            return ResourceBudgetDiagnostics(
                revision=self._revision,
                capacity=self.capacity,
                used=self._used,
                available=available,
                allocations=len(self._allocations),
                admitted_total=self._admitted_total,
                rejected_total=self._rejected_total,
                released_total=self._released_total,
                evicted_total=self._evicted_total,
                rejection_reasons=rejection_reasons,
                subsystems=subsystems,
                reservation_classes=reservation_classes,
            )


__all__ = [
    "AdmissionPlan",
    "AdmissionReason",
    "AdmissionResult",
    "BudgetAllocation",
    "BudgetRequest",
    "BudgetVector",
    "ReservationBudgetSnapshot",
    "ReservationClass",
    "ResourceBudgetBroker",
    "ResourceBudgetDiagnostics",
    "StaleBudgetPlanError",
    "SubsystemBudgetSnapshot",
]
