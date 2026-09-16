from __future__ import annotations

import argparse
import statistics
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from demo_projects.neon_frontier_1_4.run_game import run_headless_probe  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Benchmark the SwirEngine 1.4 integrated headless showcase."
    )
    parser.add_argument("--rounds", type=int, default=3)
    parser.add_argument("--budget-ms", type=float, default=2500.0)
    args = parser.parse_args()
    if args.rounds < 1:
        raise SystemExit("--rounds must be >= 1")
    if args.budget_ms <= 0.0:
        raise SystemExit("--budget-ms must be > 0")

    timings: list[float] = []
    last = None
    for _ in range(args.rounds):
        started = time.perf_counter()
        last = run_headless_probe()
        timings.append((time.perf_counter() - started) * 1000.0)

    assert last is not None
    median_ms = statistics.median(timings)
    worst_ms = max(timings)
    print(
        "SwirEngine 1.4 showcase benchmark: "
        f"rounds={args.rounds}, median={median_ms:.3f}ms, worst={worst_ms:.3f}ms, "
        f"budget={args.budget_ms:.3f}ms, terrain_triangles={last.terrain_triangles}, "
        f"renderer_draw_calls={last.renderer_draw_calls}, network_bytes={last.network_bytes}"
    )
    if worst_ms > args.budget_ms:
        raise SystemExit(
            f"1.4 showcase performance contract failed: {worst_ms:.3f}ms > {args.budget_ms:.3f}ms"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
