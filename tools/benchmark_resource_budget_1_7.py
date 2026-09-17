from __future__ import annotations

import sys
from pathlib import Path
from time import perf_counter

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from swirengine.resource_budget17 import BudgetVector, ResourceBudgetBroker

REQUESTS = 5_000
RESIDENT_LIMIT = 256
TIME_BUDGET_SECONDS = 5.0


def main() -> int:
    broker = ResourceBudgetBroker(
        BudgetVector(
            memory_bytes=RESIDENT_LIMIT * 4096,
            count=RESIDENT_LIMIT,
            work_units=RESIDENT_LIMIT * 2,
        )
    )

    started = perf_counter()
    for index in range(REQUESTS):
        result = broker.admit(
            f"resource-{index:05d}",
            subsystem=f"stream-{index % 4}",
            demand=BudgetVector(memory_bytes=4096, count=1, work_units=2),
            priority=index,
        )
        if not result.admitted:
            raise SystemExit(
                f"request {index} unexpectedly rejected with reason {result.reason.value}"
            )
    elapsed = perf_counter() - started
    diagnostics = broker.diagnostics()

    expected_evictions = REQUESTS - RESIDENT_LIMIT
    if diagnostics.allocations != RESIDENT_LIMIT:
        raise SystemExit(
            f"expected {RESIDENT_LIMIT} residents, got {diagnostics.allocations}"
        )
    if diagnostics.admitted_total != REQUESTS:
        raise SystemExit(
            f"expected {REQUESTS} admissions, got {diagnostics.admitted_total}"
        )
    if diagnostics.evicted_total != expected_evictions:
        raise SystemExit(
            f"expected {expected_evictions} evictions, got {diagnostics.evicted_total}"
        )
    if diagnostics.rejected_total != 0:
        raise SystemExit(f"unexpected rejections: {diagnostics.rejected_total}")
    if elapsed >= TIME_BUDGET_SECONDS:
        raise SystemExit(
            f"resource-budget workload took {elapsed:.4f}s; budget is {TIME_BUDGET_SECONDS:.1f}s"
        )

    print(
        "Shared Resource Budget Broker 1.7 workload: "
        f"{REQUESTS} admissions, {expected_evictions} deterministic pressure evictions "
        f"in {elapsed:.4f}s; budget {TIME_BUDGET_SECONDS:.1f}s"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
