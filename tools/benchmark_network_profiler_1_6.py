from __future__ import annotations

import time

from swirengine.network_profiler16 import MultiplayerNetworkProfiler


CLIENTS = 96
SAMPLES_PER_CLIENT = 160
BUDGET_SECONDS = 4.0


class Diagnostics:
    def __init__(self) -> None:
        self.value = 0

    def diagnostics(self):
        self.value += 1
        return {
            "updates": self.value,
            "nested": {"bytes": self.value * 8, "mode": "ignored"},
        }


def main() -> None:
    source = Diagnostics()
    profiler = MultiplayerNetworkProfiler(max_samples_per_client=96, max_events=512)
    started = time.perf_counter()
    for tick in range(1, SAMPLES_PER_CLIENT + 1):
        for client in range(CLIENTS):
            profiler.sample_runtime(
                f"client-{client:03d}",
                tick,
                prediction=source,
                sent_bytes=800 + client,
                received_bytes=260 + tick,
                replicated_entities=24 + client % 8,
                entity_budget=48,
            )
    for index in range(512):
        profiler.record_event(
            f"client-{index % CLIENTS:03d}",
            SAMPLES_PER_CLIENT,
            "benchmark",
            "sample",
            {"index": index},
        )
    hotspots = profiler.bandwidth_hotspots(limit=16)
    fingerprint = profiler.fingerprint()
    elapsed = time.perf_counter() - started
    assert len(hotspots) == 16
    assert len(fingerprint) == 64
    assert profiler.diagnostics()["samples_retained"] == CLIENTS * 96
    if elapsed >= BUDGET_SECONDS:
        raise SystemExit(
            f"network profiler workload exceeded {BUDGET_SECONDS:.1f}s budget: {elapsed:.4f}s"
        )
    print(
        f"network-profiler workload: {CLIENTS * SAMPLES_PER_CLIENT} samples, "
        f"{len(hotspots)} hotspots, {elapsed:.4f}s"
    )


if __name__ == "__main__":
    main()
