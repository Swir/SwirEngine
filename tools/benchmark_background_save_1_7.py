from __future__ import annotations

import time
from tempfile import TemporaryDirectory

from swirengine.background_save17 import BackgroundSavePipeline
from swirengine.storage15 import ProfileSaveManager2

REQUESTS = 64
BUDGET_SECONDS = 5.0


def main() -> None:
    payload = {
        "player": {"hp": 100, "mana": 75, "position": [12.5, 8.0, -4.25]},
        "inventory": [f"item-{index}" for index in range(24)],
        "quest_flags": {f"quest-{index}": index % 3 == 0 for index in range(32)},
    }

    with TemporaryDirectory(prefix="swirengine-save-benchmark-") as temporary:
        manager = ProfileSaveManager2(temporary, "benchmark")
        started = time.perf_counter()
        with BackgroundSavePipeline(
            max_workers=4,
            max_requests=REQUESTS + 8,
        ) as pipeline:
            for index in range(REQUESTS):
                pipeline.submit_profile(
                    f"save-{index}",
                    manager,
                    f"slot-{index}",
                    payload,
                    metadata={"index": index, "kind": "benchmark"},
                )
            outcomes = pipeline.run_until_idle(timeout=BUDGET_SECONDS)
            diagnostics = pipeline.diagnostics()
        elapsed = time.perf_counter() - started

    if len(outcomes) != REQUESTS or not all(outcome.successful for outcome in outcomes):
        raise SystemExit("background save workload did not complete successfully")
    if diagnostics.verified_writes_total != REQUESTS:
        raise SystemExit("background save workload verification count mismatch")
    if elapsed > BUDGET_SECONDS:
        raise SystemExit(
            f"background save workload exceeded {BUDGET_SECONDS:.1f}s budget: {elapsed:.4f}s"
        )

    print(
        f"background_save_1_7: {REQUESTS} atomic+verified writes in {elapsed:.4f}s "
        f"(budget {BUDGET_SECONDS:.1f}s)"
    )


if __name__ == "__main__":
    main()
