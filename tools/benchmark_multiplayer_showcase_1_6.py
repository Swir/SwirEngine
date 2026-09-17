from __future__ import annotations

import time

from swirengine.multiplayer_showcase16 import (
    MultiplayerSoakConfig,
    NetworkImpairmentProfile,
    run_multiplayer_soak,
)

# Keep the workload large enough to exercise multi-client interest filtering, ACK baselines,
# prediction, QoS, impairment queues and bounded profiler retention without turning a functional
# regression gate into a runner-speed benchmark. The original 12 x 480 x 96 candidate measured
# 14.36s on a GitHub-hosted Python 3.13 runner, so this gate deliberately targets roughly one third
# of that authored-world/client work and keeps a generous 8-second ceiling.
CLIENTS = 8
ENTITIES = 64
TICKS = 360
BUDGET_SECONDS = 8.0


def main() -> None:
    config = MultiplayerSoakConfig(
        clients=CLIENTS,
        entities=ENTITIES,
        ticks=TICKS,
        entity_budget=24,
        profiler_history=48,
        impairment=NetworkImpairmentProfile(
            seed=0x1609,
            loss_per_mille=50,
            duplicate_per_mille=20,
            reorder_per_mille=150,
            base_latency_ticks=1,
            jitter_ticks=3,
            reorder_extra_ticks=2,
            max_inflight_packets=256,
        ),
    )
    started = time.perf_counter()
    report = run_multiplayer_soak(config)
    elapsed = time.perf_counter() - started

    assert report.profiler_diagnostics["samples_total"] == CLIENTS * TICKS
    assert report.applied_updates > 0
    assert len(report.fingerprint()) == 64
    assert all(
        diagnostics["peak_inflight_packets"] <= config.impairment.max_inflight_packets
        for diagnostics in report.link_diagnostics.values()
    )
    if elapsed >= BUDGET_SECONDS:
        raise SystemExit(
            f"multiplayer showcase soak exceeded {BUDGET_SECONDS:.1f}s budget: {elapsed:.4f}s"
        )
    print(
        f"multiplayer-showcase soak: {CLIENTS} clients x {TICKS} ticks, "
        f"{ENTITIES} entities, {report.applied_updates} applied updates, {elapsed:.4f}s"
    )


if __name__ == "__main__":
    main()
