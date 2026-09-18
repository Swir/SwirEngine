from __future__ import annotations

import argparse
from time import perf_counter

from swirengine.diagnostics19 import RuntimeIdentity, RuntimeLogBuffer, capture_exception


def _captured_error() -> RuntimeError:
    try:
        raise RuntimeError("deterministic benchmark failure")
    except RuntimeError as exc:
        return exc


def run(*, iterations: int, max_seconds: float) -> float:
    if iterations < 1:
        raise ValueError("iterations must be >= 1")
    identity = RuntimeIdentity(
        engine_version="1.9-source",
        project_name="benchmark",
        project_fingerprint="f" * 64,
        build_id="ci",
        profile="benchmark",
    )
    logs = RuntimeLogBuffer(capacity=64)
    for index in range(64):
        logs.record("info", f"event-{index}", entity=index, token="redacted")
    error = _captured_error()

    started = perf_counter()
    checksum = 0
    for index in range(iterations):
        report = capture_exception(
            error,
            identity=identity,
            logs=logs,
            diagnostics={"frame": index, "entities": 250, "scene": "arena"},
        )
        checksum ^= int(report.fingerprint[:8], 16)
    elapsed = perf_counter() - started
    rate = iterations / elapsed if elapsed else float("inf")
    print(
        f"runtime diagnostics workload: {iterations} reports in {elapsed:.4f}s "
        f"({rate:.1f} reports/s), checksum={checksum}"
    )
    if elapsed > max_seconds:
        raise SystemExit(
            f"runtime diagnostics workload exceeded {max_seconds:.2f}s ceiling: {elapsed:.4f}s"
        )
    return elapsed


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--iterations", type=int, default=1000)
    parser.add_argument("--max-seconds", type=float, default=8.0)
    args = parser.parse_args()
    run(iterations=args.iterations, max_seconds=args.max_seconds)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
