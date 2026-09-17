from __future__ import annotations

from time import perf_counter

from swirengine.performance15 import PerformanceDiagnostics2

FRAMES = 10_000
HISTORY = 240
BUDGET_SECONDS = 3.0


def main() -> None:
    perf = PerformanceDiagnostics2(history=HISTORY)
    streaming = {
        "active_cells": 25,
        "active_cost": 25,
        "queued_activations": 3,
        "queued_deactivations": 1,
    }
    navigation = {
        "active_agents": 128,
        "moving_agents": 96,
        "avoidance_candidates": 384,
    }
    perf.bind_provider("streaming", lambda: streaming)
    perf.bind_provider("navigation", lambda: navigation)

    started = perf_counter()
    for index in range(FRAMES):
        perf.begin_frame()
        perf.record_timing("frame", "update", 0.002)
        perf.record_timing("frame", "physics", 0.001)
        perf.record_timing("frame", "render", 0.004)
        perf.record_timing("asset", "streamed_chunk", 0.0002)
        perf.set_counter("physics", "bodies", 256)
        perf.set_counter("physics", "contacts", index % 64)
        perf.add_counter("scripts", "callbacks", 12)
        perf.record_resource("scene_objects", count=1200 + index % 32)
        perf.record_resource("textures", count=96, bytes_used=256 * 1024 * 1024)
        perf.end_frame(1.0 / 60.0)
    elapsed = perf_counter() - started

    capture = perf.capture({"scenario": "diagnostics-workload", "frames": FRAMES})
    duplicate = perf.capture({"frames": FRAMES, "scenario": "diagnostics-workload"})

    if len(perf.frames) != HISTORY:
        raise RuntimeError(f"bounded history regression: {len(perf.frames)} != {HISTORY}")
    if capture.canonical_json() != duplicate.canonical_json():
        raise RuntimeError("capture canonical JSON is not reproducible")
    if capture.fingerprint != duplicate.fingerprint:
        raise RuntimeError("capture fingerprint is not reproducible")
    if perf.provider_errors:
        raise RuntimeError(f"diagnostics providers failed {perf.provider_errors} times")

    latest = perf.latest
    if latest is None:
        raise RuntimeError("performance workload did not retain a frame")

    print(
        f"{FRAMES} instrumented frames: {elapsed:.6f}s "
        f"(budget {BUDGET_SECONDS}s)"
    )
    print(
        f"retained={len(perf.frames)} counters={len(latest.counters)} "
        f"resources={len(latest.resources)} fingerprint={capture.fingerprint[:16]}"
    )
    if elapsed > BUDGET_SECONDS:
        raise SystemExit(
            f"performance diagnostics workload exceeded budget: "
            f"{elapsed:.6f}s > {BUDGET_SECONDS}s"
        )


if __name__ == "__main__":
    main()
