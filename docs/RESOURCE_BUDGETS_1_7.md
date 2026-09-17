# Shared Resource Budget Broker — SwirEngine 1.7

`swirengine.resource_budget17.ResourceBudgetBroker` is an additive accounting and admission layer for runtime systems that compete for finite memory, resident-object counts or bounded work capacity.

The broker does not allocate memory, upload GPU objects, unload scenes or call audio/streaming code. It owns deterministic accounting only. This keeps ownership explicit: a caller receives the exact `BudgetAllocation` records selected for eviction and performs the concrete subsystem cleanup itself.

Published stable 1.x APIs and package metadata remain unchanged.

## Budget dimensions

Every request uses a `BudgetVector` with three non-negative integer dimensions:

- `memory_bytes`: estimated or measured resident memory accounted by the creator;
- `count`: resource/object slots;
- `work_units`: creator-defined outstanding work pressure, such as decode/finalize slots.

A broker has one immutable global capacity. A request must reserve at least one positive dimension and can never individually exceed the global capacity.

```python
from swirengine.resource_budget17 import BudgetVector, ResourceBudgetBroker

broker = ResourceBudgetBroker(
    BudgetVector(
        memory_bytes=512 * 1024 * 1024,
        count=2_000,
        work_units=1_000,
    )
)
```

## Deterministic admission and eviction

Each admitted allocation records:

- a unique creator `resource_id`;
- a subsystem name;
- a `BudgetVector` demand;
- a reservation class;
- integer priority;
- whether the allocation is evictable;
- an immutable admission sequence.

When a request would exceed a global or subsystem budget, the broker considers resident allocations in this order:

1. lower integer priority first;
2. for equal priority, newer admission sequence first;
3. resource id as a final deterministic tie-break.

A new request never evicts an equal- or higher-priority allocation. Non-evictable allocations are also protected. The complete eviction set is planned before any accounting mutation; if enough safe capacity cannot be recovered, the request is rejected and resident accounting is unchanged.

```python
result = broker.admit(
    "texture:hero",
    subsystem="async-assets",
    demand=BudgetVector(memory_bytes=32 * 1024 * 1024, count=1, work_units=2),
    priority=50,
)

if result.admitted:
    for evicted in result.evicted:
        unload_concrete_resource(evicted.resource_id)
```

This API intentionally separates accounting from concrete cleanup. Engine integrations can therefore make eviction transactional at their own ownership boundary instead of allowing the budget broker to call renderer/window/audio code unexpectedly.

## Reservation classes

Creators can define classes whose *resident* usage is protected up to a component-wise reservation floor:

```python
broker.register_reservation_class(
    "gameplay",
    reserved=BudgetVector(
        memory_bytes=128 * 1024 * 1024,
        count=256,
        work_units=32,
    ),
)
```

The sum of configured reservations cannot exceed global capacity in any dimension.

Reservation semantics deliberately protect **resident usage**, not idle space. If a class currently uses less than its reservation, the unused portion can be borrowed by another class. Under later pressure, only usage above a resident class's protected floor can be selected for eviction. A reservation does not silently preempt equal/higher-priority work; priority remains an explicit creator contract.

This avoids permanently wasting unused capacity while still keeping loaded gameplay-critical allocations from being displaced below the creator-defined floor.

## Subsystem limits and isolation

A subsystem can have its own hard upper bound:

```python
broker.set_subsystem_limit(
    "async-assets",
    BudgetVector(
        memory_bytes=256 * 1024 * 1024,
        count=1_000,
        work_units=256,
    ),
)
```

When a subsystem is above its projected limit, only allocations belonging to that subsystem can solve that part of the pressure. A higher-priority request can replace lower-priority work inside its own subsystem; a rejected request cannot consume capacity from unrelated subsystems.

Limits must fit inside global capacity and cannot be lowered below current live usage. That check is atomic, so failed reconfiguration does not alter the broker revision or accounting state.

## Two-phase admission

`plan_admission(...)` is side-effect free and returns an immutable `AdmissionPlan`. This is useful when a creator needs to inspect an eviction set before changing concrete resources.

```python
plan = broker.plan_admission(
    "chunk:42",
    subsystem="world-stream",
    demand=BudgetVector(memory_bytes=8_000_000, count=24, work_units=4),
    priority=20,
)

if plan.admitted:
    result = broker.commit(plan)
```

Plans carry the broker revision. Any admission, release, reservation change or subsystem-limit change makes an older plan stale. `commit()` then raises `StaleBudgetPlanError` instead of applying an eviction set against different resource state.

`admit(...)` is the one-call atomic convenience path: it plans and commits while holding the broker lock.

## Rejection reasons

Rejected admissions expose a stable `AdmissionReason`, including:

- duplicate resource id;
- an individual request larger than global capacity;
- an individual request larger than its subsystem limit;
- subsystem pressure that cannot be resolved;
- reservation-protected resident usage;
- equal/higher-priority resident usage;
- explicitly non-evictable allocations;
- remaining global capacity pressure.

Malformed creator input raises normal validation exceptions before accounting changes. Capacity pressure is therefore distinct from API misuse.

## Diagnostics

`broker.diagnostics()` returns payload-free deterministic diagnostics containing:

- revision, global capacity/used/available vectors and pressure ratios;
- current allocation count;
- admitted/rejected/released/evicted cumulative counters;
- rejection counters grouped by stable reason;
- sorted subsystem usage/limits;
- sorted reservation-class usage, reservation and currently protected floor.

No resource payload or renderer/audio object is stored in diagnostics. The shape is compatible with `swirengine.performance15`'s generic portable diagnostics adapter for later frame-profiler integration.

## Performance contract

`tools/benchmark_resource_budget_1_7.py` executes 5,000 successful admissions against a 256-allocation shared capacity. After the initial fill, every higher-priority admission deterministically evicts one lower-priority resident, producing 4,744 pressure evictions. The Python 3.13 validation gate requires the workload to complete within a deliberately generous 5.0-second CI budget.

This is an accounting regression contract, not an FPS or memory-usage claim. Concrete resource destruction/allocation costs belong to each consuming subsystem and are intentionally outside this benchmark.

## Compatibility and publication

The broker lives only in additive `swirengine.resource_budget17`. Stable 1.x root imports and published package metadata are unchanged.

**Release/PyPI: frozen until SwirEngine 2.0.**
