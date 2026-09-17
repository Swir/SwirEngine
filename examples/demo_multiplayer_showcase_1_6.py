from __future__ import annotations

import json

from swirengine.multiplayer_showcase16 import (
    MultiplayerSoakConfig,
    NetworkImpairmentProfile,
    run_multiplayer_soak,
)


def main() -> None:
    report = run_multiplayer_soak(
        MultiplayerSoakConfig(
            clients=4,
            entities=32,
            ticks=120,
            entity_budget=16,
            profiler_history=32,
            impairment=NetworkImpairmentProfile(
                seed=20260917,
                loss_per_mille=40,
                duplicate_per_mille=20,
                reorder_per_mille=120,
                base_latency_ticks=1,
                jitter_ticks=3,
                reorder_extra_ticks=2,
                max_inflight_packets=128,
            ),
        )
    )
    summary = {
        "fingerprint": report.fingerprint(),
        "ticks": report.ticks,
        "clients": report.clients,
        "entities": report.entities,
        "applied_updates": report.applied_updates,
        "stale_updates": report.stale_updates,
        "resynchronizations": report.resynchronizations,
        "prediction_corrections": report.prediction_corrections,
        "final_client_ticks": report.final_client_ticks,
        "profiler": report.profiler_diagnostics,
        "links": report.link_diagnostics,
    }
    print("SwirEngine 1.6 source-only multiplayer showcase")
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
