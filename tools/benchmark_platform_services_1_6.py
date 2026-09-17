from __future__ import annotations

import time

from swirengine.platform16 import PlatformIdentity, PlatformServices


CLOUD_WRITES = 5_000
PROGRESSION_UPDATES = 10_000
CLOUD_SLOTS = 64
ACHIEVEMENTS = 20
BUDGET_SECONDS = 3.0


def main() -> None:
    services = PlatformServices.local(
        PlatformIdentity("benchmark", "Benchmark"),
        max_cloud_slots=CLOUD_SLOTS,
        max_cloud_save_bytes=1024,
        entitlements=("base-game",),
    )

    started = time.perf_counter()

    for index in range(CLOUD_WRITES):
        slot = f"slot-{index % CLOUD_SLOTS:02d}"
        current = services.cloud_load(slot)
        expected_revision = 0 if current is None else current.revision
        services.cloud_save(
            slot,
            f"save-{index}".encode("ascii"),
            expected_revision=expected_revision,
        )

    for index in range(PROGRESSION_UPDATES):
        services.stat_add(f"stat-{index % 32:02d}", 1)
        achievement_index = index % ACHIEVEMENTS
        generation = index // ACHIEVEMENTS
        progress = min(1.0, generation / 500.0)
        services.achievement_progress(
            f"achievement-{achievement_index:02d}",
            progress,
        )

    elapsed = time.perf_counter() - started

    assert len(services.cloud_slots()) == CLOUD_SLOTS
    assert services.identity().account_id == "benchmark"
    assert services.entitlement("base-game").granted
    assert len(services.stats()) == 32
    assert len(services.achievements()) == ACHIEVEMENTS
    assert services.portable_diagnostics()["capabilities"]["stats"]["failures"] == 0

    print(
        "platform-services workload:",
        f"{CLOUD_WRITES} cloud writes + {PROGRESSION_UPDATES} progression updates",
        f"in {elapsed:.4f}s (budget {BUDGET_SECONDS:.1f}s)",
    )
    if elapsed >= BUDGET_SECONDS:
        raise SystemExit(
            f"platform-services workload exceeded {BUDGET_SECONDS:.1f}s budget: "
            f"{elapsed:.4f}s"
        )


if __name__ == "__main__":
    main()
