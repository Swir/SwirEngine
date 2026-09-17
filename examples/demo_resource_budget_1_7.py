from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from swirengine.resource_budget17 import BudgetVector, ResourceBudgetBroker


def main() -> int:
    broker = ResourceBudgetBroker(
        BudgetVector(memory_bytes=512 * 1024 * 1024, count=6, work_units=12)
    )
    broker.register_reservation_class(
        "gameplay",
        reserved=BudgetVector(memory_bytes=128 * 1024 * 1024, count=2, work_units=2),
    )
    broker.set_subsystem_limit(
        "async-assets",
        BudgetVector(memory_bytes=256 * 1024 * 1024, count=4, work_units=8),
    )

    for index in range(2):
        result = broker.admit(
            f"gameplay:{index}",
            subsystem="world-stream",
            reservation_class="gameplay",
            demand=BudgetVector(memory_bytes=64 * 1024 * 1024, count=1, work_units=1),
            priority=100,
        )
        assert result.admitted

    for index in range(4):
        result = broker.admit(
            f"texture:{index}",
            subsystem="async-assets",
            demand=BudgetVector(memory_bytes=64 * 1024 * 1024, count=1, work_units=2),
            priority=index,
        )
        assert result.admitted

    replacement = broker.admit(
        "texture:hero",
        subsystem="async-assets",
        demand=BudgetVector(memory_bytes=64 * 1024 * 1024, count=1, work_units=2),
        priority=50,
    )
    assert replacement.admitted
    assert tuple(item.resource_id for item in replacement.evicted) == ("texture:0",)
    assert broker.reservation_usage("gameplay").count == 2

    diagnostics = broker.diagnostics()
    print("Shared Resource Budget Broker 1.7 demo complete")
    print(f"evicted={[item.resource_id for item in replacement.evicted]}")
    print(f"diagnostics={dict(diagnostics.portable())}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
